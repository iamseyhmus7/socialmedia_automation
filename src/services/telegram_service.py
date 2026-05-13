from __future__ import annotations

import os
import time
from typing import Any


class TelegramService:
    def __init__(self, bot_token: str | None, chat_id: str | None):
        self.token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{self.token}" if self.token else ""
        self.last_update_id: int | None = None

    def send_message(self, text: str) -> bool:
        if not self.token or not self.chat_id:
            print("  [TELEGRAM] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing.")
            return False
        response = self._requests().post(
            f"{self.api_url}/sendMessage",
            json={"chat_id": self.chat_id, "text": text},
            timeout=30,
        )
        if response.status_code == 200:
            print(f"  [TELEGRAM] Sent message: {text[:120]}")
        else:
            print(f"  [TELEGRAM] Message send failed: {response.status_code} {response.text[:200]}")
        return response.status_code == 200

    def send_video(self, video_path: str, caption: str | None = None) -> bool:
        if not self.token or not self.chat_id:
            print("  [TELEGRAM] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing.")
            return False

        print(f"  [TELEGRAM] Sending video: {os.path.basename(video_path)}")
        with open(video_path, "rb") as video:
            response = self._requests().post(
                f"{self.api_url}/sendVideo",
                data={
                    "chat_id": self.chat_id,
                    "caption": caption or "Video is ready.",
                    "supports_streaming": True,
                },
                files={"video": video},
                timeout=120,
            )
        if response.status_code != 200:
            print(f"  [TELEGRAM] Video send failed: {response.status_code} {response.text[:200]}")
        return response.status_code == 200

    def wait_for_message(self, timeout_minutes: int = 15, skip_existing: bool = True) -> str | None:
        print(f"  [TELEGRAM] Waiting for message for up to {timeout_minutes} minutes...")
        if skip_existing or self.last_update_id is None:
            self.last_update_id = self._get_latest_update_id()
        start_time = time.time()
        while (time.time() - start_time) < timeout_minutes * 60:
            try:
                response = self._requests().get(
                    f"{self.api_url}/getUpdates",
                    params={"offset": self.last_update_id + 1, "timeout": 30},
                    timeout=35,
                )
                if response.status_code != 200:
                    time.sleep(5)
                    continue

                for update in response.json().get("result", []):
                    self.last_update_id = update["update_id"]
                    message = update.get("message") or {}
                    if str(message.get("chat", {}).get("id")) == str(self.chat_id):
                        text = message.get("text", "")
                        if text:
                            print(f"  [TELEGRAM] Received user message: {text}")
                            return text
            except Exception as exc:
                print(f"  [TELEGRAM] Polling error: {exc}")
                time.sleep(5)
        return None

    def _get_latest_update_id(self) -> int:
        try:
            response = self._requests().get(f"{self.api_url}/getUpdates", params={"limit": 1}, timeout=10)
            if response.status_code == 200:
                updates: list[dict[str, Any]] = response.json().get("result", [])
                if updates:
                    return int(updates[-1]["update_id"])
        except Exception:
            pass
        return 0

    def _requests(self):
        try:
            import requests
        except ImportError as exc:
            raise RuntimeError("requests paketi kurulu degil. `pip install -r requirements.txt` calistirin.") from exc
        return requests
