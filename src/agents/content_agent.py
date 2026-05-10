from __future__ import annotations

from src.domain.feedback import FeedbackAction
from src.services.content_service import GeminiContentService
from src.services.script_quality_service import ScriptQualityService
from database import is_script_used_or_similar


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
            if not result.valid:
                print(
                    f"  [CONTENT] Script quality gate failed; retrying ({attempt + 1}/{max_attempts}): "
                    + "; ".join(result.reasons),
                    flush=True,
                )
                continue
            last_valid_script = script_data
            if not is_script_used_or_similar(script_data):
                return script_data
            print(f"  [CONTENT] Script is too similar to approved history; retrying ({attempt + 1}/{max_attempts})", flush=True)
        if last_valid_script:
            print("  [CONTENT] Using a valid script after retries, but it may be similar to approved history.", flush=True)
            return last_valid_script
        raise RuntimeError("Could not generate a script that passed the viral quality gate: " + "; ".join(last_reasons))

    def edit_script(self, script_data: dict, actions: list[FeedbackAction]) -> dict:
        return self.quality_service.normalize_script(self.content_service.edit_script(script_data, actions))

    def _generate_candidates(self) -> list[dict]:
        if hasattr(self.content_service, "generate_motivation_candidates"):
            return self.content_service.generate_motivation_candidates(count=5)
        return [self.content_service.generate_motivation_quote()]
