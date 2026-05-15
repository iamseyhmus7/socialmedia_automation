from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Callable

from database import (
    cancel_scheduled_upload,
    get_expired_scheduled_uploads,
    get_scheduled_uploads,
    get_upload_detail,
    mark_expired_scheduled_uploads,
    reschedule_scheduled_upload,
)
from src.services.publish_schedule_service import PublishScheduleService


DetailProvider = Callable[[str], dict | None]
MutationProvider = Callable[[str], bool]
RescheduleProvider = Callable[[str, str], bool]
PublishTimesProvider = Callable[[], list[str]]
ExpiredUploadsProvider = Callable[[str, int], list[dict]]
ExpiredMarker = Callable[[str], dict]


class PublishQueueService:
    def __init__(
        self,
        scheduled_uploads_provider: Callable[[int], list[dict]] | None = None,
        detail_provider: DetailProvider | None = None,
        cancel_provider: MutationProvider | None = None,
        reschedule_provider: RescheduleProvider | None = None,
        occupied_publish_times_provider: PublishTimesProvider | None = None,
        expired_uploads_provider: ExpiredUploadsProvider | None = None,
        expired_marker: ExpiredMarker | None = None,
        schedule_service: PublishScheduleService | None = None,
    ):
        self.scheduled_uploads_provider = scheduled_uploads_provider or get_scheduled_uploads
        self.detail_provider = detail_provider or get_upload_detail
        self.cancel_provider = cancel_provider or cancel_scheduled_upload
        self.reschedule_provider = reschedule_provider or reschedule_scheduled_upload
        self.occupied_publish_times_provider = occupied_publish_times_provider or self._default_occupied_publish_times
        self.expired_uploads_provider = expired_uploads_provider or get_expired_scheduled_uploads
        self.expired_marker = expired_marker or mark_expired_scheduled_uploads
        self.schedule_service = schedule_service or PublishScheduleService()

    def queue_text(self, limit: int = 20) -> str:
        uploads = self.scheduled_uploads_provider(limit)
        if not uploads:
            return "Planlanan YouTube/TikTok yayini yok."

        lines = ["Planlanan yayinlar:"]
        for index, item in enumerate(uploads, start=1):
            publish_at = item.get("publish_at") or ""
            try:
                local_time = self.schedule_service.format_local_datetime(publish_at)
            except (TypeError, ValueError):
                local_time = publish_at
            file_name = os.path.basename(item.get("final_video_path") or "")
            platform = item.get("platform")
            queue_id = item.get("queue_id") or "?"
            location = "local queue" if platform == "TikTok" else "platform schedule"
            lines.append(f"{index}. {queue_id} - {platform} ({location}) - {local_time} - {file_name}")
        return "\n".join(lines)

    def queue_detail_text(self, limit: int = 20) -> str:
        uploads = self.scheduled_uploads_provider(limit)
        if not uploads:
            return "Planlanan YouTube/TikTok yayini yok."

        lines = ["Planlanan yayin detaylari:"]
        for item in uploads:
            detail = self.detail_provider(item.get("queue_id") or "")
            if not detail:
                continue
            publish_at = detail.get("publish_at") or ""
            try:
                local_time = self.schedule_service.format_local_datetime(publish_at)
            except (TypeError, ValueError):
                local_time = publish_at
            file_name = os.path.basename(detail.get("final_video_path") or "")
            lines.append(
                "\n".join(
                    [
                        f"- ID: {detail.get('queue_id')}",
                        f"  Platform: {detail.get('platform')}",
                        f"  Status: {detail.get('status')}",
                        f"  Yayin: {local_time}",
                        f"  Dosya: {file_name}",
                    ]
                )
            )
            if detail.get("remote_url"):
                lines.append(f"  URL: {detail['remote_url']}")
            if detail.get("error"):
                lines.append(f"  Hata: {detail['error']}")
        return "\n".join(lines)

    def cancel_text(self, queue_id: str) -> str:
        try:
            detail = self.detail_provider(queue_id)
            if not detail:
                return f"Queue kaydi bulunamadi: {queue_id}"
            if detail.get("status") != "scheduled":
                return f"Queue kaydi iptal edilemez; mevcut status: {detail.get('status')}"
            if not self.cancel_provider(queue_id):
                return f"Queue kaydi iptal edilemedi: {queue_id}"
        except ValueError as exc:
            return str(exc)
        return f"Queue kaydi iptal edildi: {queue_id}"

    def reschedule_text(self, queue_id: str, raw_publish_at: str) -> str:
        try:
            detail = self.detail_provider(queue_id)
            if not detail:
                return f"Queue kaydi bulunamadi: {queue_id}"
            if detail.get("status") != "scheduled":
                return f"Queue kaydi yeniden zamanlanamaz; mevcut status: {detail.get('status')}"
            occupied_times = [time for time in self.occupied_publish_times_provider() if time != detail.get("publish_at")]
            publish_at = self.schedule_service.validate_publish_at(raw_publish_at, occupied_publish_times=occupied_times)
            if not publish_at:
                return "Yeni yayin zamani bos olamaz."
            if not self.reschedule_provider(queue_id, publish_at):
                return f"Queue kaydi yeniden zamanlanamadi: {queue_id}"
        except ValueError as exc:
            return str(exc)

        local_time = self.schedule_service.format_local_datetime(publish_at)
        return f"Queue kaydi yeniden zamanlandi: {queue_id} -> {local_time}"

    def expired_text(self, limit: int = 50) -> str:
        now_utc = self._now_utc()
        uploads = self.expired_uploads_provider(now_utc, limit)
        if not uploads:
            return "Gecmiste kalmis scheduled yayin yok."

        lines = ["Gecmiste kalmis scheduled yayinlar:"]
        for index, item in enumerate(uploads, start=1):
            publish_at = item.get("publish_at") or ""
            try:
                local_time = self.schedule_service.format_local_datetime(publish_at)
            except (TypeError, ValueError):
                local_time = publish_at
            file_name = os.path.basename(item.get("final_video_path") or "")
            lines.append(f"{index}. {item.get('queue_id')} - {item.get('platform')} - {local_time} - {file_name}")
        lines.append("Temizlemek icin /queue_cleanup yazin.")
        return "\n".join(lines)

    def cleanup_text(self) -> str:
        now_utc = self._now_utc()
        result = self.expired_marker(now_utc)
        total = int(result.get("total", 0))
        if total == 0:
            return "Temizlenecek gecmis scheduled yayin yok."
        return (
            "Gecmis scheduled yayinlar expired yapildi: "
            f"toplam={total}, YouTube={result.get('YouTube', 0)}, TikTok={result.get('TikTok', 0)}"
        )

    def _default_occupied_publish_times(self) -> list[str]:
        return [item.get("publish_at") for item in self.scheduled_uploads_provider(500) if item.get("publish_at")]

    def _now_utc(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
