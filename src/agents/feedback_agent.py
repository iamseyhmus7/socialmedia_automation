from __future__ import annotations

from src.domain.feedback import FeedbackPlan
from src.services.gemini_feedback_analyzer import GeminiFeedbackAnalyzer
from src.services.telegram_service import TelegramService


class FeedbackAgent:
    def __init__(self, telegram_service: TelegramService, analyzer: GeminiFeedbackAnalyzer):
        self.telegram_service = telegram_service
        self.analyzer = analyzer

    def send_review_video(self, video_path: str, caption: str) -> None:
        self.telegram_service.send_video(video_path, caption=caption)

    def wait_for_feedback(self, video_count: int, timeout_minutes: int = 15) -> FeedbackPlan:
        message = self.telegram_service.wait_for_message(timeout_minutes=timeout_minutes)
        if message is None:
            return FeedbackPlan(status="timeout", actions=[], raw_message=None)
        plan = self.analyzer.analyze(message, video_count=video_count)
        if plan.status == "clarify":
            self.telegram_service.send_message("Komutu net anlayamadim. Lutfen daha acik yazar misin?")
        return plan
