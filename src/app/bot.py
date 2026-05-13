from __future__ import annotations

import asyncio
import os
import sys
import warnings

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.app.main import configure_windows_console
from src.core.logging import configure_logging
from src.core.media_cleanup import MediaCleanupService
from src.core.settings import Settings, get_settings
from src.domain.state import create_initial_state
from src.services.bot_controller import BotController
from src.services.publish_queue_service import PublishQueueService
from src.services.telegram_service import TelegramService
from src.services.telegram_router import TelegramRouter
from src.services.tiktok_due_publish_service import TikTokDuePublishService
from src.services.tiktok_upload_service import TikTokUploadService
from src.workflows.factory import create_workflow


warnings.filterwarnings("ignore")


def create_tiktok_service(settings: Settings) -> TikTokUploadService:
    return TikTokUploadService(
        settings.tiktok_client_key,
        settings.tiktok_client_secret,
        settings.tiktok_redirect_uri,
        settings.tiktok_token_path,
        settings.tiktok_default_privacy_level,
        settings.tiktok_disable_comment,
        settings.tiktok_disable_duet,
        settings.tiktok_disable_stitch,
        settings.tiktok_is_aigc,
    )


def create_controller(settings: Settings, feedback_message_provider=None, message_sender=None) -> BotController:
    app = create_workflow(settings, feedback_message_provider=feedback_message_provider)

    async def run_one_video() -> dict:
        return await app.ainvoke(create_initial_state())

    queue_service = PublishQueueService()
    due_service = TikTokDuePublishService(create_tiktok_service(settings))
    cleanup_service = MediaCleanupService(settings.assets_dir)
    return BotController(
        run_one_video,
        queue_provider=queue_service.queue_text,
        due_publisher=due_service.publish_due_text,
        message_sender=message_sender,
        cleanup_callback=cleanup_service.cleanup_intermediate_assets,
    )


async def run_bot() -> None:
    configure_windows_console()
    configure_logging()
    settings = get_settings()
    telegram = TelegramService(settings.telegram_bot_token, settings.telegram_chat_id)
    router: TelegramRouter | None = None

    async def wait_for_feedback(timeout_minutes: int) -> str | None:
        if router is None:
            return None
        return await router.wait_for_feedback(timeout_minutes)

    controller = create_controller(settings, feedback_message_provider=wait_for_feedback, message_sender=telegram.send_message)
    router = TelegramRouter(telegram, controller)

    telegram.send_message("Komut sistemi hazir. /start yazabilirsiniz.")
    print("[BOT] Telegram command bot started.", flush=True)

    while True:
        await router.poll_once(1)
        await asyncio.sleep(1)


def main() -> None:
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        print("\n[INFO] Bot stopped by user.")
    except Exception as exc:
        print(f"\n[FATAL ERROR] Bot error: {exc}")
        raise


if __name__ == "__main__":
    main()
