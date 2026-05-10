from __future__ import annotations

import asyncio
from typing import Any

from src.core.settings import get_settings
from src.services.youtube_upload_service import YouTubeUploadService


class UploaderService:
    def __init__(self, youtube_service: YouTubeUploadService | None = None):
        settings = get_settings()
        self.youtube_service = youtube_service or YouTubeUploadService(
            settings.youtube_client_secrets_path,
            settings.youtube_token_path,
            settings.youtube_default_privacy_status,
            settings.youtube_category_id,
        )

    async def login_manually(self, platform_url: str = "https://studio.youtube.com/") -> None:
        print("\n[LOGIN] Starting YouTube OAuth flow...")
        print("A Google OAuth browser window will open if a fresh token is needed.")
        await asyncio.to_thread(self.youtube_service.ensure_authenticated)
        print("[LOGIN] YouTube OAuth token is ready.")

    async def upload_to_all(self, video_path: str) -> None:
        print("\n[UPLOADER] Starting social upload flow...")
        await self.upload_to_youtube(video_path)
        print("[UPLOADER] Upload flow completed.")

    async def upload_to_youtube(
        self,
        video_path: str,
        title: str = "Motivasyon",
        description: str = "#motivation #shorts #stoicism",
        script_data: dict[str, Any] | None = None,
    ) -> None:
        print(f"  -> Uploading to YouTube via Data API: {video_path}")
        result = await asyncio.to_thread(
            self.youtube_service.upload_video,
            video_path,
            script_data,
            title,
            description,
        )
        print(f"[SUCCESS] YouTube upload completed: {result.youtube_url} ({result.privacy_status})")
