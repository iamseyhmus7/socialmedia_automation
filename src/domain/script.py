from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Script:
    hook: str
    body: str
    outro: str
    shock_hook: str = ""
    tension_body: str = ""
    payoff_outro: str = ""
    loop_ending: str = ""
    style: str = "aggressive_viral_motivation"
    hook_pexels_search_term: str = ""
    pexels_theme: str = ""
    pexels_keywords: list[str] = field(default_factory=list)
    freesound_search_term: str = "epic motivational"
    highlighted_words: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Script":
        return cls(
            hook=str(data.get("hook", "")),
            body=str(data.get("body", "")),
            outro=str(data.get("outro", "")),
            shock_hook=str(data.get("shock_hook", data.get("hook", ""))),
            tension_body=str(data.get("tension_body", data.get("body", ""))),
            payoff_outro=str(data.get("payoff_outro", data.get("outro", ""))),
            loop_ending=str(data.get("loop_ending", "")),
            style=str(data.get("style", "aggressive_viral_motivation")),
            hook_pexels_search_term=str(data.get("hook_pexels_arama_terimi", "")),
            pexels_theme=str(data.get("pexels_arama_temasi", "")),
            pexels_keywords=list(data.get("pexels_anahtar_kelimeleri") or []),
            freesound_search_term=str(data.get("freesound_arama_terimi", "epic motivational")),
            highlighted_words=list(data.get("vurgulanacak_kelimeler") or []),
            raw=dict(data),
        )

    def to_text(self) -> str:
        return "\n".join(part for part in [self.hook, self.body, self.outro] if part)
