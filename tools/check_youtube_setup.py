from __future__ import annotations

import json
import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)


def _module_available(module_name: str) -> bool:
    try:
        __import__(module_name)
    except ImportError:
        return False
    return True


def _check_client_secret(path: str) -> tuple[bool, str]:
    if not os.path.exists(path):
        return False, f"missing: {path}"

    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"invalid JSON: {exc}"

    installed = data.get("installed")
    if not isinstance(installed, dict):
        return False, "JSON must contain an 'installed' object from a Desktop OAuth client"

    missing = [key for key in ["client_id", "client_secret", "auth_uri", "token_uri"] if not installed.get(key)]
    if missing:
        return False, f"missing keys in installed object: {', '.join(missing)}"

    return True, "ready"


def _load_env() -> dict[str, str]:
    env_path = os.path.join(PROJECT_ROOT, ".env")
    values = {}
    if not os.path.exists(env_path):
        return values

    with open(env_path, "r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _resolve_path(value: str) -> str:
    if os.path.isabs(value):
        return value
    return os.path.join(PROJECT_ROOT, value)


def main() -> int:
    env = _load_env()
    client_secret_path = _resolve_path(
        env.get("YOUTUBE_CLIENT_SECRETS_PATH", os.path.join("user_data", "youtube_client_secret.json"))
    )
    token_path = _resolve_path(env.get("YOUTUBE_TOKEN_PATH", os.path.join("user_data", "youtube_token.json")))
    uploads_dir = _resolve_path(env.get("YOUTUBE_UPLOADS_DIR", "outputs"))
    privacy_status = env.get("YOUTUBE_DEFAULT_PRIVACY_STATUS", "public")
    category_id = env.get("YOUTUBE_CATEGORY_ID", "22")
    checks = []

    checks.append(("google-api-python-client", _module_available("googleapiclient"), "pip install -r requirements.txt"))
    checks.append(("google-auth-oauthlib", _module_available("google_auth_oauthlib"), "pip install -r requirements.txt"))

    client_ok, client_message = _check_client_secret(client_secret_path)
    checks.append(("OAuth client secret", client_ok, client_message))

    token_exists = os.path.exists(token_path)
    checks.append(
        (
            "OAuth token",
            token_exists,
            "ready" if token_exists else "not created yet; run python tools/yt_login.py after placing the client secret",
        )
    )

    print("\nYouTube setup check")
    print("-" * 40)
    for name, ok, message in checks:
        status = "OK" if ok else "TODO"
        print(f"{status:4} {name}: {message}")

    print("\nConfigured paths")
    print(f"client secret: {client_secret_path}")
    print(f"token:         {token_path}")
    print(f"uploads dir:   {uploads_dir}")
    print(f"privacy:       {privacy_status}")
    print(f"category:      {category_id}")

    return 0 if all(ok for _name, ok, _message in checks[:-1]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
