import os
import sys
import types
import unittest
from contextlib import contextmanager
from unittest.mock import patch

sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))
import database


class FakeEmbeddingService:
    def __init__(self, vector=None, model_name="test-embedding", error=None):
        self.vector = vector or [1.0, 0.0, 0.0]
        self.model_name = model_name
        self.error = error

    def embed_script(self, script_data):
        if self.error:
            raise self.error
        return self.vector

    def embedding_text(self, script_data):
        return " ".join(
            str(script_data.get(key, ""))
            for key in ["hook", "body", "outro"]
            if script_data.get(key)
        )


class FakeCursor:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.statements = []
        self.params = []
        self._fetchone_result = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.statements.append(sql)
        self.params.append(params)
        self._fetchone_result = None
        if "information_schema.columns" in sql:
            self._fetchone_result = None
        return self

    def fetchone(self):
        if self._fetchone_result is not None:
            return self._fetchone_result
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.committed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True


class HistoryDatabaseTests(unittest.TestCase):
    def test_database_url_is_required(self):
        settings = types.SimpleNamespace(database_url=None)

        with patch.object(database, "get_settings", return_value=settings):
            with self.assertRaisesRegex(RuntimeError, "DATABASE_URL"):
                database.Database()

    def test_initialization_uses_postgres_schema_and_backfills_legacy_columns(self):
        cursor = FakeCursor()
        conn = FakeConnection(cursor)
        settings = types.SimpleNamespace(database_url="postgresql://user:pass@localhost/db")

        @contextmanager
        def fake_connection(_db):
            yield conn

        with patch.object(database, "get_settings", return_value=settings):
            with patch.object(database.PostgresDatabase, "_get_connection", fake_connection):
                database.Database()

        sql = "\n".join(cursor.statements)
        self.assertIn("id BIGSERIAL PRIMARY KEY", sql)
        self.assertIn("information_schema.columns", sql)
        self.assertIn("ALTER TABLE used_videos ADD COLUMN source TEXT DEFAULT 'pexels'", sql)
        self.assertIn("ALTER TABLE used_music ADD COLUMN source TEXT DEFAULT 'freesound'", sql)
        self.assertIn("CREATE EXTENSION IF NOT EXISTS vector", sql)
        self.assertIn("ALTER TABLE used_scripts ADD COLUMN embedding vector(768)", sql)
        self.assertIn("ALTER TABLE used_scripts ADD COLUMN embedding_model TEXT", sql)
        self.assertIn("idx_used_scripts_embedding_hnsw", sql)
        self.assertIn("DROP TABLE IF EXISTS used_voiceovers", sql)
        self.assertTrue(conn.committed)

    def test_publish_time_query_uses_postgres_any_array(self):
        cursor = FakeCursor(rows=[("2026-05-09T10:00:00Z",)])
        conn = FakeConnection(cursor)
        db = database.PostgresDatabase.__new__(database.PostgresDatabase)

        @contextmanager
        def fake_connection():
            yield conn

        db._get_connection = fake_connection

        self.assertEqual(db.get_youtube_publish_times(), ["2026-05-09T10:00:00Z"])
        self.assertIn("status = ANY(%s)", cursor.statements[-1])
        self.assertEqual(cursor.params[-1], (["scheduled", "uploaded"],))

    def test_scheduled_uploads_include_queue_ids(self):
        cursor = FakeCursor(rows=[("youtube:12", "YouTube", "/app/outputs/video.mp4", "2026-05-09T10:00:00Z", "scheduled")])
        conn = FakeConnection(cursor)
        db = database.PostgresDatabase.__new__(database.PostgresDatabase)

        @contextmanager
        def fake_connection():
            yield conn

        db._get_connection = fake_connection

        self.assertEqual(
            db.get_scheduled_uploads(),
            [
                {
                    "queue_id": "youtube:12",
                    "platform": "YouTube",
                    "final_video_path": "/app/outputs/video.mp4",
                    "publish_at": "2026-05-09T10:00:00Z",
                    "status": "scheduled",
                }
            ],
        )

    def test_expired_scheduled_uploads_use_now_filter(self):
        cursor = FakeCursor(rows=[("tiktok:7", "TikTok", "/app/outputs/video.mp4", "2026-05-09T10:00:00Z", "scheduled")])
        conn = FakeConnection(cursor)
        db = database.PostgresDatabase.__new__(database.PostgresDatabase)

        @contextmanager
        def fake_connection():
            yield conn

        db._get_connection = fake_connection

        rows = db.get_expired_scheduled_uploads("2026-05-10T00:00:00Z", limit=10)

        self.assertEqual(rows[0]["queue_id"], "tiktok:7")
        self.assertEqual(cursor.params[-1], ("2026-05-10T00:00:00Z", "2026-05-10T00:00:00Z", 10))

    def test_mark_expired_scheduled_uploads_counts_platforms(self):
        cursor = FakeCursor()
        conn = FakeConnection(cursor)
        db = database.PostgresDatabase.__new__(database.PostgresDatabase)
        fetch_results = iter([[(1,), (2,)], [(7,)]])
        cursor.fetchall = lambda: next(fetch_results)

        @contextmanager
        def fake_connection():
            yield conn

        db._get_connection = fake_connection

        self.assertEqual(
            db.mark_expired_scheduled_uploads("2026-05-10T00:00:00Z"),
            {"YouTube": 2, "TikTok": 1, "total": 3},
        )
        self.assertTrue(conn.committed)

    def test_queue_id_parser_accepts_known_platforms(self):
        db = database.PostgresDatabase.__new__(database.PostgresDatabase)

        self.assertEqual(db._parse_queue_id("youtube:12"), ("youtube", 12))
        self.assertEqual(db._parse_queue_id("tiktok:7"), ("tiktok", 7))

    def test_queue_id_parser_rejects_invalid_values(self):
        db = database.PostgresDatabase.__new__(database.PostgresDatabase)

        for value in ["12", "instagram:1", "youtube:x", "youtube:0"]:
            with self.assertRaises(ValueError):
                db._parse_queue_id(value)

    def test_record_approved_state_delegates_video_music_and_script_records(self):
        db = database.PostgresDatabase.__new__(database.PostgresDatabase)
        calls = []
        db.mark_script_as_used = lambda script, final_video_path=None: calls.append(("script", script, final_video_path))
        db.mark_video_as_used = lambda pexels_id, niche, asset_path=None, final_video_path=None: calls.append(
            ("video", pexels_id, niche, asset_path, final_video_path)
        )
        db.mark_music_as_used = lambda music_id, query=None, asset_path=None, final_video_path=None: calls.append(
            ("music", music_id, query, asset_path, final_video_path)
        )

        final_video_path = os.path.abspath("final.mp4")
        script = {"hook": "Start before sunrise.", "freesound_arama_terimi": "cinematic piano"}
        db.record_approved_state(
            {
                "script_data": script,
                "video_paths": [os.path.join("outputs", "raw_12345.mp4")],
                "music_path": os.path.join("outputs", "music_555.mp3"),
                "final_video_path": final_video_path,
            }
        )

        self.assertEqual(
            calls,
            [
                ("script", script, final_video_path),
                ("video", "12345", "motivation", os.path.join("outputs", "raw_12345.mp4"), final_video_path),
                ("music", "555", "cinematic piano", os.path.join("outputs", "music_555.mp3"), final_video_path),
            ],
        )

    def test_script_similarity_uses_embedding_search_for_duplicates(self):
        script = {
            "hook": "Your excuses are costing you.",
            "body": "Every delay becomes the future you complain about.",
            "outro": "Choose discipline before comfort chooses for you.",
            "hook_pexels_arama_terimi": "athlete training alone before sunrise",
            "pexels_arama_temasi": "discipline under pressure",
            "pexels_anahtar_kelimeleri": ["lonely runner", "dark gym"],
        }
        cursor = FakeCursor(rows=[(42, "Old hook", "Old body", "Old outro", None, "Old hook Old body Old outro", 0.91)])
        conn = FakeConnection(cursor)
        db = database.PostgresDatabase.__new__(database.PostgresDatabase)
        db._embedding_service = FakeEmbeddingService(vector=[0.7, 0.2, 0.1])

        @contextmanager
        def fake_connection():
            yield conn

        db._get_connection = fake_connection

        self.assertTrue(db.is_script_used_or_similar(script, semantic_threshold=0.8))
        self.assertIn("embedding <=> %s::vector", cursor.statements[-1])
        self.assertEqual(cursor.params[-1], ("[0.7,0.2,0.1]", "test-embedding", "[0.7,0.2,0.1]"))

    def test_find_similar_script_match_returns_prompt_context(self):
        cursor = FakeCursor(rows=[(42, "Old hook", "Old body", "Old outro", None, "Old hook Old body Old outro", 0.91)])
        conn = FakeConnection(cursor)
        db = database.PostgresDatabase.__new__(database.PostgresDatabase)
        db._embedding_service = FakeEmbeddingService(vector=[0.7, 0.2, 0.1])

        @contextmanager
        def fake_connection():
            yield conn

        db._get_connection = fake_connection

        match = db.find_similar_script_match({"hook": "New pressure story"}, semantic_threshold=0.8)

        self.assertEqual(match["id"], 42)
        self.assertEqual(match["hook"], "Old hook")
        self.assertEqual(match["body"], "Old body")
        self.assertEqual(match["outro"], "Old outro")
        self.assertEqual(match["similarity"], 0.91)

    def test_script_similarity_allows_below_threshold_matches(self):
        cursor = FakeCursor(rows=[(42, "Old hook", "Old body", "Old outro", None, "Old hook Old body Old outro", 0.73)])
        conn = FakeConnection(cursor)
        db = database.PostgresDatabase.__new__(database.PostgresDatabase)
        db._embedding_service = FakeEmbeddingService()

        @contextmanager
        def fake_connection():
            yield conn

        db._get_connection = fake_connection

        self.assertFalse(db.is_script_used_or_similar({"hook": "New pressure story"}, semantic_threshold=0.8))

    def test_script_similarity_falls_back_open_when_embedding_fails(self):
        db = database.PostgresDatabase.__new__(database.PostgresDatabase)
        db._embedding_service = FakeEmbeddingService(error=RuntimeError("quota"))

        self.assertFalse(db.is_script_used_or_similar({"hook": "New pressure story"}))

    def test_mark_script_as_used_saves_embedding_payload(self):
        cursor = FakeCursor()
        conn = FakeConnection(cursor)
        db = database.PostgresDatabase.__new__(database.PostgresDatabase)
        db._embedding_service = FakeEmbeddingService(vector=[0.5, 0.5, 0.0])

        @contextmanager
        def fake_connection():
            yield conn

        db._get_connection = fake_connection

        script_hash = db.mark_script_as_used(
            {
                "hook": "Your excuses are costing you.",
                "body": "Every delay becomes the future you complain about.",
                "outro": "Choose discipline now.",
            },
            final_video_path="final.mp4",
        )

        self.assertTrue(script_hash)
        self.assertIn("embedding, embedding_model, embedding_text", cursor.statements[-1])
        self.assertEqual(cursor.params[-1][-3:], ("[0.5,0.5,0.0]", "test-embedding", "Your excuses are costing you. Every delay becomes the future you complain about. Choose discipline now."))
        self.assertTrue(conn.committed)

if __name__ == "__main__":
    unittest.main()
