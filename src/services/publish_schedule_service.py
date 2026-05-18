from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


class PublishScheduleService:
    SCHEDULE_SLOTS = ["21:00", "00:00", "01:30", "03:00", "05:00", "06:00", "07:30", "09:00"]

    def __init__(self, timezone_name: str = "Europe/Istanbul"):
        self.timezone = ZoneInfo(timezone_name)

    def next_publish_at(
        self,
        date_folder: str | None,
        now: datetime | None = None,
        raw_slots: str | None = None,
        occupied_publish_times: list[str] | None = None,
    ) -> str:
        schedule_date = self.schedule_date_for_folder(date_folder)
        slots = self.resolve_schedule_slots(raw_slots)
        return self.build_schedule(schedule_date, 1, slots, now=now, occupied_publish_times=occupied_publish_times)[0]

    def build_schedule(
        self,
        schedule_date: date,
        video_count: int,
        slots: list[time],
        now: datetime | None = None,
        occupied_publish_times: list[str] | None = None,
    ) -> list[str]:
        if video_count < 1:
            return []

        first_slot = slots[0]
        current_time = self._normalize_datetime(now)
        occupied_times = self._normalize_publish_times(occupied_publish_times)
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

                publish_at = self._format_utc(local_dt)
                if publish_at in occupied_times:
                    continue

                scheduled_times.append(publish_at)
                occupied_times.add(publish_at)
                if len(scheduled_times) == video_count:
                    break

            cycle_date += timedelta(days=1)

        return scheduled_times

    def resolve_schedule_slots(self, raw_slots: str | None = None) -> list[time]:
        slot_values = raw_slots or ",".join(self.SCHEDULE_SLOTS)
        return self.parse_slots(slot_values)

    def schedule_date_for_folder(self, date_folder: str | None) -> date:
        if date_folder:
            try:
                return date.fromisoformat(date_folder)
            except ValueError:
                pass
        return datetime.now(self.timezone).date()

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

        return self._format_utc(publish_at)

    def validate_publish_at(
        self,
        value: str | None,
        now: datetime | None = None,
        occupied_publish_times: list[str] | None = None,
    ) -> str | None:
        publish_at = self.parse_publish_at(value)
        if not publish_at:
            return None

        local_publish_at = datetime.fromisoformat(publish_at.replace("Z", "+00:00")).astimezone(self.timezone)
        if local_publish_at <= self._normalize_datetime(now):
            raise ValueError("Publish time must be in the future.")

        if publish_at in self._normalize_publish_times(occupied_publish_times):
            raise ValueError("Publish time is already occupied by another scheduled video.")

        return publish_at

    def format_local_datetime(self, value: str) -> str:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(self.timezone).strftime(
            f"%Y-%m-%d %H:%M {self.timezone.key}"
        )

    def _normalize_datetime(self, value: datetime | None) -> datetime:
        current_time = value or datetime.now(self.timezone)
        if current_time.tzinfo is None:
            return current_time.replace(tzinfo=self.timezone)
        return current_time.astimezone(self.timezone)

    def _format_utc(self, value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    def _normalize_publish_times(self, values: list[str] | None) -> set[str]:
        publish_times = set()
        for value in values or []:
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError:
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=self.timezone)
            publish_times.add(self._format_utc(parsed))
        return publish_times
