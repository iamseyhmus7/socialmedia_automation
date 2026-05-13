from __future__ import annotations

import asyncio
import datetime
import inspect
import os
from typing import TYPE_CHECKING

from database import (
    get_youtube_metadata,
    get_youtube_publish_times,
    record_approved_state,
    record_tiktok_upload,
    record_youtube_upload,
    save_tiktok_metadata,
    save_youtube_metadata,
)
from src.domain.feedback import FeedbackAction
from src.domain.state import WorkflowState
from src.services.publish_schedule_service import PublishScheduleService
from src.services.render_brief_service import build_render_brief
from src.services.video_metadata_service import build_upload_metadata

if TYPE_CHECKING:
    from src.agents.content_agent import ContentAgent
    from src.agents.feedback_agent import FeedbackAgent
    from src.agents.media_agent import MediaAgent
    from src.agents.render_agent import RenderAgent
    from src.services.instagram_upload_service import InstagramUploadService
    from src.services.tiktok_upload_service import TikTokUploadService
    from src.services.youtube_upload_service import YouTubeUploadService


class VideoWorkflowNodes:
    def __init__(
        self,
        content_agent: "ContentAgent",
        media_agent: "MediaAgent",
        render_agent: "RenderAgent",
        feedback_agent: "FeedbackAgent",
        outputs_dir: str,
        youtube_upload_service: "YouTubeUploadService | None" = None,
        instagram_upload_service: "InstagramUploadService | None" = None,
        tiktok_upload_service: "TikTokUploadService | None" = None,
        publish_schedule_service: "PublishScheduleService | None" = None,
    ):
        self.content_agent = content_agent
        self.media_agent = media_agent
        self.render_agent = render_agent
        self.feedback_agent = feedback_agent
        self.outputs_dir = outputs_dir
        self.youtube_upload_service = youtube_upload_service
        self.instagram_upload_service = instagram_upload_service
        self.tiktok_upload_service = tiktok_upload_service
        self.publish_schedule_service = publish_schedule_service or PublishScheduleService()

    async def generate_initial_script(self, state: WorkflowState) -> dict:
        print("\n[NODE] Generating script...", flush=True)
        script_data = await asyncio.to_thread(self.content_agent.generate_script)
        return self._script_update(state, script_data)

    async def download_initial_videos(self, state: WorkflowState) -> dict:
        print("\n[NODE] Downloading initial videos...", flush=True)
        script_data = state["script_data"]
        video_paths = await asyncio.to_thread(self.media_agent.download_initial_videos, script_data)
        return {
            "media_brief": self.media_agent.media_brief(script_data),
            "video_paths": video_paths,
        }

    async def download_initial_music(self, state: WorkflowState) -> dict:
        print("\n[NODE] Downloading initial music...", flush=True)
        music_path, tried_ids = await asyncio.to_thread(
            self.media_agent.download_music,
            state["script_data"],
            state.get("tried_music_ids", []),
        )
        return {"music_path": music_path, "tried_music_ids": tried_ids}

    async def apply_feedback_actions(self, state: WorkflowState) -> dict:
        print("\n[NODE] Applying feedback actions...", flush=True)
        actions = state.get("pending_actions", [])
        updates = {}

        script_actions = [action for action in actions if action.type == "edit_script"]
        if script_actions:
            script_data = await asyncio.to_thread(self.content_agent.edit_script, state["script_data"], script_actions)
            updates.update(self._script_update(state, script_data))

        video_actions = [action for action in actions if action.type == "edit_video"]
        if video_actions:
            updates["video_paths"] = await asyncio.to_thread(
                self.media_agent.apply_video_actions,
                state.get("video_paths", []),
                video_actions,
            )

        music_actions = [action for action in actions if action.type == "retry_music"]
        if music_actions:
            music_path, tried_ids = await asyncio.to_thread(
                self.media_agent.download_music,
                updates.get("script_data") or state["script_data"],
                state.get("tried_music_ids", []),
            )
            updates["music_path"] = music_path
            updates["tried_music_ids"] = tried_ids

        render_actions = [action for action in actions if action.type == "retry_render"]
        if render_actions:
            updates["music_volume"] = self._apply_render_settings(state.get("music_volume", 1.00), render_actions)

        updates["pending_actions"] = []
        updates["status"] = "changes_applied"
        return updates

    async def render_video(self, state: WorkflowState) -> dict:
        print("\n[NODE] Rendering video...", flush=True)
        revision = int(state.get("revision", 0)) + 1
        date_folder = state.get("date_folder") or datetime.datetime.now().strftime("%Y-%m-%d")
        timestamp = state.get("timestamp") or datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = self._build_output_filename(date_folder, timestamp, revision)
        voice_filename = f"voice_{timestamp}_r{revision:02d}.mp3"

        render_brief = build_render_brief(state, output_filename, voice_filename)
        audio_path, final_video_path = await self.render_agent.render_from_brief(render_brief)
        self._remove_legacy_revision_outputs(date_folder, timestamp)
        if final_video_path:
            metadata = build_upload_metadata(state.get("script_data") or {})
            save_youtube_metadata(
                final_video_path,
                metadata["title"],
                metadata["description"],
                metadata["tags"],
            )
            save_tiktok_metadata(
                final_video_path,
                metadata["title"],
                metadata["description"],
                metadata["tags"],
            )
        return {
            "audio_path": audio_path,
            "final_video_path": final_video_path,
            "revision": revision,
            "timestamp": timestamp,
            "date_folder": date_folder,
            "render_brief": render_brief,
            "status": "rendered",
        }

    async def ask_for_approval(self, state: WorkflowState) -> dict:
        print("\n[NODE] Waiting for Telegram feedback...", flush=True)
        video_path = state["final_video_path"]
        file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
        caption = f"Video hazir ({file_size_mb:.1f} MB). Komutunuz?"
        await asyncio.to_thread(self.feedback_agent.send_review_video, video_path, caption=caption)
        plan = self.feedback_agent.wait_for_feedback(video_count=len(state.get("video_paths", [])), timeout_minutes=15)
        if inspect.isawaitable(plan):
            plan = await plan

        if plan.status == "approved":
            record_approved_state(state, niche="motivation")
            upload_update = await self._upload_approved_video(state)
            return {
                "status": "approved",
                "pending_actions": [],
                "user_message": plan.raw_message,
                **upload_update,
            }

        if plan.status == "timeout":
            return {
                "status": "timeout",
                "pending_actions": [],
                "user_message": plan.raw_message,
            }

        if plan.status == "cancelled":
            return {"status": "cancelled", "pending_actions": [], "user_message": plan.raw_message}

        if plan.status == "clarify":
            return {"status": "clarify", "pending_actions": [], "user_message": plan.raw_message}

        return {
            "status": "needs_changes",
            "pending_actions": list(plan.actions),
            "last_feedback_plan": {
                "status": plan.status,
                "actions": [action.__dict__ for action in plan.actions],
            },
            "user_message": plan.raw_message,
        }

    def _script_update(self, state: WorkflowState, script_data: dict) -> dict:
        script_section = dict(script_data.get("script") or {})
        script_text = "\n".join(
            part
            for part in [
                script_section.get("hook") or script_data.get("hook", ""),
                script_section.get("body") or script_data.get("body", ""),
                script_section.get("outro") or script_data.get("outro", ""),
            ]
            if part
        )
        return {
            "script_data": script_data,
            "script_text": script_text,
            "vurgulanacak_kelimeler": script_data.get("vurgulanacak_kelimeler", []),
            "timestamp": state.get("timestamp") or datetime.datetime.now().strftime("%Y%m%d_%H%M%S"),
            "date_folder": state.get("date_folder") or datetime.datetime.now().strftime("%Y-%m-%d"),
            "status": "script_ready",
        }

    def _build_output_filename(self, date_folder: str, timestamp: str, revision: int) -> str:
        return os.path.join(date_folder, f"motivation_{timestamp}.mp4")

    def _remove_legacy_revision_outputs(self, date_folder: str, timestamp: str) -> None:
        output_dir = os.path.join(self.outputs_dir, date_folder)
        if not os.path.isdir(output_dir):
            return

        pattern = f"motivation_{timestamp}_r"
        for file_name in os.listdir(output_dir):
            if file_name.startswith(pattern) and file_name.lower().endswith(".mp4"):
                try:
                    os.remove(os.path.join(output_dir, file_name))
                except OSError:
                    pass

    def _apply_render_settings(self, current_volume: float, actions: list[FeedbackAction]) -> float:
        volume = current_volume
        for action in actions:
            multiplier = action.params.get("volume_multiplier", 1.0)
            try:
                volume *= float(multiplier)
            except (TypeError, ValueError):
                continue
        return max(0.0, min(volume, 2.0))

    async def _upload_approved_video(self, state: WorkflowState) -> dict:
        try:
            publish_at = self.publish_schedule_service.next_publish_at(
                state.get("date_folder"),
                occupied_publish_times=get_youtube_publish_times(),
            )
        except Exception as exc:
            return {
                "upload_status": "failed",
                "upload_error": str(exc),
                "youtube_video_id": None,
                "youtube_url": None,
                "youtube_publish_at": None,
                "instagram_upload_status": "failed",
                "instagram_upload_error": str(exc),
                "instagram_media_id": None,
                "instagram_url": None,
                "tiktok_upload_status": "failed",
                "tiktok_upload_error": str(exc),
                "tiktok_publish_id": None,
                "tiktok_publish_at": None,
            }

        youtube_update, instagram_update, tiktok_update = await asyncio.gather(
            self._upload_approved_video_to_youtube(state, publish_at),
            self._upload_approved_video_to_instagram(state),
            self._schedule_approved_video_for_tiktok(state, publish_at),
        )
        return {**youtube_update, **instagram_update, **tiktok_update}

    async def _upload_approved_video_to_youtube(self, state: WorkflowState, publish_at: str | None = None) -> dict:
        if self.youtube_upload_service is None:
            return {"upload_status": "skipped", "upload_error": "YouTube upload service is not configured."}

        video_path = state.get("final_video_path")
        if not video_path:
            return {"upload_status": "failed", "upload_error": "No final video path is available for upload."}

        print("\n[NODE] Uploading approved video to YouTube...", flush=True)
        try:
            result = await asyncio.to_thread(
                self.youtube_upload_service.upload_video,
                video_path,
                state.get("script_data") or {},
                publish_at=publish_at,
            )
        except Exception as exc:
            print(f"  [YOUTUBE] Upload failed: {exc}", flush=True)
            return {
                "upload_status": "failed",
                "upload_error": str(exc),
                "youtube_video_id": None,
                "youtube_url": None,
                "youtube_publish_at": None,
            }

        if result.publish_at:
            local_publish_at = self.publish_schedule_service.format_local_datetime(result.publish_at)
            print(f"  [YOUTUBE] Scheduled: {result.youtube_url} (public at {local_publish_at})", flush=True)
        else:
            print(f"  [YOUTUBE] Uploaded: {result.youtube_url}", flush=True)
        record_youtube_upload(
            video_path,
            result.video_id,
            result.youtube_url,
            result.publish_at,
            "scheduled" if result.publish_at else "uploaded",
        )
        return {
            "upload_status": "uploaded",
            "upload_error": None,
            "youtube_video_id": result.video_id,
            "youtube_url": result.youtube_url,
            "youtube_publish_at": result.publish_at,
        }

    async def _upload_approved_video_to_instagram(self, state: WorkflowState) -> dict:
        instagram_upload_service = getattr(self, "instagram_upload_service", None)
        if instagram_upload_service is None:
            return {
                "instagram_upload_status": "skipped",
                "instagram_upload_error": "Instagram upload service is not configured.",
            }
        if not instagram_upload_service.is_configured():
            return {
                "instagram_upload_status": "skipped",
                "instagram_upload_error": "Instagram access token or user id is not configured.",
            }

        video_path = state.get("final_video_path")
        if not video_path:
            return {
                "instagram_upload_status": "failed",
                "instagram_upload_error": "No final video path is available for upload.",
                "instagram_media_id": None,
                "instagram_url": None,
            }

        print("\n[NODE] Uploading approved video to Instagram Reels...", flush=True)
        try:
            caption = self._instagram_caption_for_video(video_path, state)
            result = await asyncio.to_thread(
                instagram_upload_service.upload_reel,
                video_path,
                state.get("script_data") or {},
                caption=caption,
            )
        except Exception as exc:
            print(f"  [INSTAGRAM] Upload failed: {exc}", flush=True)
            return {
                "instagram_upload_status": "failed",
                "instagram_upload_error": str(exc),
                "instagram_media_id": None,
                "instagram_url": None,
            }

        if result.instagram_url:
            print(f"  [INSTAGRAM] Published: {result.instagram_url}", flush=True)
        else:
            print(f"  [INSTAGRAM] Published media id: {result.media_id}", flush=True)
        return {
            "instagram_upload_status": "uploaded",
            "instagram_upload_error": None,
            "instagram_media_id": result.media_id,
            "instagram_url": result.instagram_url,
        }

    def _instagram_caption_for_video(self, video_path: str, state: WorkflowState) -> str:
        youtube_metadata = get_youtube_metadata(video_path)
        if youtube_metadata and youtube_metadata.get("description"):
            return self.instagram_upload_service.build_metadata(caption=youtube_metadata["description"]).caption
        return self.instagram_upload_service.build_metadata(state.get("script_data") or {}).caption

    async def _schedule_approved_video_for_tiktok(self, state: WorkflowState, publish_at: str | None) -> dict:
        tiktok_upload_service = getattr(self, "tiktok_upload_service", None)
        if tiktok_upload_service is None:
            return {
                "tiktok_upload_status": "skipped",
                "tiktok_upload_error": "TikTok upload service is not configured.",
                "tiktok_publish_id": None,
                "tiktok_publish_at": None,
            }
        if not tiktok_upload_service.is_configured():
            return {
                "tiktok_upload_status": "skipped",
                "tiktok_upload_error": "TikTok client key/secret is not configured.",
                "tiktok_publish_id": None,
                "tiktok_publish_at": None,
            }

        video_path = state.get("final_video_path")
        if not video_path:
            return {
                "tiktok_upload_status": "failed",
                "tiktok_upload_error": "No final video path is available for upload.",
                "tiktok_publish_id": None,
                "tiktok_publish_at": None,
            }

        record_tiktok_upload(video_path, publish_at=publish_at, status="scheduled")
        local_publish_at = self.publish_schedule_service.format_local_datetime(publish_at) if publish_at else "now"
        print(
            f"  [TIKTOK] Queued locally for Direct Post at {local_publish_at}. "
            "It will not appear in TikTok Studio until the due publisher uploads it.",
            flush=True,
        )
        return {
            "tiktok_upload_status": "scheduled",
            "tiktok_upload_error": None,
            "tiktok_publish_id": None,
            "tiktok_publish_at": publish_at,
        }
