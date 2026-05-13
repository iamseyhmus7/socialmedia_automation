from __future__ import annotations

from dataclasses import dataclass
from typing import Any


WEAK_VISUAL_QUERY_MAP = {
    "man": "man close up face under pressure cinematic portrait",
    "person": "person close up face under pressure cinematic portrait",
    "human": "human face close up eye contact under pressure cinematic portrait",
    "shadow": "person alone in dark room dramatic shadow close up",
    "darkness": "person alone in dark room dramatic shadow close up",
    "dark": "person alone in dark room dramatic shadow close up",
    "mirror": "person staring into mirror tense face close up",
    "intense": "exhausted athlete close up sweat breathing under pressure",
    "pressure": "stressed person under pressure close up eye contact",
    "discipline": "athlete training alone dark gym discipline close up",
    "comfort": "person alone in dark room resisting phone procrastination",
    "excuses": "person sitting alone dark room procrastination regret",
    "fear": "anxious person close up eye contact dark cinematic",
}


@dataclass(frozen=True)
class MediaAsset:
    id: str
    url: str
    path: str | None = None
    kind: str = "video"


@dataclass(frozen=True)
class RenderJob:
    video_paths: list[str]
    audio_path: str
    music_path: str | None
    output_filename: str
    music_volume: float = 1.00


def concrete_visual_query(query: Any) -> str:
    normalized = " ".join(str(query or "").lower().replace(",", " ").split())
    if not normalized:
        return "person alone under pressure close up eye contact dark cinematic"

    words = normalized.split()
    if len(words) <= 2:
        return WEAK_VISUAL_QUERY_MAP.get(normalized, f"{normalized} person close up under pressure")

    replacements = [
        scene
        for word, scene in WEAK_VISUAL_QUERY_MAP.items()
        if word in words and len(words) <= 4
    ]
    if replacements:
        return " ".join(replacements[:2])
    return normalized


def dedupe_queries(queries: list[str]) -> list[str]:
    deduped = []
    seen = set()
    for query in queries:
        normalized = " ".join(str(query or "").split())
        key = normalized.lower()
        if normalized and key not in seen:
            deduped.append(normalized)
            seen.add(key)
    return deduped
