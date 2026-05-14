from __future__ import annotations

import io
import os
import sys

from src.core.logging import configure_logging
from src.core.settings import Settings


class ConsoleConfigurator:
    def configure(self) -> None:
        if sys.platform != "win32":
            return
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)


class AppRuntime:
    def __init__(self, settings: Settings, console: ConsoleConfigurator | None = None):
        self.settings = settings
        self.console = console or ConsoleConfigurator()

    def configure(self) -> None:
        self.console.configure()
        configure_logging()
        self.ensure_directories()

    def ensure_directories(self) -> None:
        os.makedirs(self.settings.assets_dir, exist_ok=True)
        os.makedirs(self.settings.outputs_dir, exist_ok=True)
