from __future__ import annotations

from typing import Any

from src.domain.feedback import FeedbackAction, FeedbackPlan


class FeedbackPlanValidator:
    def __init__(self, min_confidence: float = 0.55):
        self.min_confidence = min_confidence

    def validate(self, raw: dict[str, Any], raw_message: str | None = None, video_count: int = 0) -> FeedbackPlan:
        actions_raw = raw.get("actions", [])
        if not isinstance(actions_raw, list) or not actions_raw:
            return FeedbackPlan.clarify(raw_message, "Gemini did not return any actionable feedback.")

        actions = []
        for item in actions_raw:
            if not isinstance(item, dict):
                return FeedbackPlan.clarify(raw_message, "Gemini returned an invalid action item.")
            action = FeedbackAction.from_dict(item)
            if action.confidence < self.min_confidence:
                return FeedbackPlan.clarify(raw_message, "Gemini confidence was too low.")
            actions.append(action)

        status = str(raw.get("status", "needs_changes")).strip().lower()
        return FeedbackPlan(status=status, actions=actions, raw_message=raw_message).normalized(video_count)

