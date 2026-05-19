import hashlib
import json
import logging
import os
import re
from contextlib import contextmanager

from src.core.settings import get_settings
from src.services.script_embedding_service import ScriptEmbeddingService


logger = logging.getLogger(__name__)


class Database:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            settings = get_settings()
            database_url = getattr(settings, "database_url", None)
            if not database_url:
                raise RuntimeError("DATABASE_URL ayarlanmamis. PostgreSQL baglantisi kurulamiyor.")
            if not database_url.startswith(("postgresql://", "postgres://")):
                raise RuntimeError("DATABASE_URL PostgreSQL baglanti adresi olmali.")
            cls._instance = PostgresDatabase(database_url)
        return cls._instance


class HistoryDatabase:
    @contextmanager
    def _get_connection(self):
        raise NotImplementedError

    def is_video_used(self, pexels_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM used_videos WHERE pexels_id = %s AND (status = 'approved' OR status IS NULL)",
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
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT(pexels_id) DO UPDATE SET
                    niche = EXCLUDED.niche,
                    source = EXCLUDED.source,
                    status = EXCLUDED.status,
                    asset_path = EXCLUDED.asset_path,
                    final_video_path = EXCLUDED.final_video_path,
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
                "SELECT 1 FROM used_music WHERE freesound_id = %s AND (status = 'approved' OR status IS NULL)",
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
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(freesound_id) DO UPDATE SET
                    query = EXCLUDED.query,
                    name = EXCLUDED.name,
                    asset_path = EXCLUDED.asset_path,
                    final_video_path = EXCLUDED.final_video_path,
                    status = EXCLUDED.status,
                    source = EXCLUDED.source,
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

    def is_script_used_or_similar(self, script_data, semantic_threshold=None):
        return self.find_similar_script_match(script_data, semantic_threshold) is not None

    def find_similar_script_match(self, script_data, semantic_threshold=None):
        settings = get_settings()
        threshold = float(semantic_threshold or getattr(settings, "script_similarity_threshold", 0.80))
        matches = self.find_similar_script_matches(script_data, limit=1)
        if not matches:
            return None
        match = matches[0]
        similarity = float(match.get("similarity") or 0.0)
        if similarity >= threshold:
            logger.info(
                "Script semantic duplicate detected id=%s similarity=%.3f threshold=%.3f hook=%s",
                match.get("id"),
                similarity,
                threshold,
                match.get("hook"),
            )
            match["threshold"] = threshold
            return match
        return None

    def find_similar_script_matches(self, script_data, limit=5):
        settings = get_settings()
        embedding_service = self._script_embedding_service(settings)
        try:
            embedding = embedding_service.embed_script(script_data)
        except Exception as exc:
            logger.warning("Script semantic similarity check skipped: %s", exc)
            return []

        vector = self._vector_literal(embedding)
        limit = max(1, min(int(limit or 5), 20))
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, hook, body, outro, script_json, embedding_text, 1 - (embedding <=> %s::vector) AS similarity
                FROM used_scripts
                WHERE (status = 'approved' OR status IS NULL)
                  AND embedding IS NOT NULL
                  AND embedding_model = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (vector, embedding_service.model_name, vector, limit),
            )
            rows = cursor.fetchall()

        matches = []
        for row in rows:
            script_data = self._script_data_from_history(row[4], row[1], row[2], row[3])
            matches.append({
                "id": row[0],
                "hook": row[1],
                "body": row[2],
                "outro": row[3],
                "script_data": script_data,
                "embedding_text": row[5],
                "similarity": float(row[6] or 0.0),
            })
        return matches

    def mark_script_as_used(self, script_data, final_video_path=None, status="approved"):
        fingerprint = self.script_fingerprint(script_data)
        settings = get_settings()
        embedding_service = self._script_embedding_service(settings)
        embedding = None
        embedding_text = None
        try:
            embedding_text = embedding_service.embedding_text(script_data)
            embedding = embedding_service.embed_script(script_data)
        except Exception as exc:
            logger.warning("Script embedding could not be saved: %s", exc)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO used_scripts (
                    script_hash, hook_hash, theme_hash, hook, body, outro, script_json,
                    final_video_path, status, embedding, embedding_model, embedding_text
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector, %s, %s)
                ON CONFLICT(script_hash) DO UPDATE SET
                    hook = EXCLUDED.hook,
                    body = EXCLUDED.body,
                    outro = EXCLUDED.outro,
                    script_json = EXCLUDED.script_json,
                    final_video_path = EXCLUDED.final_video_path,
                    status = EXCLUDED.status,
                    embedding = EXCLUDED.embedding,
                    embedding_model = EXCLUDED.embedding_model,
                    embedding_text = EXCLUDED.embedding_text,
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
                    self._vector_literal(embedding) if embedding else None,
                    embedding_service.model_name if embedding else None,
                    embedding_text,
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
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT(final_video_path) DO UPDATE SET
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    tags_json = EXCLUDED.tags_json,
                    status = EXCLUDED.status,
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
                WHERE final_video_path = %s
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
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT(final_video_path) DO UPDATE SET
                    youtube_video_id = EXCLUDED.youtube_video_id,
                    youtube_url = EXCLUDED.youtube_url,
                    publish_at = EXCLUDED.publish_at,
                    status = EXCLUDED.status,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (final_video_path, youtube_video_id, youtube_url, publish_at, status),
            )
            conn.commit()

    def get_youtube_publish_times(self, statuses=("scheduled", "uploaded")):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT publish_at
                FROM youtube_uploads
                WHERE publish_at IS NOT NULL
                  AND status = ANY(%s)
                """,
                (list(statuses),),
            )
            return [row[0] for row in cursor.fetchall() if row[0]]

    def is_youtube_publish_time_occupied(self, publish_at, statuses=("scheduled", "uploaded")):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 1
                FROM youtube_uploads
                WHERE publish_at = %s
                  AND status = ANY(%s)
                LIMIT 1
                """,
                (publish_at, list(statuses)),
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
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT(final_video_path) DO UPDATE SET
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    tags_json = EXCLUDED.tags_json,
                    status = EXCLUDED.status,
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
                WHERE final_video_path = %s
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
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT(final_video_path) DO UPDATE SET
                    tiktok_publish_id = EXCLUDED.tiktok_publish_id,
                    tiktok_url = EXCLUDED.tiktok_url,
                    publish_at = EXCLUDED.publish_at,
                    status = EXCLUDED.status,
                    error = EXCLUDED.error,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (final_video_path, tiktok_publish_id, tiktok_url, publish_at, status, error),
            )
            conn.commit()

    def get_tiktok_publish_times(self, statuses=("scheduled", "uploaded", "processing")):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT publish_at
                FROM tiktok_uploads
                WHERE publish_at IS NOT NULL
                  AND status = ANY(%s)
                """,
                (list(statuses),),
            )
            return [row[0] for row in cursor.fetchall() if row[0]]

    def is_tiktok_publish_time_occupied(self, publish_at, statuses=("scheduled", "uploaded", "processing")):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 1
                FROM tiktok_uploads
                WHERE publish_at = %s
                  AND status = ANY(%s)
                LIMIT 1
                """,
                (publish_at, list(statuses)),
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
                  AND publish_at <= %s
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
                SELECT queue_id, platform, final_video_path, publish_at, status
                FROM (
                    SELECT 'youtube:' || id AS queue_id, 'YouTube' AS platform, final_video_path, publish_at, status
                    FROM youtube_uploads
                    WHERE publish_at IS NOT NULL
                      AND status = 'scheduled'
                    UNION ALL
                    SELECT 'tiktok:' || id AS queue_id, 'TikTok' AS platform, final_video_path, publish_at, status
                    FROM tiktok_uploads
                    WHERE publish_at IS NOT NULL
                      AND status = 'scheduled'
                )
                ORDER BY publish_at ASC
                LIMIT %s
                """,
                (limit,),
            )
            return [
                {
                    "queue_id": row[0],
                    "platform": row[1],
                    "final_video_path": row[2],
                    "publish_at": row[3],
                    "status": row[4],
                }
                for row in cursor.fetchall()
            ]

    def get_expired_scheduled_uploads(self, now_utc, limit=50):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT queue_id, platform, final_video_path, publish_at, status
                FROM (
                    SELECT 'youtube:' || id AS queue_id, 'YouTube' AS platform, final_video_path, publish_at, status
                    FROM youtube_uploads
                    WHERE publish_at IS NOT NULL
                      AND status = 'scheduled'
                      AND publish_at < %s
                    UNION ALL
                    SELECT 'tiktok:' || id AS queue_id, 'TikTok' AS platform, final_video_path, publish_at, status
                    FROM tiktok_uploads
                    WHERE publish_at IS NOT NULL
                      AND status = 'scheduled'
                      AND publish_at < %s
                )
                ORDER BY publish_at ASC
                LIMIT %s
                """,
                (now_utc, now_utc, limit),
            )
            return [
                {
                    "queue_id": row[0],
                    "platform": row[1],
                    "final_video_path": row[2],
                    "publish_at": row[3],
                    "status": row[4],
                }
                for row in cursor.fetchall()
            ]

    def mark_expired_scheduled_uploads(self, now_utc):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE youtube_uploads
                SET status = 'expired', updated_at = CURRENT_TIMESTAMP
                WHERE status = 'scheduled'
                  AND publish_at IS NOT NULL
                  AND publish_at < %s
                RETURNING id
                """,
                (now_utc,),
            )
            youtube_count = len(cursor.fetchall())
            cursor.execute(
                """
                UPDATE tiktok_uploads
                SET status = 'expired', updated_at = CURRENT_TIMESTAMP
                WHERE status = 'scheduled'
                  AND publish_at IS NOT NULL
                  AND publish_at < %s
                RETURNING id
                """,
                (now_utc,),
            )
            tiktok_count = len(cursor.fetchall())
            conn.commit()
            return {"YouTube": youtube_count, "TikTok": tiktok_count, "total": youtube_count + tiktok_count}

    def get_upload_detail(self, queue_id):
        platform, record_id = self._parse_queue_id(queue_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if platform == "youtube":
                cursor.execute(
                    """
                    SELECT id, final_video_path, youtube_video_id, youtube_url, publish_at, status, created_at, updated_at
                    FROM youtube_uploads
                    WHERE id = %s
                    """,
                    (record_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                return {
                    "queue_id": f"youtube:{row[0]}",
                    "platform": "YouTube",
                    "final_video_path": row[1],
                    "remote_id": row[2],
                    "remote_url": row[3],
                    "publish_at": row[4],
                    "status": row[5],
                    "created_at": row[6],
                    "updated_at": row[7],
                }

            cursor.execute(
                """
                SELECT id, final_video_path, tiktok_publish_id, tiktok_url, publish_at, status, error, created_at, updated_at
                FROM tiktok_uploads
                WHERE id = %s
                """,
                (record_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "queue_id": f"tiktok:{row[0]}",
                "platform": "TikTok",
                "final_video_path": row[1],
                "remote_id": row[2],
                "remote_url": row[3],
                "publish_at": row[4],
                "status": row[5],
                "error": row[6],
                "created_at": row[7],
                "updated_at": row[8],
            }

    def cancel_scheduled_upload(self, queue_id):
        platform, record_id = self._parse_queue_id(queue_id)
        table_name = self._upload_table_for_platform(platform)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                UPDATE {table_name}
                SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND status = 'scheduled'
                RETURNING id
                """,
                (record_id,),
            )
            row = cursor.fetchone()
            conn.commit()
            return row is not None

    def reschedule_scheduled_upload(self, queue_id, publish_at):
        platform, record_id = self._parse_queue_id(queue_id)
        table_name = self._upload_table_for_platform(platform)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                UPDATE {table_name}
                SET publish_at = %s, status = 'scheduled', updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND status = 'scheduled'
                RETURNING id
                """,
                (publish_at, record_id),
            )
            row = cursor.fetchone()
            conn.commit()
            return row is not None

    def _parse_queue_id(self, queue_id):
        raw = str(queue_id or "").strip().lower()
        if ":" not in raw:
            raise ValueError("Queue id formati platform:id olmali. Ornek: youtube:12")
        platform, raw_id = raw.split(":", 1)
        if platform not in {"youtube", "tiktok"}:
            raise ValueError("Queue platformu youtube veya tiktok olmali.")
        try:
            record_id = int(raw_id)
        except ValueError as exc:
            raise ValueError("Queue id sayisal olmali. Ornek: youtube:12") from exc
        if record_id < 1:
            raise ValueError("Queue id pozitif olmali.")
        return platform, record_id

    def _upload_table_for_platform(self, platform):
        if platform == "youtube":
            return "youtube_uploads"
        if platform == "tiktok":
            return "tiktok_uploads"
        raise ValueError("Queue platformu youtube veya tiktok olmali.")

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

    def _script_embedding_service(self, settings=None):
        if hasattr(self, "_embedding_service"):
            return self._embedding_service
        settings = settings or get_settings()
        return ScriptEmbeddingService(
            getattr(settings, "gemini_api_key", None),
            getattr(settings, "gemini_embedding_model", "gemini-embedding-001"),
            getattr(settings, "script_embedding_dimensions", 768),
        )

    def _vector_literal(self, values):
        if values is None:
            return None
        return "[" + ",".join(str(float(value)) for value in values) + "]"

    def _script_data_from_history(self, script_json, hook, body, outro):
        if script_json:
            try:
                parsed = json.loads(script_json)
                if isinstance(parsed, dict):
                    return parsed
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        return {"hook": hook or "", "body": body or "", "outro": outro or ""}

    def _extract_id(self, path, prefix):
        if not path:
            return None
        filename = os.path.basename(path)
        if not filename.startswith(prefix):
            return None
        value = filename[len(prefix):].split(".", 1)[0]
        return value or None


class PostgresDatabase(HistoryDatabase):
    def __init__(self, database_url):
        self.database_url = database_url
        self._init_db()

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
            except Exception as exc:
                if "extension \"vector\" is not available" in str(exc):
                    raise RuntimeError(
                        "PostgreSQL pgvector extension is not installed on the running server. "
                        "Recreate the postgres container with the pgvector image, without deleting the volume: "
                        "`docker compose up -d --force-recreate postgres`."
                    ) from exc
                raise
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
            self._ensure_column(cursor, "used_scripts", "embedding", "vector(768)")
            self._ensure_column(cursor, "used_scripts", "embedding_model", "TEXT")
            self._ensure_column(cursor, "used_scripts", "embedding_text", "TEXT")
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_used_scripts_embedding_hnsw
                ON used_scripts USING hnsw (embedding vector_cosine_ops)
                WHERE embedding IS NOT NULL
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
              AND table_name = %s
              AND column_name = %s
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
            yield conn
        finally:
            conn.close()


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


def is_script_used_or_similar(script_data, semantic_threshold=None):
    return Database().is_script_used_or_similar(script_data, semantic_threshold)


def find_similar_script_match(script_data, semantic_threshold=None):
    return Database().find_similar_script_match(script_data, semantic_threshold)


def find_similar_script_matches(script_data, limit=5):
    return Database().find_similar_script_matches(script_data, limit)


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


def get_expired_scheduled_uploads(now_utc, limit=50):
    return Database().get_expired_scheduled_uploads(now_utc, limit)


def mark_expired_scheduled_uploads(now_utc):
    return Database().mark_expired_scheduled_uploads(now_utc)


def get_upload_detail(queue_id):
    return Database().get_upload_detail(queue_id)


def cancel_scheduled_upload(queue_id):
    return Database().cancel_scheduled_upload(queue_id)


def reschedule_scheduled_upload(queue_id, publish_at):
    return Database().reschedule_scheduled_upload(queue_id, publish_at)


def record_approved_state(state, niche="motivation"):
    Database().record_approved_state(state, niche)


if __name__ == "__main__":
    init_db()
    print("PostgreSQL veritabani hazir.")
