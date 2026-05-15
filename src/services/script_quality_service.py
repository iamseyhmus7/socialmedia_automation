from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from src.domain.media import concrete_visual_query


CLICHE_PHRASES = {
    "believe in yourself",
    "never give up",
    "dream big",
    "work hard",
    "stay positive",
    "you can do anything",
    "follow your dreams",
    "success is a journey",
}

POWER_TERMS = {
    "excuse",
    "excuses",
    "wasting",
    "costing",
    "discipline",
    "comfort",
    "weak",
    "pressure",
    "silence",
    "alone",
    "quit",
    "choose",
    "decide",
    "truth",
    "fear",
    "pain",
}

CURIOSITY_TERMS = {
    "why",
    "secret",
    "truth",
    "nobody",
    "before",
    "still",
    "cost",
    "costing",
    "wrong",
    "lying",
}

VISUAL_TERMS = {
    "close",
    "face",
    "eye",
    "struggle",
    "isolation",
    "discipline",
    "dark",
    "cinematic",
    "motion",
    "portrait",
    "focus",
}

@dataclass(frozen=True)
class ScriptQualityResult:
    script: dict[str, Any]
    valid: bool
    reasons: list[str]
    score: float = 0.0
    report: dict[str, Any] = field(default_factory=dict)


class ScriptQualityService:
    def normalize_script(self, script_data: dict[str, Any]) -> dict[str, Any]:
        script = dict(script_data)
        script_section = dict(script.get("script") or {})
        voice_plan = dict(script.get("voice_plan") or {})
        media_plan = dict(script.get("media_plan") or {})
        publishing = dict(script.get("publishing") or {})

        hook = str(script_section.get("hook") or script.get("hook") or script.get("shock_hook") or "").strip()
        body = str(script_section.get("body") or script.get("body") or script.get("tension_body") or "").strip()
        outro = str(script_section.get("outro") or script.get("outro") or script.get("payoff_outro") or "").strip()
        loop_ending = str(script_section.get("loop_ending") or script.get("loop_ending") or "").strip()

        script["hook"] = hook
        script["body"] = body
        script["outro"] = outro
        script["shock_hook"] = str(script_section.get("shock_hook") or script.get("shock_hook") or hook).strip()
        script["tension_body"] = str(script_section.get("tension_body") or script.get("tension_body") or body).strip()
        script["payoff_outro"] = str(script_section.get("payoff_outro") or script.get("payoff_outro") or outro).strip()
        script["loop_ending"] = loop_ending or self._derive_loop_ending(hook, outro)
        script["style"] = str(script.get("style") or "aggressive_viral_motivation")

        highlighted = list(voice_plan.get("highlighted_words") or script.get("vurgulanacak_kelimeler") or [])
        if not highlighted:
            highlighted = self._default_highlights(script)
        script["vurgulanacak_kelimeler"] = highlighted[:4]

        visual_direction = dict(media_plan.get("visual_direction") or {})
        music_plan = dict(media_plan.get("music") or {})
        video_scene_plan = list(media_plan.get("video_scenes") or [])
        if not script.get("hook_pexels_arama_terimi"):
            first_scene = video_scene_plan[0] if video_scene_plan and isinstance(video_scene_plan[0], dict) else {}
            script["hook_pexels_arama_terimi"] = first_scene.get("search_query") or self._opening_visual_term(script)
        if not script.get("pexels_arama_temasi"):
            script["pexels_arama_temasi"] = (
                visual_direction.get("overall_theme")
                or visual_direction.get("mood")
                or "human discipline under pressure dark cinematic"
            )
        if not script.get("pexels_anahtar_kelimeleri"):
            scene_queries = [
                str(scene.get("search_query", ""))
                for scene in video_scene_plan
                if isinstance(scene, dict) and scene.get("search_query")
            ]
            script["pexels_anahtar_kelimeleri"] = [
                *scene_queries[:3],
                "intense face close up eye contact",
                "athlete struggle alone dark gym",
                "disciplined person fast motion cinematic",
            ][:5]
        if not script.get("video_sahneleri"):
            script["video_sahneleri"] = self._scene_queries_from_plan(video_scene_plan) or self._derive_video_scenes(script)
        script["hook_pexels_arama_terimi"] = concrete_visual_query(script.get("hook_pexels_arama_terimi"))
        script["pexels_arama_temasi"] = concrete_visual_query(script.get("pexels_arama_temasi"))
        script["pexels_anahtar_kelimeleri"] = [
            concrete_visual_query(query)
            for query in list(script.get("pexels_anahtar_kelimeleri") or [])
        ][:5]
        script["video_sahneleri"] = self._normalize_video_scenes(script.get("video_sahneleri"), script)
        if not script.get("freesound_arama_terimi"):
            script["freesound_arama_terimi"] = (
                music_plan.get("search_query") or "dark cinematic motivational emotional build no vocals"
            )
        if not script.get("youtube_title"):
            script["youtube_title"] = publishing.get("youtube_title") or self._youtube_title(script)
        if not script.get("youtube_description"):
            script["youtube_description"] = publishing.get("youtube_description") or self._youtube_description(script)
        if not script.get("youtube_tags"):
            script["youtube_tags"] = publishing.get("youtube_tags") or [
                "motivation",
                "shorts",
                "discipline",
                "mindset",
                "stoicism",
            ]

        script["script"] = {
            "shock_hook": script["shock_hook"],
            "tension_body": script["tension_body"],
            "payoff_outro": script["payoff_outro"],
            "loop_ending": script["loop_ending"],
            "hook": script["hook"],
            "body": script["body"],
            "outro": script["outro"],
        }
        script["voice_plan"] = {
            "highlighted_words": script["vurgulanacak_kelimeler"],
            "tone": str(voice_plan.get("tone") or "intense"),
            "pace": str(voice_plan.get("pace") or "fast_then_controlled"),
        }
        script["media_plan"] = self._normalized_media_plan(script, media_plan)
        script["publishing"] = {
            "youtube_title": script["youtube_title"],
            "youtube_description": script["youtube_description"],
            "youtube_tags": script["youtube_tags"],
        }

        scores = self.score(script)
        script.update(scores)
        valid, reasons = self.validate(script, include_score_gate=False)
        script["quality_report"] = self.quality_report(script, valid=valid, reasons=reasons)
        return script

    def select_best(self, candidates: list[dict[str, Any]]) -> ScriptQualityResult:
        normalized = [self.normalize_script(candidate) for candidate in candidates if isinstance(candidate, dict)]
        if not normalized:
            return ScriptQualityResult(
                script={},
                valid=False,
                reasons=["No valid script candidates were returned."],
                report={"grade": "F", "score": 0.0, "reasons": ["No valid script candidates were returned."]},
            )

        ranked = sorted(normalized, key=lambda item: item.get("quality_score", 0), reverse=True)
        best = ranked[0]
        valid, reasons = self.validate(best)
        report = self.quality_report(best, valid=valid, reasons=reasons)
        best["quality_report"] = report
        return ScriptQualityResult(
            script=best,
            valid=valid,
            reasons=reasons,
            score=float(best.get("quality_score", 0.0)),
            report=report,
        )

    def score(self, script_data: dict[str, Any]) -> dict[str, float]:
        hook = str(script_data.get("hook", ""))
        body = str(script_data.get("body", ""))
        outro = str(script_data.get("outro", ""))
        all_text = f"{hook} {body} {outro}"
        visual_text = " ".join(
            [
                str(script_data.get("hook_pexels_arama_terimi", "")),
                str(script_data.get("pexels_arama_temasi", "")),
                " ".join(script_data.get("pexels_anahtar_kelimeleri") or []),
            ]
        )

        hook_words = self._words(hook)
        all_words = self._words(all_text)
        hook_score = 0.0
        if 3 <= len(hook_words) <= 8:
            hook_score += 0.35
        if "you" in [word.lower() for word in hook_words]:
            hook_score += 0.20
        if any(word.lower() in POWER_TERMS for word in hook_words):
            hook_score += 0.25
        if any(word.lower() in CURIOSITY_TERMS for word in hook_words):
            hook_score += 0.20

        cliche_hits = self.find_cliches(all_text)
        cliche_score = max(0.0, 1.0 - (0.35 * len(cliche_hits)))
        retention_score = 0.25
        if 35 <= len(all_words) <= 55:
            retention_score += 0.25
        if self._has_tension(body):
            retention_score += 0.25
        if script_data.get("loop_ending"):
            retention_score += 0.15
        if "you" in [word.lower() for word in all_words]:
            retention_score += 0.10

        visual_score = min(1.0, sum(1 for term in VISUAL_TERMS if term in visual_text.lower()) / 6)
        loop_score = self._loop_score(hook, str(script_data.get("loop_ending", "")) or outro)
        quality_score = (
            min(hook_score, 1.0) * 0.30
            + retention_score * 0.25
            + cliche_score * 0.20
            + visual_score * 0.15
            + loop_score * 0.10
        )

        return {
            "hook_score": round(min(hook_score, 1.0), 3),
            "retention_score": round(min(retention_score, 1.0), 3),
            "cliche_score": round(cliche_score, 3),
            "visual_score": round(visual_score, 3),
            "loop_score": round(loop_score, 3),
            "quality_score": round(quality_score, 3),
        }

    def validate(self, script_data: dict[str, Any], include_score_gate: bool = True) -> tuple[bool, list[str]]:
        reasons = []
        hook_words = self._words(str(script_data.get("hook", "")))
        total_words = self._words(" ".join(str(script_data.get(key, "")) for key in ["hook", "body", "outro"]))
        cliches = self.find_cliches(" ".join(str(script_data.get(key, "")) for key in ["hook", "body", "outro"]))

        if not 3 <= len(hook_words) <= 8:
            reasons.append("Hook must be 3-8 words.")
        if not 35 <= len(total_words) <= 55:
            reasons.append("Script must be 35-55 words.")
        if cliches:
            reasons.append(f"Script contains cliche phrases: {', '.join(cliches)}.")
        if not script_data.get("loop_ending"):
            reasons.append("Loop ending is missing.")
        if not script_data.get("vurgulanacak_kelimeler"):
            reasons.append("Highlighted words are missing.")
        if len(script_data.get("video_sahneleri") or []) != 6:
            reasons.append("Six video scenes are required.")
        if include_score_gate and script_data.get("quality_score", 0) < 0.62:
            reasons.append("Quality score is below the render gate.")
        return not reasons, reasons

    def quality_report(self, script_data: dict[str, Any], valid: bool | None = None, reasons: list[str] | None = None) -> dict[str, Any]:
        if valid is None or reasons is None:
            valid, reasons = self.validate(script_data)

        score = float(script_data.get("quality_score", 0.0))
        components = {
            "hook": float(script_data.get("hook_score", 0.0)),
            "retention": float(script_data.get("retention_score", 0.0)),
            "cliche": float(script_data.get("cliche_score", 0.0)),
            "visual": float(script_data.get("visual_score", 0.0)),
            "loop": float(script_data.get("loop_score", 0.0)),
        }
        strengths = self._quality_strengths(components)
        risks = self._quality_risks(components, reasons)
        return {
            "score": round(score, 3),
            "grade": self._quality_grade(score, valid),
            "valid": valid,
            "components": components,
            "strengths": strengths,
            "risks": risks,
            "reasons": reasons,
            "word_count": len(self._words(" ".join(str(script_data.get(key, "")) for key in ["hook", "body", "outro"]))),
            "hook_word_count": len(self._words(str(script_data.get("hook", "")))),
            "scene_count": len(script_data.get("video_sahneleri") or []),
        }

    def find_cliches(self, text: str) -> list[str]:
        lowered = self._normalize(text)
        return sorted(phrase for phrase in CLICHE_PHRASES if phrase in lowered)

    def _derive_loop_ending(self, hook: str, outro: str) -> str:
        hook = hook.rstrip(".!?")
        if not hook:
            return outro.strip()
        return f"Remember that when {hook.lower()}."

    def _default_highlights(self, script_data: dict[str, Any]) -> list[str]:
        words = self._words(" ".join(str(script_data.get(key, "")) for key in ["hook", "body", "outro"]))
        chosen = []
        for word in words:
            clean = word.lower()
            if clean in POWER_TERMS and clean not in chosen:
                chosen.append(clean)
        return chosen or ["discipline", "choose"]

    def _opening_visual_term(self, script_data: dict[str, Any]) -> str:
        hook = str(script_data.get("hook", "")).strip()
        return f"{hook} intense human face close up eye contact struggle fast motion dark cinematic portrait"

    def _normalize_video_scenes(self, scenes: Any, script_data: dict[str, Any]) -> list[str]:
        normalized = []
        for scene in list(scenes or []):
            query_value = scene.get("search_query") if isinstance(scene, dict) else scene
            query = concrete_visual_query(query_value)
            if query and query not in normalized:
                normalized.append(query)

        for scene in self._derive_video_scenes(script_data):
            if len(normalized) >= 6:
                break
            query = concrete_visual_query(scene)
            if query not in normalized:
                normalized.append(query)
        return normalized[:6]

    def _derive_video_scenes(self, script_data: dict[str, Any]) -> list[str]:
        text = " ".join(str(script_data.get(key, "")) for key in ["hook", "body", "outro"]).lower()
        scenes = [
            self._opening_visual_term(script_data),
            str(script_data.get("pexels_arama_temasi") or "person alone under pressure close up eye contact"),
        ]
        if "water" in text or "drown" in text or "suffocat" in text:
            scenes.extend(
                [
                    "person underwater reaching toward surface",
                    "hand pressed against wet glass close up",
                ]
            )
        if "comfort" in text or "phone" in text or "scroll" in text:
            scenes.extend(
                [
                    "person alone in dark room resisting phone procrastination",
                    "stressed person sitting on bed in dark room close up",
                ]
            )
        if "mirror" in text:
            scenes.append("person staring into mirror tense face close up")
        if "office" in text or "work" in text:
            scenes.append("stressed office worker head in hands close up")
        if "discipline" in text or "train" in text or "gym" in text:
            scenes.append("athlete training alone dark gym discipline close up")
        scenes.extend(
            [
                "stressed person under pressure close up eye contact",
                "exhausted athlete close up sweat breathing under pressure",
                "person walking alone at night dark cinematic",
            ]
        )
        return scenes

    def _scene_queries_from_plan(self, scenes: list[Any]) -> list[str]:
        queries = []
        for scene in scenes:
            if isinstance(scene, dict):
                query = scene.get("search_query")
            else:
                query = scene
            if query:
                queries.append(str(query))
        return queries

    def _normalized_media_plan(self, script: dict[str, Any], media_plan: dict[str, Any]) -> dict[str, Any]:
        visual_direction = dict(media_plan.get("visual_direction") or {})
        visual_direction.setdefault("overall_theme", script["pexels_arama_temasi"])
        visual_direction.setdefault("mood", "dark cinematic human struggle")
        visual_direction.setdefault("color_style", "low key contrast, muted colors")
        visual_direction.setdefault("avoid", ["text overlays", "brands", "celebrities", "cartoons", "visual metaphors"])

        existing_scenes = list(media_plan.get("video_scenes") or [])
        normalized_scenes = []
        for index, query in enumerate(script["video_sahneleri"], start=1):
            source = existing_scenes[index - 1] if index - 1 < len(existing_scenes) and isinstance(existing_scenes[index - 1], dict) else {}
            normalized_scenes.append(
                {
                    "scene_id": int(source.get("scene_id") or index),
                    "beat": str(source.get("beat") or self._beat_for_scene(index)),
                    "line_match": str(source.get("line_match") or self._line_for_scene(script, index)),
                    "search_query": query,
                    "backup_queries": [
                        concrete_visual_query(item)
                        for item in list(source.get("backup_queries") or [])
                        if str(item).strip()
                    ][:3],
                    "emotion": str(source.get("emotion") or "intensity"),
                    "camera": str(source.get("camera") or "close up"),
                    "pace": str(source.get("pace") or ("fast" if index == 1 else "controlled")),
                }
            )

        music = dict(media_plan.get("music") or {})
        return {
            "visual_direction": visual_direction,
            "video_scenes": normalized_scenes,
            "music": {
                "search_query": script["freesound_arama_terimi"],
                "backup_queries": list(music.get("backup_queries") or [])[:3],
                "mood": str(music.get("mood") or "dark cinematic motivational emotional build"),
                "volume_hint": music.get("volume_hint", 0.55),
            },
        }

    def _beat_for_scene(self, index: int) -> str:
        if index == 1:
            return "hook"
        if index <= 4:
            return "body"
        if index == 5:
            return "outro"
        return "loop"

    def _line_for_scene(self, script: dict[str, Any], index: int) -> str:
        if index == 1:
            return str(script.get("hook") or "")
        if index <= 4:
            return str(script.get("body") or "")
        return str(script.get("outro") or script.get("loop_ending") or "")

    def _youtube_title(self, script_data: dict[str, Any]) -> str:
        title = str(script_data.get("hook") or "Daily Motivation").strip()
        return title[:100].rstrip()

    def _youtube_description(self, script_data: dict[str, Any]) -> str:
        hook = str(script_data.get("hook") or "").strip()
        description = "\n\n".join(
            part
            for part in [
                hook,
                "A short reminder for discipline, focus, and mental strength.",
                "#shorts #motivation #discipline #mindset #stoicism",
            ]
            if part
        )
        return description[:5000].rstrip()

    def _has_tension(self, text: str) -> bool:
        lowered = self._normalize(text)
        tension_words = {"but", "because", "while", "until", "pressure", "comfort", "excuse", "fear", "avoid", "delay"}
        return any(word in lowered.split() for word in tension_words)

    def _loop_score(self, hook: str, loop_ending: str) -> float:
        hook_words = {word.lower() for word in self._words(hook) if len(word) > 2}
        loop_words = {word.lower() for word in self._words(loop_ending) if len(word) > 2}
        if not hook_words or not loop_words:
            return 0.0
        return min(1.0, len(hook_words & loop_words) / 2)

    def _quality_grade(self, score: float, valid: bool) -> str:
        if not valid:
            return "F"
        if score >= 0.82:
            return "A"
        if score >= 0.72:
            return "B"
        if score >= 0.62:
            return "C"
        return "D"

    def _quality_strengths(self, components: dict[str, float]) -> list[str]:
        labels = {
            "hook": "Strong hook structure",
            "retention": "Good retention arc",
            "cliche": "Low cliche risk",
            "visual": "Concrete visual direction",
            "loop": "Loop ending ties back to hook",
        }
        return [labels[key] for key, value in components.items() if value >= 0.75]

    def _quality_risks(self, components: dict[str, float], reasons: list[str]) -> list[str]:
        risks = list(reasons)
        labels = {
            "hook": "Hook may be weak or incorrectly sized.",
            "retention": "Retention arc may lack tension or target word count.",
            "cliche": "Cliche language risk is high.",
            "visual": "Visual direction may be too abstract.",
            "loop": "Loop ending may not strongly reconnect to the hook.",
        }
        for key, value in components.items():
            if value < 0.55 and labels[key] not in risks:
                risks.append(labels[key])
        return risks

    def _words(self, text: str) -> list[str]:
        return re.findall(r"[A-Za-z']+", str(text or ""))

    def _normalize(self, text: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s']", " ", str(text or "").lower())).strip()
