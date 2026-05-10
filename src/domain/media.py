from __future__ import annotations

from dataclasses import dataclass


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
    music_volume: float = 1.25
