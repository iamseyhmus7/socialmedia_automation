from __future__ import annotations

import logging


class LoggingConfigurator:
    def configure(self) -> None:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%H:%M:%S",
        )


def configure_logging() -> None:
    LoggingConfigurator().configure()
