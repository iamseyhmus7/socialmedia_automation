from __future__ import annotations

import os
from datetime import datetime, timezone

from database import get_due_tiktok_uploads, get_tiktok_metadata, record_tiktok_upload
from src.services.tiktok_upload_service import TikTokUploadService


class TikTokDuePublishService:
    def __init__(self, tiktok_upload_service: TikTokUploadService):
        self.tiktok_upload_service = tiktok_upload_service

    def publish_due_text(self) -> str:
        now_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        due_items = get_due_tiktok_uploads(now_utc)
        if not due_items:
            return "Zamani gelen TikTok yayini yok."

        messages = []
        for item in due_items:
            video_path = item["final_video_path"]
            metadata = get_tiktok_metadata(video_path) or {}
            try:
                result = self.tiktok_upload_service.upload_video(
                    video_path,
                    title=metadata.get("title"),
                    description=metadata.get("description"),
                    tags=metadata.get("tags"),
                    publish_at=item["publish_at"],
                )
            except Exception as exc:
                record_tiktok_upload(video_path, publish_at=item["publish_at"], status="failed", error=str(exc))
                messages.append(f"Basarisiz: {os.path.basename(video_path)} - {exc}")
                continue

            record_tiktok_upload(
                video_path,
                result.publish_id,
                result.tiktok_url,
                item["publish_at"],
                result.status,
                None,
            )
            messages.append(f"Gonderildi: {os.path.basename(video_path)} publish_id={result.publish_id}")

        return "\n".join(messages)
