from __future__ import annotations

from typing import Any


def build_render_brief(state: dict[str, Any], output_filename: str, voice_filename: str) -> dict[str, Any]:
    script_data = state.get("script_data") or {}
    script_section = dict(script_data.get("script") or {})
    media_plan = dict(script_data.get("media_plan") or {})
    music_plan = dict(media_plan.get("music") or {})

    return {
        "script": _script_payload(state, script_data, script_section),
        "voice_plan": _voice_plan(state, script_data),
        "video_assets": _video_assets(state.get("video_paths", []), media_plan),
        "music_asset": {
            "path": state.get("music_path"),
            "volume_hint": state.get("music_volume", music_plan.get("volume_hint", 1.00)),
        },
        "render_settings": {
            "format": "short_vertical",
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "subtitle_style": "impact_word_by_word",
            "dark_overlay_opacity": 0.34,
            "opening_zoom": 0.16,
            "default_zoom": 0.075,
        },
        "output": {"filename": output_filename, "voice_filename": voice_filename},
    }


def _script_payload(state: dict[str, Any], script_data: dict[str, Any], script_section: dict[str, Any]) -> dict[str, str]:
    return {
        "full_text": state.get("script_text") or "",
        "hook": script_section.get("hook") or script_data.get("hook", ""),
        "body": script_section.get("body") or script_data.get("body", ""),
        "outro": script_section.get("outro") or script_data.get("outro", ""),
    }


def _voice_plan(state: dict[str, Any], script_data: dict[str, Any]) -> dict[str, Any]:
    return script_data.get("voice_plan") or {
        "highlighted_words": state.get("vurgulanacak_kelimeler", []),
        "tone": "intense",
        "pace": "fast_then_controlled",
    }


def _video_assets(video_paths: list[str], media_plan: dict[str, Any]) -> list[dict[str, Any]]:
    video_scenes = list(media_plan.get("video_scenes") or [])
    assets = []
    for index, path in enumerate(video_paths, start=1):
        scene = _scene_at(video_scenes, index)
        assets.append(
            {
                "scene_id": scene.get("scene_id", index),
                "beat": scene.get("beat", "body"),
                "path": path,
                "line_match": scene.get("line_match", ""),
                "pace": scene.get("pace", "controlled"),
                "emotion": scene.get("emotion", "intensity"),
            }
        )
    return assets


def _scene_at(video_scenes: list[Any], index: int) -> dict[str, Any]:
    scene_index = index - 1
    if scene_index < len(video_scenes) and isinstance(video_scenes[scene_index], dict):
        return video_scenes[scene_index]
    return {}
