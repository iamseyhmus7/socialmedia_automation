from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


class PublishScheduleService:
    WEEKDAY_SCHEDULE_SLOTS = ["17:30", "18:30", "20:30", "22:30", "01:00", "03:00", "05:00"]
    WEEKEND_SCHEDULE_SLOTS = ["10:00", "13:00", "17:00", "19:00", "20:30", "21:45", "23:00"]
    DEFAULT_SCHEDULE_PROFILE = "auto"

    def __init__(self, timezone_name: str = "Europe/Istanbul"):
        self.timezone = ZoneInfo(timezone_name)

    def next_publish_at(
        self,
        date_folder: str | None,
        now: datetime | None = None,
        raw_slots: str | None = None,
        requested_profile: str = DEFAULT_SCHEDULE_PROFILE,
    ) -> str:
        schedule_date = self.schedule_date_for_folder(date_folder)
        slots, _profile = self.resolve_schedule_slots(schedule_date, raw_slots, requested_profile)
        return self.build_schedule(schedule_date, 1, slots, now=now)[0]

    def build_schedule(
        self,
        schedule_date: date,
        video_count: int,
        slots: list[time],
        now: datetime | None = None,
    ) -> list[str]:
        if video_count < 1:
            return []

        first_slot = slots[0]
        current_time = self._normalize_datetime(now)
        scheduled_times = []
        cycle_date = schedule_date

        while len(scheduled_times) < video_count:
            for slot in slots:
                slot_date = cycle_date
                if slot < first_slot:
                    slot_date += timedelta(days=1)

                local_dt = datetime.combine(slot_date, slot, tzinfo=self.timezone)
                if local_dt <= current_time:
                    continue

                scheduled_times.append(local_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"))
                if len(scheduled_times) == video_count:
                    break

            cycle_date += timedelta(days=1)

        return scheduled_times

    def resolve_schedule_slots(
        self,
        schedule_date: date,
        raw_slots: str | None = None,
        requested_profile: str = DEFAULT_SCHEDULE_PROFILE,
    ) -> tuple[list[time], str]:
        profile = self.schedule_profile_for_date(schedule_date, requested_profile)
        slot_values = raw_slots.split(",") if raw_slots else self.default_slots_for_profile(profile)
        return self.parse_slots(",".join(slot_values)), profile

    def schedule_date_for_folder(self, date_folder: str | None) -> date:
        if date_folder:
            try:
                return date.fromisoformat(date_folder)
            except ValueError:
                pass
        return datetime.now(self.timezone).date()

    def schedule_profile_for_date(
        self,
        schedule_date: date,
        requested_profile: str = DEFAULT_SCHEDULE_PROFILE,
    ) -> str:
        if requested_profile != self.DEFAULT_SCHEDULE_PROFILE:
            return requested_profile
        return "weekend" if schedule_date.weekday() >= 5 else "weekday"

    def default_slots_for_profile(self, profile: str) -> list[str]:
        if profile == "weekend":
            return self.WEEKEND_SCHEDULE_SLOTS
        return self.WEEKDAY_SCHEDULE_SLOTS

    def parse_slots(self, value: str) -> list[time]:
        slots = []
        for raw_slot in value.split(","):
            raw_slot = raw_slot.strip()
            if not raw_slot:
                continue
            slots.append(datetime.strptime(raw_slot, "%H:%M").time())

        if not slots:
            raise ValueError("At least one schedule slot is required.")

        return slots

    def parse_publish_at(self, value: str | None) -> str | None:
        if not value:
            return None

        normalized = value.strip().replace(" ", "T", 1)
        publish_at = datetime.fromisoformat(normalized)
        if publish_at.tzinfo is None:
            publish_at = publish_at.replace(tzinfo=self.timezone)

        return publish_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    def format_local_datetime(self, value: str) -> str:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(self.timezone).strftime(
            f"%Y-%m-%d %H:%M {self.timezone.key}"
        )

    def _normalize_datetime(self, value: datetime | None) -> datetime:
        current_time = value or datetime.now(self.timezone)
        if current_time.tzinfo is None:
            return current_time.replace(tzinfo=self.timezone)
        return current_time.astimezone(self.timezone)
