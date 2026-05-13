from __future__ import annotations

import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.settings import get_settings
from src.services.tiktok_upload_service import TikTokUploadService


class CallbackHandler(BaseHTTPRequestHandler):
    code: str | None = None
    returned_state: str | None = None
    error: str | None = None
    last_path: str | None = None

    def do_GET(self) -> None:
        CallbackHandler.last_path = self.path
        params = parse_qs(urlparse(self.path).query)
        CallbackHandler.code = (params.get("code") or [None])[0]
        CallbackHandler.returned_state = (params.get("state") or [None])[0]
        CallbackHandler.error = (params.get("error") or params.get("error_description") or [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        if CallbackHandler.code:
            self.wfile.write("TikTok baglantisi tamam. Bu pencereyi kapatabilirsiniz.".encode("utf-8"))
        elif CallbackHandler.error:
            self.wfile.write(f"TikTok baglantisi basarisiz: {CallbackHandler.error}".encode("utf-8"))
        else:
            self.wfile.write("TikTok callback bekleniyor. OAuth linkini acin.".encode("utf-8"))

    def log_message(self, _format: str, *args) -> None:
        return


def create_service() -> TikTokUploadService:
    settings = get_settings()
    return TikTokUploadService(
        settings.tiktok_client_key,
        settings.tiktok_client_secret,
        settings.tiktok_redirect_uri,
        settings.tiktok_token_path,
        settings.tiktok_default_privacy_level,
        settings.tiktok_disable_comment,
        settings.tiktok_disable_duet,
        settings.tiktok_disable_stitch,
        settings.tiktok_is_aigc,
    )


def main() -> None:
    service = create_service()
    scopes = os.getenv("TIKTOK_SCOPES", "video.publish")
    code_verifier = service.build_code_verifier()
    code_challenge = service.build_code_challenge(code_verifier)
    auth_url, expected_state = service.authorization_url(scopes=scopes, code_challenge=code_challenge)
    parsed_redirect = urlparse(service.redirect_uri)

    print("TikTok OAuth URL:")
    print(auth_url)

    if _manual_callback_mode(parsed_redirect):
        callback_url = input("\nTikTok izin verdikten sonra acilan tam callback URL'yi buraya yapistir:\n").strip()
        params = parse_qs(urlparse(callback_url).query)
        code = (params.get("code") or [None])[0]
        returned_state = (params.get("state") or [None])[0]
        error = (params.get("error") or params.get("error_description") or [None])[0]
        if error:
            raise RuntimeError(f"TikTok OAuth failed: {error}")
        if not code:
            raise RuntimeError("Yapistirilan callback URL icinde code bulunamadi.")
        if returned_state != expected_state:
            raise RuntimeError("TikTok OAuth state mismatch.")
        token = service.exchange_code_for_token(code, code_verifier=code_verifier)
        print(f"TikTok token kaydedildi: {service.token_path}")
        print(f"Open ID: {token.get('open_id')}")
        return

    port = parsed_redirect.port or 8080
    bind_host = os.getenv("TIKTOK_CALLBACK_BIND_HOST", "127.0.0.1")
    server = HTTPServer((bind_host, port), CallbackHandler)
    server.timeout = 180

    print(f"\nCallback bekleniyor: {service.redirect_uri}")
    print(f"Local listener: http://{bind_host}:{port}{parsed_redirect.path or '/'}")
    while not CallbackHandler.code and not CallbackHandler.error:
        server.handle_request()
    server.server_close()

    if CallbackHandler.error:
        raise RuntimeError(f"TikTok OAuth failed: {CallbackHandler.error}")
    if not CallbackHandler.code:
        raise RuntimeError(f"TikTok OAuth callback code dondurmedi. Son istek: {CallbackHandler.last_path}")
    if CallbackHandler.returned_state != expected_state:
        raise RuntimeError("TikTok OAuth state mismatch.")

    token = service.exchange_code_for_token(CallbackHandler.code, code_verifier=code_verifier)
    print(f"TikTok token kaydedildi: {service.token_path}")
    print(f"Open ID: {token.get('open_id')}")


def _manual_callback_mode(parsed_redirect) -> bool:
    if os.getenv("TIKTOK_LOGIN_MANUAL", "").strip().lower() in {"1", "true", "yes", "on"}:
        return True
    return (parsed_redirect.hostname or "").lower() not in {"localhost", "127.0.0.1"}


if __name__ == "__main__":
    main()
