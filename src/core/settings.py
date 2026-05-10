from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> None:
        env_path = os.path.join(os.getcwd(), ".env")
        if not os.path.exists(env_path):
            return
        with open(env_path, "r", encoding="utf-8") as env_file:
            for line in env_file:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv()


@dataclass(frozen=True)
class Settings:
    base_dir: str
    assets_dir: str
    outputs_dir: str
    db_path: str
    pexels_api_key: str | None
    freesound_api_key: str | None
    gemini_api_key: str | None
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    youtube_client_secrets_path: str
    youtube_token_path: str
    youtube_uploads_dir: str
    youtube_default_privacy_status: str = "public"
    youtube_category_id: str = "22"
    instagram_access_token: str | None = None
    instagram_user_id: str | None = None
    instagram_graph_api_version: str = "v24.0"
    instagram_share_to_feed: bool = True
    video_width: int = 1080
    video_height: int = 1920
    fps: int = 30
    gemini_model: str = "gemini-3-flash-preview"


def get_settings() -> Settings:
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    youtube_client_secrets_path = _resolve_path(
        base_dir,
        os.getenv("YOUTUBE_CLIENT_SECRETS_PATH", os.path.join("user_data", "youtube_client_secret.json")),
    )
    youtube_token_path = _resolve_path(
        base_dir,
        os.getenv("YOUTUBE_TOKEN_PATH", os.path.join("user_data", "youtube_token.json")),
    )
    youtube_uploads_dir = _resolve_path(
        base_dir,
        os.getenv("YOUTUBE_UPLOADS_DIR", "outputs"),
    )
    return Settings(
        base_dir=base_dir,
        assets_dir=os.path.join(base_dir, "assets"),
        outputs_dir=os.path.join(base_dir, "outputs"),
        db_path=os.path.join(base_dir, "video_history.db"),
        pexels_api_key=os.getenv("PEXELS_API_KEY"),
        freesound_api_key=os.getenv("FREESOUND_API_KEY"),
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
        youtube_client_secrets_path=youtube_client_secrets_path,
        youtube_token_path=youtube_token_path,
        youtube_uploads_dir=youtube_uploads_dir,
        youtube_default_privacy_status=os.getenv("YOUTUBE_DEFAULT_PRIVACY_STATUS", "public"),
        youtube_category_id=os.getenv("YOUTUBE_CATEGORY_ID", "22"),
        instagram_access_token=os.getenv("INSTAGRAM_ACCESS_TOKEN"),
        instagram_user_id=os.getenv("INSTAGRAM_USER_ID"),
        instagram_graph_api_version=os.getenv("INSTAGRAM_GRAPH_API_VERSION", "v24.0"),
        instagram_share_to_feed=_env_bool("INSTAGRAM_SHARE_TO_FEED", True),
    )


def _resolve_path(base_dir: str, value: str) -> str:
    if os.path.isabs(value):
        return value
    return os.path.join(base_dir, value)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
