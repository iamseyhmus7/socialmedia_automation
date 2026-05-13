from __future__ import annotations

import os
from typing import Callable

from database import get_scheduled_uploads
from src.services.publish_schedule_service import PublishScheduleService


class PublishQueueService:
    def __init__(
        self,
        scheduled_uploads_provider: Callable[[int], list[dict]] | None = None,
        schedule_service: PublishScheduleService | None = None,
    ):
        self.scheduled_uploads_provider = scheduled_uploads_provider or get_scheduled_uploads
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
            location = "local queue" if platform == "TikTok" else "platform schedule"
            lines.append(f"{index}. {platform} ({location}) - {local_time} - {file_name}")
        return "\n".join(lines)
