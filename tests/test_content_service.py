import unittest
import sys
import types
from unittest.mock import patch

sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))
google_module = types.SimpleNamespace()
genai_module = types.SimpleNamespace(GenerativeModel=lambda *args, **kwargs: None, configure=lambda **kwargs: None)
google_module.generativeai = genai_module
sys.modules.setdefault("google", google_module)
sys.modules.setdefault("google.generativeai", genai_module)
from src.services.content_service import GeminiContentService
from src.services.script_quality_service import ScriptQualityService


class GeminiContentServiceJsonParsingTests(unittest.TestCase):
    def make_service(self) -> GeminiContentService:
        with patch("google.generativeai.GenerativeModel"):
            return GeminiContentService(api_key=None, model_name="test-model")

    def test_parse_json_uses_first_valid_json_object_when_extra_data_follows(self):
        service = self.make_service()
        text = '{"candidates": [{"hook": "You are hiding."}]}\n{"extra": true}'

        data = service._parse_json(text)

        self.assertEqual(data["candidates"][0]["hook"], "You are hiding.")

    def test_parse_json_extracts_json_object_from_surrounding_text(self):
        service = self.make_service()
        text = 'Here is the JSON:\n{"hook": "Your comfort is loud."}\nDone.'

        data = service._parse_json(text)

        self.assertEqual(data["hook"], "Your comfort is loud.")

    def test_avoid_prompt_includes_duplicate_context(self):
        service = self.make_service()

        prompt = service._avoid_prompt(
            [
                {
                    "similarity": 0.91,
                    "rejected_hook": "You are rotting in comfort.",
                    "matched_hook": "You are rotting in your comfort.",
                    "matched_body": "Old body",
                    "matched_outro": "Old outro",
                }
            ]
        )

        self.assertIn("similarity=0.91", prompt)
        self.assertIn("rejected_hook: You are rotting in comfort.", prompt)
        self.assertIn("matched_hook: You are rotting in your comfort.", prompt)


class ScriptQualityVisualNormalizationTests(unittest.TestCase):
    def test_normalize_script_rewrites_weak_visual_terms(self):
        service = ScriptQualityService()

        script = service.normalize_script(
            {
                "hook": "You are hiding again.",
                "body": "The mirror knows what comfort keeps delaying because you keep choosing easy.",
                "outro": "Face it before it owns you.",
                "loop_ending": "You are hiding again.",
                "vurgulanacak_kelimeler": ["hiding", "comfort"],
                "hook_pexels_arama_terimi": "mirror",
                "pexels_arama_temasi": "darkness",
                "pexels_anahtar_kelimeleri": ["man", "shadow", "intense"],
            }
        )

        self.assertEqual(script["hook_pexels_arama_terimi"], "person staring into mirror tense face close up")
        self.assertEqual(script["pexels_arama_temasi"], "person alone in dark room dramatic shadow close up")
        self.assertIn("man close up face under pressure cinematic portrait", script["pexels_anahtar_kelimeleri"])
        self.assertEqual(len(script["video_sahneleri"]), 6)

    def test_normalize_script_keeps_six_ordered_video_scenes(self):
        service = ScriptQualityService()

        script = service.normalize_script(
            {
                "hook": "Your comfort is slow death.",
                "body": "You keep choosing easy while the part of you that wants more starts suffocating.",
                "outro": "Wake up before comfort finishes you.",
                "loop_ending": "Your comfort is slow death.",
                "vurgulanacak_kelimeler": ["comfort", "death"],
                "video_sahneleri": [
                    "person underwater reaching toward surface",
                    "hand pressed against wet glass close up",
                    "person alone in dark room resisting phone procrastination",
                    "stressed person sitting on bed in dark room close up",
                    "stressed person under pressure close up eye contact",
                    "person walking alone at night dark cinematic",
                ],
            }
        )

        self.assertEqual(len(script["video_sahneleri"]), 6)
        self.assertEqual(script["video_sahneleri"][0], "person underwater reaching toward surface")
        self.assertEqual(script["video_sahneleri"][2], "person alone in dark room resisting phone procrastination")

    def test_normalize_script_accepts_production_json_schema(self):
        service = ScriptQualityService()

        script = service.normalize_script(
            {
                "style": "aggressive_viral_motivation",
                "script": {
                    "hook": "You are wasting pressure.",
                    "body": "You avoid the uncomfortable hour, but that hour is where discipline starts replacing the story you keep repeating when nobody is watching.",
                    "outro": "Use the pressure today, before comfort teaches you to waste it again.",
                    "loop_ending": "That is how you stop wasting pressure.",
                },
                "voice_plan": {"highlighted_words": ["pressure", "discipline", "comfort"]},
                "media_plan": {
                    "visual_direction": {"overall_theme": "discipline under pressure dark cinematic human"},
                    "video_scenes": [
                        {
                            "scene_id": 1,
                            "beat": "hook",
                            "line_match": "You are wasting pressure.",
                            "search_query": "stressed person close up eye contact under pressure",
                            "backup_queries": ["tense face dramatic lighting"],
                        },
                        {"scene_id": 2, "search_query": "person alone in dark room procrastinating with phone"},
                        {"scene_id": 3, "search_query": "athlete training alone dark gym intense struggle close up"},
                        {"scene_id": 4, "search_query": "stressed office worker head in hands close up dark cinematic"},
                        {"scene_id": 5, "search_query": "determined person walking alone at night cinematic backlight"},
                        {"scene_id": 6, "search_query": "person staring into mirror tense face close up dark cinematic"},
                    ],
                    "music": {"search_query": "dark cinematic motivational emotional build intense no vocals"},
                },
                "publishing": {"youtube_title": "You Are Wasting Pressure"},
            }
        )

        self.assertEqual(script["hook"], "You are wasting pressure.")
        self.assertEqual(script["vurgulanacak_kelimeler"], ["pressure", "discipline", "comfort"])
        self.assertEqual(len(script["media_plan"]["video_scenes"]), 6)
        self.assertEqual(script["media_plan"]["video_scenes"][0]["beat"], "hook")
        self.assertEqual(script["freesound_arama_terimi"], "dark cinematic motivational emotional build intense no vocals")
        self.assertEqual(script["publishing"]["youtube_title"], "You Are Wasting Pressure")
        self.assertIn("quality_report", script)
        self.assertIn("components", script["quality_report"])


if __name__ == "__main__":
    unittest.main()
