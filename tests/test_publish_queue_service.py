import unittest

from src.services.publish_queue_service import PublishQueueService


class PublishQueueServiceTests(unittest.TestCase):
    def test_empty_queue_message(self):
        service = PublishQueueService(scheduled_uploads_provider=lambda limit: [])

        self.assertEqual(service.queue_text(), "Planlanan YouTube/TikTok yayini yok.")

    def test_queue_formats_scheduled_uploads(self):
        service = PublishQueueService(
            scheduled_uploads_provider=lambda limit: [
                {
                    "platform": "YouTube",
                    "final_video_path": "C:\\videos\\motivation.mp4",
                    "publish_at": "2026-05-09T10:00:00Z",
                    "status": "scheduled",
                }
            ]
        )

        text = service.queue_text()

        self.assertIn("Planlanan yayinlar:", text)
        self.assertIn("YouTube", text)
        self.assertIn("platform schedule", text)
        self.assertIn("2026-05-09 13:00 Europe/Istanbul", text)
        self.assertIn("motivation.mp4", text)

    def test_queue_labels_tiktok_as_local_queue(self):
        service = PublishQueueService(
            scheduled_uploads_provider=lambda limit: [
                {
                    "platform": "TikTok",
                    "final_video_path": "C:\\videos\\motivation.mp4",
                    "publish_at": "2026-05-09T10:00:00Z",
                    "status": "scheduled",
                }
            ]
        )

        self.assertIn("TikTok (local queue)", service.queue_text())


if __name__ == "__main__":
    unittest.main()
