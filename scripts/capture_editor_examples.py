"""Capture the intentionally changed editor using synthetic records only."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.application import create_application
from app.core.theme import get_theme_manager
from app.data.models import FocusItem, FocusSession, FocusSessionSource
from app.focus_mode import FocusMode
from app.i18n import get_localization
from app.ui.session_editor_dialog import SessionEditorDialog
from scripts.capture_readme_screenshots import _capture
from scripts.qt_capture import prepare_capture_fonts


def main():
    application = create_application(["editor-preview"])
    prepare_capture_fonts(application)
    output = Path(__file__).resolve().parents[1] / "artifacts" / "editor"
    output.mkdir(parents=True, exist_ok=True)
    get_theme_manager().set_theme("lavender")
    start = datetime(2026, 11, 1, 10, 30, 23, tzinfo=timezone.utc)
    for language, name in [("en-US", "Deep Work"), ("zh-CN", "深度工作")]:
        get_localization().set_language(language)
        item = FocusItem(1, name, "#7C5CFC", False, False, start, start)
        session = FocusSession(
            1,
            1,
            name,
            start,
            start + timedelta(hours=2),
            3600,
            FocusMode.STOPWATCH,
            None,
            "",
            FocusSessionSource.TIMER,
            start,
            start,
        )
        dialog = SessionEditorDialog(timezone.utc)
        dialog.set_focus_items([item])
        dialog.set_session(session)
        _capture(application, dialog, output / f"editor-{language}.png", 500, 640)
        dialog.deleteLater()
        application.processEvents()


if __name__ == "__main__":
    main()
