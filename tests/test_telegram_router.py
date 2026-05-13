import asyncio
import unittest

from src.services.telegram_router import TelegramRouter


class FakeTelegramService:
    def __init__(self):
        self.sent_messages = []

    def send_message(self, text):
        self.sent_messages.append(text)
        return True


class FakeController:
    def __init__(self):
        self.handled = []

    async def handle_message(self, text):
        self.handled.append(text)
        return f"handled {text}"


class TelegramRouterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.telegram = FakeTelegramService()
        self.controller = FakeController()
        self.router = TelegramRouter(self.telegram, self.controller)

    async def test_slash_command_goes_to_controller_even_when_feedback_is_waiting(self):
        self.router.is_waiting_for_feedback = True

        await self.router.route_message("/status")

        self.assertEqual(self.controller.handled, ["/status"])
        self.assertEqual(self.telegram.sent_messages, ["handled /status"])
        self.assertTrue(self.router.feedback_queue.empty())

    async def test_plain_text_goes_to_feedback_queue_only_when_waiting(self):
        wait_task = asyncio.create_task(self.router.wait_for_feedback(timeout_minutes=1))
        await asyncio.sleep(0)

        await self.router.route_message("onay")

        self.assertEqual(await wait_task, "onay")
        self.assertEqual(self.controller.handled, [])
        self.assertEqual(self.telegram.sent_messages, [])

    async def test_plain_text_without_feedback_wait_gets_guidance(self):
        await self.router.route_message("onay")

        self.assertEqual(self.controller.handled, [])
        self.assertEqual(
            self.telegram.sent_messages,
            ["Video onayi beklenmiyor. Sistem komutlari icin / ile baslayin."],
        )


if __name__ == "__main__":
    unittest.main()
