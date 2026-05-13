from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from src.services.bot_controller import BotController

if TYPE_CHECKING:
    from src.services.telegram_service import TelegramService


class TelegramRouter:
    def __init__(self, telegram_service: "TelegramService", controller: BotController):
        self.telegram_service = telegram_service
        self.controller = controller
        self.feedback_queue: asyncio.Queue[str] = asyncio.Queue()
        self.is_waiting_for_feedback = False

    async def poll_once(self, timeout_minutes: int = 1) -> None:
        message = await asyncio.to_thread(self.telegram_service.wait_for_message, timeout_minutes, False)
        if message is not None:
            await self.route_message(message)

    async def route_message(self, message: str) -> None:
        text = (message or "").strip()
        if not text:
            return

        if text.startswith("/"):
            response = await self.controller.handle_message(text)
            self.telegram_service.send_message(response)
            return

        if self.is_waiting_for_feedback:
            await self.feedback_queue.put(text)
            return

        self.telegram_service.send_message("Video onayi beklenmiyor. Sistem komutlari icin / ile baslayin.")

    async def wait_for_feedback(self, timeout_minutes: int) -> str | None:
        self.is_waiting_for_feedback = True
        try:
            return await asyncio.wait_for(self.feedback_queue.get(), timeout=timeout_minutes * 60)
        except asyncio.TimeoutError:
            return None
        finally:
            self.is_waiting_for_feedback = False
