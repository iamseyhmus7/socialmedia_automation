import os
import tempfile
import unittest

from src.services.instagram_upload_service import INSTAGRAM_CAPTION_LIMIT, InstagramUploadService


class FakeResponse:
    def __init__(self, payload, ok=True):
        self.payload = payload
        self.ok = ok
        self.text = str(payload)

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.posts = []
        self.gets = []

    def post(self, url, data=None, headers=None, timeout=None):
        self.posts.append({"url": url, "data": data, "headers": headers, "timeout": timeout})
        if url.endswith("/ig-user/media"):
            return FakeResponse({"id": "container123", "uri": "https://rupload.facebook.com/container123"})
        if url == "https://rupload.facebook.com/container123":
            return FakeResponse({"success": True})
        if url.endswith("/ig-user/media_publish"):
            return FakeResponse({"id": "media123"})
        return FakeResponse({"error": {"message": "unexpected post"}}, ok=False)

    def get(self, url, params=None, timeout=None):
        self.gets.append({"url": url, "params": params, "timeout": timeout})
        if url.endswith("/container123"):
            return FakeResponse({"status_code": "FINISHED", "status": "Finished"})
        if url.endswith("/media123"):
            return FakeResponse({"permalink": "https://www.instagram.com/reel/media123/"})
        return FakeResponse({"error": {"message": "unexpected get"}}, ok=False)


class InstagramUploadServiceTests(unittest.TestCase):
    def test_upload_reel_uses_resumable_container_upload_and_publish(self):
        session = FakeSession()
        service = InstagramUploadService(
            "token",
            "ig-user",
            graph_api_version="v24.0",
            session=session,
            poll_interval_seconds=0,
        )
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(b"video")
            video_path = tmp.name

        try:
            result = service.upload_reel(video_path, {"hook": "Basla", "youtube_tags": ["motivation"]})
        finally:
            os.remove(video_path)

        self.assertEqual(result.media_id, "media123")
        self.assertEqual(result.instagram_url, "https://www.instagram.com/reel/media123/")
        self.assertEqual(session.posts[0]["data"]["media_type"], "REELS")
        self.assertEqual(session.posts[0]["data"]["upload_type"], "resumable")
        self.assertEqual(session.posts[0]["data"]["share_to_feed"], "true")
        self.assertEqual(session.posts[1]["headers"]["Authorization"], "OAuth token")
        self.assertEqual(session.posts[1]["headers"]["file_size"], "5")
        self.assertEqual(session.posts[2]["data"]["creation_id"], "container123")
        self.assertEqual(session.gets[0]["params"]["fields"], "status_code,status")
        self.assertEqual(session.gets[1]["params"]["fields"], "permalink")

    def test_caption_is_trimmed_to_instagram_limit(self):
        service = InstagramUploadService("token", "ig-user")

        metadata = service.build_metadata(caption="x" * (INSTAGRAM_CAPTION_LIMIT + 20))

        self.assertEqual(len(metadata.caption), INSTAGRAM_CAPTION_LIMIT)
        self.assertTrue(metadata.caption.endswith("..."))

    def test_missing_credentials_fail_before_upload(self):
        service = InstagramUploadService(None, "ig-user")

        with self.assertRaisesRegex(RuntimeError, "access token or user id"):
            service.upload_reel("missing.mp4", {})

    def test_failed_container_status_raises_clear_error(self):
        class ErrorSession(FakeSession):
            def get(self, url, params=None, timeout=None):
                return FakeResponse({"status_code": "ERROR", "status": "Encoding failed"})

        service = InstagramUploadService(
            "token",
            "ig-user",
            session=ErrorSession(),
            poll_interval_seconds=0,
        )
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(b"video")
            video_path = tmp.name

        try:
            with self.assertRaisesRegex(RuntimeError, "container processing failed"):
                service.upload_reel(video_path, {})
        finally:
            os.remove(video_path)


if __name__ == "__main__":
    unittest.main()
