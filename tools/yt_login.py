from __future__ import annotations

import asyncio
import os
import sys


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.uploader_service import UploaderService


if __name__ == "__main__":
    uploader = UploaderService()
    print("Starting YouTube OAuth setup...")
    asyncio.run(uploader.login_manually("https://studio.youtube.com/"))
    print("\nDone. The saved OAuth token can be reused by the upload tool.")
