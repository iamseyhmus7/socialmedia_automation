import unittest

from src.services.feedback_validator import FeedbackPlanValidator


class FeedbackPlanValidatorTests(unittest.TestCase):
    def setUp(self):
        self.validator = FeedbackPlanValidator(min_confidence=0.55)

    def test_multi_intent_actions_are_sorted_and_normalized(self):
        plan = self.validator.validate(
            {
                "status": "needs_changes",
                "actions": [
                    {
                        "type": "retry_render",
                        "target": "music_volume",
                        "instruction": "Increase background music volume",
                        "params": {"volume_multiplier": 1.3},
                        "confidence": 0.9,
                    },
                    {
                        "type": "edit_video",
                        "target": "video_last",
                        "instruction": "Replace final clip",
                        "params": {},
                        "confidence": 0.88,
                    },
                    {
                        "type": "edit_script",
                        "target": "intro",
                        "instruction": "Rewrite opening sentence",
                        "params": {},
                        "confidence": 0.8,
                    },
                ],
            },
            raw_message="music sesini ac, giris cumlesini degistir, son videoyu begenmedim",
            video_count=6,
        )

        self.assertEqual(plan.status, "needs_changes")
        self.assertEqual([action.type for action in plan.actions], ["edit_script", "edit_video", "retry_render"])
        self.assertEqual(plan.actions[1].target, "video_6")

    def test_changes_win_over_approve(self):
        plan = self.validator.validate(
            {
                "status": "needs_changes",
                "actions": [
                    {"type": "approve", "target": "all", "instruction": "Approved", "params": {}, "confidence": 0.9},
                    {
                        "type": "retry_music",
                        "target": "music",
                        "instruction": "Try another music track",
                        "params": {},
                        "confidence": 0.9,
                    },
                ],
            }
        )

        self.assertEqual(plan.status, "needs_changes")
        self.assertEqual([action.type for action in plan.actions], ["retry_music"])

    def test_cancel_wins_over_everything(self):
        plan = self.validator.validate(
            {
                "status": "cancelled",
                "actions": [
                    {"type": "edit_script", "target": "intro", "instruction": "Change intro", "params": {}, "confidence": 0.9},
                    {"type": "cancel", "target": "all", "instruction": "Stop", "params": {}, "confidence": 0.9},
                ],
            }
        )

        self.assertEqual(plan.status, "cancelled")
        self.assertEqual([action.type for action in plan.actions], ["cancel"])

    def test_low_confidence_becomes_clarify_not_approve(self):
        plan = self.validator.validate(
            {
                "status": "needs_changes",
                "actions": [
                    {"type": "edit_video", "target": "video_1", "instruction": "Maybe change", "params": {}, "confidence": 0.2}
                ],
            }
        )

        self.assertEqual(plan.status, "clarify")
        self.assertEqual(plan.actions[0].type, "clarify")

    def test_missing_actions_becomes_clarify_not_approve(self):
        plan = self.validator.validate({"status": "approved"})

        self.assertEqual(plan.status, "clarify")
        self.assertEqual(plan.actions[0].type, "clarify")


if __name__ == "__main__":
    unittest.main()

