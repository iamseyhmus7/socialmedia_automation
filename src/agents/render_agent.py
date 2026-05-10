from __future__ import annotations

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
        final_video_path = self.render_service.create_video(
            video_paths,
            audio_path,
            music_path,
            script_text,
            output_filename,
            highlighted_words,
            music_volume=music_volume,
        )
        return audio_path, final_video_path
