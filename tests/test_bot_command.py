import unittest

from src.domain.bot_command import BotCommandType, command_help_text, parse_bot_command


class BotCommandTests(unittest.TestCase):
    def test_parse_simple_commands(self):
        for text, expected_type in [
            ("/start", BotCommandType.START),
            ("/stop", BotCommandType.STOP),
            ("/status", BotCommandType.STATUS),
            ("/pause", BotCommandType.PAUSE),
            ("/resume", BotCommandType.RESUME),
            ("/queue", BotCommandType.QUEUE),
            ("/queue_detail", BotCommandType.QUEUE_DETAIL),
            ("/queue_expired", BotCommandType.QUEUE_EXPIRED),
            ("/queue_cleanup", BotCommandType.QUEUE_CLEANUP),
            ("/publish_due", BotCommandType.PUBLISH_DUE),
        ]:
            command = parse_bot_command(text)

            self.assertTrue(command.is_valid)
            self.assertEqual(command.type, expected_type)

    def test_parse_generate_count(self):
        command = parse_bot_command("/generate 3")

        self.assertTrue(command.is_valid)
        self.assertEqual(command.type, BotCommandType.GENERATE)
        self.assertEqual(command.count, 3)

    def test_generate_requires_positive_number(self):
        self.assertIn("requires a count", parse_bot_command("/generate").error)
        self.assertIn("must be a number", parse_bot_command("/generate uc").error)
        self.assertIn("at least 1", parse_bot_command("/generate 0").error)

    def test_parse_cancel_queue_id(self):
        command = parse_bot_command("/cancel youtube:12")

        self.assertTrue(command.is_valid)
        self.assertEqual(command.type, BotCommandType.CANCEL)
        self.assertEqual(command.queue_id, "youtube:12")

    def test_parse_reschedule_queue_id_and_time(self):
        command = parse_bot_command("/reschedule tiktok:8 2026-05-16 17:30")

        self.assertTrue(command.is_valid)
        self.assertEqual(command.type, BotCommandType.RESCHEDULE)
        self.assertEqual(command.queue_id, "tiktok:8")
        self.assertEqual(command.publish_at, "2026-05-16 17:30")

    def test_unknown_command_is_invalid(self):
        command = parse_bot_command("/hello")

        self.assertFalse(command.is_valid)
        self.assertEqual(command.type, BotCommandType.UNKNOWN)

    def test_generating_typo_suggests_generate(self):
        command = parse_bot_command("/generating 1")

        self.assertFalse(command.is_valid)
        self.assertIn("/generate 1", command.error)

    def test_help_text_contains_english_commands(self):
        text = command_help_text()

        self.assertIn("/generate 3", text)
        self.assertIn("/queue_detail", text)
        self.assertIn("/queue_expired", text)
        self.assertIn("/queue_cleanup", text)
        self.assertIn("/cancel", text)
        self.assertIn("/reschedule", text)
        self.assertIn("/publish_due", text)


if __name__ == "__main__":
    unittest.main()
