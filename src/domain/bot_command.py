from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BotCommandType(str, Enum):
    START = "start"
    GENERATE = "generate"
    STOP = "stop"
    STATUS = "status"
    PAUSE = "pause"
    RESUME = "resume"
    QUEUE = "queue"
    QUEUE_DETAIL = "queue_detail"
    QUEUE_EXPIRED = "queue_expired"
    QUEUE_CLEANUP = "queue_cleanup"
    CANCEL = "cancel"
    RESCHEDULE = "reschedule"
    PUBLISH_DUE = "publish_due"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class BotCommand:
    type: BotCommandType
    raw_text: str
    count: int | None = None
    queue_id: str | None = None
    publish_at: str | None = None
    error: str | None = None

    @property
    def is_valid(self) -> bool:
        return self.error is None and self.type is not BotCommandType.UNKNOWN


COMMAND_HELP: tuple[tuple[str, str], ...] = (
    ("/start", "Sistemi baslatir."),
    ("/generate 3", "3 video uretim-onay dongusu baslatir."),
    ("/stop", "Yeni video uretmeyi durdurur. O anki render/upload kritik islemdeyse onu guvenli bitirir."),
    ("/status", "Su an ne yapiyor, kac video uretti, sirada ne var gosterir."),
    ("/pause", "Yeni ise baslamaz, mevcut isi bitirip bekler."),
    ("/resume", "Devam eder."),
    ("/queue", "Planlanan YouTube/TikTok yayinlari gosterir."),
    ("/queue_detail", "Planlanan yayinlari queue id ve ayrintilarla gosterir."),
    ("/queue_expired", "Gecmiste kalmis ama scheduled gorunen yayinlari listeler."),
    ("/queue_cleanup", "Gecmiste kalmis scheduled yayinlari expired olarak isaretler."),
    ("/cancel youtube:12", "Planlanan bir yayini iptal eder."),
    ("/reschedule youtube:12 2026-05-16 17:30", "Planlanan bir yayinin saatini degistirir."),
    ("/publish_due", "Zamani gelen yayinlari elle tetikler."),
)


def parse_bot_command(text: str | None) -> BotCommand:
    raw_text = (text or "").strip()
    if not raw_text:
        return BotCommand(BotCommandType.UNKNOWN, raw_text, error="Command is empty.")

    parts = raw_text.split()
    name = parts[0].lstrip("/").lower()

    if name == BotCommandType.GENERATE.value:
        return _parse_generate(raw_text, parts)
    if name == BotCommandType.CANCEL.value:
        return _parse_cancel(raw_text, parts)
    if name == BotCommandType.RESCHEDULE.value:
        return _parse_reschedule(raw_text, parts)
    if name == "generating":
        return BotCommand(
            BotCommandType.UNKNOWN,
            raw_text,
            error="Unknown command: /generating. Did you mean /generate 1?",
        )

    simple_commands = {
        BotCommandType.START.value: BotCommandType.START,
        BotCommandType.STOP.value: BotCommandType.STOP,
        BotCommandType.STATUS.value: BotCommandType.STATUS,
        BotCommandType.PAUSE.value: BotCommandType.PAUSE,
        BotCommandType.RESUME.value: BotCommandType.RESUME,
        BotCommandType.QUEUE.value: BotCommandType.QUEUE,
        BotCommandType.QUEUE_DETAIL.value: BotCommandType.QUEUE_DETAIL,
        BotCommandType.QUEUE_EXPIRED.value: BotCommandType.QUEUE_EXPIRED,
        BotCommandType.QUEUE_CLEANUP.value: BotCommandType.QUEUE_CLEANUP,
        BotCommandType.PUBLISH_DUE.value: BotCommandType.PUBLISH_DUE,
    }
    command_type = simple_commands.get(name)
    if command_type is None:
        return BotCommand(BotCommandType.UNKNOWN, raw_text, error=f"Unknown command: /{name}")
    if len(parts) > 1:
        return BotCommand(command_type, raw_text, error=f"/{name} does not accept arguments.")
    return BotCommand(command_type, raw_text)


def command_help_text() -> str:
    return "\n\n".join(f"{command}\n{description}" for command, description in COMMAND_HELP)


def _parse_generate(raw_text: str, parts: list[str]) -> BotCommand:
    if len(parts) != 2:
        return BotCommand(BotCommandType.GENERATE, raw_text, error="/generate requires a count, for example /generate 3.")

    try:
        count = int(parts[1])
    except ValueError:
        return BotCommand(BotCommandType.GENERATE, raw_text, error="/generate count must be a number.")

    if count < 1:
        return BotCommand(BotCommandType.GENERATE, raw_text, error="/generate count must be at least 1.")
    return BotCommand(BotCommandType.GENERATE, raw_text, count=count)


def _parse_cancel(raw_text: str, parts: list[str]) -> BotCommand:
    if len(parts) != 2:
        return BotCommand(BotCommandType.CANCEL, raw_text, error="/cancel requires a queue id, for example /cancel youtube:12.")
    return BotCommand(BotCommandType.CANCEL, raw_text, queue_id=parts[1])


def _parse_reschedule(raw_text: str, parts: list[str]) -> BotCommand:
    if len(parts) < 3:
        return BotCommand(
            BotCommandType.RESCHEDULE,
            raw_text,
            error="/reschedule requires a queue id and time, for example /reschedule youtube:12 2026-05-16 17:30.",
        )
    return BotCommand(BotCommandType.RESCHEDULE, raw_text, queue_id=parts[1], publish_at=" ".join(parts[2:]))
