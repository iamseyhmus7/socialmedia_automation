from __future__ import annotations

from typing import Any, Optional, TypedDict

from .feedback import FeedbackAction


class WorkflowState(TypedDict, total=False):
    script_data: Optional[dict[str, Any]]
    script_text: Optional[str]
    vurgulanacak_kelimeler: list[str]
    video_paths: list[str]
    audio_path: Optional[str]
    music_path: Optional[str]
    final_video_path: Optional[str]
    tried_music_ids: list[str]
    music_volume: float
    pending_actions: list[FeedbackAction]
    last_feedback_plan: Optional[dict[str, Any]]
    user_message: Optional[str]
    error: Optional[str]
    status: str
    timestamp: str
    date_folder: str
    revision: int
    youtube_video_id: Optional[str]
    youtube_url: Optional[str]
    youtube_publish_at: Optional[str]
    upload_status: Optional[str]
    upload_error: Optional[str]
    instagram_media_id: Optional[str]
    instagram_url: Optional[str]
    instagram_upload_status: Optional[str]
    instagram_upload_error: Optional[str]


def create_initial_state() -> WorkflowState:
    return {
        "script_data": None,
        "script_text": None,
        "vurgulanacak_kelimeler": [],
        "video_paths": [],
        "audio_path": None,
        "music_path": None,
        "final_video_path": None,
        "tried_music_ids": [],
        "music_volume": 1.25,
        "pending_actions": [],
        "last_feedback_plan": None,
        "user_message": None,
        "error": None,
        "status": "new",
        "timestamp": "",
        "date_folder": "",
        "revision": 0,
        "youtube_video_id": None,
        "youtube_url": None,
        "youtube_publish_at": None,
        "upload_status": None,
        "upload_error": None,
        "instagram_media_id": None,
        "instagram_url": None,
        "instagram_upload_status": None,
        "instagram_upload_error": None,
    }
