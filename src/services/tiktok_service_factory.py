from __future__ import annotations

from src.core.settings import Settings
from src.services.tiktok_upload_service import TikTokUploadService


class TikTokUploadServiceFactory:
    def create(self, settings: Settings) -> TikTokUploadService:
        return TikTokUploadService(
            settings.tiktok_client_key,
            settings.tiktok_client_secret,
            settings.tiktok_redirect_uri,
            settings.tiktok_token_path,
            settings.tiktok_default_privacy_level,
            settings.tiktok_disable_comment,
            settings.tiktok_disable_duet,
            settings.tiktok_disable_stitch,
            settings.tiktok_is_aigc,
        )
