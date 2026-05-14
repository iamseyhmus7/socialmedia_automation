import hashlib
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from difflib import SequenceMatcher

from src.core.settings import get_settings


class Database:
    def __new__(cls):
        settings = get_settings()
        database_url = getattr(settings, "database_url", None)
        if database_url and database_url.startswith(("postgresql://", "postgres://")):
            return PostgresDatabase(database_url)
        return SQLiteDatabase(getattr(settings, "db_path"))


class SQLiteDatabase:
    def __init__(self, db_path=None):
        self.db_path = db_path or get_settings().db_path
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
            self._ensure_column(cursor, "used_music", "source", "TEXT DEFAULT 'freesound'")
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
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS youtube_uploads (
                    id INTEGER PRIMARY KEY,
                    final_video_path TEXT UNIQUE NOT NULL,
                    youtube_video_id TEXT,
                    youtube_url TEXT,
                    publish_at TEXT,
                    status TEXT DEFAULT 'scheduled',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_youtube_uploads_publish_at ON youtube_uploads(publish_at)")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS tiktok_metadata (
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
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS tiktok_uploads (
                    id INTEGER PRIMARY KEY,
                    final_video_path TEXT UNIQUE NOT NULL,
                    tiktok_publish_id TEXT,
                    tiktok_url TEXT,
                    publish_at TEXT,
                    status TEXT DEFAULT 'scheduled',
                    error TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tiktok_uploads_publish_at ON tiktok_uploads(publish_at)")
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
        source = self._video_source(pexels_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO used_videos (pexels_id, niche, source, status, asset_path, final_video_path)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(pexels_id) DO UPDATE SET
                    niche = excluded.niche,
                    source = excluded.source,
                    status = excluded.status,
                    asset_path = excluded.asset_path,
                    final_video_path = excluded.final_video_path,
                    used_at = CURRENT_TIMESTAMP
                """,
                (pexels_id, niche, source, status, asset_path, final_video_path),
            )
            conn.commit()

    def _video_source(self, pexels_id):
        value = str(pexels_id)
        if value.startswith("pixabay_"):
            return "pixabay"
        if value.startswith("coverr_"):
            return "coverr"
        return "pexels"

    def is_music_used(self, freesound_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM used_music WHERE freesound_id = ? AND (status = 'approved' OR status IS NULL)",
                (freesound_id,),
            )
            return cursor.fetchone() is not None

    def mark_music_as_used(self, freesound_id, query=None, name=None, asset_path=None, final_video_path=None, status="approved"):
        source = self._music_source(freesound_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO used_music (freesound_id, query, name, asset_path, final_video_path, status, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(freesound_id) DO UPDATE SET
                    query = excluded.query,
                    name = excluded.name,
                    asset_path = excluded.asset_path,
                    final_video_path = excluded.final_video_path,
                    status = excluded.status,
                    source = excluded.source,
                    used_at = CURRENT_TIMESTAMP
                """,
                (freesound_id, query, name, asset_path, final_video_path, status, source),
            )
            conn.commit()

    def _music_source(self, music_id):
        return "freesound"

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

    def record_youtube_upload(
        self,
        final_video_path,
        youtube_video_id=None,
        youtube_url=None,
        publish_at=None,
        status="scheduled",
    ):
        final_video_path = os.path.abspath(final_video_path)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO youtube_uploads (final_video_path, youtube_video_id, youtube_url, publish_at, status)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(final_video_path) DO UPDATE SET
                    youtube_video_id = excluded.youtube_video_id,
                    youtube_url = excluded.youtube_url,
                    publish_at = excluded.publish_at,
                    status = excluded.status,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (final_video_path, youtube_video_id, youtube_url, publish_at, status),
            )
            conn.commit()

    def get_youtube_publish_times(self, statuses=("scheduled", "uploaded")):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ",".join("?" for _status in statuses)
            cursor.execute(
                f"""
                SELECT publish_at
                FROM youtube_uploads
                WHERE publish_at IS NOT NULL
                  AND status IN ({placeholders})
                """,
                tuple(statuses),
            )
            return [row[0] for row in cursor.fetchall() if row[0]]

    def is_youtube_publish_time_occupied(self, publish_at, statuses=("scheduled", "uploaded")):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ",".join("?" for _status in statuses)
            cursor.execute(
                f"""
                SELECT 1
                FROM youtube_uploads
                WHERE publish_at = ?
                  AND status IN ({placeholders})
                LIMIT 1
                """,
                (publish_at, *statuses),
            )
            return cursor.fetchone() is not None

    def save_tiktok_metadata(self, final_video_path, title, description="", tags=None, status="ready"):
        final_video_path = os.path.abspath(final_video_path)
        tags = tags or []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO tiktok_metadata (final_video_path, title, description, tags_json, status)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(final_video_path) DO UPDATE SET
                    title = excluded.title,
                    description = excluded.description,
                    tags_json = excluded.tags_json,
                    status = excluded.status,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (final_video_path, title, description or "", json.dumps(tags, ensure_ascii=False), status),
            )
            conn.commit()

    def get_tiktok_metadata(self, final_video_path):
        final_video_path = os.path.abspath(final_video_path)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT title, description, tags_json
                FROM tiktok_metadata
                WHERE final_video_path = ?
                """,
                (final_video_path,),
            )
            row = cursor.fetchone()

        if not row:
            return self.get_youtube_metadata(final_video_path)

        title, description, tags_json = row
        try:
            tags = json.loads(tags_json or "[]")
        except json.JSONDecodeError:
            tags = []
        if not isinstance(tags, list):
            tags = []
        return {"title": title, "description": description or "", "tags": tags}

    def record_tiktok_upload(
        self,
        final_video_path,
        tiktok_publish_id=None,
        tiktok_url=None,
        publish_at=None,
        status="scheduled",
        error=None,
    ):
        final_video_path = os.path.abspath(final_video_path)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO tiktok_uploads (
                    final_video_path, tiktok_publish_id, tiktok_url, publish_at, status, error
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(final_video_path) DO UPDATE SET
                    tiktok_publish_id = excluded.tiktok_publish_id,
                    tiktok_url = excluded.tiktok_url,
                    publish_at = excluded.publish_at,
                    status = excluded.status,
                    error = excluded.error,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (final_video_path, tiktok_publish_id, tiktok_url, publish_at, status, error),
            )
            conn.commit()

    def get_tiktok_publish_times(self, statuses=("scheduled", "uploaded", "processing")):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ",".join("?" for _status in statuses)
            cursor.execute(
                f"""
                SELECT publish_at
                FROM tiktok_uploads
                WHERE publish_at IS NOT NULL
                  AND status IN ({placeholders})
                """,
                tuple(statuses),
            )
            return [row[0] for row in cursor.fetchall() if row[0]]

    def is_tiktok_publish_time_occupied(self, publish_at, statuses=("scheduled", "uploaded", "processing")):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ",".join("?" for _status in statuses)
            cursor.execute(
                f"""
                SELECT 1
                FROM tiktok_uploads
                WHERE publish_at = ?
                  AND status IN ({placeholders})
                LIMIT 1
                """,
                (publish_at, *statuses),
            )
            return cursor.fetchone() is not None

    def get_due_tiktok_uploads(self, now_utc):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT final_video_path, publish_at
                FROM tiktok_uploads
                WHERE status = 'scheduled'
                  AND publish_at IS NOT NULL
                  AND publish_at <= ?
                ORDER BY publish_at ASC
                """,
                (now_utc,),
            )
            return [{"final_video_path": row[0], "publish_at": row[1]} for row in cursor.fetchall()]

    def get_next_scheduled_tiktok_upload(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT final_video_path, publish_at
                FROM tiktok_uploads
                WHERE status = 'scheduled'
                  AND publish_at IS NOT NULL
                ORDER BY publish_at ASC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {"final_video_path": row[0], "publish_at": row[1]}

    def get_scheduled_uploads(self, limit=20):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT platform, final_video_path, publish_at, status
                FROM (
                    SELECT 'YouTube' AS platform, final_video_path, publish_at, status
                    FROM youtube_uploads
                    WHERE publish_at IS NOT NULL
                      AND status = 'scheduled'
                    UNION ALL
                    SELECT 'TikTok' AS platform, final_video_path, publish_at, status
                    FROM tiktok_uploads
                    WHERE publish_at IS NOT NULL
                      AND status = 'scheduled'
                )
                ORDER BY publish_at ASC
                LIMIT ?
                """,
                (limit,),
            )
            return [
                {
                    "platform": row[0],
                    "final_video_path": row[1],
                    "publish_at": row[2],
                    "status": row[3],
                }
                for row in cursor.fetchall()
            ]

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


class PostgresCursor:
    def __init__(self, cursor):
        self.cursor = cursor

    def execute(self, sql, params=None):
        self.cursor.execute(sql.replace("?", "%s"), params)
        return self

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()


class PostgresDatabase(SQLiteDatabase):
    def __init__(self, database_url):
        self.database_url = database_url
        self._init_db()

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS used_videos (
                    id BIGSERIAL PRIMARY KEY,
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
                    id BIGSERIAL PRIMARY KEY,
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
            self._ensure_column(cursor, "used_music", "source", "TEXT DEFAULT 'freesound'")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS used_scripts (
                    id BIGSERIAL PRIMARY KEY,
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
                    id BIGSERIAL PRIMARY KEY,
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
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS youtube_uploads (
                    id BIGSERIAL PRIMARY KEY,
                    final_video_path TEXT UNIQUE NOT NULL,
                    youtube_video_id TEXT,
                    youtube_url TEXT,
                    publish_at TEXT,
                    status TEXT DEFAULT 'scheduled',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_youtube_uploads_publish_at ON youtube_uploads(publish_at)")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS tiktok_metadata (
                    id BIGSERIAL PRIMARY KEY,
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
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS tiktok_uploads (
                    id BIGSERIAL PRIMARY KEY,
                    final_video_path TEXT UNIQUE NOT NULL,
                    tiktok_publish_id TEXT,
                    tiktok_url TEXT,
                    publish_at TEXT,
                    status TEXT DEFAULT 'scheduled',
                    error TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tiktok_uploads_publish_at ON tiktok_uploads(publish_at)")
            cursor.execute("UPDATE used_music SET status = 'approved' WHERE status IS NULL")
            cursor.execute("UPDATE used_scripts SET status = 'approved' WHERE status IS NULL")
            cursor.execute("DROP TABLE IF EXISTS used_voiceovers")
            conn.commit()

    def _ensure_column(self, cursor, table_name, column_name, definition):
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = ?
              AND column_name = ?
            """,
            (table_name, column_name),
        )
        if cursor.fetchone() is None:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

    def _get_connection(self):
        return self._postgres_connection()

    @contextmanager
    def _postgres_connection(self):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("psycopg paketi kurulu degil. `pip install -r requirements.txt` calistirin.") from exc

        conn = psycopg.connect(self.database_url)
        try:
            yield PostgresConnection(conn)
        finally:
            conn.close()


class PostgresConnection:
    def __init__(self, conn):
        self.conn = conn

    def cursor(self):
        return PostgresCursor(self.conn.cursor())

    def commit(self):
        self.conn.commit()


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


def record_youtube_upload(final_video_path, youtube_video_id=None, youtube_url=None, publish_at=None, status="scheduled"):
    Database().record_youtube_upload(final_video_path, youtube_video_id, youtube_url, publish_at, status)


def get_youtube_publish_times(statuses=("scheduled", "uploaded")):
    return Database().get_youtube_publish_times(statuses)


def is_youtube_publish_time_occupied(publish_at, statuses=("scheduled", "uploaded")):
    return Database().is_youtube_publish_time_occupied(publish_at, statuses)


def save_tiktok_metadata(final_video_path, title, description="", tags=None, status="ready"):
    Database().save_tiktok_metadata(final_video_path, title, description, tags, status)


def get_tiktok_metadata(final_video_path):
    return Database().get_tiktok_metadata(final_video_path)


def record_tiktok_upload(
    final_video_path,
    tiktok_publish_id=None,
    tiktok_url=None,
    publish_at=None,
    status="scheduled",
    error=None,
):
    Database().record_tiktok_upload(final_video_path, tiktok_publish_id, tiktok_url, publish_at, status, error)


def get_tiktok_publish_times(statuses=("scheduled", "uploaded", "processing")):
    return Database().get_tiktok_publish_times(statuses)


def is_tiktok_publish_time_occupied(publish_at, statuses=("scheduled", "uploaded", "processing")):
    return Database().is_tiktok_publish_time_occupied(publish_at, statuses)


def get_due_tiktok_uploads(now_utc):
    return Database().get_due_tiktok_uploads(now_utc)


def get_next_scheduled_tiktok_upload():
    return Database().get_next_scheduled_tiktok_upload()


def get_scheduled_uploads(limit=20):
    return Database().get_scheduled_uploads(limit)


def record_approved_state(state, niche="motivation"):
    Database().record_approved_state(state, niche)


if __name__ == "__main__":
    init_db()
    print("Veritabani hazir ve optimize edildi.")
