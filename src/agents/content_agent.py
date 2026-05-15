from __future__ import annotations

import logging

from database import is_script_used_or_similar
from src.domain.feedback import FeedbackAction
from src.services.content_service import GeminiContentService
from src.services.script_quality_service import ScriptQualityService

logger = logging.getLogger(__name__)


class ContentAgent:
    def __init__(self, content_service: GeminiContentService, quality_service: ScriptQualityService | None = None):
        self.content_service = content_service
        self.quality_service = quality_service or ScriptQualityService()

    def generate_script(self, max_attempts: int = 4) -> dict:
        last_valid_script = None
        last_reasons = []
        for attempt in range(max_attempts):
            candidates = self._generate_candidates()
            result = self.quality_service.select_best(candidates)
            script_data = result.script
            last_reasons = result.reasons
            report = result.report or script_data.get("quality_report") or {}
            logger.info(
                "Selected script candidate score=%s grade=%s valid=%s hook=%s",
                report.get("score", result.score),
                report.get("grade"),
                result.valid,
                script_data.get("hook"),
            )
            if not result.valid:
                logger.info(
                    "Script quality gate failed; retrying %s/%s: %s",
                    attempt + 1,
                    max_attempts,
                    "; ".join(result.reasons),
                )
                continue
            last_valid_script = script_data
            if not is_script_used_or_similar(script_data):
                return script_data
            logger.info("Script is too similar to approved history; retrying %s/%s", attempt + 1, max_attempts)
        if last_valid_script:
            logger.warning("Using a valid script after retries, but it may be similar to approved history")
            return last_valid_script
        raise RuntimeError("Could not generate a script that passed the viral quality gate: " + "; ".join(last_reasons))

    def edit_script(self, script_data: dict, actions: list[FeedbackAction]) -> dict:
        return self.quality_service.normalize_script(self.content_service.edit_script(script_data, actions))

    def _generate_candidates(self) -> list[dict]:
        if hasattr(self.content_service, "generate_motivation_candidates"):
            return self.content_service.generate_motivation_candidates(count=5)
        return [self.content_service.generate_motivation_quote()]
