import unittest
import os
import tempfile
from unittest.mock import patch

from src.domain.feedback import FeedbackAction
from src.domain.state import create_initial_state
from src.services.publish_schedule_service import PublishScheduleService
from src.workflows.nodes import VideoWorkflowNodes
from src.workflows.router import route_after_feedback


class RouterAndStateTests(unittest.TestCase):
    def test_router_routes_needs_changes_to_apply_actions(self):
        self.assertEqual(route_after_feedback({"status": "needs_changes"}), "apply_feedback_actions")

    def test_router_routes_clarify_back_to_approval_wait(self):
        self.assertEqual(route_after_feedback({"status": "clarify"}), "ask_for_approval")

    def test_router_ends_for_approve_cancel_timeout(self):
        self.assertEqual(route_after_feedback({"status": "approved"}), "end")
        self.assertEqual(route_after_feedback({"status": "cancelled"}), "end")
        self.assertEqual(route_after_feedback({"status": "timeout"}), "end")

    def test_render_volume_multiplier_does_not_retry_music(self):
        nodes = VideoWorkflowNodes.__new__(VideoWorkflowNodes)
        volume = nodes._apply_render_settings(
            0.08,
            [
                FeedbackAction(
                    type="retry_render",
                    target="music_volume",
                    instruction="Increase music volume",
                    params={"volume_multiplier": 1.5},
                    confidence=0.9,
                )
            ],
        )

        self.assertAlmostEqual(volume, 0.12)

    def test_render_volume_is_clamped(self):
        nodes = VideoWorkflowNodes.__new__(VideoWorkflowNodes)
        volume = nodes._apply_render_settings(
            0.8,
            [
                FeedbackAction(
                    type="retry_render",
                    target="music_volume",
                    instruction="Make music much louder",
                    params={"volume_multiplier": 10},
                    confidence=0.9,
                )
            ],
        )

        self.assertEqual(volume, 2.0)

    def test_initial_state_uses_louder_background_music(self):
        state = create_initial_state()

        self.assertEqual(state["music_volume"], 1.25)

    def test_output_filename_stays_directly_under_date_folder(self):
        nodes = VideoWorkflowNodes.__new__(VideoWorkflowNodes)

        self.assertEqual(
            nodes._build_output_filename("2026-05-08", "20260508_121545", 1),
            "2026-05-08\\motivation_20260508_121545.mp4",
        )
        self.assertEqual(
            nodes._build_output_filename("2026-05-08", "20260508_121545", 2),
            "2026-05-08\\motivation_20260508_121545.mp4",
        )

    def test_legacy_revision_outputs_are_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = os.path.join(tmp, "2026-05-08")
            os.makedirs(output_dir)
            stale_revision = os.path.join(output_dir, "motivation_20260508_121545_r02.mp4")
            current_output = os.path.join(output_dir, "motivation_20260508_121545.mp4")
            unrelated = os.path.join(output_dir, "motivation_20260508_999999_r02.mp4")
            for path in [stale_revision, current_output, unrelated]:
                with open(path, "w", encoding="utf-8") as file:
                    file.write("x")

            nodes = VideoWorkflowNodes.__new__(VideoWorkflowNodes)
            nodes.outputs_dir = tmp
            nodes._remove_legacy_revision_outputs("2026-05-08", "20260508_121545")

            self.assertFalse(os.path.exists(stale_revision))
            self.assertTrue(os.path.exists(current_output))
            self.assertTrue(os.path.exists(unrelated))

    def test_initial_state_includes_youtube_upload_fields(self):
        state = create_initial_state()

        self.assertIsNone(state["youtube_video_id"])
        self.assertIsNone(state["youtube_url"])
        self.assertIsNone(state["youtube_publish_at"])
        self.assertIsNone(state["upload_status"])
        self.assertIsNone(state["upload_error"])
        self.assertIsNone(state["instagram_media_id"])
        self.assertIsNone(state["instagram_url"])
        self.assertIsNone(state["instagram_upload_status"])
        self.assertIsNone(state["instagram_upload_error"])


class ApprovalUploadTests(unittest.IsolatedAsyncioTestCase):
    async def test_approval_upload_success_is_returned_in_state(self):
        class FakeUploadResult:
            video_id = "abc123"
            youtube_url = "https://www.youtube.com/watch?v=abc123"
            publish_at = "2026-05-09T10:00:00Z"

        class FakeUploadService:
            def upload_video(self, video_path, script_data, publish_at=None):
                self.publish_at = publish_at
                return FakeUploadResult()

        nodes = VideoWorkflowNodes.__new__(VideoWorkflowNodes)
        fake_upload_service = FakeUploadService()
        nodes.youtube_upload_service = fake_upload_service
        nodes.publish_schedule_service = PublishScheduleService()

        with patch.object(nodes.publish_schedule_service, "next_publish_at", return_value="2026-05-09T10:00:00Z"):
            result = await nodes._upload_approved_video(
                {"final_video_path": "video.mp4", "script_data": {"hook": "Hook"}, "date_folder": "2026-05-09"}
            )

        self.assertEqual(result["upload_status"], "uploaded")
        self.assertEqual(result["youtube_video_id"], "abc123")
        self.assertEqual(result["youtube_url"], "https://www.youtube.com/watch?v=abc123")
        self.assertEqual(result["youtube_publish_at"], "2026-05-09T10:00:00Z")
        self.assertEqual(fake_upload_service.publish_at, "2026-05-09T10:00:00Z")
        self.assertEqual(result["instagram_upload_status"], "skipped")

    async def test_approval_upload_failure_is_captured_without_raising(self):
        class FakeUploadService:
            def upload_video(self, video_path, script_data, publish_at=None):
                raise RuntimeError("quota exceeded")

        nodes = VideoWorkflowNodes.__new__(VideoWorkflowNodes)
        nodes.youtube_upload_service = FakeUploadService()
        nodes.publish_schedule_service = PublishScheduleService()

        result = await nodes._upload_approved_video({"final_video_path": "video.mp4", "script_data": {}})

        self.assertEqual(result["upload_status"], "failed")
        self.assertIn("quota exceeded", result["upload_error"])
        self.assertEqual(result["instagram_upload_status"], "skipped")

    async def test_approval_upload_calls_youtube_and_instagram_independently(self):
        class FakeYouTubeResult:
            video_id = "yt123"
            youtube_url = "https://www.youtube.com/watch?v=yt123"
            publish_at = "2026-05-09T10:00:00Z"

        class FakeYouTubeService:
            def upload_video(self, video_path, script_data, publish_at=None):
                self.called = True
                return FakeYouTubeResult()

        class FakeInstagramResult:
            media_id = "ig123"
            instagram_url = "https://www.instagram.com/reel/ig123/"

        class FakeInstagramService:
            def is_configured(self):
                return True

            def build_metadata(self, script_data=None, caption=None):
                if caption is not None:
                    return type("FakeInstagramResult", (), {"caption": caption})()
                return type("FakeInstagramMetadata", (), {"caption": "Instagram caption"})()

            def upload_reel(self, video_path, script_data, caption=None):
                self.call = {"video_path": video_path, "script_data": script_data, "caption": caption}
                return FakeInstagramResult()

        nodes = VideoWorkflowNodes.__new__(VideoWorkflowNodes)
        nodes.youtube_upload_service = FakeYouTubeService()
        nodes.instagram_upload_service = FakeInstagramService()
        nodes.publish_schedule_service = PublishScheduleService()

        with (
            patch.object(nodes.publish_schedule_service, "next_publish_at", return_value="2026-05-09T10:00:00Z"),
            patch("src.workflows.nodes.get_youtube_metadata", return_value=None),
        ):
            result = await nodes._upload_approved_video(
                {"final_video_path": "video.mp4", "script_data": {"hook": "Hook"}}
            )

        self.assertEqual(result["upload_status"], "uploaded")
        self.assertEqual(result["youtube_video_id"], "yt123")
        self.assertEqual(result["instagram_upload_status"], "uploaded")
        self.assertEqual(result["instagram_media_id"], "ig123")
        self.assertEqual(result["instagram_url"], "https://www.instagram.com/reel/ig123/")
        self.assertEqual(nodes.instagram_upload_service.call["caption"], "Instagram caption")

    async def test_instagram_upload_uses_saved_youtube_description_as_caption(self):
        class FakeInstagramResult:
            media_id = "ig123"
            instagram_url = "https://www.instagram.com/reel/ig123/"

        class FakeInstagramService:
            def is_configured(self):
                return True

            def build_metadata(self, script_data=None, caption=None):
                return type("FakeInstagramResult", (), {"caption": caption or "fallback"})()

            def upload_reel(self, video_path, script_data, caption=None):
                self.caption = caption
                return FakeInstagramResult()

        nodes = VideoWorkflowNodes.__new__(VideoWorkflowNodes)
        nodes.youtube_upload_service = None
        nodes.instagram_upload_service = FakeInstagramService()
        nodes.publish_schedule_service = PublishScheduleService()

        with patch("src.workflows.nodes.get_youtube_metadata", return_value={"description": "Exact YouTube description"}):
            result = await nodes._upload_approved_video_to_instagram(
                {"final_video_path": "video.mp4", "script_data": {"hook": "Hook"}}
            )

        self.assertEqual(result["instagram_upload_status"], "uploaded")
        self.assertEqual(nodes.instagram_upload_service.caption, "Exact YouTube description")

    async def test_instagram_failure_does_not_hide_youtube_success(self):
        class FakeYouTubeResult:
            video_id = "yt123"
            youtube_url = "https://www.youtube.com/watch?v=yt123"
            publish_at = "2026-05-09T10:00:00Z"

        class FakeYouTubeService:
            def upload_video(self, video_path, script_data, publish_at=None):
                return FakeYouTubeResult()

        class FailingInstagramService:
            def is_configured(self):
                return True

            def build_metadata(self, script_data=None, caption=None):
                return type("FakeInstagramMetadata", (), {"caption": "caption"})()

            def upload_reel(self, video_path, script_data, caption=None):
                raise RuntimeError("container failed")

        nodes = VideoWorkflowNodes.__new__(VideoWorkflowNodes)
        nodes.youtube_upload_service = FakeYouTubeService()
        nodes.instagram_upload_service = FailingInstagramService()
        nodes.publish_schedule_service = PublishScheduleService()

        with (
            patch.object(nodes.publish_schedule_service, "next_publish_at", return_value="2026-05-09T10:00:00Z"),
            patch("src.workflows.nodes.get_youtube_metadata", return_value=None),
        ):
            result = await nodes._upload_approved_video(
                {"final_video_path": "video.mp4", "script_data": {"hook": "Hook"}}
            )

        self.assertEqual(result["upload_status"], "uploaded")
        self.assertEqual(result["youtube_video_id"], "yt123")
        self.assertEqual(result["instagram_upload_status"], "failed")
        self.assertIn("container failed", result["instagram_upload_error"])

    async def test_approval_node_records_history_then_uploads(self):
        class FakeFeedbackPlan:
            status = "approved"
            raw_message = "onay"

        class FakeFeedbackAgent:
            def send_review_video(self, video_path, caption=None):
                pass

            def wait_for_feedback(self, video_count, timeout_minutes=15):
                return FakeFeedbackPlan()

        class FakeUploadResult:
            video_id = "xyz789"
            youtube_url = "https://www.youtube.com/watch?v=xyz789"
            publish_at = "2026-05-09T10:00:00Z"

        class FakeUploadService:
            def upload_video(self, video_path, script_data, publish_at=None):
                return FakeUploadResult()

        nodes = VideoWorkflowNodes.__new__(VideoWorkflowNodes)
        nodes.feedback_agent = FakeFeedbackAgent()
        nodes.youtube_upload_service = FakeUploadService()
        nodes.publish_schedule_service = PublishScheduleService()

        with (
            patch("os.path.getsize", return_value=1024),
            patch("src.workflows.nodes.record_approved_state") as record,
            patch.object(nodes.publish_schedule_service, "next_publish_at", return_value="2026-05-09T10:00:00Z"),
        ):
            result = await nodes.ask_for_approval(
                {
                    "final_video_path": "video.mp4",
                    "video_paths": [],
                    "script_data": {"hook": "Hook"},
                }
            )

        record.assert_called_once()
        self.assertEqual(result["status"], "approved")
        self.assertEqual(result["upload_status"], "uploaded")
        self.assertEqual(result["youtube_video_id"], "xyz789")


if __name__ == "__main__":
    unittest.main()
