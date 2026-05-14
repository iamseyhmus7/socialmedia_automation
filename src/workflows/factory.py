from __future__ import annotations

from typing import Awaitable, Callable

from langgraph.graph import END, StateGraph

from src.agents.content_agent import ContentAgent
from src.agents.feedback_agent import FeedbackAgent
from src.agents.media_agent import MediaAgent
from src.agents.render_agent import RenderAgent
from src.core.settings import Settings
from src.domain.state import WorkflowState
from src.services.content_service import GeminiContentService
from src.services.feedback_validator import FeedbackPlanValidator
from src.services.gemini_feedback_analyzer import GeminiFeedbackAnalyzer
from src.services.instagram_upload_service import InstagramUploadService
from src.services.music_service import FreesoundMusicService
from src.services.publish_schedule_service import PublishScheduleService
from src.services.render_service import RenderService
from src.services.telegram_service import TelegramService
from src.services.tiktok_upload_service import TikTokUploadService
from src.services.video_service import CoverrVideoService, MultiSourceVideoService, PexelsVideoService, PixabayVideoService
from src.services.youtube_upload_service import YouTubeUploadService
from src.workflows.nodes import VideoWorkflowNodes
from src.workflows.router import route_after_feedback


FeedbackMessageProvider = Callable[[int], Awaitable[str | None]]


class WorkflowFactory:
    def __init__(self, settings: Settings):
        self.settings = settings

    def create(self, feedback_message_provider: FeedbackMessageProvider | None = None):
        nodes = self._create_nodes(feedback_message_provider)
        workflow = StateGraph(WorkflowState)
        self._add_nodes(workflow, nodes)
        self._add_edges(workflow)
        return workflow.compile()

    def _create_nodes(self, feedback_message_provider: FeedbackMessageProvider | None) -> VideoWorkflowNodes:
        content_service = GeminiContentService(self.settings.gemini_api_key, self.settings.gemini_model)
        video_service = MultiSourceVideoService(
            PexelsVideoService(self.settings.pexels_api_key, self.settings.assets_dir),
            [
                PixabayVideoService(self.settings.pixabay_api_key, self.settings.assets_dir),
                CoverrVideoService(self.settings.coverr_api_key, self.settings.assets_dir),
            ],
        )
        music_service = FreesoundMusicService(self.settings.freesound_api_key, self.settings.assets_dir)
        publish_schedule_service = PublishScheduleService()
        render_service = RenderService(self.settings.assets_dir, self.settings.outputs_dir, self.settings.fps)
        telegram_service = TelegramService(self.settings.telegram_bot_token, self.settings.telegram_chat_id)
        analyzer = GeminiFeedbackAnalyzer(self.settings.gemini_api_key, self.settings.gemini_model, FeedbackPlanValidator())
        youtube_upload_service = YouTubeUploadService(
            self.settings.youtube_client_secrets_path,
            self.settings.youtube_token_path,
            self.settings.youtube_default_privacy_status,
            self.settings.youtube_category_id,
        )
        instagram_upload_service = InstagramUploadService(
            self.settings.instagram_access_token,
            self.settings.instagram_user_id,
            self.settings.instagram_graph_api_version,
            self.settings.instagram_share_to_feed,
        )
        tiktok_upload_service = TikTokUploadService(
            self.settings.tiktok_client_key,
            self.settings.tiktok_client_secret,
            self.settings.tiktok_redirect_uri,
            self.settings.tiktok_token_path,
            self.settings.tiktok_default_privacy_level,
            self.settings.tiktok_disable_comment,
            self.settings.tiktok_disable_duet,
            self.settings.tiktok_disable_stitch,
            self.settings.tiktok_is_aigc,
        )

        return VideoWorkflowNodes(
            content_agent=ContentAgent(content_service),
            media_agent=MediaAgent(video_service, music_service),
            render_agent=RenderAgent(render_service),
            feedback_agent=FeedbackAgent(telegram_service, analyzer, message_provider=feedback_message_provider),
            outputs_dir=self.settings.outputs_dir,
            youtube_upload_service=youtube_upload_service,
            instagram_upload_service=instagram_upload_service,
            tiktok_upload_service=tiktok_upload_service,
            publish_schedule_service=publish_schedule_service,
        )

    def _add_nodes(self, workflow: StateGraph, nodes: VideoWorkflowNodes) -> None:
        workflow.add_node("generate_initial_script", nodes.generate_initial_script)
        workflow.add_node("download_initial_videos", nodes.download_initial_videos)
        workflow.add_node("download_initial_music", nodes.download_initial_music)
        workflow.add_node("render_video", nodes.render_video)
        workflow.add_node("ask_for_approval", nodes.ask_for_approval)
        workflow.add_node("apply_feedback_actions", nodes.apply_feedback_actions)

    def _add_edges(self, workflow: StateGraph) -> None:
        workflow.set_entry_point("generate_initial_script")
        workflow.add_edge("generate_initial_script", "download_initial_videos")
        workflow.add_edge("download_initial_videos", "download_initial_music")
        workflow.add_edge("download_initial_music", "render_video")
        workflow.add_edge("render_video", "ask_for_approval")
        workflow.add_conditional_edges(
            "ask_for_approval",
            route_after_feedback,
            {
                "apply_feedback_actions": "apply_feedback_actions",
                "ask_for_approval": "ask_for_approval",
                "end": END,
            },
        )
        workflow.add_edge("apply_feedback_actions", "render_video")


def create_workflow(settings: Settings, feedback_message_provider: FeedbackMessageProvider | None = None):
    return WorkflowFactory(settings).create(feedback_message_provider)
