"""Widget tests for the calendar-based monthly Focus presentation."""

from calendar import monthrange
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest

from app.core.theme import (
    COLOR_THEMES,
    DEFAULT_COLOR_THEME,
    THEME_TOKENS,
    get_theme_manager,
)
from app.i18n import get_localization
from app.statistics import DailyTotal
from app.ui.monthly_calendar import (
    CELL_ASPECT_RATIO,
    CELL_GAP,
    CELL_WIDTH_SCALE,
    DATE_FONT_SIZE,
    MAX_CELL_HEIGHT,
    MAX_CELL_WIDTH,
    MIN_CELL_HEIGHT,
    MIN_CELL_WIDTH,
    OUTER_MARGIN,
    MonthlyCalendarWidget,
    _calendar_activity_gradient_stops,
    _calendar_cell_colors,
    _calendar_cell_dimensions,
    _calendar_column_center,
    _cell_text_rects,
    _contrast_ratio,
    _duration_font_size,
    _duration_text_rect,
    _format_calendar_duration,
)


def _month_values(
    year: int,
    month: int,
    durations: dict[int, float] | None = None,
) -> tuple[DailyTotal, ...]:
    duration_by_day = durations or {}
    return tuple(
        DailyTotal(date(year, month, day), duration_by_day.get(day, 0.0))
        for day in range(1, monthrange(year, month)[1] + 1)
    )


def test_month_calendar_places_days_in_a_monday_first_grid(qt_application) -> None:
    calendar = MonthlyCalendarWidget()
    calendar.set_values(
        _month_values(
            2026,
            7,
            {9: 78 * 60, 10: 204 * 60, 18: 56 * 60},
        )
    )
    calendar.resize(720, calendar.heightForWidth(720))
    calendar.show()
    QTest.qWait(10)
    calendar.repaint()
    qt_application.processEvents()

    cells = {cell.value.day.day: cell for cell in calendar.cells}
    assert len(cells) == 31
    assert (cells[1].row, cells[1].column) == (0, 2)
    assert (cells[5].row, cells[5].column) == (0, 6)
    assert (cells[6].row, cells[6].column) == (1, 0)
    assert cells[9].value.duration_seconds == 78 * 60
    assert cells[8].value.duration_seconds == 0
    assert calendar._row_count() == 5
    assert CELL_ASPECT_RATIO == 0.90
    assert CELL_WIDTH_SCALE == 0.75
    assert MIN_CELL_WIDTH == 50.0
    assert MAX_CELL_WIDTH == 80.0
    assert MIN_CELL_HEIGHT == 50.0
    assert MAX_CELL_HEIGHT == 72.0
    assert DATE_FONT_SIZE == 12
    assert calendar.heightForWidth(720) <= 400
    sample_ratio = cells[9].rect.height() / cells[9].rect.width()
    assert 0.88 <= sample_ratio <= 0.92
    date_rect, duration_rect = _cell_text_rects(cells[9].rect)
    assert date_rect.center().x() == cells[9].rect.center().x()
    assert duration_rect.center().x() == cells[9].rect.center().x()
    assert date_rect.bottom() == duration_rect.top()
    assert _duration_text_rect(cells[9].rect) == duration_rect
    assert _duration_font_size(cells[9].rect.height(), cells[9].rect.width()) == 11
    inactive_date_rect, inactive_duration_rect = _cell_text_rects(cells[8].rect)
    assert inactive_date_rect.top() == date_rect.top()
    assert inactive_date_rect.height() == date_rect.height()
    assert inactive_date_rect.center().y() == date_rect.center().y()
    assert inactive_duration_rect.top() == duration_rect.top()
    assert inactive_duration_rect.height() == duration_rect.height()
    assert calendar.accessibleName() == "Daily Focus Time"
    calendar.close()


def test_six_week_month_expands_and_cell_durations_use_h_and_min(
    qt_application,
) -> None:
    localization = get_localization()
    original_language = localization.language
    calendar = MonthlyCalendarWidget()
    calendar.set_values(_month_values(2026, 8, {1: 56 * 60, 2: 78 * 60, 3: 204 * 60}))

    try:
        assert calendar._row_count() == 6
        assert calendar.heightForWidth(640) > MonthlyCalendarWidget().heightForWidth(640)
        assert calendar.heightForWidth(720) <= 480
        localization.set_language("en-US")
        assert _format_calendar_duration(25 * 60) == "25min"
        assert _format_calendar_duration(60 * 60) == "1h"
        assert _format_calendar_duration(90 * 60) == "1h 30min"
        assert _format_calendar_duration(19 * 3600) == "19h"
        localization.set_language("zh-CN")
        assert _format_calendar_duration(25 * 60) == "25min"
        assert _format_calendar_duration(90 * 60) == "1h 30min"
        assert calendar.accessibleName() == "每日专注时长"
    finally:
        localization.set_language(original_language)
        calendar.close()


def test_month_calendar_renders_in_light_and_dark_themes(qt_application) -> None:
    manager = get_theme_manager()
    original_theme = manager.theme_name
    calendar = MonthlyCalendarWidget()
    calendar.set_values(_month_values(2026, 7, {9: 3600}))
    calendar.resize(720, calendar.heightForWidth(720))
    calendar.show()

    try:
        for theme_name in (DEFAULT_COLOR_THEME, "dark"):
            manager.set_theme(theme_name)
            QTest.qWait(5)
            calendar.repaint()
            qt_application.processEvents()
            assert len(calendar.cells) == 31
            assert not calendar.grab().isNull()
    finally:
        manager.set_theme(original_theme)
        calendar.close()


def test_month_calendar_cells_are_compact_responsive_and_column_centered(
    qt_application,
) -> None:
    calendar = MonthlyCalendarWidget()
    calendar.set_values(_month_values(2026, 7, {9: 90 * 60}))

    try:
        for width in (420, 760, 1024):
            calendar.resize(width, calendar.heightForWidth(width))
            calendar.show()
            QTest.qWait(5)
            calendar.repaint()
            qt_application.processEvents()

            expected_width, expected_height = _calendar_cell_dimensions(width)
            assert 50.0 <= expected_width <= 80.0
            assert 50.0 <= expected_height <= 72.0
            assert all(
                abs(cell.rect.width() - expected_width) < 0.01
                and abs(cell.rect.height() - expected_height) < 0.01
                for cell in calendar.cells
            )
            content_width = width - OUTER_MARGIN * 2
            column_slot_width = (
                content_width - CELL_GAP * 6
            ) / 7
            for cell in calendar.cells:
                expected_center = _calendar_column_center(
                    OUTER_MARGIN,
                    column_slot_width,
                    cell.column,
                )
                assert abs(cell.rect.center().x() - expected_center) < 0.01

        compact_width, compact_height = _calendar_cell_dimensions(420)
        assert compact_width == 50.0
        assert compact_height == 50.0
        wide_width, wide_height = _calendar_cell_dimensions(1024)
        assert wide_width == 80.0
        assert wide_height == 72.0
        assert _duration_font_size(compact_height, compact_width) == 8
    finally:
        calendar.close()


def test_month_calendar_uses_one_active_fill_and_ignores_clicks(
    qt_application,
) -> None:
    calendar = MonthlyCalendarWidget()
    calendar.set_values(
        _month_values(
            2026,
            8,
            {3: 15 * 60, 8: 45 * 60, 14: 90 * 60, 23: 180 * 60},
        )
    )
    calendar.resize(720, calendar.heightForWidth(720))
    calendar.show()
    QTest.qWait(5)
    calendar.repaint()
    qt_application.processEvents()

    assert calendar.cursor().shape() == Qt.CursorShape.ArrowCursor
    hovered_before = calendar._hovered_day
    cells = {cell.value.day.day: cell for cell in calendar.cells}
    for day_number in (3, 10, 23):
        QTest.mouseClick(
            calendar,
            Qt.MouseButton.LeftButton,
            pos=cells[day_number].rect.center().toPoint(),
        )
    assert not hasattr(calendar, "selected_day")
    assert not hasattr(calendar, "_selected_day")
    assert calendar._hovered_day == hovered_before
    assert "3h" in calendar.accessibleDescription()
    calendar.close()


def test_month_calendar_activity_colors_are_uniform_and_legible() -> None:
    durations = (0, 15 * 60, 45 * 60, 90 * 60, 180 * 60)
    themed_gradients: dict[str, tuple[str, str, str]] = {}
    for theme_name in COLOR_THEMES:
        tokens = THEME_TOKENS[theme_name]
        gradient_stops = _calendar_activity_gradient_stops(tokens)
        hover_stops = _calendar_activity_gradient_stops(tokens, hovered=True)
        themed_gradients[theme_name] = (
            gradient_stops[0].name(),
            gradient_stops[1].name(),
            gradient_stops[2].name(),
        )
        assert gradient_stops[0].lightnessF() > gradient_stops[1].lightnessF()
        assert gradient_stops[1].lightnessF() > gradient_stops[2].lightnessF()
        channel_delta = max(
            abs(gradient_stops[0].red() - gradient_stops[2].red()),
            abs(gradient_stops[0].green() - gradient_stops[2].green()),
            abs(gradient_stops[0].blue() - gradient_stops[2].blue()),
        )
        assert 8 <= channel_delta <= 32
        assert all(
            hovered.lightnessF() > normal.lightnessF()
            for normal, hovered in zip(gradient_stops, hover_stops, strict=True)
        )
        active_fills: set[str] = set()
        active_text: set[str] = set()
        for duration in durations:
            fill, text = _calendar_cell_colors(duration, tokens)
            if duration == 0:
                assert fill == QColor(tokens.heatmap_levels[0])
                assert text == QColor(tokens.muted)
            else:
                active_fills.add(fill.name())
                active_text.add(text.name())
                assert fill == gradient_stops[1]
                assert all(
                    _contrast_ratio(stop, text) >= 4.5
                    for stop in (*gradient_stops, *hover_stops)
                )
        assert active_fills == {gradient_stops[1].name()}
        assert len(active_text) == 1
    assert themed_gradients["dark"] != themed_gradients["charcoal"]


def test_month_calendar_paints_a_visible_subtle_activity_gradient(
    qt_application,
) -> None:
    manager = get_theme_manager()
    original_theme = manager.theme_name
    calendar = MonthlyCalendarWidget()
    calendar.set_values(_month_values(2026, 7, {9: 60 * 60}))
    calendar.resize(720, calendar.heightForWidth(720))
    calendar.show()

    try:
        for theme_name in COLOR_THEMES:
            manager.set_theme(theme_name)
            QTest.qWait(5)
            calendar.repaint()
            qt_application.processEvents()
            active_cell = next(cell for cell in calendar.cells if cell.value.day.day == 9)
            image = calendar.grab().toImage()
            center = active_cell.rect.center()
            horizontal_left = image.pixelColor(
                round(center.x() - 22),
                round(center.y()),
            )
            horizontal_right = image.pixelColor(
                round(center.x() + 22),
                round(center.y()),
            )
            vertical_top = image.pixelColor(
                round(center.x() + 22),
                round(center.y() - 16),
            )
            vertical_bottom = image.pixelColor(
                round(center.x() + 22),
                round(center.y() + 16),
            )
            center_fill = image.pixelColor(
                round(center.x() + 13),
                round(center.y()),
            )
            edge_fill = image.pixelColor(
                round(active_cell.rect.right() - 5),
                round(center.y()),
            )
            assert _maximum_channel_delta(horizontal_left, horizontal_right) <= 2
            assert _maximum_channel_delta(vertical_top, vertical_bottom) <= 2
            assert _maximum_channel_delta(center_fill, edge_fill) >= 4
    finally:
        manager.set_theme(original_theme)
        calendar.close()


def _maximum_channel_delta(first: QColor, second: QColor) -> int:
    return max(
        abs(first.red() - second.red()),
        abs(first.green() - second.green()),
        abs(first.blue() - second.blue()),
    )
