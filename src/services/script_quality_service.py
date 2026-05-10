from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


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


class ScriptQualityService:
    def normalize_script(self, script_data: dict[str, Any]) -> dict[str, Any]:
        script = dict(script_data)
        hook = str(script.get("hook") or script.get("shock_hook") or "").strip()
        body = str(script.get("body") or script.get("tension_body") or "").strip()
        outro = str(script.get("outro") or script.get("payoff_outro") or "").strip()
        loop_ending = str(script.get("loop_ending") or "").strip()

        script["hook"] = hook
        script["body"] = body
        script["outro"] = outro
        script["shock_hook"] = str(script.get("shock_hook") or hook).strip()
        script["tension_body"] = str(script.get("tension_body") or body).strip()
        script["payoff_outro"] = str(script.get("payoff_outro") or outro).strip()
        script["loop_ending"] = loop_ending or self._derive_loop_ending(hook, outro)
        script["style"] = str(script.get("style") or "aggressive_viral_motivation")

        highlighted = list(script.get("vurgulanacak_kelimeler") or [])
        if not highlighted:
            highlighted = self._default_highlights(script)
        script["vurgulanacak_kelimeler"] = highlighted[:4]

        if not script.get("hook_pexels_arama_terimi"):
            script["hook_pexels_arama_terimi"] = self._opening_visual_term(script)
        if not script.get("pexels_arama_temasi"):
            script["pexels_arama_temasi"] = "human discipline under pressure dark cinematic"
        if not script.get("pexels_anahtar_kelimeleri"):
            script["pexels_anahtar_kelimeleri"] = [
                "intense face close up eye contact",
                "athlete struggle alone dark gym",
                "disciplined person fast motion cinematic",
            ]
        if not script.get("freesound_arama_terimi"):
            script["freesound_arama_terimi"] = "dark cinematic motivational emotional build no vocals"
        if not script.get("youtube_title"):
            script["youtube_title"] = self._youtube_title(script)
        if not script.get("youtube_description"):
            script["youtube_description"] = self._youtube_description(script)
        if not script.get("youtube_tags"):
            script["youtube_tags"] = ["motivation", "shorts", "discipline", "mindset", "stoicism"]

        scores = self.score(script)
        script.update(scores)
        return script

    def select_best(self, candidates: list[dict[str, Any]]) -> ScriptQualityResult:
        normalized = [self.normalize_script(candidate) for candidate in candidates if isinstance(candidate, dict)]
        if not normalized:
            return ScriptQualityResult(script={}, valid=False, reasons=["No valid script candidates were returned."])

        ranked = sorted(normalized, key=lambda item: item.get("quality_score", 0), reverse=True)
        best = ranked[0]
        valid, reasons = self.validate(best)
        return ScriptQualityResult(script=best, valid=valid, reasons=reasons)

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

    def validate(self, script_data: dict[str, Any]) -> tuple[bool, list[str]]:
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
        if script_data.get("quality_score", 0) < 0.62:
            reasons.append("Quality score is below the render gate.")
        return not reasons, reasons

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

    def _words(self, text: str) -> list[str]:
        return re.findall(r"[A-Za-z']+", str(text or ""))

    def _normalize(self, text: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s']", " ", str(text or "").lower())).strip()
