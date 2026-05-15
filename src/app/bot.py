from __future__ import annotations

import asyncio
import logging
import os
import sys
import warnings
from typing import Awaitable, Callable

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.app.runtime import AppRuntime
from src.core.media_cleanup import MediaCleanupService
from src.core.settings import Settings, get_settings
from src.domain.state import create_initial_state
from src.services.bot_controller import BotController
from src.services.publish_queue_service import PublishQueueService
from src.services.system_health_service import SystemHealthService
from src.services.telegram_service import TelegramService
from src.services.telegram_router import TelegramRouter
from src.services.tiktok_due_publish_service import TikTokDuePublishService
from src.services.tiktok_service_factory import TikTokUploadServiceFactory
from src.services.tiktok_upload_service import TikTokUploadService
from src.workflows.factory import create_workflow


warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

FeedbackMessageProvider = Callable[[int], Awaitable[str | None]]


class BotControllerFactory:
    def __init__(
        self,
        settings: Settings,
        tiktok_service_factory: TikTokUploadServiceFactory | None = None,
    ):
        self.settings = settings
        self.tiktok_service_factory = tiktok_service_factory or TikTokUploadServiceFactory()

    def create(
        self,
        feedback_message_provider: FeedbackMessageProvider | None = None,
        message_sender: Callable[[str], bool] | None = None,
    ) -> BotController:
        app = create_workflow(self.settings, feedback_message_provider=feedback_message_provider)

        async def run_one_video() -> dict:
            return await app.ainvoke(create_initial_state())

        queue_service = PublishQueueService()
        health_service = SystemHealthService(self.settings)
        due_service = TikTokDuePublishService(self.tiktok_service_factory.create(self.settings))
        cleanup_service = MediaCleanupService(self.settings.assets_dir)
        return BotController(
            run_one_video,
            queue_provider=queue_service.queue_text,
            queue_detail_provider=queue_service.queue_detail_text,
            queue_expired_provider=queue_service.expired_text,
            queue_cleanup_provider=queue_service.cleanup_text,
            queue_cancel_provider=queue_service.cancel_text,
            queue_reschedule_provider=queue_service.reschedule_text,
            due_publisher=due_service.publish_due_text,
            message_sender=message_sender,
            cleanup_callback=cleanup_service.cleanup_intermediate_assets,
            status_provider=health_service.health_text,
        )


class TelegramBotApplication:
    def __init__(
        self,
        settings: Settings | None = None,
        runtime: AppRuntime | None = None,
        controller_factory: BotControllerFactory | None = None,
    ):
        self.settings = settings or get_settings()
        self.runtime = runtime or AppRuntime(self.settings)
        self.controller_factory = controller_factory or BotControllerFactory(self.settings)
        self.telegram = TelegramService(self.settings.telegram_bot_token, self.settings.telegram_chat_id)
        self.router: TelegramRouter | None = None

    async def run(self) -> None:
        self.runtime.configure()
        self.router = self._create_router()

        self.telegram.send_message("Komut sistemi hazir. /start yazabilirsiniz.")
        logger.info("Telegram command bot started")

        while True:
            await self.router.poll_once(1)
            await asyncio.sleep(1)

    def _create_router(self) -> TelegramRouter:
        controller = self.controller_factory.create(
            feedback_message_provider=self.wait_for_feedback,
            message_sender=self.telegram.send_message,
        )
        return TelegramRouter(self.telegram, controller)

    async def wait_for_feedback(self, timeout_minutes: int) -> str | None:
        if self.router is None:
            return None
        return await self.router.wait_for_feedback(timeout_minutes)


def create_tiktok_service(settings: Settings) -> TikTokUploadService:
    return TikTokUploadServiceFactory().create(settings)


def create_controller(settings: Settings, feedback_message_provider=None, message_sender=None) -> BotController:
    return BotControllerFactory(settings).create(feedback_message_provider, message_sender)


async def run_bot() -> None:
    await TelegramBotApplication().run()


def main() -> None:
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as exc:
        logger.exception("Bot error: %s", exc)
        raise


if __name__ == "__main__":
    main()
