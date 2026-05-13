import os
import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime

from src.services.publish_now_service import PublishNowConfig, PublishNowService
from src.services.publish_schedule_service import PublishScheduleService


@dataclass(frozen=True)
class FakeUploadResult:
    youtube_url: str = "https://www.youtube.com/watch?v=abc123"
    privacy_status: str = "public"
    publish_at: str | None = None


class FakeYouTubeService:
    def __init__(self):
        self.calls = []

    def upload_video(self, video_path, **kwargs):
        self.calls.append({"video_path": video_path, **kwargs})
        return FakeUploadResult(publish_at=kwargs.get("publish_at"))


class FixedScheduleService(PublishScheduleService):
    def build_schedule(self, schedule_date, video_count, slots, now=None, occupied_publish_times=None):
        return [f"2026-05-09T{hour:02d}:00:00Z" for hour in range(10, 10 + video_count)]


class PublishNowServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.uploads_dir = self.tmp.name
        self.date_dir = os.path.join(self.uploads_dir, "2026-05-09")
        os.makedirs(self.date_dir)
        self.youtube = FakeYouTubeService()
        self.metadata = {}
        self.recorded_uploads = []
        self.service = PublishNowService(
            self.youtube,
            schedule_service=FixedScheduleService(),
            metadata_provider=lambda path: self.metadata.get(path, {}),
            occupied_publish_times_provider=lambda: [],
            upload_recorder=lambda video_path, result: self.recorded_uploads.append((video_path, result.publish_at)),
        )

    def tearDown(self):
        self.tmp.cleanup()

    def touch_video(self, name: str) -> str:
        path = os.path.join(self.date_dir, name)
        with open(path, "w", encoding="utf-8") as file:
            file.write("video")
        return path

    def config(self, **overrides):
        values = {
            "base_dir": self.uploads_dir,
            "uploads_dir": self.uploads_dir,
            "date_folder": "2026-05-09",
        }
        values.update(overrides)
        return PublishNowConfig(**values)

    def test_publishable_videos_keep_latest_revision_per_generated_video(self):
        old_revision = self.touch_video("motivation_20260509_100000_r01.mp4")
        latest_revision = self.touch_video("motivation_20260509_100000_r02.mp4")
        other_video = self.touch_video("motivation_20260509_110000.mp4")
        ignored = self.touch_video("random.mp4")

        selected = self.service.find_publishable_videos(self.date_dir)

        self.assertNotIn(old_revision, selected)
        self.assertIn(latest_revision, selected)
        self.assertIn(other_video, selected)
        self.assertNotIn(ignored, selected)

    def test_dry_run_does_not_upload(self):
        video = self.touch_video("motivation_20260509_100000.mp4")
        self.metadata[video] = {"title": "Planned title"}

        messages = self.service.run(self.config(dry_run=True))

        self.assertEqual(self.youtube.calls, [])
        self.assertIn("DRY RUN motivation_20260509_100000.mp4", messages[-1])
        self.assertIn("Planned title", messages[-1])

    def test_default_plan_uses_latest_publishable_video_only(self):
        older = self.touch_video("motivation_20260509_100000.mp4")
        latest = self.touch_video("motivation_20260509_110000.mp4")

        os.utime(older, (1, 1))
        os.utime(latest, (2, 2))
        plan = self.service.build_plan(self.config())

        self.assertEqual([item.video_path for item in plan], [latest])

    def test_single_video_publish_at_is_parsed_and_uploaded(self):
        video = self.touch_video("manual.mp4")

        self.service.run(self.config(video_path=video, publish_at="2099-06-09 18:00"))

        self.assertEqual(len(self.youtube.calls), 1)
        self.assertEqual(self.youtube.calls[0]["video_path"], video)
        self.assertEqual(self.youtube.calls[0]["publish_at"], "2099-06-09T15:00:00Z")
        self.assertEqual(self.recorded_uploads, [(video, "2099-06-09T15:00:00Z")])

    def test_manual_publish_at_rejects_occupied_slot(self):
        video = self.touch_video("manual.mp4")
        occupied = ["2099-06-09T15:00:00Z"]
        self.service.occupied_publish_times_provider = lambda: occupied

        with self.assertRaisesRegex(ValueError, "already occupied"):
            self.service.run(self.config(video_path=video, publish_at="2099-06-09 18:00"))

        self.assertEqual(self.youtube.calls, [])

    def test_manual_publish_at_rejects_past_slot(self):
        video = self.touch_video("manual.mp4")

        with self.assertRaisesRegex(ValueError, "future"):
            self.service.run(self.config(video_path=video, publish_at="2000-05-09 18:00"))

        self.assertEqual(self.youtube.calls, [])


if __name__ == "__main__":
    unittest.main()
