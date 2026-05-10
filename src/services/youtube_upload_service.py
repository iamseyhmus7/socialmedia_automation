from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from src.services.video_metadata_service import build_upload_metadata


YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"


@dataclass(frozen=True)
class YouTubeUploadResult:
    video_id: str
    youtube_url: str
    privacy_status: str
    publish_at: str | None = None


@dataclass(frozen=True)
class YouTubeVideoMetadata:
    title: str
    description: str
    tags: list[str]
    category_id: str
    privacy_status: str
    publish_at: str | None = None


class YouTubeUploadService:
    def __init__(
        self,
        client_secrets_path: str,
        token_path: str,
        default_privacy_status: str = "public",
        category_id: str = "22",
    ):
        self.client_secrets_path = client_secrets_path
        self.token_path = token_path
        self.default_privacy_status = default_privacy_status or "public"
        self.category_id = category_id or "22"

    def ensure_authenticated(self) -> None:
        self._get_credentials()

    def upload_video(
        self,
        video_path: str,
        script_data: dict[str, Any] | None = None,
        title: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        privacy_status: str | None = None,
        publish_at: str | None = None,
    ) -> YouTubeUploadResult:
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file was not found: {video_path}")

        metadata = self.build_metadata(
            script_data=script_data,
            title=title,
            description=description,
            tags=tags,
            privacy_status=privacy_status,
            publish_at=publish_at,
        )
        youtube = self._build_client()
        media_body = self._build_media_upload(video_path)
        status = {
            "privacyStatus": metadata.privacy_status,
            "selfDeclaredMadeForKids": False,
        }
        if metadata.publish_at:
            status["publishAt"] = metadata.publish_at

        request = youtube.videos().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": metadata.title,
                    "description": metadata.description,
                    "tags": metadata.tags,
                    "categoryId": metadata.category_id,
                },
                "status": status,
            },
            media_body=media_body,
        )

        response = self._execute_resumable_upload(request)
        video_id = response.get("id")
        if not video_id:
            raise RuntimeError(f"YouTube upload finished without a video id: {response}")

        return YouTubeUploadResult(
            video_id=video_id,
            youtube_url=f"https://www.youtube.com/watch?v={video_id}",
            privacy_status=metadata.privacy_status,
            publish_at=metadata.publish_at,
        )

    def build_metadata(
        self,
        script_data: dict[str, Any] | None = None,
        title: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        privacy_status: str | None = None,
        publish_at: str | None = None,
    ) -> YouTubeVideoMetadata:
        script_data = script_data or {}
        upload_metadata = build_upload_metadata(script_data, title, description, tags)
        resolved_privacy = privacy_status or self.default_privacy_status
        if publish_at:
            resolved_privacy = "private"

        return YouTubeVideoMetadata(
            title=upload_metadata["title"],
            description=upload_metadata["description"],
            tags=upload_metadata["tags"],
            category_id=self.category_id,
            privacy_status=resolved_privacy,
            publish_at=publish_at,
        )

    def _build_client(self):
        try:
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError(
                "Google API paketleri kurulu degil. `pip install -r requirements.txt` calistirin."
            ) from exc

        return build("youtube", "v3", credentials=self._get_credentials())

    def _build_media_upload(self, video_path: str):
        try:
            from googleapiclient.http import MediaFileUpload
        except ImportError as exc:
            raise RuntimeError(
                "google-api-python-client kurulu degil. `pip install -r requirements.txt` calistirin."
            ) from exc

        return MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/*")

    def _get_credentials(self):
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError as exc:
            raise RuntimeError(
                "Google OAuth paketleri kurulu degil. `pip install -r requirements.txt` calistirin."
            ) from exc

        credentials = None
        if os.path.exists(self.token_path):
            credentials = Credentials.from_authorized_user_file(self.token_path, [YOUTUBE_UPLOAD_SCOPE])

        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())

        if not credentials or not credentials.valid:
            if not os.path.exists(self.client_secrets_path):
                raise FileNotFoundError(
                    "YouTube OAuth client secret bulunamadi: "
                    f"{self.client_secrets_path}. Google Cloud'dan Desktop OAuth JSON indirip bu path'e koyun."
                )
            flow = InstalledAppFlow.from_client_secrets_file(self.client_secrets_path, [YOUTUBE_UPLOAD_SCOPE])
            credentials = flow.run_local_server(port=0, prompt="consent")

        os.makedirs(os.path.dirname(self.token_path), exist_ok=True)
        with open(self.token_path, "w", encoding="utf-8") as token_file:
            token_file.write(credentials.to_json())
        return credentials

    def _execute_resumable_upload(self, request) -> dict[str, Any]:
        response = None
        while response is None:
            _status, response = request.next_chunk()
        return response
