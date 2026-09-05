"""Non-mutating tests for desktop integration helpers."""

import sys
from pathlib import Path

from app.core.logging_config import configure_logging
from app.integration.startup_manager import VALUE_NAME, WindowsStartupManager


def test_development_startup_command_uses_main_entrypoint(tmp_path: Path) -> None:
    manager = WindowsStartupManager(tmp_path)

    command = manager.build_command()

    assert str(tmp_path / "main.py") in command
    assert "python" in command.casefold()
    assert VALUE_NAME == "Desktop Focus Companion"


def test_logging_uses_bounded_app_data_file(tmp_path: Path) -> None:
    log_path = configure_logging(tmp_path / "logs")

    assert log_path == tmp_path / "logs" / "desktop-focus-companion.log"
    assert log_path.exists()
    assert sys.excepthook is not sys.__excepthook__
