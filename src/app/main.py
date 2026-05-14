from __future__ import annotations

import asyncio
import os
import sys
import warnings

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.app.runtime import AppRuntime, ConsoleConfigurator
from src.core.media_cleanup import MediaCleanupService
from src.core.settings import Settings, get_settings
from src.domain.state import create_initial_state
from src.services.publish_schedule_service import PublishScheduleService
from src.workflows.factory import create_workflow


warnings.filterwarnings("ignore")


class ProductionApplication:
    def __init__(
        self,
        settings: Settings | None = None,
        runtime: AppRuntime | None = None,
        schedule_service: PublishScheduleService | None = None,
    ):
        self.settings = settings or get_settings()
        self.runtime = runtime or AppRuntime(self.settings)
        self.schedule_service = schedule_service or PublishScheduleService()
        self.cleanup_service = MediaCleanupService(self.settings.assets_dir)

    async def run(self) -> dict:
        self.runtime.configure()
        self._print_header()

        app = create_workflow(self.settings)
        final_state = await app.ainvoke(create_initial_state())

        self._print_result(final_state)
        self.cleanup_service.cleanup_intermediate_assets()
        return final_state

    def _print_header(self) -> None:
        print("\n" + "=" * 60)
        print("LANGGRAPH MULTI-AGENT VIDEO ENGINE STARTED")
        print("=" * 60)

    def _print_result(self, final_state: dict) -> None:
        print("\n" + "=" * 60)
        print("PROCESS COMPLETED")
        for line in self._result_lines(final_state):
            print(line)
        print("=" * 60 + "\n")

    def _result_lines(self, final_state: dict) -> list[str]:
        lines = []
        if final_state.get("final_video_path"):
            lines.append(f"Output: {final_state['final_video_path']}")
        if final_state.get("youtube_url"):
            lines.append(f"YouTube: {final_state['youtube_url']}")
        if final_state.get("youtube_publish_at"):
            lines.append(f"Public at: {self.schedule_service.format_local_datetime(final_state['youtube_publish_at'])}")
        if final_state.get("upload_error"):
            lines.append(f"YouTube upload error: {final_state['upload_error']}")
        if final_state.get("instagram_url"):
            lines.append(f"Instagram: {final_state['instagram_url']}")
        elif final_state.get("instagram_media_id"):
            lines.append(f"Instagram media id: {final_state['instagram_media_id']}")
        if final_state.get("instagram_upload_error"):
            lines.append(f"Instagram upload error: {final_state['instagram_upload_error']}")
        if final_state.get("tiktok_publish_at"):
            local_time = self.schedule_service.format_local_datetime(final_state["tiktok_publish_at"])
            lines.append(f"TikTok queued locally at: {local_time}")
        if final_state.get("tiktok_publish_id"):
            lines.append(f"TikTok publish id: {final_state['tiktok_publish_id']}")
        if final_state.get("tiktok_upload_error"):
            lines.append(f"TikTok upload error: {final_state['tiktok_upload_error']}")
        lines.append(f"Status: {final_state.get('status')}")
        return lines


def configure_windows_console() -> None:
    ConsoleConfigurator().configure()


async def run_production() -> dict:
    return await ProductionApplication().run()


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
