from __future__ import annotations

import asyncio
import io
import os
import sys
import warnings

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.logging import configure_logging
from src.core.media_cleanup import MediaCleanupService
from src.core.settings import get_settings
from src.domain.state import create_initial_state
from src.services.publish_schedule_service import PublishScheduleService
from src.workflows.factory import create_workflow


warnings.filterwarnings("ignore")


def configure_windows_console() -> None:
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)


async def run_production() -> dict:
    configure_windows_console()
    configure_logging()
    settings = get_settings()
    os.makedirs(settings.assets_dir, exist_ok=True)
    os.makedirs(settings.outputs_dir, exist_ok=True)

    print("\n" + "=" * 60)
    print("LANGGRAPH MULTI-AGENT VIDEO ENGINE STARTED")
    print("=" * 60)

    app = create_workflow(settings)
    final_state = await app.ainvoke(create_initial_state())

    print("\n" + "=" * 60)
    print("PROCESS COMPLETED")
    if final_state.get("final_video_path"):
        print(f"Output: {final_state['final_video_path']}")
    if final_state.get("youtube_url"):
        print(f"YouTube: {final_state['youtube_url']}")
    if final_state.get("youtube_publish_at"):
        print(f"Public at: {PublishScheduleService().format_local_datetime(final_state['youtube_publish_at'])}")
    if final_state.get("upload_error"):
        print(f"YouTube upload error: {final_state['upload_error']}")
    if final_state.get("instagram_url"):
        print(f"Instagram: {final_state['instagram_url']}")
    elif final_state.get("instagram_media_id"):
        print(f"Instagram media id: {final_state['instagram_media_id']}")
    if final_state.get("instagram_upload_error"):
        print(f"Instagram upload error: {final_state['instagram_upload_error']}")
    print(f"Status: {final_state.get('status')}")
    print("=" * 60 + "\n")

    MediaCleanupService(settings.assets_dir).cleanup_intermediate_assets()
    return final_state


def main() -> None:
    try:
        asyncio.run(run_production())
    except KeyboardInterrupt:
        print("\n[INFO] Stopped by user.")
    except Exception as exc:
        print(f"\n[FATAL ERROR] System error: {exc}")
        raise


if __name__ == "__main__":
    main()
