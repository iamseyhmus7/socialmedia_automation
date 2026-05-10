import unittest
from datetime import datetime

from src.services.publish_schedule_service import PublishScheduleService


class PublishScheduleServiceTests(unittest.TestCase):
    def setUp(self):
        self.schedule_service = PublishScheduleService()

    def test_weekend_approval_after_first_slot_uses_next_slot(self):
        publish_at = self.schedule_service.next_publish_at(
            "2026-05-09",
            now=datetime(2026, 5, 9, 11, 0, tzinfo=self.schedule_service.timezone),
        )

        self.assertEqual(publish_at, "2026-05-09T10:00:00Z")

    def test_weekday_late_approval_uses_overnight_slot(self):
        publish_at = self.schedule_service.next_publish_at(
            "2026-05-08",
            now=datetime(2026, 5, 8, 23, 0, tzinfo=self.schedule_service.timezone),
        )

        self.assertEqual(publish_at, "2026-05-08T22:00:00Z")

    def test_upcoming_slot_is_used_even_when_close(self):
        publish_at = self.schedule_service.next_publish_at(
            "2026-05-09",
            now=datetime(2026, 5, 9, 12, 50, tzinfo=self.schedule_service.timezone),
        )

        self.assertEqual(publish_at, "2026-05-09T10:00:00Z")


if __name__ == "__main__":
    unittest.main()
