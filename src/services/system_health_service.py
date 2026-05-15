from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import Callable

from database import get_scheduled_uploads
from src.core.settings import Settings
from src.services.publish_schedule_service import PublishScheduleService


ScheduledUploadsProvider = Callable[[int], list[dict]]


@dataclass(frozen=True)
class HealthItem:
    label: str
    ok: bool
    detail: str

    def format(self) -> str:
        status = "OK" if self.ok else "UYARI"
        return f"- {self.label}: {status} - {self.detail}"


class SystemHealthService:
    def __init__(
        self,
        settings: Settings,
        scheduled_uploads_provider: ScheduledUploadsProvider | None = None,
        schedule_service: PublishScheduleService | None = None,
    ):
        self.settings = settings
        self.scheduled_uploads_provider = scheduled_uploads_provider or get_scheduled_uploads
        self.schedule_service = schedule_service or PublishScheduleService()

    def health_text(self) -> str:
        items = [
            self._database_health(),
            self._outputs_health(),
            self._assets_health(),
            self._disk_health(),
            self._gemini_health(),
            self._telegram_health(),
            self._youtube_health(),
            self._video_provider_health(),
            self._queue_health(),
        ]
        lines = ["Sistem sagligi:"]
        lines.extend(item.format() for item in items)
        return "\n".join(lines)

    def _database_health(self) -> HealthItem:
        if not self.settings.database_url:
            return HealthItem("PostgreSQL", False, "DATABASE_URL ayarlanmamis.")
        if not self.settings.database_url.startswith(("postgresql://", "postgres://")):
            return HealthItem("PostgreSQL", False, "DATABASE_URL PostgreSQL adresi degil.")
        try:
            self.scheduled_uploads_provider(1)
        except Exception as exc:
            return HealthItem("PostgreSQL", False, str(exc))
        return HealthItem("PostgreSQL", True, "baglanti ve sorgu calisiyor.")

    def _outputs_health(self) -> HealthItem:
        if not os.path.isdir(self.settings.outputs_dir):
            return HealthItem("Outputs", False, f"klasor yok: {self.settings.outputs_dir}")

        latest = self._latest_video_file(self.settings.outputs_dir)
        if latest:
            return HealthItem("Outputs", True, f"son video: {os.path.basename(latest)}")
        return HealthItem("Outputs", True, "klasor hazir, video bulunmadi.")

    def _assets_health(self) -> HealthItem:
        if os.path.isdir(self.settings.assets_dir):
            return HealthItem("Assets", True, "klasor hazir.")
        return HealthItem("Assets", False, f"klasor yok: {self.settings.assets_dir}")

    def _disk_health(self) -> HealthItem:
        path = self.settings.outputs_dir if os.path.exists(self.settings.outputs_dir) else self.settings.base_dir
        try:
            usage = shutil.disk_usage(path)
        except OSError as exc:
            return HealthItem("Disk", False, str(exc))

        free_gb = usage.free / (1024**3)
        ok = free_gb >= 5
        detail = f"{free_gb:.1f} GB bos alan"
        if not ok:
            detail += " kaldigi icin render riskli olabilir."
        return HealthItem("Disk", ok, detail)

    def _gemini_health(self) -> HealthItem:
        if self.settings.gemini_api_key:
            return HealthItem("Gemini", True, self.settings.gemini_model)
        return HealthItem("Gemini", False, "GEMINI_API_KEY eksik.")

    def _telegram_health(self) -> HealthItem:
        if self.settings.telegram_bot_token and self.settings.telegram_chat_id:
            return HealthItem("Telegram", True, "bot token ve chat id var.")
        return HealthItem("Telegram", False, "TELEGRAM_BOT_TOKEN veya TELEGRAM_CHAT_ID eksik.")

    def _youtube_health(self) -> HealthItem:
        if not os.path.exists(self.settings.youtube_client_secrets_path):
            return HealthItem("YouTube", False, "client secret dosyasi yok.")
        if not os.path.exists(self.settings.youtube_token_path):
            return HealthItem("YouTube", False, "token dosyasi yok; yeniden auth gerekebilir.")
        return HealthItem("YouTube", True, "client secret ve token var.")

    def _video_provider_health(self) -> HealthItem:
        configured = [
            name
            for name, value in [
                ("Pexels", self.settings.pexels_api_key),
                ("Pixabay", self.settings.pixabay_api_key),
                ("Coverr", self.settings.coverr_api_key),
            ]
            if value
        ]
        if configured:
            return HealthItem("Video kaynaklari", True, ", ".join(configured))
        return HealthItem("Video kaynaklari", False, "Pexels/Pixabay/Coverr anahtari yok.")

    def _queue_health(self) -> HealthItem:
        try:
            uploads = self.scheduled_uploads_provider(1)
        except Exception as exc:
            return HealthItem("Yayin kuyrugu", False, str(exc))

        if not uploads:
            return HealthItem("Yayin kuyrugu", True, "planlanan yayin yok.")

        item = uploads[0]
        publish_at = item.get("publish_at") or ""
        try:
            local_time = self.schedule_service.format_local_datetime(publish_at)
        except (TypeError, ValueError):
            local_time = publish_at or "zaman yok"
        file_name = os.path.basename(item.get("final_video_path") or "")
        platform = item.get("platform") or "?"
        return HealthItem("Yayin kuyrugu", True, f"sirada {platform} {local_time} {file_name}".strip())

    def _latest_video_file(self, directory: str) -> str | None:
        latest_path = None
        latest_mtime = -1.0
        for root, _dirs, files in os.walk(directory):
            for file_name in files:
                if not file_name.lower().endswith(".mp4"):
                    continue
                path = os.path.join(root, file_name)
                try:
                    mtime = os.path.getmtime(path)
                except OSError:
                    continue
                if mtime > latest_mtime:
                    latest_path = path
                    latest_mtime = mtime
        return latest_path
