"""Rotating file logging for production diagnostics."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(logs_dir: Path) -> Path:
    """Configure one bounded application log and return its path."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "desktop-focus-companion.log"
    root_logger = logging.getLogger()
    if not any(
        isinstance(handler, RotatingFileHandler)
        and Path(getattr(handler, "baseFilename", "")) == log_path
        for handler in root_logger.handlers
    ):
        handler = RotatingFileHandler(
            log_path,
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
    sys.excepthook = _log_uncaught_exception
    return log_path


def _log_uncaught_exception(exception_type, exception, traceback) -> None:
    logging.getLogger("desktop-focus-companion.uncaught").critical(
        "Unhandled exception",
        exc_info=(exception_type, exception, traceback),
    )
