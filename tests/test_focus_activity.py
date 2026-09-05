"""Tests for the Daily, Weekly, and Cumulative Focus Activity views."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta, timezone
from itertools import pairwise

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QWidget

from app.core.theme import COLOR_THEMES, get_theme_manager
from app.i18n import get_localization, tr
from app.statistics import HeatmapData, HeatmapDay
from app.timer.formatting import format_compact_duration
from app.ui.components import SegmentedControl
from app.ui.dashboard import DashboardWindow, _FocusActivityCard
from app.ui.heatmap_widget import (
    FocusActivityMode,
    HeatmapWidget,
    _diagonal_reveal_opacity,
    _ModeTransitionPhase,
)


def _activity_data(
    first: date,
    durations: Sequence[float],
) -> HeatmapData:
    days = tuple(
        HeatmapDay(
            first + timedelta(days=offset),
            duration,
            int(duration > 0),
        )
        for offset, duration in enumerate(durations)
    )
    return HeatmapData(days[0].day, days[-1].day, days)


def _render(widget: HeatmapWidget, qt_application) -> None:
    widget.resize(760, 130)
    widget.show()
    widget.repaint()
    qt_application.processEvents()


def _settle_mode(widget: HeatmapWidget, qt_application) -> None:
    widget._complete_mode_transition()
    widget.repaint()
    qt_application.processEvents()


def test_weekly_activity_uses_monday_boundaries_and_partial_edge_weeks(
    qt_application,
) -> None:
    data = _activity_data(
        date(2025, 12, 30),
        [600, 0, 1200, 0, 1800, 0, 2400, 0, 3000, 0],
    )
    widget = HeatmapWidget()
    widget.set_data(data)
    widget.set_mode(FocusActivityMode.WEEKLY)
    _render(widget, qt_application)

    assert len(widget._weekly_values) == 2
    first, second = widget._weekly_values
    assert (first.start_day, first.end_day) == (
        date(2025, 12, 30),
        date(2026, 1, 4),
    )
    assert first.duration_seconds == 3600
    assert (second.start_day, second.end_day) == (
        date(2026, 1, 5),
        date(2026, 1, 8),
    )
    assert second.duration_seconds == 5400
    assert len(widget._weekly_regions) == 2
    assert widget._weekly_fill_heights == (5, 7)
    assert len(widget._cell_rects) == 14
    widget.close()


def test_cumulative_activity_is_monotonic_and_matches_daily_total(
    qt_application,
) -> None:
    durations = [0, 600, 0, 1800, 1200]
    widget = HeatmapWidget()
    widget.set_data(_activity_data(date(2026, 8, 1), durations))
    widget.set_mode(FocusActivityMode.CUMULATIVE)
    _render(widget, qt_application)

    values = [value.duration_seconds for value in widget._cumulative_values]
    assert values == sorted(values)
    assert values[-1] == sum(durations)
    assert len(widget._cumulative_regions) == len(widget._weekly_values)
    assert widget._cumulative_fill_heights == tuple(
        sorted(widget._cumulative_fill_heights)
    )
    assert widget._cumulative_fill_heights[-1] == 7
    assert format_compact_duration(sum(durations)) in widget.accessibleDescription()
    widget.close()


def test_activity_matrix_is_hover_only_and_clicks_do_not_select(qt_application) -> None:
    widget = HeatmapWidget()
    widget.set_data(_activity_data(date(2026, 8, 1), [600] * 14))
    _render(widget, qt_application)

    daily_rect, _expected = widget._hit_regions[5]
    QTest.mouseClick(
        widget,
        Qt.MouseButton.LeftButton,
        pos=daily_rect.center().toPoint(),
    )
    QTest.keyClick(widget, Qt.Key.Key_Enter)
    QTest.keyClick(widget, Qt.Key.Key_Space)
    assert not hasattr(widget, "day_clicked")
    assert not hasattr(widget, "_selected_day")

    widget.set_mode(FocusActivityMode.WEEKLY)
    _settle_mode(widget, qt_application)
    weekly_rect, _weekly = widget._weekly_regions[0]
    QTest.mouseClick(
        widget,
        Qt.MouseButton.LeftButton,
        pos=weekly_rect.center().toPoint(),
    )

    widget.set_mode(FocusActivityMode.CUMULATIVE)
    _settle_mode(widget, qt_application)
    cumulative_rect, _cumulative = widget._cumulative_regions[-1]
    QTest.mouseClick(
        widget,
        Qt.MouseButton.LeftButton,
        pos=cumulative_rect.center().toPoint(),
    )
    widget.close()


@pytest.mark.parametrize("language", ["zh-CN", "en-US"])
def test_anchored_callout_stays_above_target_and_weekly_omits_active_days(
    qt_application,
    language: str,
) -> None:
    localization = get_localization()
    original_language = localization.language
    container = QWidget()
    container.resize(900, 420)
    widget = HeatmapWidget()
    widget.setParent(container)
    try:
        localization.set_language(language)
        widget.set_data(
            _activity_data(date(2025, 9, 1), [1800] + [0] * 364)
        )
        widget.move(70, 190)
        widget.set_mode(FocusActivityMode.WEEKLY)
        container.show()
        _render(widget, qt_application)
        rect, _week = widget._weekly_regions[0]

        QTest.mouseMove(widget, rect.topLeft().toPoint())
        qt_application.processEvents()
        first_position = widget._callout.pos()
        assert widget._callout.isVisible()
        callout_parent = widget._callout.parentWidget()
        assert callout_parent is not None
        callout_bottom = callout_parent.mapToGlobal(
            widget._callout.geometry().bottomLeft()
        ).y()
        assert callout_bottom <= widget.mapToGlobal(rect.topLeft().toPoint()).y()
        assert widget._callout.geometry().left() >= callout_parent.rect().left()
        assert widget._callout.geometry().right() <= callout_parent.rect().right()
        assert "活跃天数" not in widget._callout._text
        assert "Active days" not in widget._callout._text

        QTest.mouseMove(widget, rect.bottomRight().toPoint())
        qt_application.processEvents()
        assert widget._callout.pos() == first_position
        widget.move(widget.x() + 20, widget.y() + 10)
        qt_application.processEvents()
        assert not widget._callout.isVisible()
    finally:
        widget.close()
        container.close()
        localization.set_language(original_language)


def test_keyboard_browsing_uses_hover_feedback_without_selection(
    qt_application,
) -> None:
    widget = HeatmapWidget()
    widget.set_data(_activity_data(date(2025, 9, 1), [0] * 364 + [1800]))
    _render(widget, qt_application)
    widget.setFocus()

    QTest.keyClick(widget, Qt.Key.Key_Home)
    assert widget._keyboard_target == (FocusActivityMode.DAILY, 0)
    assert widget._hover_target == (FocusActivityMode.DAILY, 0)
    assert widget._callout.isVisible()
    QTest.keyClick(widget, Qt.Key.Key_Right)
    assert widget._keyboard_target == (FocusActivityMode.DAILY, 1)
    QTest.keyClick(widget, Qt.Key.Key_Enter)
    QTest.keyClick(widget, Qt.Key.Key_Space)
    assert widget._keyboard_target == (FocusActivityMode.DAILY, 1)
    assert not hasattr(widget, "_selected_day")
    widget.close()


def test_cumulative_zero_data_keeps_the_shared_empty_matrix(
    qt_application,
) -> None:
    widget = HeatmapWidget()
    widget.set_data(_activity_data(date(2026, 8, 1), [0] * 30))
    widget.set_mode(FocusActivityMode.CUMULATIVE)
    _render(widget, qt_application)

    assert widget._cumulative_values[-1].duration_seconds == 0
    assert len(widget._cumulative_regions) == len(widget._weekly_values)
    assert set(widget._cumulative_fill_heights) == {0}
    assert len(widget._cell_rects) == len(widget._weekly_values) * 7
    assert not widget.grab().isNull()
    widget.close()


def test_all_modes_share_the_same_53_by_7_matrix_and_month_baseline(
    qt_application,
) -> None:
    widget = HeatmapWidget()
    widget.set_data(
        _activity_data(
            date(2025, 9, 1),
            [1800 if offset % 13 == 0 else 0 for offset in range(365)],
        )
    )
    matrices: list[tuple[tuple[float, float, float, float], ...]] = []
    month_positions: list[tuple[tuple[int, int, float, float], ...]] = []
    rendered_month_labels: list[tuple[tuple[int, int, str, float, float], ...]] = []
    for mode in FocusActivityMode:
        widget.set_mode(mode)
        _render(widget, qt_application)
        matrices.append(
            tuple(
                (rect.x(), rect.y(), rect.width(), rect.height())
                for rect in widget._cell_rects
            )
        )
        month_positions.append(
            tuple(
                (day.year, day.month, x, width)
                for day, x, width in widget._month_label_positions
            )
        )
        rendered_month_labels.append(
            tuple(
                (day.year, day.month, label, rect.x(), rect.width())
                for day, label, rect in widget._rendered_month_labels
            )
        )

    assert len(matrices[0]) == 53 * 7
    assert matrices[0] == matrices[1] == matrices[2]
    assert month_positions[0] == month_positions[1] == month_positions[2]
    assert (
        rendered_month_labels[0]
        == rendered_month_labels[1]
        == rendered_month_labels[2]
    )
    assert min(rect[1] for rect in matrices[0]) == 4.0
    widget.close()


def test_mode_transition_fades_then_reveals_from_top_left(
    qt_application,
) -> None:
    widget = HeatmapWidget()
    widget.set_data(
        _activity_data(
            date(2025, 9, 1),
            [1800 if offset % 9 == 0 else 0 for offset in range(365)],
        )
    )
    _render(widget, qt_application)
    geometry_before = tuple(widget._cell_rects)
    months_before = tuple(widget._month_label_positions)
    widget._mode_exit_duration_ms = 40
    widget._mode_reveal_duration_ms = 100
    finished = QSignalSpy(widget._mode_transition_animation.finished)

    widget.set_mode(FocusActivityMode.WEEKLY)

    assert widget.mode is FocusActivityMode.WEEKLY
    assert widget._rendered_mode is FocusActivityMode.DAILY
    assert widget._mode_transition_phase is _ModeTransitionPhase.FADING
    assert finished.wait(250)
    assert widget._rendered_mode is FocusActivityMode.WEEKLY
    assert widget._mode_transition_phase is _ModeTransitionPhase.REVEALING
    assert finished.wait(300)
    assert widget._mode_transition_phase is _ModeTransitionPhase.IDLE
    assert widget._rendered_mode is FocusActivityMode.WEEKLY
    widget.repaint()
    qt_application.processEvents()

    assert tuple(widget._cell_rects) == geometry_before
    assert tuple(widget._month_label_positions) == months_before
    assert _diagonal_reveal_opacity(0, 0, 53, 0.0) == 0.0
    assert _diagonal_reveal_opacity(52, 6, 53, 1.0) == 1.0
    top_left = _diagonal_reveal_opacity(0, 0, 53, 0.5)
    middle = _diagonal_reveal_opacity(26, 3, 53, 0.5)
    bottom_right = _diagonal_reveal_opacity(52, 6, 53, 0.5)
    assert top_left > middle > bottom_right
    widget.close()


def test_mode_transition_keeps_only_the_latest_rapid_selection(
    qt_application,
) -> None:
    widget = HeatmapWidget()
    widget.set_data(_activity_data(date(2025, 9, 1), [900] * 365))
    _render(widget, qt_application)
    widget._mode_exit_duration_ms = 40
    widget._mode_reveal_duration_ms = 120
    finished = QSignalSpy(widget._mode_transition_animation.finished)

    widget.set_mode(FocusActivityMode.WEEKLY)
    widget.set_mode(FocusActivityMode.CUMULATIVE)
    assert widget.mode is FocusActivityMode.CUMULATIVE
    assert widget._mode_transition_phase is _ModeTransitionPhase.FADING
    assert finished.wait(250)
    assert widget._rendered_mode is FocusActivityMode.CUMULATIVE
    assert widget._mode_transition_phase is _ModeTransitionPhase.REVEALING

    QTest.qWait(35)
    reveal_progress = widget._mode_transition_progress
    widget.set_mode(FocusActivityMode.DAILY)
    assert 0.0 < reveal_progress < 1.0
    assert widget._fade_reveal_progress == pytest.approx(reveal_progress)
    assert widget._mode_transition_phase is _ModeTransitionPhase.FADING
    assert finished.wait(250)
    assert widget._rendered_mode is FocusActivityMode.DAILY
    assert widget._mode_transition_phase is _ModeTransitionPhase.REVEALING
    assert finished.wait(300)
    assert widget.mode is FocusActivityMode.DAILY
    assert widget._rendered_mode is FocusActivityMode.DAILY
    assert widget._mode_transition_phase is _ModeTransitionPhase.IDLE
    widget.close()


@pytest.mark.parametrize("language", ["zh-CN", "en-US"])
@pytest.mark.parametrize("width", [420, 760, 1024])
def test_month_axis_omits_colliding_leading_partial_month_and_stays_in_bounds(
    qt_application,
    language: str,
    width: int,
) -> None:
    localization = get_localization()
    original_language = localization.language
    widget = HeatmapWidget()
    try:
        localization.set_language(language)
        # A Monday-aligned range beginning on August 25 has only seven August
        # days before the first complete month marker at September 1.
        widget.set_data(
            _activity_data(
                date(2025, 8, 25),
                [0] * 370,
            )
        )
        widget.resize(width, 130)
        widget.show()
        widget.repaint()
        qt_application.processEvents()

        labels = widget._rendered_month_labels
        assert labels
        assert (labels[0][0].year, labels[0][0].month) == (2025, 9)
        assert (labels[-1][0].year, labels[-1][0].month) == (2026, 8)

        geometry = widget._grid_geometry()
        grid_right = (
            geometry.left
            + (geometry.columns - 1) * geometry.stride
            + geometry.cell
        )
        for _day, _label, rect in labels:
            assert rect.left() >= geometry.left
            assert rect.right() <= grid_right
        for previous, current in pairwise(labels):
            assert current[2].left() - previous[2].right() >= 8.0
    finally:
        widget.close()
        localization.set_language(original_language)


def test_weekly_and_cumulative_heights_form_columns_and_staircase(
    qt_application,
) -> None:
    durations = [0.0] * 365
    durations[8] = 3600
    durations[90] = 7200
    durations[250] = 10_800
    widget = HeatmapWidget()
    widget.set_data(_activity_data(date(2025, 9, 1), durations))

    assert max(widget._weekly_fill_heights) == 7
    assert all(
        height >= 1
        for height, week in zip(
            widget._weekly_fill_heights,
            widget._weekly_values,
            strict=True,
        )
        if week.duration_seconds > 0
    )
    assert tuple(sorted(widget._cumulative_fill_heights)) == (
        widget._cumulative_fill_heights
    )
    assert widget._cumulative_fill_heights[0] == 0
    assert widget._cumulative_fill_heights[-1] == 7
    assert all(
        height >= 1
        for height, value in zip(
            widget._cumulative_fill_heights,
            widget._cumulative_values,
            strict=True,
        )
        if value.duration_seconds > 0
    )
    widget.close()


@pytest.mark.parametrize(
    ("mode", "region_name"),
    [
        (FocusActivityMode.DAILY, "_hit_regions"),
        (FocusActivityMode.WEEKLY, "_weekly_regions"),
        (FocusActivityMode.CUMULATIVE, "_cumulative_regions"),
    ],
)
def test_activity_hover_uses_interruptible_opaque_color_animation(
    qt_application,
    mode: FocusActivityMode,
    region_name: str,
) -> None:
    widget = HeatmapWidget()
    widget.set_data(
        _activity_data(
            date(2025, 9, 1),
            [1800 if offset == 20 else 0 for offset in range(365)],
        )
    )
    widget.set_mode(mode)
    _render(widget, qt_application)
    regions = getattr(widget, region_name)
    target_index = min(2, len(regions) - 1)
    rect, _value = regions[target_index]
    key = (mode, target_index)
    geometry_before = tuple(widget._cell_rects)

    QTest.mouseMove(widget, rect.center().toPoint())
    QTest.qWait(45)
    qt_application.processEvents()
    assert 0 < widget._hover_strengths[key] < 1
    assert tuple(widget._cell_rects) == geometry_before

    QTest.qWait(120)
    assert widget._hover_strengths[key] == pytest.approx(1.0)
    QTest.mouseMove(widget, widget.rect().bottomRight())
    QTest.qWait(45)
    assert 0 < widget._hover_strengths[key] < 1
    QTest.qWait(160)
    assert key not in widget._hover_strengths
    widget.close()


def test_dashboard_activity_control_keeps_mode_across_data_refresh(
    qt_application,
) -> None:
    window = DashboardWindow(timezone.utc)
    first_data = _activity_data(date(2025, 8, 2), [0] * 364 + [1800])
    second_data = _activity_data(date(2025, 8, 3), [600] * 365)

    assert window._heatmap.mode is FocusActivityMode.DAILY
    window._activity_mode_control.set_current_value(
        FocusActivityMode.CUMULATIVE,
        emit=True,
    )
    window.set_heatmap(first_data)
    window.set_heatmap(second_data)

    assert window._heatmap.mode is FocusActivityMode.CUMULATIVE
    assert window._activity_card.title_label.text() == tr(
        "dashboard.heatmap_title"
    )
    assert window._activity_mode_control.current_value is FocusActivityMode.CUMULATIVE
    window.close()


@pytest.mark.parametrize("width", [420, 760, 1024])
def test_all_activity_modes_render_at_supported_widths_and_themes(
    qt_application,
    width: int,
) -> None:
    manager = get_theme_manager()
    original_theme = manager.theme_name
    data = _activity_data(
        date(2025, 8, 30),
        [1800 if offset % 11 == 0 else 0 for offset in range(365)],
    )
    widget = HeatmapWidget()
    widget.set_data(data)
    widget.resize(width, 130)
    try:
        for theme in COLOR_THEMES:
            manager.set_theme(theme)
            manager._transition.finish_all()
            for mode in FocusActivityMode:
                widget.set_mode(mode)
                widget.show()
                widget.repaint()
                qt_application.processEvents()
                assert widget.height() == 130
                assert widget.minimumWidth() <= width
                assert not widget.grab().isNull()
    finally:
        widget.close()
        manager.set_theme(original_theme)
        manager._transition.finish_all()


@pytest.mark.parametrize("language", ["zh-CN", "en-US"])
def test_activity_header_reflows_without_losing_localized_modes(
    qt_application,
    language: str,
) -> None:
    localization = get_localization()
    original_language = localization.language
    try:
        localization.set_language(language)
        control = SegmentedControl(
            (
                (tr("heatmap.mode.daily"), FocusActivityMode.DAILY),
                (tr("heatmap.mode.weekly"), FocusActivityMode.WEEKLY),
                (
                    tr("heatmap.mode.cumulative"),
                    FocusActivityMode.CUMULATIVE,
                ),
            )
        )
        card = _FocusActivityCard(tr("dashboard.heatmap_title"), control)
        card.resize(420, 190)
        card.show()
        qt_application.processEvents()
        assert card._narrow
        assert [
            button.text()
            for button in control._buttons
        ] == [
            tr("heatmap.mode.daily"),
            tr("heatmap.mode.weekly"),
            tr("heatmap.mode.cumulative"),
        ]

        card.resize(760, 190)
        qt_application.processEvents()
        assert not card._narrow
        assert control.minimumWidth() <= 420
        card.close()
    finally:
        localization.set_language(original_language)
