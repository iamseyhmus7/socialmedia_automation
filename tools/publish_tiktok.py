from __future__ import annotations

import argparse
import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database import get_tiktok_metadata, get_tiktok_publish_times, record_tiktok_upload
from src.core.settings import get_settings
from src.services.publish_now_service import PublishNowConfig, PublishNowService
from src.services.publish_schedule_service import PublishScheduleService
from src.services.tiktok_upload_service import TikTokUploadService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upload or locally schedule a video for TikTok Direct Post.")
    parser.add_argument("video_path", nargs="?", help="Path to the video file.")
    parser.add_argument("--dir", dest="upload_dir", default=None, help="Directory to scan for videos.")
    parser.add_argument("--date", default=None, help="Date folder under outputs, for example 2026-05-13.")
    parser.add_argument("--latest", action="store_true", help="Use the newest publishable .mp4 from the selected directory.")
    parser.add_argument("--title", default=None, help="TikTok caption title.")
    parser.add_argument("--description", default=None, help="TikTok caption description.")
    parser.add_argument("--tags", default=None, help="Comma-separated tags.")
    parser.add_argument("--privacy", default=None, help="TikTok privacy level, for example SELF_ONLY or PUBLIC_TO_EVERYONE.")
    parser.add_argument("--publish-at", default=None, help="Local schedule time, for example '2026-05-14 18:00'.")
    parser.add_argument("--dry-run", action="store_true", help="Show the selected action without changing TikTok.")
    return parser.parse_args()


def config_from_args(args: argparse.Namespace, settings) -> PublishNowConfig:
    tags = [tag.strip() for tag in args.tags.split(",") if tag.strip()] if args.tags else None
    requested_dir = resolve_path(settings.base_dir, args.upload_dir) if args.upload_dir else None
    return PublishNowConfig(
        base_dir=settings.base_dir,
        uploads_dir=settings.youtube_uploads_dir,
        upload_dir=requested_dir,
        date_folder=args.date,
        video_path=args.video_path,
        latest=args.latest,
        title=args.title,
        description=args.description,
        tags=tags,
        privacy=args.privacy or settings.tiktok_default_privacy_level,
        publish_at=args.publish_at,
        dry_run=args.dry_run,
    )


def resolve_path(base_dir: str, value: str) -> str:
    if os.path.isabs(value):
        return value
    return os.path.join(base_dir, value)


def create_tiktok_service(settings) -> TikTokUploadService:
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
    config = config_from_args(parse_args(), settings)
    finder = PublishNowService(
        create_tiktok_service(settings),
        schedule_service=PublishScheduleService(),
        metadata_provider=get_tiktok_metadata,
        occupied_publish_times_provider=get_tiktok_publish_times,
    )
    plan = finder.build_plan(config)
    service = create_tiktok_service(settings)
    schedule_service = PublishScheduleService()

    for item in plan:
        metadata = get_tiktok_metadata(item.video_path) or {}
        if config.dry_run:
            when = schedule_service.format_local_datetime(item.publish_at) if item.publish_at else "now"
            print(f"DRY RUN TikTok {os.path.basename(item.video_path)}: {when}")
            continue

        if item.publish_at:
            record_tiktok_upload(item.video_path, publish_at=item.publish_at, status="scheduled")
            print(
                f"Scheduled TikTok locally: {os.path.basename(item.video_path)} "
                f"({schedule_service.format_local_datetime(item.publish_at)})"
            )
            continue

        result = service.upload_video(
            item.video_path,
            title=config.title or metadata.get("title"),
            description=config.description if config.description is not None else metadata.get("description"),
            tags=config.tags or metadata.get("tags"),
            privacy_level=config.privacy,
        )
        record_tiktok_upload(item.video_path, result.publish_id, result.tiktok_url, None, result.status)
        print(f"Uploaded to TikTok Direct Post: publish_id={result.publish_id}, status={result.status}")


if __name__ == "__main__":
    main()
