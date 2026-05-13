from __future__ import annotations

import json
import base64
import hashlib
import math
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from src.services.video_metadata_service import build_upload_metadata


TIKTOK_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
TIKTOK_CREATOR_INFO_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
TIKTOK_VIDEO_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
TIKTOK_STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
TIKTOK_CONTENT_POSTING_SCOPE = "video.publish"
TIKTOK_CAPTION_LIMIT = 2200
DEFAULT_CHUNK_SIZE = 64 * 1024 * 1024


@dataclass(frozen=True)
class TikTokUploadResult:
    publish_id: str
    status: str = "processing"
    tiktok_url: str | None = None
    publish_at: str | None = None


@dataclass(frozen=True)
class TikTokVideoMetadata:
    caption: str
    privacy_level: str
    disable_comment: bool
    disable_duet: bool
    disable_stitch: bool
    is_aigc: bool


class TikTokUploadService:
    def __init__(
        self,
        client_key: str | None,
        client_secret: str | None,
        redirect_uri: str,
        token_path: str,
        default_privacy_level: str = "SELF_ONLY",
        disable_comment: bool = False,
        disable_duet: bool = False,
        disable_stitch: bool = False,
        is_aigc: bool = True,
        session: Any | None = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ):
        self.client_key = client_key
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.token_path = token_path
        self.default_privacy_level = default_privacy_level or "SELF_ONLY"
        self.disable_comment = disable_comment
        self.disable_duet = disable_duet
        self.disable_stitch = disable_stitch
        self.is_aigc = is_aigc
        self.session = session
        self.chunk_size = chunk_size

    def is_configured(self) -> bool:
        return bool(self.client_key and self.client_secret and self.redirect_uri and self.token_path)

    def authorization_url(
        self,
        state: str | None = None,
        scopes: str | None = None,
        code_challenge: str | None = None,
    ) -> tuple[str, str]:
        if not self.client_key:
            raise RuntimeError("TIKTOK_CLIENT_KEY is not configured.")
        resolved_state = state or secrets.token_urlsafe(24)
        params = {
            "client_key": self.client_key,
            "scope": scopes or TIKTOK_CONTENT_POSTING_SCOPE,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "state": resolved_state,
        }
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        query = urlencode(params)
        return f"{TIKTOK_AUTH_URL}?{query}", resolved_state

    def exchange_code_for_token(self, code: str, code_verifier: str | None = None) -> dict[str, Any]:
        self._ensure_app_credentials()
        payload = self._post_form(
            TIKTOK_TOKEN_URL,
            {
                "client_key": self.client_key,
                "client_secret": self.client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": self.redirect_uri,
                "code_verifier": code_verifier,
            },
        )
        self._save_token(payload)
        return payload

    def refresh_access_token(self, refresh_token: str | None = None) -> dict[str, Any]:
        self._ensure_app_credentials()
        token = self._load_token()
        resolved_refresh_token = refresh_token or token.get("refresh_token")
        if not resolved_refresh_token:
            raise RuntimeError("TikTok refresh_token bulunamadi. Once tools\\tiktok_login.py calistirin.")
        payload = self._post_form(
            TIKTOK_TOKEN_URL,
            {
                "client_key": self.client_key,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": resolved_refresh_token,
            },
        )
        self._save_token({**token, **payload})
        return payload

    def ensure_authenticated(self) -> None:
        self._access_token()

    def upload_video(
        self,
        video_path: str,
        script_data: dict[str, Any] | None = None,
        title: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        privacy_level: str | None = None,
        publish_at: str | None = None,
    ) -> TikTokUploadResult:
        if not self.is_configured():
            raise RuntimeError("TikTok client key/secret, redirect uri or token path is not configured.")
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file was not found: {video_path}")

        metadata = self.build_metadata(script_data, title, description, tags, privacy_level)
        creator_info = self.query_creator_info()
        allowed_privacy = set(creator_info.get("privacy_level_options") or [])
        if allowed_privacy and metadata.privacy_level not in allowed_privacy:
            metadata = TikTokVideoMetadata(
                caption=metadata.caption,
                privacy_level=next(iter(allowed_privacy)),
                disable_comment=metadata.disable_comment,
                disable_duet=metadata.disable_duet,
                disable_stitch=metadata.disable_stitch,
                is_aigc=metadata.is_aigc,
            )

        init_response = self._init_video_upload(video_path, metadata)
        data = init_response.get("data") or {}
        publish_id = str(data.get("publish_id") or "")
        upload_url = data.get("upload_url")
        if not publish_id or not upload_url:
            raise RuntimeError(f"TikTok video init did not return publish_id and upload_url: {init_response}")

        self._upload_video_file(str(upload_url), video_path)
        return TikTokUploadResult(publish_id=publish_id, status="processing", publish_at=publish_at)

    def build_metadata(
        self,
        script_data: dict[str, Any] | None = None,
        title: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        privacy_level: str | None = None,
    ) -> TikTokVideoMetadata:
        upload_metadata = build_upload_metadata(script_data, title, description, tags)
        caption = self._build_caption(upload_metadata["title"], upload_metadata["description"], upload_metadata["tags"])
        return TikTokVideoMetadata(
            caption=caption,
            privacy_level=privacy_level or self.default_privacy_level,
            disable_comment=self.disable_comment,
            disable_duet=self.disable_duet,
            disable_stitch=self.disable_stitch,
            is_aigc=self.is_aigc,
        )

    def query_creator_info(self) -> dict[str, Any]:
        response = self._session().post(
            TIKTOK_CREATOR_INFO_URL,
            headers=self._auth_headers(),
            timeout=60,
        )
        payload = self._json_response(response)
        return payload.get("data") or {}

    def fetch_publish_status(self, publish_id: str) -> dict[str, Any]:
        response = self._session().post(
            TIKTOK_STATUS_URL,
            headers=self._auth_headers(),
            json={"publish_id": publish_id},
            timeout=60,
        )
        return self._json_response(response)

    def _init_video_upload(self, video_path: str, metadata: TikTokVideoMetadata) -> dict[str, Any]:
        video_size = os.path.getsize(video_path)
        chunk_size = min(self.chunk_size, video_size) if video_size else self.chunk_size
        total_chunk_count = max(1, math.ceil(video_size / chunk_size))
        response = self._session().post(
            TIKTOK_VIDEO_INIT_URL,
            headers=self._auth_headers(),
            json={
                "post_info": {
                    "title": metadata.caption,
                    "privacy_level": metadata.privacy_level,
                    "disable_duet": metadata.disable_duet,
                    "disable_comment": metadata.disable_comment,
                    "disable_stitch": metadata.disable_stitch,
                    "is_aigc": metadata.is_aigc,
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": video_size,
                    "chunk_size": chunk_size,
                    "total_chunk_count": total_chunk_count,
                },
            },
            timeout=60,
        )
        return self._json_response(response)

    def _upload_video_file(self, upload_url: str, video_path: str) -> None:
        file_size = os.path.getsize(video_path)
        chunk_size = min(self.chunk_size, file_size) if file_size else self.chunk_size
        with open(video_path, "rb") as video_file:
            start = 0
            while start < file_size:
                chunk = video_file.read(chunk_size)
                end = start + len(chunk) - 1
                response = self._session().put(
                    upload_url,
                    headers={
                        "Content-Type": "video/mp4",
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {start}-{end}/{file_size}",
                    },
                    data=chunk,
                    timeout=300,
                )
                self._raise_for_upload_response(response)
                start = end + 1

    def _access_token(self) -> str:
        token = self._load_token()
        access_token = token.get("access_token")
        expires_at = float(token.get("expires_at") or 0)
        if access_token and expires_at - 60 > time.time():
            return str(access_token)
        refreshed = self.refresh_access_token(token.get("refresh_token"))
        return str(refreshed.get("access_token") or self._load_token().get("access_token") or "")

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token()}",
            "Content-Type": "application/json; charset=UTF-8",
        }

    def _post_form(self, url: str, data: dict[str, Any]) -> dict[str, Any]:
        response = self._session().post(
            url,
            data={key: value for key, value in data.items() if value is not None},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=60,
        )
        return self._json_response(response)

    def _session(self):
        if self.session is None:
            try:
                import requests
            except ImportError as exc:
                raise RuntimeError("requests paketi kurulu degil. `pip install -r requirements.txt` calistirin.") from exc
            self.session = requests.Session()
        return self.session

    def _json_response(self, response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"TikTok API returned a non-JSON response: {response.text}") from exc

        error = payload.get("error") if isinstance(payload, dict) else None
        error_code = error.get("code") if isinstance(error, dict) else None
        if getattr(response, "ok", False) and error_code in {None, "ok"}:
            return payload

        message = error.get("message") if isinstance(error, dict) else payload
        raise RuntimeError(f"TikTok API request failed: {message}")

    def _raise_for_upload_response(self, response) -> None:
        if getattr(response, "ok", False):
            return
        raise RuntimeError(f"TikTok video upload failed: {getattr(response, 'text', '')}")

    def _load_token(self) -> dict[str, Any]:
        if not os.path.exists(self.token_path):
            raise FileNotFoundError(f"TikTok token bulunamadi: {self.token_path}. Once tools\\tiktok_login.py calistirin.")
        with open(self.token_path, "r", encoding="utf-8") as token_file:
            return json.load(token_file)

    def _save_token(self, payload: dict[str, Any]) -> None:
        token = dict(payload)
        if token.get("access_token") and token.get("expires_in"):
            token["expires_at"] = time.time() + int(token["expires_in"])
        os.makedirs(os.path.dirname(self.token_path), exist_ok=True)
        with open(self.token_path, "w", encoding="utf-8") as token_file:
            json.dump(token, token_file, ensure_ascii=False, indent=2)

    def _ensure_app_credentials(self) -> None:
        if not self.client_key or not self.client_secret:
            raise RuntimeError("TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET must be configured.")

    def build_code_verifier(self) -> str:
        return secrets.token_urlsafe(64)[:128]

    def build_code_challenge(self, code_verifier: str) -> str:
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    def _build_caption(self, title: str, description: str, tags: list[str]) -> str:
        hashtags = " ".join(f"#{tag.replace(' ', '')}" for tag in tags[:8])
        caption = "\n\n".join(part for part in [title, description, hashtags] if part)
        if len(caption) <= TIKTOK_CAPTION_LIMIT:
            return caption
        return caption[: TIKTOK_CAPTION_LIMIT - 3].rstrip() + "..."
