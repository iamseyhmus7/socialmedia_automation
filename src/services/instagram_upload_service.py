from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from src.services.video_metadata_service import build_upload_metadata


INSTAGRAM_CAPTION_LIMIT = 2200
DEFAULT_GRAPH_API_VERSION = "v24.0"


@dataclass(frozen=True)
class InstagramUploadResult:
    media_id: str
    instagram_url: str | None = None


@dataclass(frozen=True)
class InstagramVideoMetadata:
    caption: str
    share_to_feed: bool


class InstagramUploadService:
    def __init__(
        self,
        access_token: str | None,
        instagram_user_id: str | None,
        graph_api_version: str = DEFAULT_GRAPH_API_VERSION,
        share_to_feed: bool = True,
        session: Any | None = None,
        poll_interval_seconds: float = 5.0,
        poll_attempts: int = 24,
    ):
        self.access_token = access_token
        self.instagram_user_id = instagram_user_id
        self.graph_api_version = graph_api_version or DEFAULT_GRAPH_API_VERSION
        self.share_to_feed = share_to_feed
        self.session = session
        self.poll_interval_seconds = poll_interval_seconds
        self.poll_attempts = poll_attempts

    def is_configured(self) -> bool:
        return bool(self.access_token and self.instagram_user_id)

    def upload_reel(
        self,
        video_path: str,
        script_data: dict[str, Any] | None = None,
        caption: str | None = None,
        share_to_feed: bool | None = None,
    ) -> InstagramUploadResult:
        if not self.is_configured():
            raise RuntimeError("Instagram access token or user id is not configured.")
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file was not found: {video_path}")

        metadata = self.build_metadata(script_data, caption=caption, share_to_feed=share_to_feed)
        container = self._create_reel_container(metadata)
        container_id = str(container.get("id") or "")
        upload_uri = container.get("uri")
        if not container_id or not upload_uri:
            raise RuntimeError(f"Instagram container creation did not return id and uri: {container}")

        self._upload_video_file(str(upload_uri), video_path)
        self._wait_until_container_ready(container_id)
        publish_response = self._publish_container(container_id)
        media_id = str(publish_response.get("id") or "")
        if not media_id:
            raise RuntimeError(f"Instagram publish finished without a media id: {publish_response}")

        return InstagramUploadResult(media_id=media_id, instagram_url=self._fetch_permalink(media_id))

    def build_metadata(
        self,
        script_data: dict[str, Any] | None = None,
        caption: str | None = None,
        share_to_feed: bool | None = None,
    ) -> InstagramVideoMetadata:
        upload_metadata = build_upload_metadata(script_data)
        resolved_caption = caption if caption is not None else upload_metadata["description"]
        return InstagramVideoMetadata(
            caption=self._trim_caption(resolved_caption),
            share_to_feed=self.share_to_feed if share_to_feed is None else share_to_feed,
        )

    def _create_reel_container(self, metadata: InstagramVideoMetadata) -> dict[str, Any]:
        return self._post_graph(
            f"{self.instagram_user_id}/media",
            data={
                "media_type": "REELS",
                "upload_type": "resumable",
                "caption": metadata.caption,
                "share_to_feed": str(metadata.share_to_feed).lower(),
                "access_token": self.access_token,
            },
        )

    def _upload_video_file(self, upload_uri: str, video_path: str) -> None:
        file_size = os.path.getsize(video_path)
        with open(video_path, "rb") as video_file:
            response = self._session().post(
                upload_uri,
                headers={
                    "Authorization": f"OAuth {self.access_token}",
                    "offset": "0",
                    "file_size": str(file_size),
                },
                data=video_file,
                timeout=300,
            )
        payload = self._json_response(response)
        if payload.get("success") is not True:
            raise RuntimeError(f"Instagram video upload failed: {payload}")

    def _wait_until_container_ready(self, container_id: str) -> None:
        for _attempt in range(self.poll_attempts):
            status = self._get_graph(container_id, params={"fields": "status_code,status"})
            status_code = str(status.get("status_code") or "").upper()
            if status_code in {"FINISHED", "PUBLISHED"}:
                return
            if status_code in {"ERROR", "EXPIRED"}:
                raise RuntimeError(f"Instagram container processing failed: {status}")
            if self.poll_interval_seconds:
                time.sleep(self.poll_interval_seconds)

        raise TimeoutError(f"Instagram container was not ready after {self.poll_attempts} checks: {container_id}")

    def _publish_container(self, container_id: str) -> dict[str, Any]:
        return self._post_graph(
            f"{self.instagram_user_id}/media_publish",
            data={"creation_id": container_id, "access_token": self.access_token},
        )

    def _fetch_permalink(self, media_id: str) -> str | None:
        try:
            response = self._get_graph(media_id, params={"fields": "permalink"})
        except Exception:
            return None
        permalink = response.get("permalink")
        return str(permalink) if permalink else None

    def _post_graph(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        response = self._session().post(self._graph_url(path), data=data, timeout=60)
        return self._json_response(response)

    def _get_graph(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query = {"access_token": self.access_token}
        query.update(params or {})
        response = self._session().get(self._graph_url(path), params=query, timeout=60)
        return self._json_response(response)

    def _session(self):
        if self.session is None:
            try:
                import requests
            except ImportError as exc:
                raise RuntimeError("requests paketi kurulu degil. `pip install -r requirements.txt` calistirin.") from exc
            self.session = requests.Session()
        return self.session

    def _graph_url(self, path: str) -> str:
        clean_path = str(path).lstrip("/")
        return f"https://graph.facebook.com/{self.graph_api_version}/{clean_path}"

    def _json_response(self, response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"Instagram API returned a non-JSON response: {response.text}") from exc

        if getattr(response, "ok", False):
            return payload

        error = payload.get("error") if isinstance(payload, dict) else None
        message = error.get("message") if isinstance(error, dict) else payload
        raise RuntimeError(f"Instagram API request failed: {message}")

    def _trim_caption(self, value: str) -> str:
        value = str(value or "").strip()
        if len(value) <= INSTAGRAM_CAPTION_LIMIT:
            return value
        return value[: INSTAGRAM_CAPTION_LIMIT - 3].rstrip() + "..."
