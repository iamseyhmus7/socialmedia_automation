from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from dataclasses import dataclass


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database import PostgresDatabase
from src.core.settings import get_settings


@dataclass(frozen=True)
class TableMigration:
    name: str
    conflict_column: str
    columns: tuple[str, ...]


TABLES: tuple[TableMigration, ...] = (
    TableMigration("used_videos", "pexels_id", ("id", "pexels_id", "niche", "used_at", "source", "status", "asset_path", "final_video_path")),
    TableMigration("used_music", "freesound_id", ("id", "freesound_id", "query", "name", "asset_path", "final_video_path", "status", "used_at", "source")),
    TableMigration(
        "used_scripts",
        "script_hash",
        ("id", "script_hash", "hook_hash", "theme_hash", "hook", "body", "outro", "script_json", "final_video_path", "status", "used_at"),
    ),
    TableMigration(
        "youtube_metadata",
        "final_video_path",
        ("id", "final_video_path", "title", "description", "tags_json", "status", "created_at", "updated_at"),
    ),
    TableMigration(
        "youtube_uploads",
        "final_video_path",
        ("id", "final_video_path", "youtube_video_id", "youtube_url", "publish_at", "status", "created_at", "updated_at"),
    ),
    TableMigration(
        "tiktok_metadata",
        "final_video_path",
        ("id", "final_video_path", "title", "description", "tags_json", "status", "created_at", "updated_at"),
    ),
    TableMigration(
        "tiktok_uploads",
        "final_video_path",
        ("id", "final_video_path", "tiktok_publish_id", "tiktok_url", "publish_at", "status", "error", "created_at", "updated_at"),
    ),
)


class SQLiteToPostgresMigrator:
    PATH_COLUMNS = {"asset_path", "final_video_path"}

    def __init__(self, sqlite_path: str, database_url: str, container_root: str = "/app"):
        self.sqlite_path = sqlite_path
        self.database_url = database_url
        self.container_root = container_root.rstrip("/")

    def migrate(self) -> None:
        if not os.path.exists(self.sqlite_path):
            raise FileNotFoundError(f"SQLite database not found: {self.sqlite_path}")

        PostgresDatabase(self.database_url)
        sqlite_conn = sqlite3.connect(self.sqlite_path)
        sqlite_conn.row_factory = sqlite3.Row
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("psycopg paketi kurulu degil. `pip install -r requirements.txt` calistirin.") from exc

        with psycopg.connect(self.database_url) as pg_conn:
            for table in TABLES:
                count = self._migrate_table(sqlite_conn, pg_conn, table)
                print(f"[MIGRATE] {table.name}: {count} rows")
            pg_conn.commit()

    def _migrate_table(self, sqlite_conn, pg_conn, table: TableMigration) -> int:
        rows = sqlite_conn.execute(f"SELECT {', '.join(table.columns)} FROM {table.name} ORDER BY id ASC").fetchall()
        if not rows:
            return 0
        normalized_rows = self._dedupe_rows(table, [self._normalize_row(table, row) for row in rows])

        columns_sql = ", ".join(table.columns)
        placeholders_sql = ", ".join("%s" for _column in table.columns)
        update_columns = [column for column in table.columns if column not in {"id", table.conflict_column}]
        update_sql = ", ".join(f"{column} = EXCLUDED.{column}" for column in update_columns)
        sql = (
            f"INSERT INTO {table.name} ({columns_sql}) VALUES ({placeholders_sql}) "
            f"ON CONFLICT ({table.conflict_column}) DO UPDATE SET {update_sql}"
        )

        values = [tuple(row[column] for column in table.columns) for row in normalized_rows]
        with pg_conn.cursor() as cursor:
            cursor.executemany(sql, values)
            self._sync_sequence(cursor, table.name)
        return len(normalized_rows)

    def _normalize_row(self, table: TableMigration, row) -> dict:
        normalized = {column: row[column] for column in table.columns}
        for column in self.PATH_COLUMNS & set(table.columns):
            normalized[column] = self._normalize_runtime_path(normalized[column])
        return normalized

    def _dedupe_rows(self, table: TableMigration, rows: list[dict]) -> list[dict]:
        by_key = {}
        for row in rows:
            key = row.get(table.conflict_column)
            if key is None:
                by_key[(row.get("id"), key)] = row
                continue
            current = by_key.get(key)
            if current is None or self._row_score(row) >= self._row_score(current):
                by_key[key] = row
        return list(by_key.values())

    def _row_score(self, row: dict) -> tuple[int, int]:
        status = str(row.get("status") or "").lower()
        error = str(row.get("error") or "")
        if status == "failed" and "Video file was not found" in error:
            status_score = -10
        else:
            status_score = {
                "uploaded": 50,
                "processing": 40,
                "scheduled": 30,
                "ready": 20,
                "approved": 20,
                "failed": 10,
            }.get(status, 0)
        return (status_score, int(row.get("id") or 0))

    def _normalize_runtime_path(self, value):
        if not value:
            return value
        normalized = str(value).replace("\\", "/")
        if normalized.startswith(f"{self.container_root}/") and len(normalized) > len(self.container_root) + 2:
            next_value = normalized[len(self.container_root) + 1:]
            if len(next_value) > 1 and next_value[1] == ":":
                normalized = next_value
            else:
                return normalized
        if normalized.startswith(f"{self.container_root}/"):
            return normalized
        if normalized.startswith("/app/") and len(normalized) > 7 and normalized[6] == ":":
            normalized = normalized[len("/app/"):]
        for marker in ["/outputs/", "/assets/", "/user_data/"]:
            if marker in normalized:
                relative_path = normalized.split(marker, 1)[1]
                return f"{self.container_root}{marker}{relative_path}"
        return value

    def _sync_sequence(self, cursor, table_name: str) -> None:
        cursor.execute(f"SELECT MAX(id) FROM {table_name}")
        max_id = cursor.fetchone()[0]
        if max_id is None:
            return
        cursor.execute("SELECT setval(pg_get_serial_sequence(%s, 'id'), %s, true)", (table_name, max_id))


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Migrate local SQLite video history to PostgreSQL.")
    parser.add_argument("--sqlite-path", default=settings.db_path, help="Path to video_history.db")
    parser.add_argument("--database-url", default=settings.database_url, help="PostgreSQL DATABASE_URL")
    parser.add_argument("--container-root", default="/app", help="Runtime project root used inside Docker containers")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.database_url:
        raise RuntimeError("DATABASE_URL is required for PostgreSQL migration.")
    SQLiteToPostgresMigrator(args.sqlite_path, args.database_url, args.container_root).migrate()


if __name__ == "__main__":
    main()
