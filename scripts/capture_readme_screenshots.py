"""Create privacy-safe README screenshots from an isolated demo profile."""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from datetime import datetime, timedelta
from datetime import time as datetime_time
from pathlib import Path

from PySide6.QtWidgets import QApplication, QScrollArea, QWidget

from app.application import build_runtime, create_application
from app.core.paths import ApplicationPaths
from app.data.database import Database
from app.data.database_settings_repository import DatabaseSettingsRepository
from app.data.focus_item_repository import FocusItemRepository
from app.data.focus_session_repository import FocusSessionRepository
from app.data.models import FocusItem
from app.data.settings_repository import AppSettings, SettingsRepository
from app.focus_mode import FocusMode
from app.gamification.gamification_service import (
    DAILY_GOAL_KEY,
    STREAK_MINIMUM_KEY,
    WEEKLY_GOAL_KEY,
)
from app.i18n import get_localization
from app.ui.dashboard import DashboardPage

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CAPTURE_ROOT = PROJECT_ROOT / "build" / "readme-screenshots"
SUPPORTED_LANGUAGES = {"zh-CN": "zh", "en-US": "en"}


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", choices=SUPPORTED_LANGUAGES, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        help="Output directory; defaults to docs/images/<language>.",
    )
    return parser.parse_args()


def _wait_for_paint(application: QApplication, milliseconds: int = 260) -> None:
    deadline = time.monotonic() + milliseconds / 1000
    while time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.01)
    application.processEvents()


def _capture(
    application: QApplication,
    widget: QWidget,
    destination: Path,
    width: int,
    height: int,
) -> None:
    widget.resize(width, height)
    widget.show()
    widget.raise_()
    _wait_for_paint(application)
    image = widget.grab().toImage()
    if image.isNull() or not image.save(str(destination), "PNG", 82):
        raise RuntimeError(f"Unable to save screenshot: {destination}")
    widget.hide()
    application.processEvents()


def _capture_scrolled_to_bottom(
    application: QApplication,
    widget: QWidget,
    scroll_area: QScrollArea,
    destination: Path,
    width: int,
    height: int,
) -> None:
    widget.resize(width, height)
    widget.show()
    widget.raise_()
    _wait_for_paint(application)
    scroll_area.verticalScrollBar().setValue(
        scroll_area.verticalScrollBar().maximum()
    )
    _wait_for_paint(application)
    image = widget.grab().toImage()
    if image.isNull() or not image.save(str(destination), "PNG", 82):
        raise RuntimeError(f"Unable to save screenshot: {destination}")
    widget.hide()
    application.processEvents()


def _localized_copy(language: str) -> tuple[list[tuple[str, str]], list[str]]:
    if language == "zh-CN":
        return (
            [
                ("深度工作", "#14B8A6"),
                ("阅读", "#3B82F6"),
                ("学习", "#8B5CF6"),
                ("健身", "#EC4899"),
            ],
            ["整理产品路线图", "阅读设计章节", "复习课程笔记", "晚间训练"],
        )
    return (
        [
            ("Deep Work", "#14B8A6"),
            ("Reading", "#3B82F6"),
            ("Learning", "#8B5CF6"),
            ("Exercise", "#EC4899"),
        ],
        [
            "Product roadmap",
            "Design systems chapter",
            "Course review",
            "Evening training",
        ],
    )


def _seed_demo_profile(paths: ApplicationPaths, language: str) -> None:
    paths.prepare_data_directory()
    SettingsRepository(paths.settings_path).save(
        AppSettings(language=language, color_theme="lavender")
    )
    database = Database(paths.database_path)
    database.initialize()
    item_repository = FocusItemRepository(database)
    session_repository = FocusSessionRepository(database)
    item_copy, notes = _localized_copy(language)
    items = [item_repository.create(name, color) for name, color in item_copy]
    item_repository.ensure_defaults()

    local_now = datetime.now().astimezone()
    today = local_now.date()
    schedule = (
        (0, 7, 30, 45, 1),
        (0, 10, 0, 90, 0),
        (0, 14, 15, 50, 2),
        (0, 18, 30, 30, 3),
        (1, 9, 0, 75, 0),
        (1, 15, 30, 40, 1),
        (2, 8, 20, 35, 2),
        (2, 13, 10, 60, 0),
        (3, 10, 30, 50, 1),
        (4, 9, 15, 80, 0),
        (5, 16, 0, 45, 2),
        (6, 8, 45, 55, 1),
        (7, 11, 0, 70, 0),
        (9, 14, 30, 50, 2),
        (12, 9, 40, 65, 0),
        (15, 17, 10, 40, 3),
        (19, 8, 30, 95, 0),
        (23, 19, 0, 35, 1),
    )
    for index, (days_ago, hour, minute, duration, item_index) in enumerate(schedule):
        day = today - timedelta(days=days_ago)
        start = datetime.combine(
            day,
            datetime_time(hour=hour, minute=minute),
            tzinfo=local_now.tzinfo,
        )
        end = start + timedelta(minutes=duration)
        mode = FocusMode.COUNTDOWN if index % 3 == 0 else FocusMode.STOPWATCH
        session_repository.create(
            items[item_index],
            start,
            end,
            duration * 60,
            mode=mode,
            target_duration_seconds=duration * 60 if mode is FocusMode.COUNTDOWN else None,
            note=notes[item_index],
        )

    settings = DatabaseSettingsRepository(database)
    settings.set(DAILY_GOAL_KEY, str(3 * 60 * 60))
    settings.set(WEEKLY_GOAL_KEY, str(12 * 60 * 60))
    settings.set(STREAK_MINIMUM_KEY, str(30 * 60))


def _new_demo_paths(language: str) -> ApplicationPaths:
    target = CAPTURE_ROOT / SUPPORTED_LANGUAGES[language]
    resolved_capture_root = CAPTURE_ROOT.resolve()
    resolved_target = target.resolve()
    if resolved_target.parent != resolved_capture_root:
        raise RuntimeError(f"Refusing to reset unexpected demo path: {resolved_target}")
    if resolved_target.exists():
        shutil.rmtree(resolved_target)
    return ApplicationPaths(PROJECT_ROOT, PROJECT_ROOT / "assets", resolved_target)


def _select_first_focus_item(items: list[FocusItem]) -> int:
    if not items:
        raise RuntimeError("The screenshot profile did not create Focus Items.")
    return items[0].id


def main() -> int:
    arguments = _arguments()
    language = str(arguments.language)
    output = (
        arguments.output.resolve()
        if arguments.output is not None
        else PROJECT_ROOT / "docs" / "images" / SUPPORTED_LANGUAGES[language]
    )
    output.mkdir(parents=True, exist_ok=True)

    paths = _new_demo_paths(language)
    get_localization().set_language(language)
    _seed_demo_profile(paths, language)
    application = create_application(["desktop-focus-companion-screenshot"])
    runtime = build_runtime(paths)
    runtime.pet_controller.start()
    runtime.pet_window.hide()
    runtime.dashboard_controller.refresh()
    runtime.quick_panel_controller.refresh_summary()
    runtime.gamification_controller.refresh()

    dashboard = runtime.dashboard_window
    for page, filename in (
        (DashboardPage.OVERVIEW, "overview.png"),
        (DashboardPage.TIMELINE, "timeline.png"),
        (DashboardPage.ANALYTICS, "analytics.png"),
        (DashboardPage.MONTHLY, "monthly.png"),
        (DashboardPage.HISTORY, "history.png"),
    ):
        dashboard.set_current_page(page)
        _capture(application, dashboard, output / filename, 1060, 752)

    items = runtime.focus_item_repository.list_active()
    runtime.quick_panel.set_focus_items(items, _select_first_focus_item(items))
    _capture(application, runtime.quick_panel, output / "focus-panel.png", 380, 620)

    runtime.focus_item_dialog.set_focus_items(items)
    runtime.quick_panel_controller.refresh_focus_items(_select_first_focus_item(items))
    _capture(
        application,
        runtime.focus_item_dialog,
        output / "focus-items.png",
        440,
        430,
    )

    runtime.pet_controller.update_color_theme("charcoal")
    runtime.settings_dialog.set_color_theme("charcoal")
    runtime.settings_dialog._select_page(0)
    _wait_for_paint(application, 300)
    appearance_scroll = runtime.settings_dialog._appearance_tab.findChild(QScrollArea)
    if appearance_scroll is None:
        raise RuntimeError("The settings screenshot could not find its scroll area.")
    _capture_scrolled_to_bottom(
        application,
        runtime.settings_dialog,
        appearance_scroll,
        output / "themes.png",
        760,
        680,
    )

    application.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
