from __future__ import annotations

import os
import sys
import time
from datetime import datetime


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.logging import configure_logging
from src.core.settings import Settings, get_settings
from src.services.telegram_service import TelegramService
from src.services.tiktok_due_publish_service import TikTokDuePublishService
from src.services.tiktok_service_factory import TikTokUploadServiceFactory
from src.services.tiktok_upload_service import TikTokUploadService


class DueTikTokNotifier:
    def should_notify(self, text: str) -> bool:
        return "Gonderildi:" in text or "Basarisiz:" in text


class TikTokDueLoopApplication:
    def __init__(
        self,
        settings: Settings | None = None,
        interval_seconds: int | None = None,
        notifier: DueTikTokNotifier | None = None,
        service_factory: TikTokUploadServiceFactory | None = None,
    ):
        self.settings = settings or get_settings()
        self.interval_seconds = interval_seconds or int(os.getenv("TIKTOK_DUE_CHECK_INTERVAL_SECONDS", "300"))
        self.notifier = notifier or DueTikTokNotifier()
        self.service_factory = service_factory or TikTokUploadServiceFactory()
        self.due_service = TikTokDuePublishService(self.service_factory.create(self.settings))
        self.telegram = TelegramService(self.settings.telegram_bot_token, self.settings.telegram_chat_id)

    def run_forever(self) -> None:
        configure_logging()
        print(f"[TIKTOK-DUE] Loop started. interval={self.interval_seconds}s", flush=True)
        while True:
            self.run_once()
            time.sleep(self.interval_seconds)

    def run_once(self) -> str:
        try:
            text = self.due_service.publish_due_text()
            timestamp = datetime.now().isoformat(timespec="seconds")
            print(f"[TIKTOK-DUE] {timestamp}\n{text}", flush=True)
            if self.notifier.should_notify(text):
                self.telegram.send_message(text)
            return text
        except Exception as exc:
            message = f"TikTok due loop hata: {exc}"
            print(f"[TIKTOK-DUE] {message}", flush=True)
            self.telegram.send_message(message)
            return message


def create_tiktok_service(settings: Settings) -> TikTokUploadService:
    return TikTokUploadServiceFactory().create(settings)


def should_notify(text: str) -> bool:
    return DueTikTokNotifier().should_notify(text)


def main() -> None:
    TikTokDueLoopApplication().run_forever()


if __name__ == "__main__":
    main()
