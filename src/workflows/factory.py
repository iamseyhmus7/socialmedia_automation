from __future__ import annotations

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
from src.services.video_service import PexelsVideoService
from src.services.youtube_upload_service import YouTubeUploadService
from src.workflows.nodes import VideoWorkflowNodes
from src.workflows.router import route_after_feedback


def create_workflow(settings: Settings):
    content_service = GeminiContentService(settings.gemini_api_key, settings.gemini_model)
    video_service = PexelsVideoService(settings.pexels_api_key, settings.assets_dir)
    music_service = FreesoundMusicService(settings.freesound_api_key, settings.assets_dir)
    publish_schedule_service = PublishScheduleService()
    render_service = RenderService(settings.assets_dir, settings.outputs_dir, settings.fps)
    telegram_service = TelegramService(settings.telegram_bot_token, settings.telegram_chat_id)
    analyzer = GeminiFeedbackAnalyzer(settings.gemini_api_key, settings.gemini_model, FeedbackPlanValidator())
    youtube_upload_service = YouTubeUploadService(
        settings.youtube_client_secrets_path,
        settings.youtube_token_path,
        settings.youtube_default_privacy_status,
        settings.youtube_category_id,
    )
    instagram_upload_service = InstagramUploadService(
        settings.instagram_access_token,
        settings.instagram_user_id,
        settings.instagram_graph_api_version,
        settings.instagram_share_to_feed,
    )

    nodes = VideoWorkflowNodes(
        content_agent=ContentAgent(content_service),
        media_agent=MediaAgent(video_service, music_service),
        render_agent=RenderAgent(render_service),
        feedback_agent=FeedbackAgent(telegram_service, analyzer),
        outputs_dir=settings.outputs_dir,
        youtube_upload_service=youtube_upload_service,
        instagram_upload_service=instagram_upload_service,
        publish_schedule_service=publish_schedule_service,
    )

    workflow = StateGraph(WorkflowState)
    workflow.add_node("generate_initial_script", nodes.generate_initial_script)
    workflow.add_node("download_initial_videos", nodes.download_initial_videos)
    workflow.add_node("download_initial_music", nodes.download_initial_music)
    workflow.add_node("render_video", nodes.render_video)
    workflow.add_node("ask_for_approval", nodes.ask_for_approval)
    workflow.add_node("apply_feedback_actions", nodes.apply_feedback_actions)

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
    return workflow.compile()
