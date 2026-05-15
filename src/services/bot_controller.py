from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable

from src.domain.bot_command import BotCommandType, command_help_text, parse_bot_command
from src.services.publish_schedule_service import PublishScheduleService


WorkflowRunner = Callable[[], Awaitable[dict]]
TextProvider = Callable[[], str]
QueueMutationProvider = Callable[[str], str]
QueueRescheduleProvider = Callable[[str, str], str]
MessageSender = Callable[[str], bool]
CleanupCallback = Callable[[], None]
StatusProvider = Callable[[], str]


@dataclass
class BotControllerState:
    is_started: bool = False
    is_paused: bool = False
    is_generating: bool = False
    stop_requested: bool = False
    target_count: int = 0
    completed_count: int = 0
    current_index: int = 0
    last_status: str = "idle"
    last_error: str | None = None


class BotController:
    def __init__(
        self,
        workflow_runner: WorkflowRunner,
        queue_provider: TextProvider | None = None,
        queue_detail_provider: TextProvider | None = None,
        queue_expired_provider: TextProvider | None = None,
        queue_cleanup_provider: TextProvider | None = None,
        queue_cancel_provider: QueueMutationProvider | None = None,
        queue_reschedule_provider: QueueRescheduleProvider | None = None,
        due_publisher: TextProvider | None = None,
        message_sender: MessageSender | None = None,
        schedule_service: PublishScheduleService | None = None,
        cleanup_callback: CleanupCallback | None = None,
        status_provider: StatusProvider | None = None,
    ):
        self.workflow_runner = workflow_runner
        self.queue_provider = queue_provider or (lambda: "Planlanan yayin yok.")
        self.queue_detail_provider = queue_detail_provider or self.queue_provider
        self.queue_expired_provider = queue_expired_provider or (lambda: "Queue expired servisi hazir degil.")
        self.queue_cleanup_provider = queue_cleanup_provider or (lambda: "Queue cleanup servisi hazir degil.")
        self.queue_cancel_provider = queue_cancel_provider or (lambda queue_id: f"Queue iptal servisi hazir degil: {queue_id}")
        self.queue_reschedule_provider = queue_reschedule_provider or (
            lambda queue_id, publish_at: f"Queue zamanlama servisi hazir degil: {queue_id} {publish_at}"
        )
        self.due_publisher = due_publisher or (lambda: "Zamani gelen yayin yok.")
        self.message_sender = message_sender or (lambda _text: True)
        self.schedule_service = schedule_service or PublishScheduleService()
        self.cleanup_callback = cleanup_callback or (lambda: None)
        self.status_provider = status_provider
        self.state = BotControllerState()
        self._generation_task: asyncio.Task | None = None

    async def handle_message(self, text: str | None) -> str:
        command = parse_bot_command(text)
        if not command.is_valid:
            return f"{command.error}\n\n{command_help_text()}"

        if command.type == BotCommandType.START:
            self.state.is_started = True
            self.state.last_status = "ready"
            return f"Sistem baslatildi.\n\n{command_help_text()}"

        if command.type == BotCommandType.GENERATE:
            return self._start_generation(command.count or 1)

        if command.type == BotCommandType.STOP:
            self.state.stop_requested = True
            self.state.is_started = False
            if self.state.is_generating:
                return "Durdurma istendi. Mevcut video guvenli tamamlaninca yeni video uretilmeyecek."
            self.state.last_status = "stopped"
            return "Sistem durduruldu. Yeni video uretilmeyecek."

        if command.type == BotCommandType.STATUS:
            return self.status_text()

        if command.type == BotCommandType.PAUSE:
            self.state.is_paused = True
            if self.state.is_generating:
                return "Duraklatildi. Mevcut video tamamlaninca yeni ise baslanmayacak."
            self.state.last_status = "paused"
            return "Duraklatildi. Yeni ise baslanmayacak."

        if command.type == BotCommandType.RESUME:
            self.state.is_started = True
            self.state.is_paused = False
            self.state.stop_requested = False
            if self.state.is_generating:
                return "Devam ediyor."
            self.state.last_status = "ready"
            return "Devam etmeye hazir."

        if command.type == BotCommandType.QUEUE:
            return self.queue_provider()

        if command.type == BotCommandType.QUEUE_DETAIL:
            return self.queue_detail_provider()

        if command.type == BotCommandType.QUEUE_EXPIRED:
            return self.queue_expired_provider()

        if command.type == BotCommandType.QUEUE_CLEANUP:
            return self.queue_cleanup_provider()

        if command.type == BotCommandType.CANCEL:
            return self.queue_cancel_provider(command.queue_id or "")

        if command.type == BotCommandType.RESCHEDULE:
            return self.queue_reschedule_provider(command.queue_id or "", command.publish_at or "")

        if command.type == BotCommandType.PUBLISH_DUE:
            return self.due_publisher()

        return f"Komut desteklenmiyor.\n\n{command_help_text()}"

    def status_text(self) -> str:
        lines = [
            f"Durum: {self.state.last_status}",
            f"Uretilen: {self.state.completed_count}/{self.state.target_count}",
        ]
        if self.state.is_generating:
            lines.append(f"Siradaki: {self.state.current_index + 1}. video")
        elif self.state.is_paused:
            lines.append("Siradaki: duraklatildi")
        elif self.state.stop_requested:
            lines.append("Siradaki: durduruldu")
        else:
            lines.append("Siradaki: beklemede")
        if self.state.last_error:
            lines.append(f"Son hata: {self.state.last_error}")
        if self.status_provider:
            try:
                lines.append("")
                lines.append(self.status_provider())
            except Exception as exc:
                lines.append("")
                lines.append(f"Sistem sagligi: UYARI - durum raporu alinamadi: {exc}")
        return "\n".join(lines)

    def _start_generation(self, count: int) -> str:
        if not self.state.is_started:
            self.state.is_started = True
        if self.state.is_generating:
            return "Zaten bir uretim dongusu calisiyor. Yeni komut icin once bitmesini bekleyin veya /stop yazin."
        if self.state.is_paused:
            return "Sistem duraklatilmis. Devam etmek icin /resume yazin."

        self.state.target_count = count
        self.state.completed_count = 0
        self.state.current_index = 0
        self.state.stop_requested = False
        self.state.last_error = None
        self.state.last_status = "generating"
        self._generation_task = asyncio.create_task(self._generate_loop(count))
        return f"{count} video uretim-onay dongusu baslatildi."

    async def _generate_loop(self, count: int) -> None:
        self.state.is_generating = True
        try:
            for index in range(count):
                self.state.current_index = index
                if self.state.stop_requested:
                    self.state.last_status = "stopped"
                    break
                if self.state.is_paused:
                    self.state.last_status = "paused"
                    break

                self.state.last_status = f"generating {index + 1}/{count}"
                try:
                    final_state = await self.workflow_runner()
                except Exception as exc:
                    self.state.last_error = str(exc)
                    self.state.last_status = "failed"
                    break

                status = final_state.get("status")
                if status == "approved":
                    self.state.completed_count += 1
                    self.state.last_status = f"approved {self.state.completed_count}/{count}"
                    self.message_sender(self._video_result_text(final_state, self.state.completed_count, count))
                    await self._cleanup_after_video()
                    continue

                self.state.last_status = str(status or "finished")
                self.message_sender(self._video_result_text(final_state, self.state.completed_count, count))
                await self._cleanup_after_video()
                break

            if self.state.completed_count >= count:
                self.state.last_status = "completed"
        finally:
            self.state.is_generating = False

    async def _cleanup_after_video(self) -> None:
        try:
            await asyncio.to_thread(self.cleanup_callback)
        except Exception as exc:
            self.state.last_error = f"Cleanup failed: {exc}"
            self.message_sender(f"Cleanup hata: {exc}")

    def _video_result_text(self, final_state: dict, completed_count: int, target_count: int) -> str:
        lines = [
            f"Video sonucu: {final_state.get('status')}",
            f"Tamamlanan: {completed_count}/{target_count}",
        ]
        if final_state.get("final_video_path"):
            lines.append(f"Output: {final_state['final_video_path']}")
        if final_state.get("youtube_url"):
            lines.append(f"YouTube: {final_state['youtube_url']}")
        if final_state.get("youtube_publish_at"):
            lines.append(f"YouTube yayin: {self.schedule_service.format_local_datetime(final_state['youtube_publish_at'])}")
        if final_state.get("upload_error"):
            lines.append(f"YouTube hata: {final_state['upload_error']}")
        if final_state.get("instagram_url"):
            lines.append(f"Instagram: {final_state['instagram_url']}")
        if final_state.get("instagram_upload_error"):
            lines.append(f"Instagram hata: {final_state['instagram_upload_error']}")
        if final_state.get("tiktok_publish_at"):
            lines.append(
                "TikTok local queue: "
                f"{self.schedule_service.format_local_datetime(final_state['tiktok_publish_at'])}"
            )
        if final_state.get("tiktok_publish_id"):
            lines.append(f"TikTok publish id: {final_state['tiktok_publish_id']}")
        if final_state.get("tiktok_upload_error"):
            lines.append(f"TikTok hata: {final_state['tiktok_upload_error']}")
        return "\n".join(lines)
