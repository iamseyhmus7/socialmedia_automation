from __future__ import annotations

import logging
import re

from database import find_similar_script_matches
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
            angle_brief = self._select_distinct_angle(avoid_scripts)
            candidates = self._generate_candidates(avoid_scripts, angle_brief)
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
            similar_match = self._script_duplicate_match(script_data)
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

    def _generate_candidates(self, avoid_scripts: list[dict] | None = None, angle_brief: dict | None = None) -> list[dict]:
        if hasattr(self.content_service, "generate_motivation_candidates"):
            try:
                return self.content_service.generate_motivation_candidates(
                    count=5,
                    avoid_scripts=avoid_scripts or [],
                    angle_brief=angle_brief,
                )
            except TypeError:
                try:
                    return self.content_service.generate_motivation_candidates(count=5, avoid_scripts=avoid_scripts or [])
                except TypeError:
                    return self.content_service.generate_motivation_candidates(count=5)
        return [self.content_service.generate_motivation_quote()]

    def _select_distinct_angle(self, avoid_scripts: list[dict]) -> dict | None:
        if not hasattr(self.content_service, "generate_motivation_angle_candidates"):
            return None
        try:
            angle_candidates = self.content_service.generate_motivation_angle_candidates(
                count=6,
                avoid_scripts=avoid_scripts or [],
            )
        except TypeError:
            angle_candidates = self.content_service.generate_motivation_angle_candidates(count=6)
        except Exception as exc:
            logger.warning("Angle prefilter skipped: %s", exc)
            return None

        if not angle_candidates:
            return None

        ranked_angles = []
        for angle in angle_candidates:
            angle_script = self._angle_similarity_payload(angle)
            matches = find_similar_script_matches(angle_script, limit=5)
            ranked = self._rank_angle(angle, matches)
            ranked_angles.append(ranked)
            logger.info(
                "Angle rank candidate name=%s top1=%.3f top3_avg=%.3f top5_avg=%.3f novelty=%.3f",
                angle.get("angle_name"),
                ranked["top1_similarity"],
                ranked["top3_average_similarity"],
                ranked["top5_average_similarity"],
                ranked["novelty_score"],
            )

        selected = max(ranked_angles, key=lambda item: item["novelty_score"]) if ranked_angles else None
        if not selected:
            return None
        selected_angle = selected["angle"]
        if selected["top1_similarity"] < 0.80:
            logger.info(
                "Selected distinct angle=%s audience=%s premise=%s top1=%.3f novelty=%.3f",
                selected_angle.get("angle_name"),
                selected_angle.get("audience"),
                selected_angle.get("psychological_charge") or selected_angle.get("psychological_premise"),
                selected["top1_similarity"],
                selected["novelty_score"],
            )
            return selected_angle
        logger.info(
            "All angle candidates looked familiar; using ranked angle=%s top1=%.3f top3_avg=%.3f top5_avg=%.3f novelty=%.3f",
            selected_angle.get("angle_name"),
            selected["top1_similarity"],
            selected["top3_average_similarity"],
            selected["top5_average_similarity"],
            selected["novelty_score"],
        )
        return selected_angle

    def _rank_angle(self, angle: dict, matches: list[dict]) -> dict:
        similarities = [float(match.get("similarity") or 0.0) for match in matches[:5]]
        top1 = similarities[0] if similarities else 0.0
        top3 = self._average(similarities[:3])
        top5 = self._average(similarities[:5])
        duplicate_pressure = (top1 * 0.55) + (top3 * 0.30) + (top5 * 0.15)
        return {
            "angle": angle,
            "matches": matches,
            "top1_similarity": top1,
            "top3_average_similarity": top3,
            "top5_average_similarity": top5,
            "novelty_score": round(max(0.0, 1.0 - duplicate_pressure), 3),
        }

    def _average(self, values: list[float]) -> float:
        if not values:
            return 0.0
        return round(sum(values) / len(values), 3)

    def _script_duplicate_match(self, script_data: dict) -> dict | None:
        matches = find_similar_script_matches(script_data, limit=5)
        if not matches:
            return None

        top_match = matches[0]
        similarity = float(top_match.get("similarity") or 0.0)
        if similarity >= 0.90:
            logger.info(
                "Script hard duplicate detected similarity=%.3f hook=%s",
                similarity,
                top_match.get("hook"),
            )
            return top_match
        if similarity < 0.84:
            logger.info("Script semantic similarity accepted top1=%.3f below gray zone", similarity)
            return None

        if self._same_hook_family(script_data, top_match) or self._meaningful_overlap(script_data, top_match) >= 0.35:
            logger.info(
                "Script gray-zone duplicate detected similarity=%.3f overlap=%.3f hook=%s",
                similarity,
                self._meaningful_overlap(script_data, top_match),
                top_match.get("hook"),
            )
            return top_match

        logger.info(
            "Script gray-zone similarity accepted top1=%.3f hook=%s matched_hook=%s",
            similarity,
            script_data.get("hook"),
            top_match.get("hook"),
        )
        return None

    def _same_hook_family(self, script_data: dict, match: dict) -> bool:
        return self._hook_family(script_data.get("hook")) == self._hook_family(match.get("hook"))

    def _hook_family(self, hook: str | None) -> str:
        normalized = self._normalize_text(hook)
        for prefix in [
            "you are",
            "you re",
            "your",
            "you dont",
            "you don t",
            "you cant",
            "you can t",
            "nobody",
            "stop",
            "the",
            "that",
        ]:
            if normalized.startswith(prefix + " ") or normalized == prefix:
                return prefix
        words = normalized.split()
        return " ".join(words[:2])

    def _meaningful_overlap(self, script_data: dict, match: dict) -> float:
        current_terms = self._meaningful_terms(self._script_compare_text(script_data))
        matched_terms = self._meaningful_terms(self._script_compare_text(match.get("script_data") or match))
        if not current_terms or not matched_terms:
            return 0.0
        return len(current_terms & matched_terms) / max(len(current_terms), 1)

    def _script_compare_text(self, script_data: dict) -> str:
        script_section = dict(script_data.get("script") or {})
        return " ".join(
            str(value or "")
            for value in [
                script_section.get("hook") or script_data.get("hook"),
                script_section.get("body") or script_data.get("body"),
                script_section.get("outro") or script_data.get("outro"),
            ]
        )

    def _meaningful_terms(self, text: str) -> set[str]:
        stopwords = {
            "about",
            "after",
            "again",
            "before",
            "because",
            "being",
            "that",
            "the",
            "then",
            "this",
            "what",
            "when",
            "while",
            "with",
            "without",
            "your",
            "you",
            "youre",
        }
        return {word for word in self._normalize_text(text).split() if len(word) > 3 and word not in stopwords}

    def _normalize_text(self, text: str | None) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", str(text or "").lower())).strip()

    def _angle_similarity_payload(self, angle: dict) -> dict:
        visual_story = str(angle.get("visual_story") or angle.get("search_seed") or "")
        return {
            "hook": str(angle.get("hook_direction") or angle.get("angle_name") or ""),
            "body": " ".join(
                str(angle.get(key) or "")
                for key in [
                    "audience",
                    "psychological_charge",
                    "psychological_premise",
                    "behavior_evidence",
                    "conflict",
                    "consequence",
                    "action_trigger",
                    "fresh_metaphor",
                ]
            ).strip(),
            "outro": str(angle.get("angle_name") or angle.get("hook_direction") or ""),
            "media_plan": {
                "visual_direction": {
                    "overall_theme": visual_story,
                    "mood": "dark cinematic human struggle",
                },
                "video_scenes": [{"search_query": visual_story}] if visual_story else [],
            },
        }

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
