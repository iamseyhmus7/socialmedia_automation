from __future__ import annotations

import os
import sys
from datetime import datetime, timezone


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database import get_due_tiktok_uploads, get_tiktok_metadata, record_tiktok_upload
from src.core.settings import get_settings
from src.services.tiktok_upload_service import TikTokUploadService


def create_service(settings) -> TikTokUploadService:
    return TikTokUploadService(
        settings.tiktok_client_key,
        settings.tiktok_client_secret,
        settings.tiktok_redirect_uri,
        settings.tiktok_token_path,
        settings.tiktok_default_privacy_level,
        settings.tiktok_disable_comment,
        settings.tiktok_disable_duet,
        settings.tiktok_disable_stitch,
        settings.tiktok_is_aigc,
    )


def main() -> None:
    settings = get_settings()
    service = create_service(settings)
    now_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    due_items = get_due_tiktok_uploads(now_utc)
    if not due_items:
        print("No due TikTok uploads.")
        return

    for item in due_items:
        video_path = item["final_video_path"]
        metadata = get_tiktok_metadata(video_path) or {}
        try:
            result = service.upload_video(
                video_path,
                title=metadata.get("title"),
                description=metadata.get("description"),
                tags=metadata.get("tags"),
                publish_at=item["publish_at"],
            )
        except Exception as exc:
            record_tiktok_upload(video_path, publish_at=item["publish_at"], status="failed", error=str(exc))
            print(f"Failed TikTok upload for {os.path.basename(video_path)}: {exc}")
            continue

        record_tiktok_upload(
            video_path,
            result.publish_id,
            result.tiktok_url,
            item["publish_at"],
            result.status,
            None,
        )
        print(f"Sent TikTok upload: {os.path.basename(video_path)} publish_id={result.publish_id}")


if __name__ == "__main__":
    main()
