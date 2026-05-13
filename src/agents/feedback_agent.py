from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from src.domain.feedback import FeedbackPlan
from src.services.gemini_feedback_analyzer import GeminiFeedbackAnalyzer
from src.services.telegram_service import TelegramService


FeedbackMessageProvider = Callable[[int], Awaitable[str | None]]


class FeedbackAgent:
    def __init__(
        self,
        telegram_service: TelegramService,
        analyzer: GeminiFeedbackAnalyzer,
        message_provider: FeedbackMessageProvider | None = None,
    ):
        self.telegram_service = telegram_service
        self.analyzer = analyzer
        self.message_provider = message_provider

    def send_review_video(self, video_path: str, caption: str) -> None:
        self.telegram_service.send_video(video_path, caption=caption)

    async def wait_for_feedback(self, video_count: int, timeout_minutes: int = 15) -> FeedbackPlan:
        if self.message_provider is not None:
            message = await self.message_provider(timeout_minutes)
        else:
            message = await asyncio.to_thread(self.telegram_service.wait_for_message, timeout_minutes)
        if message is None:
            return FeedbackPlan(status="timeout", actions=[], raw_message=None)
        plan = self.analyzer.analyze(message, video_count=video_count)
        if plan.status == "clarify":
            self.telegram_service.send_message("Komutu net anlayamadim. Lutfen daha acik yazar misin?")
        return plan
