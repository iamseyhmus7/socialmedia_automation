import unittest
import sys
import types
from unittest.mock import patch

sys.modules.setdefault("requests", types.SimpleNamespace())
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))
from src.agents.media_agent import MediaAgent
from src.services.music_service import FreesoundMusicService
from src.services.video_service import (
    CoverrVideoService,
    MultiSourceVideoService,
    PexelsVideoService,
    PixabayVideoService,
    VideoAssetValidator,
    VideoCandidate,
    VideoValidationResult,
    _vertical_provider_query,
)


class MediaAgentQueryTests(unittest.TestCase):
    def test_download_initial_videos_skips_invalid_downloaded_assets(self):
        class FakeVideoService:
            def search_videos(self, queries, count=1):
                return [("bad", "bad-url"), ("good", "good-url")]

            def download_video(self, url, filename):
                return f"assets/{filename}"

        class FakeValidator:
            def validate(self, path):
                if "bad" in path:
                    return VideoValidationResult(False, "broken file")
                return VideoValidationResult(True, width=1080, height=1920, duration=5.0)

        agent = MediaAgent(FakeVideoService(), types.SimpleNamespace(), video_validator=FakeValidator())

        paths = agent.download_initial_videos({"video_sahneleri": ["stressed person close up"]})

        self.assertEqual(paths, ["assets/raw_good.mp4"])

    def test_download_by_queries_returns_only_valid_assets(self):
        class FakeVideoService:
            def search_videos(self, queries, count=1):
                return [("bad", "bad-url"), ("good", "good-url")]

            def download_video(self, url, filename):
                return f"assets/{filename}"

        class FakeValidator:
            def validate(self, path):
                return VideoValidationResult("good" in path, "invalid" if "bad" in path else "", 1080, 1920, 4.0)

        agent = MediaAgent(FakeVideoService(), types.SimpleNamespace(), video_validator=FakeValidator())

        self.assertEqual(agent._download_by_queries(["discipline"], count=2), ["assets/raw_good.mp4"])

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

    def test_music_query_compacts_script_music_intent_for_freesound(self):
        agent = MediaAgent.__new__(MediaAgent)
        query = agent._music_query("low tense piano")

        self.assertEqual(query, "tense piano cinematic")

    def test_music_query_removes_prompt_noise_for_freesound(self):
        agent = MediaAgent.__new__(MediaAgent)
        query = agent._music_query(
            "cinematic dark clock ticking beat with sub bass motivational emotional build intense no vocals"
        )

        self.assertEqual(query, "clock ticking cinematic")

    def test_visual_queries_expand_abstract_script_keywords_into_concrete_scenes(self):
        agent = MediaAgent.__new__(MediaAgent)
        queries = agent._build_visual_queries(
            {
                "hook": "You are hiding again.",
                "body": "The mirror knows what comfort keeps delaying.",
                "outro": "Face it before it owns you.",
                "pexels_arama_temasi": "darkness",
                "pexels_anahtar_kelimeleri": ["man", "shadow", "mirror"],
            }
        )

        joined = " | ".join(queries)
        self.assertIn("person alone in dark room dramatic shadow close up", joined)
        self.assertIn("man close up face under pressure cinematic portrait", joined)
        self.assertIn("person staring into mirror tense face close up", joined)
        self.assertNotIn("man dark cinematic portrait motivation human close up motion", queries)

    def test_visual_queries_prefer_ordered_video_scene_plan(self):
        agent = MediaAgent.__new__(MediaAgent)
        queries = agent._build_visual_queries(
            {
                "pexels_arama_temasi": "ignored theme",
                "pexels_anahtar_kelimeleri": ["ignored keyword"],
                "video_sahneleri": [
                    "person underwater reaching toward surface",
                    "hand pressed against wet glass close up",
                    "person alone in dark room resisting phone procrastination",
                    "stressed office worker head in hands close up",
                    "athlete training alone dark gym discipline close up",
                    "person staring into mirror tense face close up",
                ],
            }
        )

        self.assertEqual(len(queries), 6)
        self.assertIn("person underwater reaching toward surface", queries[0])
        self.assertIn("person staring into mirror tense face close up", queries[-1])
        self.assertNotIn("ignored theme", " | ".join(queries))

    def test_scene_query_groups_use_media_plan_with_backup_queries(self):
        agent = MediaAgent.__new__(MediaAgent)

        groups = agent._build_scene_query_groups(
            {
                "media_plan": {
                    "video_scenes": [
                        {
                            "scene_id": 1,
                            "search_query": "stressed person close up eye contact",
                            "backup_queries": ["tense face dramatic lighting"],
                        }
                    ]
                }
            }
        )

        self.assertEqual(len(groups), 1)
        self.assertIn("stressed person close up eye contact", groups[0][0])
        self.assertIn("tense face dramatic lighting", groups[0][1])
        self.assertIn("cinematic", groups[0][0])

    def test_vertical_provider_query_keeps_scene_specific_terms(self):
        cases = {
            "stressed person under pressure eye contact dark cinematic portrait motivation human close up motion": "stressed person vertical",
            "man looking at blank computer screen dark cinematic portrait motivation human close up motion": "office computer vertical",
            "empty wallet on table dark cinematic portrait motivation human close up motion": "wallet table vertical",
            "person standing on edge of diving board hesitant dark cinematic portrait motivation human close up motion": "diving board vertical",
            "close up of hands shaking with anxiety dark cinematic portrait motivation human motion": "anxious hands vertical",
            "person looking through rainy window dark cinematic portrait motivation human close up motion": "rainy window person vertical",
            "man shouting in frustration alone dark cinematic portrait motivation human close up motion": "angry person vertical",
            "extreme close up eyes narrowing dark cinematic portrait motivation human motion": "eyes close up vertical",
        }

        for raw_query, provider_query in cases.items():
            with self.subTest(raw_query=raw_query):
                self.assertEqual(_vertical_provider_query(raw_query), provider_query)

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

    def test_pixabay_video_search_returns_prefixed_ids_and_best_vertical_url(self):
        service = PixabayVideoService("key", "assets")
        response = types.SimpleNamespace(
            status_code=200,
            json=lambda: {
                "hits": [
                    {
                        "id": 456,
                        "videos": {
                            "large": {"width": 1920, "height": 1080, "url": "landscape"},
                            "medium": {"width": 1080, "height": 1920, "url": "portrait"},
                        },
                    }
                ]
            },
        )

        with (
            patch("src.services.video_service.requests.get", return_value=response, create=True) as get,
            patch("src.services.video_service.is_video_used", return_value=False),
        ):
            self.assertEqual(service.search_videos(["discipline"], count=1), [("pixabay_456", "portrait")])

        self.assertEqual(get.call_args.kwargs["params"]["q"], "discipline vertical")

    def test_multi_source_video_search_fills_missing_pexels_results_from_pixabay(self):
        primary = types.SimpleNamespace(
            search_videos=lambda queries, count=6: [("pexels_1", "pexels-url")],
            download_video=lambda url, filename: "pexels-path",
        )
        fallback = types.SimpleNamespace(
            search_videos=lambda queries, count=6: [("pixabay_2", "pixabay-url")],
            download_video=lambda url, filename: "pixabay-path",
        )
        service = MultiSourceVideoService(primary, [fallback])

        self.assertEqual(
            service.search_videos(["discipline"], count=2),
            [("pexels_1", "pexels-url"), ("pixabay_2", "pixabay-url")],
        )

    def test_multi_source_video_search_ranks_candidates_across_all_providers(self):
        primary = types.SimpleNamespace(
            search_candidates=lambda queries, count=6: [VideoCandidate("pexels_1", "pexels-url", 3.0, "pexels")],
            download_video=lambda url, filename: "pexels-path",
        )
        pixabay = types.SimpleNamespace(
            search_candidates=lambda queries, count=6: [VideoCandidate("pixabay_2", "pixabay-url", 9.0, "pixabay")],
            download_video=lambda url, filename: "pixabay-path",
        )
        coverr = types.SimpleNamespace(
            search_candidates=lambda queries, count=6: [VideoCandidate("coverr_3", "coverr-url", 6.0, "coverr")],
            download_video=lambda url, filename: "coverr-path",
        )
        service = MultiSourceVideoService(primary, [pixabay, coverr])

        self.assertEqual(
            service.search_videos(["discipline"], count=2),
            [("pixabay_2", "pixabay-url"), ("coverr_3", "coverr-url")],
        )

    def test_multi_source_video_search_avoids_single_source_monopoly_when_possible(self):
        primary = types.SimpleNamespace(
            search_candidates=lambda queries, count=6: [
                VideoCandidate("pexels_1", "pexels-1-url", 10.0, "pexels"),
                VideoCandidate("pexels_2", "pexels-2-url", 9.0, "pexels"),
                VideoCandidate("pexels_3", "pexels-3-url", 8.0, "pexels"),
            ],
            download_video=lambda url, filename: "pexels-path",
        )
        pixabay = types.SimpleNamespace(
            search_candidates=lambda queries, count=6: [VideoCandidate("pixabay_1", "pixabay-url", 7.0, "pixabay")],
            download_video=lambda url, filename: "pixabay-path",
        )
        service = MultiSourceVideoService(primary, [pixabay])

        self.assertEqual(
            service.search_videos(["discipline"], count=3),
            [("pexels_1", "pexels-1-url"), ("pexels_2", "pexels-2-url"), ("pixabay_1", "pixabay-url")],
        )

    def test_video_asset_validator_rejects_missing_file(self):
        result = VideoAssetValidator().validate("missing-file.mp4")

        self.assertFalse(result.valid)
        self.assertIn("file not found", result.reason)

    def test_video_asset_validator_accepts_vertical_video(self):
        class FakeClip:
            w = 1080
            h = 1920
            duration = 4.0

            def close(self):
                pass

        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.getsize", return_value=1024),
            patch.dict("sys.modules", {"moviepy": types.SimpleNamespace(VideoFileClip=lambda path: FakeClip())}),
        ):
            result = VideoAssetValidator().validate("video.mp4")

        self.assertTrue(result.valid)
        self.assertEqual(result.width, 1080)
        self.assertEqual(result.height, 1920)

    def test_video_asset_validator_rejects_landscape_video(self):
        class FakeClip:
            w = 1920
            h = 1080
            duration = 4.0

            def close(self):
                pass

        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.getsize", return_value=1024),
            patch.dict("sys.modules", {"moviepy": types.SimpleNamespace(VideoFileClip=lambda path: FakeClip())}),
        ):
            result = VideoAssetValidator().validate("video.mp4")

        self.assertFalse(result.valid)
        self.assertIn("not vertical", result.reason)

    def test_coverr_video_search_uses_bearer_auth_and_download_url(self):
        service = CoverrVideoService("key", "assets")
        response = types.SimpleNamespace(
            status_code=200,
            json=lambda: {
                "hits": [
                    {
                        "id": "abc123",
                        "is_vertical": True,
                        "urls": {
                            "mp4": "stream-url",
                            "mp4_download": "download-url",
                        },
                    }
                ]
            },
        )

        with (
            patch("src.services.video_service.requests.get", return_value=response, create=True) as get,
            patch("src.services.video_service.is_video_used", return_value=False),
        ):
            self.assertEqual(service.search_videos(["discipline"], count=1), [("coverr_abc123", "download-url")])

        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Bearer key")
        self.assertTrue(get.call_args.kwargs["params"]["urls"])
        self.assertEqual(get.call_args.kwargs["params"]["query"], "discipline vertical")

    def test_pixabay_video_search_rejects_landscape_only_results(self):
        service = PixabayVideoService("key", "assets")
        response = types.SimpleNamespace(
            status_code=200,
            json=lambda: {
                "hits": [
                    {
                        "id": 456,
                        "tags": "gym, discipline",
                        "videos": {
                            "large": {"width": 1920, "height": 1080, "url": "landscape"},
                            "medium": {"width": 1280, "height": 720, "url": "landscape-medium"},
                        },
                    }
                ]
            },
        )

        with (
            patch("src.services.video_service.requests.get", return_value=response, create=True),
            patch("src.services.video_service.is_video_used", return_value=False),
        ):
            self.assertEqual(service.search_videos(["discipline"], count=1), [])

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
