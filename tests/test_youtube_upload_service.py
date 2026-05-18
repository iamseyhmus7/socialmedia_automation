import unittest
from unittest.mock import Mock, patch

from src.services.youtube_upload_service import YouTubeAuthenticationError, YouTubeUploadService


class YouTubeUploadServiceTests(unittest.TestCase):
    def test_metadata_uses_hook_as_title_and_adds_shorts_hashtag(self):
        service = YouTubeUploadService("client.json", "token.json")

        metadata = service.build_metadata(
            {
                "hook": "Disiplin seni ozgur yapar",
                "body": "Bugun kucuk bir karar ver.",
                "outro": "Yarin aynaya daha guclu bak.",
            }
        )

        self.assertEqual(metadata.title, "Disiplin seni ozgur yapar")
        self.assertEqual(metadata.privacy_status, "public")
        self.assertEqual(metadata.category_id, "22")
        self.assertIn("#shorts", metadata.description.lower())
        self.assertEqual(metadata.tags, ["motivation", "shorts", "stoicism"])

    def test_metadata_trims_long_title(self):
        service = YouTubeUploadService("client.json", "token.json")

        metadata = service.build_metadata({"hook": "x" * 150})

        self.assertLessEqual(len(metadata.title), 100)
        self.assertTrue(metadata.title.endswith("..."))

    def test_scheduled_publish_uses_private_until_publish_time(self):
        service = YouTubeUploadService("client.json", "token.json", default_privacy_status="public")

        metadata = service.build_metadata(
            {"hook": "Planli yayin"},
            privacy_status="public",
            publish_at="2026-05-09T15:00:00Z",
        )

        self.assertEqual(metadata.privacy_status, "private")
        self.assertEqual(metadata.publish_at, "2026-05-09T15:00:00Z")

    def test_expired_or_revoked_refresh_token_has_actionable_error(self):
        class FakeRefreshError(Exception):
            pass

        credentials = Mock()
        credentials.expired = True
        credentials.refresh_token = "refresh-token"
        credentials.refresh.side_effect = FakeRefreshError("invalid_grant: Token has been expired or revoked.")

        service = YouTubeUploadService("client.json", "token.json")

        with (
            patch("os.path.exists", return_value=True),
            patch.dict(
                "sys.modules",
                {
                    "google.auth.transport.requests": type("Module", (), {"Request": Mock})(),
                    "google.oauth2.credentials": type(
                        "Module",
                        (),
                        {
                            "Credentials": type(
                                "Credentials",
                                (),
                                {"from_authorized_user_file": Mock(return_value=credentials)},
                            )
                        },
                    )(),
                    "google_auth_oauthlib.flow": type("Module", (), {"InstalledAppFlow": Mock})(),
                    "google.auth.exceptions": type("Module", (), {"RefreshError": FakeRefreshError})(),
                },
            ),
        ):
            with self.assertRaisesRegex(YouTubeAuthenticationError, "tools/yt_login.py"):
                service._get_credentials()


if __name__ == "__main__":
    unittest.main()
