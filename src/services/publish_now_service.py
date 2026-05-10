from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable

from src.services.publish_schedule_service import PublishScheduleService
from src.services.youtube_upload_service import YouTubeUploadService


GENERATED_VIDEO_PATTERN = re.compile(
    r"^(?P<prefix>[a-zA-Z]+)_(?P<date>\d{8})_(?P<time>\d{6})(?:_r(?P<revision>\d+))?\.mp4$",
    re.IGNORECASE,
)
MANUAL_REVISION_PATTERN = re.compile(r"^revision_(?P<revision>\d+)\.mp4$", re.IGNORECASE)


@dataclass(frozen=True)
class PublishNowConfig:
    base_dir: str
    uploads_dir: str
    upload_dir: str | None = None
    date_folder: str | None = None
    video_path: str | None = None
    all_videos: bool = False
    all_mp4: bool = False
    latest: bool = False
    title: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    privacy: str = "public"
    publish_at: str | None = None
    slots: str | None = None
    schedule_profile: str = PublishScheduleService.DEFAULT_SCHEDULE_PROFILE
    dry_run: bool = False


@dataclass(frozen=True)
class PublishPlanItem:
    video_path: str
    publish_at: str | None


class PublishNowService:
    def __init__(
        self,
        youtube_service: YouTubeUploadService,
        schedule_service: PublishScheduleService | None = None,
        metadata_provider: Callable[[str], dict[str, Any] | None] | None = None,
    ):
        self.youtube_service = youtube_service
        self.schedule_service = schedule_service or PublishScheduleService()
        self.metadata_provider = metadata_provider or (lambda _path: {})

    def run(self, config: PublishNowConfig) -> list[str]:
        plan = self.build_plan(config)
        messages = []
        if len(plan) > 1:
            upload_dir = self.resolve_upload_dir(config.uploads_dir, config.upload_dir, config.date_folder)
            messages.append(f"Scheduling {len(plan)} video(s) from: {upload_dir} ({self.schedule_profile(upload_dir, config)} slots)")

        for item in plan:
            if config.dry_run:
                messages.append(self.dry_run_message(item.video_path, item.publish_at))
                continue

            result = self.upload(item.video_path, config, item.publish_at)
            messages.append(self.result_message(item.video_path, result))

        return messages

    def build_plan(self, config: PublishNowConfig) -> list[PublishPlanItem]:
        upload_dir = self.resolve_upload_dir(config.uploads_dir, config.upload_dir, config.date_folder)

        if self.should_schedule_directory(config):
            videos = self.find_videos(upload_dir, include_all_mp4=config.all_mp4)
            slots, _profile = self.resolve_schedule_slots(upload_dir, config)
            scheduled_times = self.build_schedule(upload_dir, len(videos), slots)
            return [PublishPlanItem(video_path, scheduled_times[index]) for index, video_path in enumerate(videos)]

        video_path = self.resolve_path(config.base_dir, config.video_path) if config.video_path else self.find_latest_video(upload_dir)
        return [PublishPlanItem(video_path, self.schedule_service.parse_publish_at(config.publish_at))]

    def upload(self, video_path: str, config: PublishNowConfig, publish_at: str | None):
        metadata = self.metadata_for_video(video_path)
        return self.youtube_service.upload_video(
            video_path,
            title=config.title or metadata.get("title"),
            description=config.description if config.description is not None else metadata.get("description"),
            tags=config.tags or metadata.get("tags"),
            privacy_status=config.privacy,
            publish_at=publish_at,
        )

    def should_schedule_directory(self, config: PublishNowConfig) -> bool:
        return config.all_videos or config.all_mp4 or (
            not config.video_path and not config.latest and not config.publish_at
        )

    def resolve_path(self, base_dir: str, value: str) -> str:
        if os.path.isabs(value):
            return value
        return os.path.join(base_dir, value)

    def resolve_upload_dir(self, base_uploads_dir: str, upload_dir: str | None, date_folder: str | None) -> str:
        if upload_dir:
            return upload_dir
        if date_folder:
            return os.path.join(base_uploads_dir, date_folder)
        return self.find_latest_date_dir(base_uploads_dir)

    def schedule_date_for_upload_dir(self, upload_dir: str) -> date:
        folder_name = os.path.basename(os.path.normpath(upload_dir))
        return self.schedule_service.schedule_date_for_folder(folder_name)

    def schedule_profile(self, upload_dir: str, config: PublishNowConfig) -> str:
        schedule_date = self.schedule_date_for_upload_dir(upload_dir)
        return self.schedule_service.schedule_profile_for_date(schedule_date, config.schedule_profile)

    def resolve_schedule_slots(self, upload_dir: str, config: PublishNowConfig):
        schedule_date = self.schedule_date_for_upload_dir(upload_dir)
        return self.schedule_service.resolve_schedule_slots(schedule_date, config.slots, config.schedule_profile)

    def build_schedule(self, upload_dir: str, video_count: int, slots) -> list[str]:
        schedule_date = self.schedule_date_for_upload_dir(upload_dir)
        return self.schedule_service.build_schedule(schedule_date, video_count, slots)

    def find_latest_date_dir(self, base_uploads_dir: str) -> str:
        date_dirs = []
        for entry in os.scandir(base_uploads_dir):
            if entry.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", entry.name):
                date_dirs.append((date.fromisoformat(entry.name), entry.path))

        if not date_dirs:
            raise FileNotFoundError(f"No YYYY-MM-DD date folders were found in: {base_uploads_dir}")

        return max(date_dirs)[1]

    def find_mp4_files(self, upload_dir: str) -> list[str]:
        mp4_files = [
            os.path.join(upload_dir, file_name)
            for file_name in os.listdir(upload_dir)
            if file_name.lower().endswith(".mp4") and os.path.isfile(os.path.join(upload_dir, file_name))
        ]
        if not mp4_files:
            raise FileNotFoundError(f"No .mp4 files were found in upload directory: {upload_dir}")

        return mp4_files

    def find_videos(self, upload_dir: str, include_all_mp4: bool = False) -> list[str]:
        if include_all_mp4:
            return sorted(self.find_mp4_files(upload_dir))
        return self.find_publishable_videos(upload_dir)

    def find_latest_video(self, upload_dir: str) -> str:
        candidates = [(os.path.getmtime(path), path) for path in self.find_videos(upload_dir)]
        return max(candidates)[1]

    def find_publishable_videos(self, upload_dir: str) -> list[str]:
        selected_by_base_key = {}
        manual_revisions = []

        for path in self.find_mp4_files(upload_dir):
            generated = self.parse_generated_video(path)
            if generated:
                base_key, created_at, revision = generated
                current = selected_by_base_key.get(base_key)
                if current is None or revision > current["revision"]:
                    selected_by_base_key[base_key] = {
                        "created_at": created_at,
                        "revision": revision,
                        "path": path,
                    }
                continue

            manual_revision = self.parse_manual_revision(path)
            if manual_revision:
                created_at, revision = manual_revision
                manual_revisions.append({"created_at": created_at, "revision": revision, "path": path})

        publishable = list(selected_by_base_key.values()) + manual_revisions
        if not publishable:
            raise FileNotFoundError(f"No publishable generated or revision videos were found in: {upload_dir}")

        selected = sorted(publishable, key=lambda item: (item["created_at"], item["revision"], item["path"]))
        return [str(item["path"]) for item in selected]

    def parse_generated_video(self, path: str) -> tuple[str, datetime, int] | None:
        file_name = os.path.basename(path)
        match = GENERATED_VIDEO_PATTERN.fullmatch(file_name)
        if not match:
            return None

        created_at = datetime.strptime(f"{match.group('date')}{match.group('time')}", "%Y%m%d%H%M%S")
        revision = int(match.group("revision") or 0)
        base_key = f"{match.group('prefix').lower()}_{match.group('date')}_{match.group('time')}"
        return base_key, created_at, revision

    def parse_manual_revision(self, path: str) -> tuple[datetime, int] | None:
        match = MANUAL_REVISION_PATTERN.fullmatch(os.path.basename(path))
        if not match:
            return None

        return datetime.fromtimestamp(os.path.getmtime(path)), int(match.group("revision"))

    def metadata_for_video(self, video_path: str) -> dict[str, Any]:
        return self.metadata_provider(video_path) or {}

    def dry_run_message(self, video_path: str, publish_at: str | None = None) -> str:
        file_name = os.path.basename(video_path)
        title = self.metadata_for_video(video_path).get("title") or "manual/default"
        if publish_at:
            local_time = self.schedule_service.format_local_datetime(publish_at)
            return f"DRY RUN {file_name}: public at {local_time} | title: {title}"
        return f"DRY RUN {file_name}: upload as public now | title: {title}"

    def result_message(self, video_path: str, result) -> str:
        file_name = os.path.basename(video_path)
        if result.publish_at:
            local_time = self.schedule_service.format_local_datetime(result.publish_at)
            return f"Scheduled {file_name}: {result.youtube_url} (public at {local_time})"
        return f"Uploaded {file_name}: {result.youtube_url} ({result.privacy_status})"
