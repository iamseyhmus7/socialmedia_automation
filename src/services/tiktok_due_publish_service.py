from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Callable

from database import get_due_tiktok_uploads, get_next_scheduled_tiktok_upload, get_tiktok_metadata, record_tiktok_upload
from src.services.publish_schedule_service import PublishScheduleService
from src.services.tiktok_upload_service import TikTokUploadService


class TikTokDuePublishService:
    def __init__(
        self,
        tiktok_upload_service: TikTokUploadService,
        due_uploads_provider: Callable[[str], list[dict]] | None = None,
        metadata_provider: Callable[[str], dict | None] | None = None,
        upload_recorder: Callable[..., None] | None = None,
        next_scheduled_provider: Callable[[], dict | None] | None = None,
        schedule_service: PublishScheduleService | None = None,
        clock: Callable[[], datetime] | None = None,
    ):
        self.tiktok_upload_service = tiktok_upload_service
        self.due_uploads_provider = due_uploads_provider or get_due_tiktok_uploads
        self.metadata_provider = metadata_provider or get_tiktok_metadata
        self.upload_recorder = upload_recorder or record_tiktok_upload
        self.next_scheduled_provider = next_scheduled_provider or get_next_scheduled_tiktok_upload
        self.schedule_service = schedule_service or PublishScheduleService()
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def publish_due_text(self) -> str:
        now_utc = self.clock().isoformat().replace("+00:00", "Z")
        due_items = self.due_uploads_provider(now_utc)
        if not due_items:
            return self._no_due_text()

        messages = []
        for item in due_items:
            video_path = item["final_video_path"]
            metadata = self.metadata_provider(video_path) or {}
            try:
                result = self.tiktok_upload_service.upload_video(
                    video_path,
                    title=metadata.get("title"),
                    description=metadata.get("description"),
                    tags=metadata.get("tags"),
                    publish_at=item["publish_at"],
                )
            except Exception as exc:
                self.upload_recorder(video_path, publish_at=item["publish_at"], status="failed", error=str(exc))
                messages.append(f"Basarisiz: {os.path.basename(video_path)} - {exc}")
                continue

            self.upload_recorder(
                video_path,
                result.publish_id,
                result.tiktok_url,
                item["publish_at"],
                result.status,
                None,
            )
            messages.append(f"Gonderildi: {os.path.basename(video_path)} publish_id={result.publish_id}")

        return "\n".join(messages)

    def _no_due_text(self) -> str:
        next_item = self.next_scheduled_provider()
        if not next_item or not next_item.get("publish_at"):
            return "Zamani gelen TikTok yayini yok.\nSiradaki TikTok yayini da planlanmamis."

        publish_at = str(next_item["publish_at"])
        try:
            local_time = self.schedule_service.format_local_datetime(publish_at)
        except (TypeError, ValueError):
            local_time = publish_at

        file_name = os.path.basename(next_item.get("final_video_path") or "")
        suffix = f" - {file_name}" if file_name else ""
        return f"Zamani gelen TikTok yayini yok.\nSiradaki TikTok: {local_time}{suffix}"
