from __future__ import annotations

import argparse
import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database import get_youtube_metadata, get_youtube_publish_times, record_youtube_upload
from src.core.settings import get_settings
from src.services.publish_now_service import PublishNowConfig, PublishNowService
from src.services.publish_schedule_service import PublishScheduleService
from src.services.youtube_upload_service import YouTubeUploadService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upload a local video to YouTube.")
    parser.add_argument("video_path", nargs="?", help="Path to the video file to upload.")
    parser.add_argument(
        "--dir",
        dest="upload_dir",
        default=None,
        help="Directory to scan for videos. Defaults to the latest date folder under YOUTUBE_UPLOADS_DIR.",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Date folder under YOUTUBE_UPLOADS_DIR, for example 2026-05-08.",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Upload only the newest .mp4 file from the selected directory.",
    )
    parser.add_argument("--title", default=None, help="YouTube title. Defaults to generated metadata.")
    parser.add_argument("--description", default=None, help="YouTube description.")
    parser.add_argument(
        "--tags",
        default=None,
        help="Comma-separated tags, for example: motivation,shorts,stoicism",
    )
    parser.add_argument(
        "--privacy",
        choices=["private", "unlisted", "public"],
        default="public",
        help="Upload privacy. Defaults to public.",
    )
    parser.add_argument(
        "--publish-at",
        default=None,
        help=(
            "Schedule public release time for a single video, for example '2026-05-09 18:00'. "
            "Local times are interpreted as Europe/Istanbul."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the selected video without uploading.",
    )
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
        privacy=args.privacy,
        publish_at=args.publish_at,
        dry_run=args.dry_run,
    )


def resolve_path(base_dir: str, value: str) -> str:
    if os.path.isabs(value):
        return value
    return os.path.join(base_dir, value)


def create_publish_service(settings) -> PublishNowService:
    youtube_service = YouTubeUploadService(
        settings.youtube_client_secrets_path,
        settings.youtube_token_path,
        settings.youtube_default_privacy_status,
        settings.youtube_category_id,
    )
    return PublishNowService(
        youtube_service,
        schedule_service=PublishScheduleService(),
        metadata_provider=get_youtube_metadata,
        occupied_publish_times_provider=get_youtube_publish_times,
        upload_recorder=lambda video_path, result: record_youtube_upload(
            video_path,
            result.video_id,
            result.youtube_url,
            result.publish_at,
            "scheduled" if result.publish_at else "uploaded",
        ),
    )


def main() -> None:
    settings = get_settings()
    config = config_from_args(parse_args(), settings)
    publish_service = create_publish_service(settings)
    for message in publish_service.run(config):
        print(message)


if __name__ == "__main__":
    main()
