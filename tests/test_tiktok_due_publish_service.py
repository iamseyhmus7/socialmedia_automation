import os
import tempfile
import unittest
from datetime import datetime, timezone

from src.services.tiktok_due_publish_service import TikTokDuePublishService
from src.services.tiktok_upload_service import TikTokUploadResult


class FakeTikTokUploadService:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.uploads = []

    def upload_video(self, video_path, title=None, description=None, tags=None, publish_at=None):
        self.uploads.append(
            {
                "video_path": video_path,
                "title": title,
                "description": description,
                "tags": tags,
                "publish_at": publish_at,
            }
        )
        if self.should_fail:
            raise RuntimeError("upload failed")
        return TikTokUploadResult("pub_123", tiktok_url="https://www.tiktok.com/@user/video/123", publish_at=publish_at)


class TikTokDuePublishServiceTests(unittest.TestCase):
    def test_publish_due_text_returns_empty_message_when_no_due_uploads(self):
        service = TikTokDuePublishService(
            FakeTikTokUploadService(),
            due_uploads_provider=lambda now_utc: [],
            next_scheduled_provider=lambda: None,
            clock=lambda: datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(
            service.publish_due_text(),
            "Zamani gelen TikTok yayini yok.\nSiradaki TikTok yayini da planlanmamis.",
        )

    def test_publish_due_text_shows_next_tiktok_slot_when_no_due_uploads(self):
        service = TikTokDuePublishService(
            FakeTikTokUploadService(),
            due_uploads_provider=lambda now_utc: [],
            next_scheduled_provider=lambda: {
                "final_video_path": r"C:\videos\next.mp4",
                "publish_at": "2026-05-09T17:30:00Z",
            },
            clock=lambda: datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc),
        )

        text = service.publish_due_text()

        self.assertIn("Zamani gelen TikTok yayini yok.", text)
        self.assertIn("Siradaki TikTok: 2026-05-09 20:30 Europe/Istanbul", text)
        self.assertIn("next.mp4", text)

    def test_publish_due_text_uploads_due_items_and_records_success(self):
        records = []
        uploader = FakeTikTokUploadService()
        with tempfile.TemporaryDirectory() as tmp:
            video_path = os.path.join(tmp, "final.mp4")
            service = TikTokDuePublishService(
                uploader,
                due_uploads_provider=lambda now_utc: [{"final_video_path": video_path, "publish_at": "2026-05-09T10:00:00Z"}],
                metadata_provider=lambda path: {"title": "Title", "description": "Caption", "tags": ["motivation"]},
                upload_recorder=lambda *args, **kwargs: records.append((args, kwargs)),
                next_scheduled_provider=lambda: None,
                clock=lambda: datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc),
            )

            text = service.publish_due_text()

        self.assertIn("Gonderildi: final.mp4 publish_id=pub_123", text)
        self.assertEqual(uploader.uploads[0]["title"], "Title")
        self.assertEqual(uploader.uploads[0]["description"], "Caption")
        self.assertEqual(uploader.uploads[0]["tags"], ["motivation"])
        self.assertEqual(records[0][0][1], "pub_123")
        self.assertEqual(records[0][0][4], "processing")

    def test_publish_due_text_records_failed_upload_and_continues(self):
        records = []
        uploader = FakeTikTokUploadService(should_fail=True)
        with tempfile.TemporaryDirectory() as tmp:
            video_path = os.path.join(tmp, "final.mp4")
            service = TikTokDuePublishService(
                uploader,
                due_uploads_provider=lambda now_utc: [{"final_video_path": video_path, "publish_at": "2026-05-09T10:00:00Z"}],
                metadata_provider=lambda path: None,
                upload_recorder=lambda *args, **kwargs: records.append((args, kwargs)),
                next_scheduled_provider=lambda: None,
                clock=lambda: datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc),
            )

            text = service.publish_due_text()

        self.assertIn("Basarisiz: final.mp4 - upload failed", text)
        self.assertEqual(records[0][0], (video_path,))
        self.assertEqual(records[0][1]["publish_at"], "2026-05-09T10:00:00Z")
        self.assertEqual(records[0][1]["status"], "failed")
        self.assertEqual(records[0][1]["error"], "upload failed")


if __name__ == "__main__":
    unittest.main()
