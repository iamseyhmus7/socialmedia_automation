from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.render_service import RenderService


class RenderAgent:
    def __init__(self, render_service: "RenderService"):
        self.render_service = render_service

    async def render(
        self,
        video_paths: list[str],
        script_text: str,
        music_path: str | None,
        output_filename: str,
        voice_filename: str,
        highlighted_words: list[str],
        music_volume: float,
    ) -> tuple[str | None, str | None]:
        audio_path = await self.render_service.generate_voiceover(script_text, voice_filename, highlighted_words)
        if not audio_path:
            return None, None
        final_video_path = await asyncio.to_thread(
            self.render_service.create_video,
            video_paths,
            audio_path,
            music_path,
            script_text,
            output_filename,
            highlighted_words,
            music_volume=music_volume,
        )
        return audio_path, final_video_path

    async def render_from_brief(self, render_brief: dict) -> tuple[str | None, str | None]:
        script = dict(render_brief.get("script") or {})
        voice_plan = dict(render_brief.get("voice_plan") or {})
        music_asset = dict(render_brief.get("music_asset") or {})
        output = dict(render_brief.get("output") or {})
        video_assets = list(render_brief.get("video_assets") or [])

        return await self.render(
            [str(asset.get("path")) for asset in video_assets if asset.get("path")],
            str(script.get("full_text") or ""),
            music_asset.get("path"),
            str(output.get("filename") or "motivation.mp4"),
            str(output.get("voice_filename") or "voice.mp3"),
            list(voice_plan.get("highlighted_words") or []),
            float(music_asset.get("volume_hint", render_brief.get("music_volume", 1.00))),
        )
