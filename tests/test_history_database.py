import os
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))
import database


class HistoryDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "history.db")
        self.settings = types.SimpleNamespace(db_path=self.db_path)
        self.settings_patch = patch.object(database, "get_settings", return_value=self.settings)
        self.settings_patch.start()

    def tearDown(self):
        self.settings_patch.stop()
        self.tmp.cleanup()

    def test_migration_keeps_used_videos_and_adds_history_tables(self):
        db = database.Database()

        conn = sqlite3.connect(self.db_path)
        try:
            tables = {
                row[0]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            video_columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(used_videos)")
            }
        finally:
            conn.close()

            self.assertIn("used_videos", tables)
            self.assertIn("used_music", tables)
            self.assertIn("used_scripts", tables)
            self.assertIn("youtube_metadata", tables)
            self.assertIn("youtube_uploads", tables)
            self.assertIn("tiktok_metadata", tables)
            self.assertIn("tiktok_uploads", tables)
            self.assertNotIn("used_voiceovers", tables)
            self.assertIn("status", video_columns)
            self.assertIn("asset_path", video_columns)

    def test_record_approved_state_persists_video_music_and_script(self):
        db = database.Database()

        db.record_approved_state(
            {
                "script_data": {
                    "hook": "Discipline starts in silence.",
                    "body": "Nobody sees the first choice.",
                    "outro": "Make it before the world wakes.",
                    "freesound_arama_terimi": "low cinematic piano",
                },
                "video_paths": [
                    os.path.join(self.tmp.name, "raw_12345.mp4"),
                    os.path.join(self.tmp.name, "raw_67890.mp4"),
                ],
                "music_path": os.path.join(self.tmp.name, "music_555.mp3"),
                "final_video_path": os.path.join(self.tmp.name, "final.mp4"),
            }
        )

        conn = sqlite3.connect(self.db_path)
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM used_videos").fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM used_music").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM used_scripts").fetchone()[0], 1)
        finally:
            conn.close()

        self.assertTrue(db.is_video_used("12345"))
        self.assertTrue(db.is_music_used("555"))

    def test_youtube_metadata_is_saved_by_final_video_path(self):
        db = database.Database()
        video_path = os.path.join(self.tmp.name, "final.mp4")

        db.save_youtube_metadata(
            video_path,
            "You are wasting your edge.",
            "A short discipline reminder.",
            ["motivation", "shorts"],
        )

        metadata = db.get_youtube_metadata(video_path)

        self.assertEqual(metadata["title"], "You are wasting your edge.")
        self.assertEqual(metadata["description"], "A short discipline reminder.")
        self.assertEqual(metadata["tags"], ["motivation", "shorts"])

    def test_youtube_upload_records_publish_times(self):
        db = database.Database()
        video_path = os.path.join(self.tmp.name, "final.mp4")

        db.record_youtube_upload(
            video_path,
            youtube_video_id="abc123",
            youtube_url="https://www.youtube.com/watch?v=abc123",
            publish_at="2026-05-09T10:00:00Z",
        )

        self.assertEqual(db.get_youtube_publish_times(), ["2026-05-09T10:00:00Z"])
        self.assertTrue(db.is_youtube_publish_time_occupied("2026-05-09T10:00:00Z"))

    def test_tiktok_upload_records_publish_times_and_due_items(self):
        db = database.Database()
        video_path = os.path.join(self.tmp.name, "final.mp4")

        db.save_tiktok_metadata(video_path, "TikTok title", "Caption", ["motivation"])
        db.record_tiktok_upload(video_path, publish_at="2026-05-09T10:00:00Z")

        self.assertEqual(db.get_tiktok_metadata(video_path)["title"], "TikTok title")
        self.assertEqual(db.get_tiktok_publish_times(), ["2026-05-09T10:00:00Z"])
        self.assertTrue(db.is_tiktok_publish_time_occupied("2026-05-09T10:00:00Z"))
        self.assertEqual(
            db.get_due_tiktok_uploads("2026-05-09T10:00:00Z"),
            [{"final_video_path": os.path.abspath(video_path), "publish_at": "2026-05-09T10:00:00Z"}],
        )
        self.assertEqual(
            db.get_next_scheduled_tiktok_upload(),
            {"final_video_path": os.path.abspath(video_path), "publish_at": "2026-05-09T10:00:00Z"},
        )

    def test_script_similarity_blocks_near_duplicate_approved_scripts(self):
        db = database.Database()
        script = {
            "hook": "Your excuses are costing you.",
            "body": "Every delay becomes the future you complain about.",
            "outro": "Choose discipline before comfort chooses for you.",
            "hook_pexels_arama_terimi": "athlete training alone before sunrise",
            "pexels_arama_temasi": "discipline under pressure",
            "pexels_anahtar_kelimeleri": ["lonely runner", "dark gym"],
        }
        db.mark_script_as_used(script)

        near_duplicate = dict(script)
        near_duplicate["hook"] = "Your excuses are costing you"

        self.assertTrue(db.is_script_used_or_similar(near_duplicate))


if __name__ == "__main__":
    unittest.main()
