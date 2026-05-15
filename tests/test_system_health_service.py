import os
import tempfile
import types
import unittest

from src.services.system_health_service import SystemHealthService


class SystemHealthServiceTests(unittest.TestCase):
    def _settings(self, tmp: str, **overrides):
        settings = types.SimpleNamespace(
            base_dir=tmp,
            assets_dir=os.path.join(tmp, "assets"),
            outputs_dir=os.path.join(tmp, "outputs"),
            database_url="postgresql://user:pass@postgres/db",
            gemini_api_key="gemini",
            gemini_model="gemini-test",
            telegram_bot_token="token",
            telegram_chat_id="chat",
            youtube_client_secrets_path=os.path.join(tmp, "youtube_client_secret.json"),
            youtube_token_path=os.path.join(tmp, "youtube_token.json"),
            pexels_api_key="pexels",
            pixabay_api_key=None,
            coverr_api_key=None,
        )
        for key, value in overrides.items():
            setattr(settings, key, value)
        return settings

    def test_health_text_reports_ready_system(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "assets"))
            os.makedirs(os.path.join(tmp, "outputs", "2026-05-15"))
            video_path = os.path.join(tmp, "outputs", "2026-05-15", "video.mp4")
            with open(video_path, "w", encoding="utf-8") as file:
                file.write("video")
            for path in ["youtube_client_secret.json", "youtube_token.json"]:
                with open(os.path.join(tmp, path), "w", encoding="utf-8") as file:
                    file.write("{}")

            service = SystemHealthService(
                self._settings(tmp),
                scheduled_uploads_provider=lambda _limit: [
                    {
                        "platform": "YouTube",
                        "publish_at": "2026-05-15T14:30:00Z",
                        "final_video_path": video_path,
                    }
                ],
            )

            text = service.health_text()

        self.assertIn("PostgreSQL: OK", text)
        self.assertIn("son video: video.mp4", text)
        self.assertIn("Gemini: OK - gemini-test", text)
        self.assertIn("Yayin kuyrugu: OK - sirada YouTube", text)

    def test_health_text_reports_missing_database_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "assets"))
            os.makedirs(os.path.join(tmp, "outputs"))
            service = SystemHealthService(
                self._settings(tmp, database_url=None),
                scheduled_uploads_provider=lambda _limit: [],
            )

            text = service.health_text()

        self.assertIn("PostgreSQL: UYARI - DATABASE_URL ayarlanmamis.", text)

    def test_health_text_captures_database_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "assets"))
            os.makedirs(os.path.join(tmp, "outputs"))

            def failing_provider(_limit):
                raise RuntimeError("connection refused")

            service = SystemHealthService(
                self._settings(tmp),
                scheduled_uploads_provider=failing_provider,
            )

            text = service.health_text()

        self.assertIn("PostgreSQL: UYARI - connection refused", text)
        self.assertIn("Yayin kuyrugu: UYARI - connection refused", text)


if __name__ == "__main__":
    unittest.main()
