from __future__ import annotations

import os
from dataclasses import dataclass

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(path: str | None = None) -> None:
        env_path = path or os.path.join(os.getcwd(), ".env")
        if not os.path.exists(env_path):
            return
        with open(env_path, "r", encoding="utf-8") as env_file:
            for line in env_file:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


try:
    load_dotenv(ENV_PATH)
except TypeError:
    load_dotenv()


@dataclass(frozen=True)
class Settings:
    base_dir: str
    assets_dir: str
    outputs_dir: str
    database_url: str | None
    pexels_api_key: str | None
    pixabay_api_key: str | None
    coverr_api_key: str | None
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
    tiktok_client_key: str | None = None
    tiktok_client_secret: str | None = None
    tiktok_redirect_uri: str = "http://localhost:8080/tiktok/callback"
    tiktok_token_path: str = ""
    tiktok_default_privacy_level: str = "SELF_ONLY"
    tiktok_disable_comment: bool = False
    tiktok_disable_duet: bool = False
    tiktok_disable_stitch: bool = False
    tiktok_is_aigc: bool = True
    video_width: int = 1080
    video_height: int = 1920
    fps: int = 30
    gemini_model: str = "gemini-3-flash-preview"
    gemini_embedding_model: str = "gemini-embedding-001"
    script_embedding_dimensions: int = 768
    script_similarity_threshold: float = 0.80


def get_settings() -> Settings:
    base_dir = PROJECT_ROOT
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
    tiktok_token_path = _resolve_path(
        base_dir,
        os.getenv("TIKTOK_TOKEN_PATH", os.path.join("user_data", "tiktok_token.json")),
    )
    return Settings(
        base_dir=base_dir,
        assets_dir=os.path.join(base_dir, "assets"),
        outputs_dir=os.path.join(base_dir, "outputs"),
        database_url=os.getenv("DATABASE_URL"),
        pexels_api_key=os.getenv("PEXELS_API_KEY"),
        pixabay_api_key=os.getenv("PIXABAY_API_KEY"),
        coverr_api_key=os.getenv("COVERR_API_KEY"),
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
        tiktok_client_key=os.getenv("TIKTOK_CLIENT_KEY"),
        tiktok_client_secret=os.getenv("TIKTOK_CLIENT_SECRET"),
        tiktok_redirect_uri=os.getenv("TIKTOK_REDIRECT_URI", "http://localhost:8080/tiktok/callback"),
        tiktok_token_path=tiktok_token_path,
        tiktok_default_privacy_level=os.getenv("TIKTOK_DEFAULT_PRIVACY_LEVEL", "SELF_ONLY"),
        tiktok_disable_comment=_env_bool("TIKTOK_DISABLE_COMMENT", False),
        tiktok_disable_duet=_env_bool("TIKTOK_DISABLE_DUET", False),
        tiktok_disable_stitch=_env_bool("TIKTOK_DISABLE_STITCH", False),
        tiktok_is_aigc=_env_bool("TIKTOK_IS_AIGC", True),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3-flash-preview"),
        gemini_embedding_model=os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"),
        script_embedding_dimensions=_env_int("SCRIPT_EMBEDDING_DIMENSIONS", 768),
        script_similarity_threshold=_env_float("SCRIPT_SIMILARITY_THRESHOLD", 0.80),
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


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default
