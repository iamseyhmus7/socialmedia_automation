import unittest
from unittest.mock import Mock, patch

from src.services.telegram_service import TelegramService


class TelegramServiceTests(unittest.TestCase):
    def test_send_message_uses_plain_text_payload(self):
        service = TelegramService("token", "123")
        post = Mock(return_value=Mock(status_code=200, text="OK"))

        with patch.object(service, "_requests", return_value=Mock(post=post)):
            self.assertTrue(service.send_message("/publish_due"))

        self.assertEqual(post.call_args.kwargs["json"], {"chat_id": "123", "text": "/publish_due"})

    @patch("src.services.telegram_service.time.sleep", return_value=None)
    @patch("src.services.telegram_service.time.time")
    def test_wait_for_message_can_keep_existing_offset(self, time_mock, _sleep):
        service = TelegramService("token", "123")
        service.last_update_id = 10
        time_mock.side_effect = [0, 0]
        get = Mock()
        get.return_value = Mock(
            status_code=200,
            json=lambda: {
                "result": [
                    {
                        "update_id": 11,
                        "message": {"chat": {"id": "123"}, "text": "/status"},
                    }
                ]
            },
        )

        with patch.object(service, "_requests", return_value=Mock(get=get)):
            message = service.wait_for_message(timeout_minutes=1, skip_existing=False)

        self.assertEqual(message, "/status")
        self.assertEqual(get.call_args.kwargs["params"]["offset"], 11)
        self.assertEqual(service.last_update_id, 11)


if __name__ == "__main__":
    unittest.main()
