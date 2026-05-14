import unittest

from tools.migrate_sqlite_to_postgres import SQLiteToPostgresMigrator, TableMigration


class SQLiteToPostgresMigrationTests(unittest.TestCase):
    def test_normalizes_windows_output_path_to_container_path(self):
        migrator = SQLiteToPostgresMigrator("video_history.db", "postgresql://user:pass@postgres/db")

        self.assertEqual(
            migrator._normalize_runtime_path(r"D:\sosyal_medya_icerik_uretimi\outputs\2026-05-13\video.mp4"),
            "/app/outputs/2026-05-13/video.mp4",
        )

    def test_normalizes_bad_rebased_container_windows_path(self):
        migrator = SQLiteToPostgresMigrator("video_history.db", "postgresql://user:pass@postgres/db")

        self.assertEqual(
            migrator._normalize_runtime_path(r"/app/D:\sosyal_medya_icerik_uretimi\outputs\2026-05-13\video.mp4"),
            "/app/outputs/2026-05-13/video.mp4",
        )

    def test_dedupe_prefers_scheduled_row_over_path_failure_duplicate(self):
        migrator = SQLiteToPostgresMigrator("video_history.db", "postgresql://user:pass@postgres/db")
        table = TableMigration("tiktok_uploads", "final_video_path", ("id", "final_video_path", "status", "error"))

        rows = migrator._dedupe_rows(
            table,
            [
                {"id": 3, "final_video_path": "/app/outputs/video.mp4", "status": "scheduled", "error": None},
                {
                    "id": 7,
                    "final_video_path": "/app/outputs/video.mp4",
                    "status": "failed",
                    "error": "Video file was not found: D:\\video.mp4",
                },
            ],
        )

        self.assertEqual(rows, [{"id": 3, "final_video_path": "/app/outputs/video.mp4", "status": "scheduled", "error": None}])


if __name__ == "__main__":
    unittest.main()
