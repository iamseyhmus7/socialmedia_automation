from __future__ import annotations

import logging

from database import find_similar_script_match
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
        avoid_scripts = []
        for attempt in range(max_attempts):
            candidates = self._generate_candidates(avoid_scripts)
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
            similar_match = find_similar_script_match(script_data)
            if not similar_match:
                return script_data
            avoid_scripts.append(self._avoid_entry(script_data, similar_match))
            logger.info(
                "Script is too similar to approved history; retrying %s/%s with %s avoid examples",
                attempt + 1,
                max_attempts,
                len(avoid_scripts),
            )
        if last_valid_script and avoid_scripts:
            raise RuntimeError(
                "Could not generate a script that is semantically distinct from approved history "
                f"after {max_attempts} attempts."
            )
        if last_valid_script:
            return last_valid_script
        raise RuntimeError("Could not generate a script that passed the viral quality gate: " + "; ".join(last_reasons))

    def edit_script(self, script_data: dict, actions: list[FeedbackAction]) -> dict:
        return self.quality_service.normalize_script(self.content_service.edit_script(script_data, actions))

    def _generate_candidates(self, avoid_scripts: list[dict] | None = None) -> list[dict]:
        if hasattr(self.content_service, "generate_motivation_candidates"):
            try:
                return self.content_service.generate_motivation_candidates(count=5, avoid_scripts=avoid_scripts or [])
            except TypeError:
                return self.content_service.generate_motivation_candidates(count=5)
        return [self.content_service.generate_motivation_quote()]

    def _avoid_entry(self, rejected_script: dict, similar_match: dict) -> dict:
        matched_script = dict(similar_match.get("script_data") or {})
        matched_section = dict(matched_script.get("script") or {})
        rejected_section = dict(rejected_script.get("script") or {})
        return {
            "similarity": round(float(similar_match.get("similarity", 0.0)), 3),
            "rejected_hook": rejected_section.get("hook") or rejected_script.get("hook", ""),
            "matched_hook": matched_section.get("hook") or similar_match.get("hook") or matched_script.get("hook", ""),
            "matched_body": matched_section.get("body") or matched_script.get("body", similar_match.get("body", "")),
            "matched_outro": matched_section.get("outro") or matched_script.get("outro", similar_match.get("outro", "")),
        }
