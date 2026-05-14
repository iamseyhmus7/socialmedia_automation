import json
import os
import tempfile
import unittest

from src.services.tiktok_upload_service import TikTokUploadService


class FakeResponse:
    def __init__(self, payload=None, ok=True, text=""):
        self.payload = payload if payload is not None else {}
        self.ok = ok
        self.text = text or json.dumps(self.payload)

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.posts = []
        self.puts = []

    def post(self, url, data=None, json=None, headers=None, timeout=None):
        self.posts.append({"url": url, "data": data, "json": json, "headers": headers, "timeout": timeout})
        if url.endswith("/creator_info/query/"):
            return FakeResponse(
                {
                    "data": {"privacy_level_options": ["SELF_ONLY", "PUBLIC_TO_EVERYONE"]},
                    "error": {"code": "ok", "message": ""},
                }
            )
        if url.endswith("/video/init/"):
            return FakeResponse(
                {
                    "data": {"publish_id": "v_pub_123", "upload_url": "https://upload.tiktok.test/video"},
                    "error": {"code": "ok", "message": ""},
                }
            )
        return FakeResponse({"error": {"code": "unexpected", "message": "unexpected post"}}, ok=False)

    def put(self, url, headers=None, data=None, timeout=None):
        self.puts.append({"url": url, "headers": headers, "data": data, "timeout": timeout})
        return FakeResponse({}, ok=True)


class TikTokUploadServiceTests(unittest.TestCase):
    def test_upload_video_initializes_direct_post_and_puts_file(self):
        session = FakeSession()
        with tempfile.TemporaryDirectory() as tmp:
            token_path = os.path.join(tmp, "tiktok_token.json")
            with open(token_path, "w", encoding="utf-8") as token_file:
                json.dump({"access_token": "token", "expires_at": 9999999999}, token_file)
            video_path = os.path.join(tmp, "video.mp4")
            with open(video_path, "wb") as video_file:
                video_file.write(b"video")

            service = TikTokUploadService(
                "client-key",
                "client-secret",
                "http://localhost:8080/tiktok/callback",
                token_path,
                session=session,
                chunk_size=10,
            )
            result = service.upload_video(video_path, {"hook": "Basla", "youtube_tags": ["motivation"]})

        self.assertEqual(result.publish_id, "v_pub_123")
        self.assertEqual(session.posts[0]["headers"]["Authorization"], "Bearer token")
        init_body = session.posts[1]["json"]
        self.assertEqual(init_body["post_info"]["privacy_level"], "SELF_ONLY")
        self.assertEqual(init_body["source_info"]["source"], "FILE_UPLOAD")
        self.assertEqual(init_body["source_info"]["video_size"], 5)
        self.assertEqual(session.puts[0]["url"], "https://upload.tiktok.test/video")
        self.assertEqual(session.puts[0]["headers"]["Content-Range"], "bytes 0-4/5")

    def test_authorization_url_contains_content_posting_scope(self):
        service = TikTokUploadService(
            "client-key",
            "secret",
            "http://localhost:8080/tiktok/callback",
            "token.json",
        )

        url, state = service.authorization_url("state-123", code_challenge="challenge-123")

        self.assertEqual(state, "state-123")
        self.assertIn("client_key=client-key", url)
        self.assertIn("scope=video.publish", url)
        self.assertIn("code_challenge=challenge-123", url)
        self.assertIn("code_challenge_method=S256", url)
        self.assertIn("redirect_uri=http%3A%2F%2Flocalhost%3A8080%2Ftiktok%2Fcallback", url)

    def test_code_challenge_uses_s256_pkce(self):
        service = TikTokUploadService("client-key", "secret", "http://localhost:8080/tiktok/callback", "token.json")

        challenge = service.build_code_challenge("abc123")

        self.assertEqual(challenge, "bKE9UspwyIPg8LsQHkJaiehiTeUdstI5JZOvaoQRgJA")

    def test_save_token_accepts_plain_file_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                service = TikTokUploadService("client-key", "secret", "http://localhost:8080/tiktok/callback", "token.json")

                service._save_token({"access_token": "token", "expires_in": 3600})

                self.assertTrue(os.path.exists("token.json"))
            finally:
                os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
