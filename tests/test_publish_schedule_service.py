import unittest
from datetime import datetime

from src.services.publish_schedule_service import PublishScheduleService


class PublishScheduleServiceTests(unittest.TestCase):
    def setUp(self):
        self.schedule_service = PublishScheduleService()

    def test_saturday_uses_shared_schedule_slots(self):
        publish_at = self.schedule_service.next_publish_at(
            "2026-05-09",
            now=datetime(2026, 5, 9, 11, 0, tzinfo=self.schedule_service.timezone),
        )

        self.assertEqual(publish_at, "2026-05-09T18:00:00Z")

    def test_friday_uses_same_shared_schedule_slots(self):
        publish_at = self.schedule_service.next_publish_at(
            "2026-05-08",
            now=datetime(2026, 5, 8, 11, 0, tzinfo=self.schedule_service.timezone),
        )

        self.assertEqual(publish_at, "2026-05-08T18:00:00Z")

    def test_late_approval_uses_overnight_slot(self):
        publish_at = self.schedule_service.next_publish_at(
            "2026-05-08",
            now=datetime(2026, 5, 8, 23, 0, tzinfo=self.schedule_service.timezone),
        )

        self.assertEqual(publish_at, "2026-05-08T21:00:00Z")

    def test_upcoming_slot_is_used_even_when_close(self):
        publish_at = self.schedule_service.next_publish_at(
            "2026-05-09",
            now=datetime(2026, 5, 9, 12, 50, tzinfo=self.schedule_service.timezone),
        )

        self.assertEqual(publish_at, "2026-05-09T18:00:00Z")

    def test_occupied_slots_are_skipped(self):
        publish_at = self.schedule_service.next_publish_at(
            "2026-05-09",
            now=datetime(2026, 5, 9, 9, 0, tzinfo=self.schedule_service.timezone),
            occupied_publish_times=["2026-05-09T07:00:00Z"],
        )

        self.assertEqual(publish_at, "2026-05-09T18:00:00Z")

    def test_schedule_moves_to_next_day_when_today_slots_are_occupied(self):
        schedule = self.schedule_service.build_schedule(
            self.schedule_service.schedule_date_for_folder("2026-05-09"),
            1,
            self.schedule_service.parse_slots("10:00"),
            now=datetime(2026, 5, 9, 9, 0, tzinfo=self.schedule_service.timezone),
            occupied_publish_times=["2026-05-09T07:00:00Z"],
        )

        self.assertEqual(schedule, ["2026-05-10T07:00:00Z"])

    def test_validate_publish_at_rejects_past_and_occupied_slots(self):
        now = datetime(2026, 5, 9, 9, 0, tzinfo=self.schedule_service.timezone)

        with self.assertRaisesRegex(ValueError, "future"):
            self.schedule_service.validate_publish_at("2026-05-09 08:00", now=now)

        with self.assertRaisesRegex(ValueError, "occupied"):
            self.schedule_service.validate_publish_at(
                "2026-05-09 10:00",
                now=now,
                occupied_publish_times=["2026-05-09T07:00:00Z"],
            )


if __name__ == "__main__":
    unittest.main()
