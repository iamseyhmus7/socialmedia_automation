import unittest

from src.services.youtube_upload_service import YouTubeUploadService


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


if __name__ == "__main__":
    unittest.main()
