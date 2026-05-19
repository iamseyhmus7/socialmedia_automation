import unittest
from datetime import datetime

from src.services.publish_queue_service import PublishQueueService
from src.services.publish_schedule_service import PublishScheduleService


class FrozenPublishScheduleService(PublishScheduleService):
    def validate_publish_at(self, value, now=None, occupied_publish_times=None):
        return super().validate_publish_at(
            value,
            now=datetime(2026, 5, 9, 10, 0),
            occupied_publish_times=occupied_publish_times,
        )


class PublishQueueServiceTests(unittest.TestCase):
    def test_empty_queue_message(self):
        service = PublishQueueService(scheduled_uploads_provider=lambda limit: [])

        self.assertEqual(service.queue_text(), "Planlanan YouTube/TikTok yayini yok.")

    def test_queue_formats_scheduled_uploads(self):
        service = PublishQueueService(
            scheduled_uploads_provider=lambda limit: [
                {
                    "platform": "YouTube",
                    "queue_id": "youtube:12",
                    "final_video_path": "C:\\videos\\motivation.mp4",
                    "publish_at": "2026-05-09T10:00:00Z",
                    "status": "scheduled",
                }
            ]
        )

        text = service.queue_text()

        self.assertIn("Planlanan yayinlar:", text)
        self.assertIn("youtube:12", text)
        self.assertIn("YouTube", text)
        self.assertIn("platform schedule", text)
        self.assertIn("2026-05-09 13:00 Europe/Istanbul", text)
        self.assertIn("motivation.mp4", text)

    def test_queue_labels_tiktok_as_local_queue(self):
        service = PublishQueueService(
            scheduled_uploads_provider=lambda limit: [
                {
                    "platform": "TikTok",
                    "queue_id": "tiktok:7",
                    "final_video_path": "C:\\videos\\motivation.mp4",
                    "publish_at": "2026-05-09T10:00:00Z",
                    "status": "scheduled",
                }
            ]
        )

        self.assertIn("TikTok (local queue)", service.queue_text())

    def test_queue_detail_formats_details(self):
        service = PublishQueueService(
            scheduled_uploads_provider=lambda limit: [{"queue_id": "youtube:12"}],
            detail_provider=lambda queue_id: {
                "queue_id": queue_id,
                "platform": "YouTube",
                "final_video_path": "C:\\videos\\motivation.mp4",
                "publish_at": "2026-05-09T10:00:00Z",
                "status": "scheduled",
                "remote_url": "https://youtube.test/video",
            },
        )

        text = service.queue_detail_text()

        self.assertIn("ID: youtube:12", text)
        self.assertIn("Status: scheduled", text)
        self.assertIn("URL: https://youtube.test/video", text)

    def test_cancel_scheduled_item(self):
        service = PublishQueueService(
            detail_provider=lambda queue_id: {"queue_id": queue_id, "status": "scheduled"},
            cancel_provider=lambda queue_id: queue_id == "youtube:12",
        )

        self.assertEqual(service.cancel_text("youtube:12"), "Queue kaydi iptal edildi: youtube:12")

    def test_cancel_missing_item(self):
        service = PublishQueueService(detail_provider=lambda queue_id: None)

        self.assertIn("bulunamadi", service.cancel_text("youtube:99"))

    def test_reschedule_scheduled_item(self):
        calls = []
        service = PublishQueueService(
            detail_provider=lambda queue_id: {
                "queue_id": queue_id,
                "status": "scheduled",
                "publish_at": "2026-05-09T10:00:00Z",
            },
            reschedule_provider=lambda queue_id, publish_at: calls.append((queue_id, publish_at)) is None or True,
            occupied_publish_times_provider=lambda: [],
            schedule_service=FrozenPublishScheduleService(),
        )

        text = service.reschedule_text("youtube:12", "2026-05-16 17:30")

        self.assertIn("yeniden zamanlandi", text)
        self.assertEqual(calls, [("youtube:12", "2026-05-16T14:30:00Z")])

    def test_reschedule_rejects_occupied_time(self):
        service = PublishQueueService(
            detail_provider=lambda queue_id: {
                "queue_id": queue_id,
                "status": "scheduled",
                "publish_at": "2026-05-09T10:00:00Z",
            },
            occupied_publish_times_provider=lambda: ["2026-05-16T14:30:00Z"],
            schedule_service=FrozenPublishScheduleService(),
        )

        self.assertIn("already occupied", service.reschedule_text("youtube:12", "2026-05-16 17:30"))

    def test_expired_text_lists_past_scheduled_items(self):
        service = PublishQueueService(
            expired_uploads_provider=lambda now_utc, limit: [
                {
                    "queue_id": "youtube:1",
                    "platform": "YouTube",
                    "final_video_path": "C:\\videos\\old.mp4",
                    "publish_at": "2026-05-09T10:00:00Z",
                    "status": "scheduled",
                }
            ]
        )

        text = service.expired_text()

        self.assertIn("Gecmiste kalmis", text)
        self.assertIn("youtube:1", text)
        self.assertIn("/queue_cleanup", text)

    def test_expired_text_reports_empty_queue(self):
        service = PublishQueueService(expired_uploads_provider=lambda now_utc, limit: [])

        self.assertEqual(service.expired_text(), "Gecmiste kalmis scheduled yayin yok.")

    def test_cleanup_text_marks_expired_items(self):
        service = PublishQueueService(expired_marker=lambda now_utc: {"YouTube": 2, "TikTok": 1, "total": 3})

        text = service.cleanup_text()

        self.assertIn("expired yapildi", text)
        self.assertIn("toplam=3", text)

    def test_cleanup_text_reports_nothing_to_clean(self):
        service = PublishQueueService(expired_marker=lambda now_utc: {"YouTube": 0, "TikTok": 0, "total": 0})

        self.assertEqual(service.cleanup_text(), "Temizlenecek gecmis scheduled yayin yok.")


if __name__ == "__main__":
    unittest.main()
