import unittest
from unittest.mock import patch

from src.agents.content_agent import ContentAgent
from src.services.script_quality_service import ScriptQualityService


class ScriptQualityServiceTests(unittest.TestCase):
    def setUp(self):
        self.quality = ScriptQualityService()

    def test_cliche_script_is_rejected(self):
        script = self.quality.normalize_script(
            {
                "hook": "You must never give up.",
                "body": "Believe in yourself and dream big because success is a journey.",
                "outro": "Stay positive and work hard every single day.",
                "loop_ending": "Never give up.",
                "vurgulanacak_kelimeler": ["success"],
            }
        )

        valid, reasons = self.quality.validate(script)

        self.assertFalse(valid)
        self.assertTrue(any("cliche" in reason.lower() for reason in reasons))
        self.assertEqual(script["quality_report"]["grade"], "F")
        self.assertFalse(script["quality_report"]["valid"])

    def test_best_candidate_prefers_strong_hook_and_loop(self):
        weak = {
            "hook": "Believe in yourself today.",
            "body": "Never give up and dream big because you can do anything.",
            "outro": "Stay positive and keep going.",
        }
        strong = {
            "hook": "Your excuses are costing you.",
            "body": "You call it timing, but it is comfort quietly training you to delay the life you keep talking about.",
            "outro": "Choose the hard thing now, before your excuses choose your future for you.",
            "loop_ending": "That is why your excuses are costing you.",
            "hook_pexels_arama_terimi": "human face close up eye contact struggle fast motion dark cinematic portrait",
            "pexels_arama_temasi": "discipline under pressure dark cinematic human",
            "pexels_anahtar_kelimeleri": ["close up face", "dark gym struggle", "fast motion focus"],
            "vurgulanacak_kelimeler": ["excuses", "comfort", "choose"],
        }

        result = self.quality.select_best([weak, strong])

        self.assertEqual(result.script["hook"], "Your excuses are costing you.")
        self.assertTrue(result.valid)
        self.assertGreater(result.script["quality_score"], 0.62)
        self.assertEqual(result.score, result.script["quality_score"])
        self.assertEqual(result.report["grade"], result.script["quality_report"]["grade"])
        self.assertIn("components", result.report)

    def test_content_agent_uses_best_quality_candidate(self):
        class FakeContentService:
            def generate_motivation_candidates(self, count=5):
                return [
                    {"hook": "Dream big now.", "body": "Believe in yourself.", "outro": "Never give up."},
                    {
                        "hook": "You are wasting pressure.",
                        "body": "You avoid the uncomfortable hour, but that hour is where discipline starts replacing the story you keep repeating when nobody is watching.",
                        "outro": "Use the pressure today, before comfort teaches you to waste it again.",
                        "loop_ending": "That is how you stop wasting pressure.",
                        "vurgulanacak_kelimeler": ["pressure", "discipline", "comfort"],
                    },
                ]

        agent = ContentAgent(FakeContentService(), self.quality)

        with patch("src.agents.content_agent.find_similar_script_match", return_value=None):
            script = agent.generate_script(max_attempts=1)

        self.assertEqual(script["hook"], "You are wasting pressure.")
        self.assertEqual(script["style"], "aggressive_viral_motivation")
        self.assertIn("quality_report", script)
        self.assertTrue(script["quality_report"]["valid"])

    def test_content_agent_feeds_duplicate_matches_back_to_generation_prompt(self):
        class FakeContentService:
            def __init__(self):
                self.avoid_calls = []

            def generate_motivation_candidates(self, count=5, avoid_scripts=None):
                self.avoid_calls.append(list(avoid_scripts or []))
                return [
                    {
                        "hook": "You are wasting pressure.",
                        "body": "You avoid the uncomfortable hour, but that hour is where discipline starts replacing the story you keep repeating when nobody is watching.",
                        "outro": "Use the pressure today, before comfort teaches you to waste it again.",
                        "loop_ending": "That is how you stop wasting pressure.",
                        "vurgulanacak_kelimeler": ["pressure", "discipline", "comfort"],
                    }
                ]

        content_service = FakeContentService()
        agent = ContentAgent(content_service, self.quality)
        duplicate = {
            "similarity": 0.91,
            "hook": "Old hook",
            "body": "Old body",
            "outro": "Old outro",
            "script_data": {"hook": "Old hook", "body": "Old body", "outro": "Old outro"},
        }

        with patch("src.agents.content_agent.find_similar_script_match", side_effect=[duplicate, None]):
            script = agent.generate_script(max_attempts=2)

        self.assertEqual(script["hook"], "You are wasting pressure.")
        self.assertEqual(content_service.avoid_calls[0], [])
        self.assertEqual(content_service.avoid_calls[1][0]["matched_hook"], "Old hook")
        self.assertEqual(content_service.avoid_calls[1][0]["matched_body"], "Old body")

    def test_content_agent_rejects_all_similar_scripts_after_retries(self):
        class FakeContentService:
            def generate_motivation_candidates(self, count=5, avoid_scripts=None):
                return [
                    {
                        "hook": "You are wasting pressure.",
                        "body": "You avoid the uncomfortable hour, but that hour is where discipline starts replacing the story you keep repeating when nobody is watching.",
                        "outro": "Use the pressure today, before comfort teaches you to waste it again.",
                        "loop_ending": "That is how you stop wasting pressure.",
                        "vurgulanacak_kelimeler": ["pressure", "discipline", "comfort"],
                    }
                ]

        agent = ContentAgent(FakeContentService(), self.quality)
        duplicate = {
            "similarity": 0.91,
            "hook": "Old hook",
            "body": "Old body",
            "outro": "Old outro",
            "script_data": {"hook": "Old hook", "body": "Old body", "outro": "Old outro"},
        }

        with patch("src.agents.content_agent.find_similar_script_match", return_value=duplicate):
            with self.assertRaisesRegex(RuntimeError, "semantically distinct"):
                agent.generate_script(max_attempts=2)

    def test_quality_report_exposes_counts_components_and_risks(self):
        script = self.quality.normalize_script(
            {
                "hook": "You are wasting pressure.",
                "body": "You avoid the uncomfortable hour, but that hour is where discipline starts replacing the story you keep repeating when nobody is watching.",
                "outro": "Use the pressure today, before comfort teaches you to waste it again.",
                "loop_ending": "That is how you stop wasting pressure.",
                "vurgulanacak_kelimeler": ["pressure", "discipline", "comfort"],
            }
        )
        valid, reasons = self.quality.validate(script)
        report = self.quality.quality_report(script, valid, reasons)

        self.assertIn(report["grade"], {"A", "B", "C"})
        self.assertEqual(report["word_count"], 38)
        self.assertEqual(report["hook_word_count"], 4)
        self.assertEqual(report["scene_count"], 6)
        self.assertIn("hook", report["components"])
        self.assertIsInstance(report["strengths"], list)
        self.assertIsInstance(report["risks"], list)


if __name__ == "__main__":
    unittest.main()
