"""Ensure offscreen Windows captures contain real glyphs, not missing-font boxes."""

import os
from pathlib import Path

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication


def prepare_capture_fonts(application: QApplication) -> None:
    if application.platformName() != "offscreen" or QFontDatabase.families():
        return
    font_root = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for name in ("segoeui.ttf", "segoeuib.ttf", "msyh.ttc", "msyhbd.ttc"):
        path = font_root / name
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))
    if not QFontDatabase.families():
        raise RuntimeError(
            "No fonts available for visual verification; use the native Windows Qt platform."
        )
