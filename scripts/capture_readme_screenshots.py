"""Create privacy-safe README screenshots from an isolated demo profile."""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from datetime import datetime, timedelta
from datetime import time as datetime_time
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QImageWriter,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QApplication, QWidget

from app.application import ApplicationRuntime, build_runtime, create_application
from app.core.paths import ApplicationPaths
from app.core.theme import COLOR_THEMES, THEME_TOKENS
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
from app.i18n import get_localization, tr
from app.ui.dashboard import DashboardPage

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CAPTURE_ROOT = PROJECT_ROOT / "build" / "readme-screenshots"
SUPPORTED_LANGUAGES = {"zh-CN": "zh", "en-US": "en"}
THEME_PREVIEW_WIDTH = 420
THEME_PREVIEW_HEIGHT = 298
THEME_LABEL_HEIGHT = 28
THEME_SHEET_COLUMNS = 3
THEME_SHEET_ROWS = 2
THEME_SHEET_GAP = 16
THEME_SHEET_MARGIN = 20
THEME_SHEET_WIDTH = (
    THEME_SHEET_MARGIN * 2
    + THEME_PREVIEW_WIDTH * THEME_SHEET_COLUMNS
    + THEME_SHEET_GAP * (THEME_SHEET_COLUMNS - 1)
)
THEME_SHEET_HEIGHT = (
    THEME_SHEET_MARGIN * 2
    + (THEME_LABEL_HEIGHT + THEME_PREVIEW_HEIGHT) * THEME_SHEET_ROWS
    + THEME_SHEET_GAP * (THEME_SHEET_ROWS - 1)
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", choices=SUPPORTED_LANGUAGES, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        help="Output directory; defaults to docs/images/<language>.",
    )
    parser.add_argument(
        "--only",
        choices=("all", "themes"),
        default="all",
        help="Capture every README image or only the six-theme contact sheet.",
    )
    return parser.parse_args()


def _wait_for_paint(application: QApplication, milliseconds: int = 260) -> None:
    deadline = time.monotonic() + milliseconds / 1000
    while time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.01)
    application.processEvents()


def _grab(
    application: QApplication,
    widget: QWidget,
    width: int,
    height: int,
) -> QImage:
    widget.resize(width, height)
    widget.show()
    widget.raise_()
    _wait_for_paint(application)
    image = widget.grab().toImage()
    widget.hide()
    application.processEvents()
    if image.isNull():
        raise RuntimeError("Unable to capture screenshot")
    return image


def _save_png(image: QImage, destination: Path) -> None:
    writer = QImageWriter(str(destination), b"PNG")
    writer.setQuality(82)
    if image.isNull() or not writer.write(image):
        raise RuntimeError(f"Unable to save screenshot: {destination}")


def _capture(
    application: QApplication,
    widget: QWidget,
    destination: Path,
    width: int,
    height: int,
) -> None:
    _save_png(_grab(application, widget, width, height), destination)


def _theme_contact_sheet(previews: dict[str, QImage]) -> QImage:
    expected = set(COLOR_THEMES)
    if set(previews) != expected:
        raise ValueError("Theme previews must contain every supported theme exactly once.")

    sheet = QImage(
        THEME_SHEET_WIDTH,
        THEME_SHEET_HEIGHT,
        QImage.Format.Format_ARGB32_Premultiplied,
    )
    sheet.fill(Qt.GlobalColor.transparent)
    painter = QPainter(sheet)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    label_font = QFont(QApplication.font())
    label_font.setPixelSize(13)
    label_font.setWeight(QFont.Weight.DemiBold)

    try:
        for index, theme_name in enumerate(COLOR_THEMES):
            row, column = divmod(index, THEME_SHEET_COLUMNS)
            left = THEME_SHEET_MARGIN + column * (
                THEME_PREVIEW_WIDTH + THEME_SHEET_GAP
            )
            top = THEME_SHEET_MARGIN + row * (
                THEME_LABEL_HEIGHT + THEME_PREVIEW_HEIGHT + THEME_SHEET_GAP
            )
            tile = QRectF(
                left,
                top,
                THEME_PREVIEW_WIDTH,
                THEME_LABEL_HEIGHT + THEME_PREVIEW_HEIGHT,
            )
            clip = QPainterPath()
            clip.addRoundedRect(tile, 12, 12)
            tokens = THEME_TOKENS[theme_name]

            painter.save()
            painter.setClipPath(clip)
            painter.fillPath(clip, QColor(tokens.surface_elevated))
            painter.fillRect(
                left,
                top,
                THEME_PREVIEW_WIDTH,
                THEME_LABEL_HEIGHT,
                QColor(tokens.surface_elevated),
            )
            preview = previews[theme_name].scaled(
                THEME_PREVIEW_WIDTH,
                THEME_PREVIEW_HEIGHT,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.drawImage(left, top + THEME_LABEL_HEIGHT, preview)
            painter.setFont(label_font)
            painter.setPen(QColor(tokens.text))
            painter.drawText(
                QRectF(left + 12, top, THEME_PREVIEW_WIDTH - 24, THEME_LABEL_HEIGHT),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                tr(f"settings.theme.{theme_name}"),
            )
            painter.restore()

            painter.setPen(QPen(QColor(tokens.border), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(clip)
    finally:
        painter.end()
    return sheet


def _capture_theme_contact_sheet(
    application: QApplication,
    runtime: ApplicationRuntime,
    destination: Path,
) -> None:
    dashboard = runtime.dashboard_window
    dashboard.set_current_page(DashboardPage.OVERVIEW)
    previews: dict[str, QImage] = {}
    for theme_name in COLOR_THEMES:
        if not runtime.pet_controller.update_color_theme(theme_name):
            raise RuntimeError(f"Unable to apply screenshot theme: {theme_name}")
        _wait_for_paint(application, 300)
        previews[theme_name] = _grab(application, dashboard, 1060, 752)
    _save_png(_theme_contact_sheet(previews), destination)


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

    if arguments.only == "all":
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
        runtime.quick_panel_controller.refresh_focus_items(
            _select_first_focus_item(items)
        )
        _capture(
            application,
            runtime.focus_item_dialog,
            output / "focus-items.png",
            440,
            430,
        )

    _capture_theme_contact_sheet(application, runtime, output / "themes.png")

    application.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
