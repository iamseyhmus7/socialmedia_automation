import unittest
import types
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

    def test_concrete_angle_hook_scores_without_generic_you_attack(self):
        script = self.quality.normalize_script(
            {
                "hook": "Your saved videos are debt.",
                "body": "You keep collecting proof, but every saved clip becomes another payment you avoid because action would expose the comfort you protect.",
                "outro": "Pay it today with one ugly start, before motivation becomes your favorite excuse.",
                "loop_ending": "That is why your saved videos are debt.",
                "vurgulanacak_kelimeler": ["debt", "action", "excuse"],
                "hook_pexels_arama_terimi": "person using phone alone dark room close up",
                "pexels_arama_temasi": "person scrolling saved videos alone at night",
                "pexels_anahtar_kelimeleri": ["phone close up dark room", "person sitting alone at night"],
            }
        )

        valid, reasons = self.quality.validate(script)

        self.assertTrue(valid, reasons)
        self.assertGreaterEqual(script["hook_score"], 0.75)
        self.assertGreaterEqual(script["quality_score"], 0.62)

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

        with patch("src.agents.content_agent.find_similar_script_matches", return_value=[]):
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

        with patch("src.agents.content_agent.find_similar_script_matches", side_effect=[[duplicate], [], [], []]):
            script = agent.generate_script(max_attempts=2)

        self.assertEqual(script["hook"], "You are wasting pressure.")
        self.assertEqual(content_service.avoid_calls[0], [])
        self.assertEqual(content_service.avoid_calls[1][0]["matched_hook"], "Old hook")
        self.assertEqual(content_service.avoid_calls[1][0]["matched_body"], "Old body")

    def test_content_agent_prefilters_angle_before_full_script_generation(self):
        class FakeContentService:
            def __init__(self):
                self.angle_calls = []
                self.script_angle_briefs = []

            def generate_motivation_angle_candidates(self, count=6, avoid_scripts=None):
                self.angle_calls.append(list(avoid_scripts or []))
                return [
                    {
                        "angle_name": "Average ego attack",
                        "audience": "generic viewer",
                        "psychological_charge": "the viewer is using insult as motivation instead of facing behavior",
                        "behavior_evidence": "the viewer keeps searching for a harsher label",
                        "consequence": "nothing changes after the emotional hit fades",
                        "action_trigger": "name the first action and do it today",
                        "fresh_metaphor": "ranking table",
                        "hook_direction": "You are actually average.",
                        "visual_story": "person staring into mirror tense face close up",
                        "search_seed": "person staring into mirror tense face close up",
                    },
                    {
                        "angle_name": "Saved videos as debt",
                        "audience": "people who collect motivation",
                        "psychological_charge": "the viewer turned learning into a cleaner form of hiding",
                        "behavior_evidence": "the viewer saves clips but avoids starting",
                        "consequence": "the goal keeps aging while the viewer feels productive",
                        "action_trigger": "start one ugly action before saving another video",
                        "fresh_metaphor": "unpaid debt",
                        "hook_direction": "Your saved videos are debt.",
                        "visual_story": "person scrolling saved videos alone at night",
                        "search_seed": "person using phone alone dark room close up",
                    },
                ]

            def generate_motivation_candidates(self, count=5, avoid_scripts=None, angle_brief=None):
                self.script_angle_briefs.append(dict(angle_brief or {}))
                return [
                    {
                        "hook": "Your saved videos are debt.",
                        "body": "You keep collecting proof, but every saved clip becomes another payment you avoid because action would expose the comfort you protect.",
                        "outro": "Pay it today with one ugly start, before motivation becomes your favorite excuse.",
                        "loop_ending": "That is why your saved videos are debt.",
                        "vurgulanacak_kelimeler": ["debt", "action", "excuse"],
                    }
                ]

        content_service = FakeContentService()
        agent = ContentAgent(content_service, self.quality)
        duplicate_angle = {
            "similarity": 0.92,
            "hook": "Old average hook",
            "body": "Old average body",
            "outro": "Old average outro",
            "script_data": {"hook": "Old average hook", "body": "Old average body", "outro": "Old average outro"},
        }

        with patch("src.agents.content_agent.find_similar_script_matches", side_effect=[[duplicate_angle], [], []]):
            script = agent.generate_script(max_attempts=1)

        self.assertEqual(script["hook"], "Your saved videos are debt.")
        self.assertEqual(content_service.script_angle_briefs[0]["angle_name"], "Saved videos as debt")

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

        with patch("src.agents.content_agent.find_similar_script_matches", return_value=[duplicate]):
            with self.assertRaisesRegex(RuntimeError, "semantically distinct"):
                agent.generate_script(max_attempts=2)

    def test_content_agent_accepts_gray_zone_distinct_script(self):
        agent = ContentAgent(types.SimpleNamespace(), self.quality)
        script = {
            "hook": "Loud dreams pay zero rent.",
            "body": "You talk like ambition is proof, but the unpaid hour keeps exposing the gap between your mouth and your movement.",
            "outro": "Pay today with action, or keep letting noise pretend it is progress.",
        }
        match = {
            "similarity": 0.857,
            "hook": "Nobody cares about your potential.",
            "body": "Old body",
            "outro": "Old outro",
            "script_data": {
                "hook": "Nobody cares about your potential.",
                "body": "Old body",
                "outro": "Old outro",
            },
        }

        with patch("src.agents.content_agent.find_similar_script_matches", return_value=[match]):
            self.assertIsNone(agent._script_duplicate_match(script))

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
