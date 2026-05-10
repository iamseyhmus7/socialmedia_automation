import unittest
import sys
import types
from unittest.mock import patch

sys.modules.setdefault("requests", types.SimpleNamespace())
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))
from src.agents.media_agent import MediaAgent
from src.services.music_service import FreesoundMusicService
from src.services.video_service import PexelsVideoService


class MediaAgentQueryTests(unittest.TestCase):
    def test_opening_query_is_tied_to_script_hook_and_theme(self):
        agent = MediaAgent.__new__(MediaAgent)
        query = agent._build_opening_query(
            {
                "hook": "Your excuses are costing you.",
                "hook_pexels_arama_terimi": "athlete training alone before sunrise",
                "pexels_arama_temasi": "discipline under pressure",
            }
        )

        self.assertIn("Your excuses are costing you.", query)
        self.assertIn("athlete training alone before sunrise", query)
        self.assertIn("discipline under pressure", query)
        self.assertIn("intense human face close up", query)
        self.assertIn("fast motion opening shot", query)
        self.assertIn("dark", query)
        self.assertIn("cinematic", query)
        self.assertIn("portrait", query)
        self.assertIn("motivation", query)

    def test_music_query_keeps_script_music_intent_and_required_constraints(self):
        agent = MediaAgent.__new__(MediaAgent)
        query = agent._music_query("low tense piano")

        self.assertIn("low tense piano", query)
        self.assertIn("cinematic", query)
        self.assertIn("motivational", query)
        self.assertIn("emotional build", query)
        self.assertIn("intense", query)
        self.assertIn("no vocals", query)

    def test_video_search_filters_approved_history_without_marking_new_ids(self):
        service = PexelsVideoService("key", "assets")
        response = types.SimpleNamespace(
            status_code=200,
            json=lambda: {
                "videos": [
                    {"id": "used", "video_files": [{"width": 1080, "height": 1920, "link": "used-link"}]},
                    {"id": "fresh", "video_files": [{"width": 1080, "height": 1920, "link": "fresh-link"}]},
                ]
            },
        )

        with (
            patch("src.services.video_service.requests.get", return_value=response, create=True),
            patch("src.services.video_service.is_video_used", side_effect=lambda video_id: video_id == "used"),
        ):
            self.assertEqual(service.search_videos(["discipline"], count=1), [("fresh", "fresh-link")])

    def test_best_video_file_prefers_vertical_hd(self):
        service = PexelsVideoService("key", "assets")

        best = service._get_best_video_file(
            [
                {"width": 1920, "height": 1080, "link": "landscape"},
                {"width": 720, "height": 1280, "link": "portrait-hd"},
                {"width": 540, "height": 960, "link": "portrait-low"},
            ]
        )

        self.assertEqual(best["link"], "portrait-hd")

    def test_music_search_tries_broader_fallback_queries(self):
        service = FreesoundMusicService("key", "assets")
        responses = [
            types.SimpleNamespace(status_code=200, json=lambda: {"results": []}),
            types.SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "results": [
                        {
                            "id": "123",
                            "name": "Cinematic Drone",
                            "previews": {"preview-hq-mp3": "https://example.test/music.mp3"},
                        }
                    ]
                },
            ),
        ]

        with (
            patch("src.services.music_service.requests.get", side_effect=responses, create=True) as get,
            patch("src.services.music_service.is_music_used", return_value=False),
            patch("src.services.music_service.random.choice", side_effect=lambda values: values[0]),
        ):
            music_id, music_url = service.search_music("too specific no result query")

        self.assertEqual(music_id, "123")
        self.assertEqual(music_url, "https://example.test/music.mp3")
        self.assertEqual(get.call_args_list[0].kwargs["params"]["query"], "too specific no result query")
        self.assertEqual(get.call_args_list[1].kwargs["params"]["query"], "cinematic drone")


if __name__ == "__main__":
    unittest.main()
