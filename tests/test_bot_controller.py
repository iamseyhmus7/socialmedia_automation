import asyncio
import unittest

from src.services.bot_controller import BotController


class BotControllerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.calls = 0
        self.sent_messages = []
        self.cleanup_calls = 0

        async def runner():
            self.calls += 1
            await asyncio.sleep(0)
            return {
                "status": "approved",
                "final_video_path": "outputs/video.mp4",
                "youtube_url": "https://www.youtube.com/watch?v=abc123",
                "youtube_publish_at": "2026-05-09T10:00:00Z",
                "tiktok_publish_at": "2026-05-09T10:00:00Z",
            }

        self.controller = BotController(
            runner,
            queue_provider=lambda: "Queue item",
            queue_detail_provider=lambda: "Queue detail",
            queue_expired_provider=lambda: "Queue expired",
            queue_cleanup_provider=lambda: "Queue cleanup",
            queue_cancel_provider=lambda queue_id: f"Cancelled {queue_id}",
            queue_reschedule_provider=lambda queue_id, publish_at: f"Rescheduled {queue_id} {publish_at}",
            due_publisher=lambda: "Published due item",
            message_sender=lambda text: self.sent_messages.append(text) is None,
            cleanup_callback=lambda: setattr(self, "cleanup_calls", self.cleanup_calls + 1),
            status_provider=lambda: "Sistem sagligi:\n- PostgreSQL: OK - test",
        )

    async def test_generate_runs_requested_count(self):
        message = await self.controller.handle_message("/generate 6")

        self.assertIn("6 video", message)
        await self.controller._generation_task
        self.assertEqual(self.calls, 6)
        self.assertEqual(self.controller.state.completed_count, 6)
        self.assertEqual(self.controller.state.last_status, "completed")
        self.assertEqual(len(self.sent_messages), 6)
        self.assertIn("Output: outputs/video.mp4", self.sent_messages[-1])
        self.assertIn("YouTube:", self.sent_messages[-1])
        self.assertIn("TikTok local queue:", self.sent_messages[-1])
        self.assertEqual(self.cleanup_calls, 6)

    async def test_generate_does_not_start_when_paused(self):
        await self.controller.handle_message("/pause")
        message = await self.controller.handle_message("/generate 2")

        self.assertIn("duraklatilmis", message)
        self.assertEqual(self.calls, 0)

    async def test_stop_prevents_next_video_after_current_finishes(self):
        can_finish = asyncio.Event()

        async def runner():
            self.calls += 1
            await can_finish.wait()
            return {"status": "approved"}

        controller = BotController(runner)
        await controller.handle_message("/generate 3")
        await asyncio.sleep(0)

        message = await controller.handle_message("/stop")
        can_finish.set()
        await controller._generation_task

        self.assertIn("Durdurma istendi", message)
        self.assertEqual(self.calls, 1)
        self.assertEqual(controller.state.completed_count, 1)

    async def test_non_approved_status_stops_loop(self):
        async def runner():
            self.calls += 1
            return {"status": "cancelled"}

        controller = BotController(runner)
        await controller.handle_message("/generate 3")
        await controller._generation_task

        self.assertEqual(self.calls, 1)
        self.assertEqual(controller.state.completed_count, 0)
        self.assertEqual(controller.state.last_status, "cancelled")

    async def test_status_queue_and_publish_due(self):
        await self.controller.handle_message("/generate 1")
        await self.controller._generation_task

        status = await self.controller.handle_message("/status")

        self.assertIn("Uretilen: 1/1", status)
        self.assertIn("Sistem sagligi:", status)
        self.assertIn("PostgreSQL: OK", status)
        self.assertEqual(await self.controller.handle_message("/queue"), "Queue item")
        self.assertEqual(await self.controller.handle_message("/queue_detail"), "Queue detail")
        self.assertEqual(await self.controller.handle_message("/queue_expired"), "Queue expired")
        self.assertEqual(await self.controller.handle_message("/queue_cleanup"), "Queue cleanup")
        self.assertEqual(await self.controller.handle_message("/cancel youtube:12"), "Cancelled youtube:12")
        self.assertEqual(
            await self.controller.handle_message("/reschedule youtube:12 2026-05-16 17:30"),
            "Rescheduled youtube:12 2026-05-16 17:30",
        )
        self.assertEqual(await self.controller.handle_message("/publish_due"), "Published due item")

    async def test_status_handles_health_provider_failure(self):
        controller = BotController(lambda: {"status": "approved"}, status_provider=lambda: (_ for _ in ()).throw(RuntimeError("boom")))

        status = await controller.handle_message("/status")

        self.assertIn("Sistem sagligi: UYARI", status)
        self.assertIn("boom", status)


if __name__ == "__main__":
    unittest.main()
