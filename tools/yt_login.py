from __future__ import annotations

import asyncio
import argparse
import os
import sys


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.uploader_service import UploaderService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a fresh YouTube OAuth token.")
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Local OAuth callback port. Use 8080 for Docker port mapping.",
    )
    parser.add_argument(
        "--bind-addr",
        default=None,
        help="Address to bind the callback server to. Use 0.0.0.0 inside Docker.",
    )
    parser.add_argument("--no-browser", action="store_true", help="Print the auth URL instead of opening a browser.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    auth_server_kwargs = {
        "port": args.port,
        "open_browser": not args.no_browser,
    }
    if args.bind_addr:
        auth_server_kwargs["bind_addr"] = args.bind_addr

    uploader = UploaderService()
    print("Starting YouTube OAuth setup...")
    asyncio.run(
        uploader.login_manually("https://studio.youtube.com/", auth_server_kwargs=auth_server_kwargs)
    )
    print("\nDone. The saved OAuth token can be reused by the upload tool.")
