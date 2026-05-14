from __future__ import annotations

import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.settings import Settings, get_settings
from src.services.tiktok_due_publish_service import TikTokDuePublishService
from src.services.tiktok_service_factory import TikTokUploadServiceFactory
from src.services.tiktok_upload_service import TikTokUploadService


class DueTikTokPublisher:
    def __init__(
        self,
        settings: Settings | None = None,
        service_factory: TikTokUploadServiceFactory | None = None,
    ):
        self.settings = settings or get_settings()
        self.service_factory = service_factory or TikTokUploadServiceFactory()
        self.due_service = TikTokDuePublishService(self.service_factory.create(self.settings))

    def publish(self) -> str:
        text = self.due_service.publish_due_text()
        print(text)
        return text


def create_service(settings: Settings) -> TikTokUploadService:
    return TikTokUploadServiceFactory().create(settings)


def main() -> None:
    DueTikTokPublisher().publish()


if __name__ == "__main__":
    main()
