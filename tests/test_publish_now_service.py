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
    def build_schedule(self, schedule_date, video_count, slots, now=None):
        return [f"2026-05-09T{hour:02d}:00:00Z" for hour in range(10, 10 + video_count)]


class PublishNowServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.uploads_dir = self.tmp.name
        self.date_dir = os.path.join(self.uploads_dir, "2026-05-09")
        os.makedirs(self.date_dir)
        self.youtube = FakeYouTubeService()
        self.metadata = {}
        self.service = PublishNowService(
            self.youtube,
            schedule_service=FixedScheduleService(),
            metadata_provider=lambda path: self.metadata.get(path, {}),
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

    def test_all_mp4_selects_every_mp4(self):
        generated = self.touch_video("motivation_20260509_100000.mp4")
        random_video = self.touch_video("random.mp4")

        plan = self.service.build_plan(self.config(all_mp4=True))

        self.assertEqual([item.video_path for item in plan], sorted([generated, random_video]))

    def test_directory_schedule_uploads_each_video_with_generated_publish_times(self):
        first = self.touch_video("motivation_20260509_100000.mp4")
        second = self.touch_video("motivation_20260509_110000.mp4")

        messages = self.service.run(self.config(all_videos=True))

        self.assertEqual(len(self.youtube.calls), 2)
        self.assertEqual(self.youtube.calls[0]["video_path"], first)
        self.assertEqual(self.youtube.calls[0]["publish_at"], "2026-05-09T10:00:00Z")
        self.assertEqual(self.youtube.calls[1]["video_path"], second)
        self.assertEqual(self.youtube.calls[1]["publish_at"], "2026-05-09T11:00:00Z")
        self.assertIn("Scheduling 2 video(s)", messages[0])

    def test_dry_run_does_not_upload(self):
        video = self.touch_video("motivation_20260509_100000.mp4")
        self.metadata[video] = {"title": "Planned title"}

        messages = self.service.run(self.config(all_videos=True, dry_run=True))

        self.assertEqual(self.youtube.calls, [])
        self.assertIn("DRY RUN motivation_20260509_100000.mp4", messages[-1])
        self.assertIn("Planned title", messages[-1])

    def test_single_video_publish_at_is_parsed_and_uploaded(self):
        video = self.touch_video("manual.mp4")

        self.service.run(self.config(video_path=video, publish_at="2026-05-09 18:00"))

        self.assertEqual(len(self.youtube.calls), 1)
        self.assertEqual(self.youtube.calls[0]["video_path"], video)
        self.assertEqual(self.youtube.calls[0]["publish_at"], "2026-05-09T15:00:00Z")


if __name__ == "__main__":
    unittest.main()
