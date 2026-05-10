from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar


CHANGE_ACTION_TYPES = {"edit_script", "edit_video", "retry_music", "retry_render"}
TERMINAL_ACTION_TYPES = {"approve", "cancel", "clarify"}
SUPPORTED_ACTION_TYPES = CHANGE_ACTION_TYPES | TERMINAL_ACTION_TYPES
ACTION_PRIORITY = {
    "edit_script": 10,
    "edit_video": 20,
    "retry_music": 30,
    "retry_render": 40,
    "clarify": 90,
    "approve": 100,
    "cancel": 0,
}


@dataclass(frozen=True)
class FeedbackAction:
    type: str
    target: str = "all"
    instruction: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0

    allowed_types: ClassVar[set[str]] = SUPPORTED_ACTION_TYPES

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "FeedbackAction":
        action_type = str(raw.get("type", "clarify")).strip().lower()
        if action_type not in SUPPORTED_ACTION_TYPES:
            action_type = "clarify"

        params = raw.get("params")
        if not isinstance(params, dict):
            params = {}

        try:
            confidence = float(raw.get("confidence", 1.0))
        except (TypeError, ValueError):
            confidence = 0.0

        confidence = max(0.0, min(confidence, 1.0))
        return cls(
            type=action_type,
            target=str(raw.get("target", "all")).strip().lower() or "all",
            instruction=str(raw.get("instruction", "")).strip(),
            params=params,
            confidence=confidence,
        )

    def normalize_target(self, video_count: int = 0) -> "FeedbackAction":
        target = self.target.replace(" ", "_")
        aliases = {
            "intro": "intro",
            "giris": "intro",
            "giriş": "intro",
            "hook": "intro",
            "body": "body",
            "govde": "body",
            "gövde": "body",
            "outro": "outro",
            "son": "outro" if self.type == "edit_script" else "video_last",
            "all": "all",
            "tum": "all",
            "tüm": "all",
            "music": "music",
            "muzik": "music",
            "müzik": "music",
            "music_volume": "music_volume",
            "volume": "music_volume",
            "video_last": "video_last",
            "last_video": "video_last",
            "son_video": "video_last",
        }
        target = aliases.get(target, target)

        if target == "video_last" and video_count > 0:
            target = f"video_{video_count}"

        return FeedbackAction(
            type=self.type,
            target=target,
            instruction=self.instruction,
            params=dict(self.params),
            confidence=self.confidence,
        )

    @property
    def is_change(self) -> bool:
        return self.type in CHANGE_ACTION_TYPES


@dataclass(frozen=True)
class FeedbackPlan:
    status: str
    actions: list[FeedbackAction]
    raw_message: str | None = None

    @classmethod
    def clarify(cls, raw_message: str | None = None, reason: str = "") -> "FeedbackPlan":
        return cls(
            status="clarify",
            actions=[
                FeedbackAction(
                    type="clarify",
                    target="all",
                    instruction=reason or "Could not safely understand the feedback.",
                    confidence=1.0,
                )
            ],
            raw_message=raw_message,
        )

    @classmethod
    def approve(cls, raw_message: str | None = None) -> "FeedbackPlan":
        return cls(
            status="approved",
            actions=[FeedbackAction(type="approve", confidence=1.0)],
            raw_message=raw_message,
        )

    def normalized(self, video_count: int = 0) -> "FeedbackPlan":
        actions = [action.normalize_target(video_count) for action in self.actions]

        if any(action.type == "cancel" for action in actions):
            actions = [action for action in actions if action.type == "cancel"][:1]
            return FeedbackPlan(status="cancelled", actions=actions, raw_message=self.raw_message)

        change_actions = [action for action in actions if action.is_change]
        if change_actions:
            actions = sorted(change_actions, key=lambda action: ACTION_PRIORITY[action.type])
            return FeedbackPlan(status="needs_changes", actions=actions, raw_message=self.raw_message)

        clarify_actions = [action for action in actions if action.type == "clarify"]
        if clarify_actions:
            return FeedbackPlan(status="clarify", actions=clarify_actions[:1], raw_message=self.raw_message)

        return FeedbackPlan.approve(self.raw_message)

    @property
    def has_changes(self) -> bool:
        return any(action.is_change for action in self.actions)

