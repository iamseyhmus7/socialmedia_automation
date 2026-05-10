import hashlib
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from difflib import SequenceMatcher

from src.core.settings import get_settings


class Database:
    def __init__(self):
        self.db_path = get_settings().db_path
        self._init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS used_videos (
                    id INTEGER PRIMARY KEY,
                    pexels_id TEXT UNIQUE,
                    niche TEXT,
                    used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._ensure_column(cursor, "used_videos", "source", "TEXT DEFAULT 'pexels'")
            self._ensure_column(cursor, "used_videos", "status", "TEXT DEFAULT 'approved'")
            self._ensure_column(cursor, "used_videos", "asset_path", "TEXT")
            self._ensure_column(cursor, "used_videos", "final_video_path", "TEXT")
            cursor.execute("UPDATE used_videos SET status = 'approved' WHERE status IS NULL")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS used_music (
                    id INTEGER PRIMARY KEY,
                    freesound_id TEXT UNIQUE,
                    query TEXT,
                    name TEXT,
                    asset_path TEXT,
                    final_video_path TEXT,
                    status TEXT DEFAULT 'approved',
                    used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS used_scripts (
                    id INTEGER PRIMARY KEY,
                    script_hash TEXT UNIQUE,
                    hook_hash TEXT,
                    theme_hash TEXT,
                    hook TEXT,
                    body TEXT,
                    outro TEXT,
                    script_json TEXT,
                    final_video_path TEXT,
                    status TEXT DEFAULT 'approved',
                    used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS youtube_metadata (
                    id INTEGER PRIMARY KEY,
                    final_video_path TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    tags_json TEXT DEFAULT '[]',
                    status TEXT DEFAULT 'ready',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute("UPDATE used_music SET status = 'approved' WHERE status IS NULL")
            cursor.execute("UPDATE used_scripts SET status = 'approved' WHERE status IS NULL")
            cursor.execute("DROP TABLE IF EXISTS used_voiceovers")
            conn.commit()

    def _ensure_column(self, cursor, table_name, column_name, definition):
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = {row[1] for row in cursor.fetchall()}
        if column_name not in columns:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

    def is_video_used(self, pexels_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM used_videos WHERE pexels_id = ? AND (status = 'approved' OR status IS NULL)",
                (pexels_id,),
            )
            return cursor.fetchone() is not None

    def mark_video_as_used(self, pexels_id, niche, asset_path=None, final_video_path=None, status="approved"):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO used_videos (pexels_id, niche, source, status, asset_path, final_video_path)
                VALUES (?, ?, 'pexels', ?, ?, ?)
                ON CONFLICT(pexels_id) DO UPDATE SET
                    niche = excluded.niche,
                    status = excluded.status,
                    asset_path = excluded.asset_path,
                    final_video_path = excluded.final_video_path,
                    used_at = CURRENT_TIMESTAMP
                """,
                (pexels_id, niche, status, asset_path, final_video_path),
            )
            conn.commit()

    def is_music_used(self, freesound_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM used_music WHERE freesound_id = ? AND (status = 'approved' OR status IS NULL)",
                (freesound_id,),
            )
            return cursor.fetchone() is not None

    def mark_music_as_used(self, freesound_id, query=None, name=None, asset_path=None, final_video_path=None, status="approved"):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO used_music (freesound_id, query, name, asset_path, final_video_path, status)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(freesound_id) DO UPDATE SET
                    query = excluded.query,
                    name = excluded.name,
                    asset_path = excluded.asset_path,
                    final_video_path = excluded.final_video_path,
                    status = excluded.status,
                    used_at = CURRENT_TIMESTAMP
                """,
                (freesound_id, query, name, asset_path, final_video_path, status),
            )
            conn.commit()

    def script_fingerprint(self, script_data):
        hook = str(script_data.get("hook", ""))
        body = str(script_data.get("body", ""))
        outro = str(script_data.get("outro", ""))
        theme = " ".join(
            str(value)
            for value in [
                script_data.get("hook_pexels_arama_terimi", ""),
                script_data.get("pexels_arama_temasi", ""),
                " ".join(script_data.get("pexels_anahtar_kelimeleri") or []),
            ]
            if value
        )
        script_norm = self._normalize_text(" ".join([hook, body, outro]))
        hook_norm = self._normalize_text(hook)
        theme_norm = self._normalize_text(theme)
        return {
            "script_hash": self._hash_text(script_norm),
            "hook_hash": self._hash_text(hook_norm),
            "theme_hash": self._hash_text(theme_norm),
            "script_norm": script_norm,
            "hook_norm": hook_norm,
            "theme_norm": theme_norm,
        }

    def is_script_used_or_similar(self, script_data, hook_threshold=0.88, theme_threshold=0.90):
        fingerprint = self.script_fingerprint(script_data)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT script_hash, hook, hook_hash, theme_hash, script_json
                FROM used_scripts
                WHERE status = 'approved' OR status IS NULL
                """
            )
            for script_hash, hook, hook_hash, theme_hash, script_json in cursor.fetchall():
                if script_hash == fingerprint["script_hash"]:
                    return True
                if hook_hash == fingerprint["hook_hash"] or theme_hash == fingerprint["theme_hash"]:
                    return True
                existing_theme = ""
                if script_json:
                    try:
                        existing_data = json.loads(script_json)
                        existing_theme = self.script_fingerprint(existing_data)["theme_norm"]
                    except (TypeError, ValueError, json.JSONDecodeError):
                        existing_theme = ""
                hook_score = SequenceMatcher(None, fingerprint["hook_norm"], self._normalize_text(hook or "")).ratio()
                theme_score = SequenceMatcher(None, fingerprint["theme_norm"], existing_theme).ratio() if existing_theme else 0
                if hook_score >= hook_threshold or theme_score >= theme_threshold:
                    return True
        return False

    def mark_script_as_used(self, script_data, final_video_path=None, status="approved"):
        fingerprint = self.script_fingerprint(script_data)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO used_scripts (
                    script_hash, hook_hash, theme_hash, hook, body, outro, script_json, final_video_path, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(script_hash) DO UPDATE SET
                    hook = excluded.hook,
                    body = excluded.body,
                    outro = excluded.outro,
                    script_json = excluded.script_json,
                    final_video_path = excluded.final_video_path,
                    status = excluded.status,
                    used_at = CURRENT_TIMESTAMP
                """,
                (
                    fingerprint["script_hash"],
                    fingerprint["hook_hash"],
                    fingerprint["theme_hash"],
                    script_data.get("hook"),
                    script_data.get("body"),
                    script_data.get("outro"),
                    json.dumps(script_data, ensure_ascii=False),
                    final_video_path,
                    status,
                ),
            )
            conn.commit()
        return fingerprint["script_hash"]

    def save_youtube_metadata(self, final_video_path, title, description="", tags=None, status="ready"):
        final_video_path = os.path.abspath(final_video_path)
        tags = tags or []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO youtube_metadata (final_video_path, title, description, tags_json, status)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(final_video_path) DO UPDATE SET
                    title = excluded.title,
                    description = excluded.description,
                    tags_json = excluded.tags_json,
                    status = excluded.status,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    final_video_path,
                    title,
                    description or "",
                    json.dumps(tags, ensure_ascii=False),
                    status,
                ),
            )
            conn.commit()

    def get_youtube_metadata(self, final_video_path):
        final_video_path = os.path.abspath(final_video_path)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT title, description, tags_json
                FROM youtube_metadata
                WHERE final_video_path = ?
                """,
                (final_video_path,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        title, description, tags_json = row
        try:
            tags = json.loads(tags_json or "[]")
        except json.JSONDecodeError:
            tags = []
        if not isinstance(tags, list):
            tags = []
        return {
            "title": title,
            "description": description or "",
            "tags": tags,
        }

    def record_approved_state(self, state, niche="motivation"):
        final_video_path = state.get("final_video_path")
        script_data = state.get("script_data")
        if script_data:
            self.mark_script_as_used(script_data, final_video_path=final_video_path)

        for path in state.get("video_paths", []):
            pexels_id = self._extract_id(path, "raw_")
            if pexels_id:
                self.mark_video_as_used(pexels_id, niche, asset_path=path, final_video_path=final_video_path)

        music_path = state.get("music_path")
        music_id = self._extract_id(music_path, "music_") if music_path else None
        if music_id:
            query = script_data.get("freesound_arama_terimi") if script_data else None
            self.mark_music_as_used(music_id, query=query, asset_path=music_path, final_video_path=final_video_path)

    def _normalize_text(self, text):
        text = str(text or "").lower()
        text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _hash_text(self, text):
        return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()

    def _extract_id(self, path, prefix):
        if not path:
            return None
        filename = os.path.basename(path)
        if not filename.startswith(prefix):
            return None
        value = filename[len(prefix):].split(".", 1)[0]
        return value or None


def init_db():
    Database()


def is_video_used(pexels_id):
    return Database().is_video_used(pexels_id)


def mark_video_as_used(pexels_id, niche, asset_path=None, final_video_path=None, status="approved"):
    Database().mark_video_as_used(pexels_id, niche, asset_path, final_video_path, status)


def is_music_used(freesound_id):
    return Database().is_music_used(freesound_id)


def mark_music_as_used(freesound_id, query=None, name=None, asset_path=None, final_video_path=None, status="approved"):
    Database().mark_music_as_used(freesound_id, query, name, asset_path, final_video_path, status)


def is_script_used_or_similar(script_data, hook_threshold=0.88, theme_threshold=0.90):
    return Database().is_script_used_or_similar(script_data, hook_threshold, theme_threshold)


def save_youtube_metadata(final_video_path, title, description="", tags=None, status="ready"):
    Database().save_youtube_metadata(final_video_path, title, description, tags, status)


def get_youtube_metadata(final_video_path):
    return Database().get_youtube_metadata(final_video_path)


def record_approved_state(state, niche="motivation"):
    Database().record_approved_state(state, niche)


if __name__ == "__main__":
    init_db()
    print("Veritabani hazir ve optimize edildi.")
