"""Personal Focus Analytics domain and visual component tests."""

from datetime import datetime, timedelta, timezone

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest

from app.data.database import Database
from app.data.focus_item_repository import FocusItemRepository
from app.data.focus_session_repository import FocusSessionRepository
from app.statistics import (
    AnalyticsDistributionPeriod,
    ConsistencySummary,
    FocusAnalyticsSnapshot,
    FocusItemTotal,
    FocusPatternSummary,
    StatisticsService,
    TrendPoint,
)
from app.ui.analytics_widgets import (
    DistributionTransitionPhase,
    FocusDistributionChart,
)
from app.ui.dashboard import DashboardPage, DashboardWindow


def test_analytics_snapshot_calculates_trends_patterns_and_consistency(tmp_path) -> None:
    database = Database(tmp_path / "focus.sqlite3")
    database.initialize()
    items = FocusItemRepository(database)
    sessions = FocusSessionRepository(database)
    deep_work = items.create("Deep Work", "#7C5CFC")
    reading = items.create("Reading", "#10B981")
    tz = timezone(timedelta(hours=8))
    entries = (
        (deep_work, datetime(2026, 8, 14, 19, tzinfo=tz), 7200),
        (deep_work, datetime(2026, 8, 15, 20, tzinfo=tz), 3600),
        (deep_work, datetime(2026, 8, 16, 9, tzinfo=tz), 1800),
        (reading, datetime(2026, 8, 16, 10, tzinfo=tz), 1800),
    )
    for item, start, duration in entries:
        sessions.create(item, start, start + timedelta(seconds=duration), duration)

    snapshot = StatisticsService(sessions, tz).analytics_snapshot(
        datetime(2026, 8, 16, 21, tzinfo=tz)
    )

    assert len(snapshot.daily_trend) == 14
    assert len(snapshot.weekly_trend) == 8
    assert len(snapshot.monthly_trend) == 6
    assert snapshot.daily_trend[-1].duration_seconds == 3600
    assert snapshot.weekly_trend[-1].duration_seconds == 14400
    assert snapshot.monthly_trend[-1].duration_seconds == 14400
    assert snapshot.pattern.best_start_hour == 18
    assert snapshot.pattern.best_end_hour == 21
    assert snapshot.pattern.average_session_seconds == pytest.approx(3600)
    assert snapshot.pattern.common_start_hour == 9
    assert snapshot.consistency.current_streak_days == 3
    assert snapshot.consistency.longest_streak_days == 3
    assert snapshot.consistency.active_days == 3


def test_distribution_chart_uses_stable_item_colors_and_percentages(
    qt_application,
) -> None:
    chart = FocusDistributionChart()
    values = [
        FocusItemTotal(1, "Project", 5400),
        FocusItemTotal(2, "Reading", 1800),
    ]

    chart.set_values(values, {1: "#EC4899", 2: "#3B82F6"})

    assert len(chart.segments) == 2
    assert chart.segments[0].color == "#EC4899"
    assert chart.segments[0].percentage == pytest.approx(0.75)
    assert chart.segments[1].color == "#3B82F6"
    assert chart.segments[1].percentage == pytest.approx(0.25)
    chart.close()


def test_dashboard_analytics_tab_renders_all_periods(qt_application) -> None:
    window = DashboardWindow(timezone.utc)
    snapshot = FocusAnalyticsSnapshot(
        daily_trend=(TrendPoint("2026-08-16", 3600),),
        weekly_trend=(TrendPoint("2026-08-10", 7200),),
        monthly_trend=(TrendPoint("2026-08", 10800),),
        pattern=FocusPatternSummary(18, 21, 2700, 19),
        consistency=ConsistencySummary(4, 9, 24),
    )
    window.set_focus_item_colors({7: "#10B981"})
    window.set_analytics(snapshot)
    window.set_focus_distribution(
        AnalyticsDistributionPeriod.WEEKLY,
        [FocusItemTotal(7, "Writing", 7200)],
    )

    assert window._tabs.count() == 6
    assert window._daily_trend.values == snapshot.daily_trend
    assert window._weekly_trend.values == snapshot.weekly_trend
    assert window._monthly_trend.values == snapshot.monthly_trend
    assert window._distribution_chart.segments[0].name == "Writing"
    assert window._distribution_chart.segments[0].color == "#10B981"
    assert len(window._analytics_period_control._buttons) == 3
    assert (
        window._analytics_period_control.current_value
        is AnalyticsDistributionPeriod.WEEKLY
    )
    assert not hasattr(window, "_milestone_layout")
    window.close()


def test_dashboard_animates_only_an_actual_distribution_period_change(
    qt_application,
) -> None:
    window = DashboardWindow(timezone.utc)
    window._tabs.setCurrentIndex(DashboardPage.ANALYTICS)
    window.show()
    qt_application.processEvents()
    daily = [FocusItemTotal(1, "Daily", 1800)]
    weekly = [FocusItemTotal(2, "Weekly", 7200)]

    window.set_focus_distribution(AnalyticsDistributionPeriod.DAILY, daily)
    assert (
        window._distribution_chart.transition_phase
        is DistributionTransitionPhase.IDLE
    )

    window.set_focus_distribution(AnalyticsDistributionPeriod.WEEKLY, weekly)
    assert (
        window._distribution_chart.transition_phase
        is DistributionTransitionPhase.EXIT
    )
    window.close()


def test_distribution_uses_empty_state_for_sub_minute_data_and_seamless_single_item(
    qt_application,
) -> None:
    chart = FocusDistributionChart()
    chart.set_values([FocusItemTotal(1, "Too short", 59)], {1: "#EC4899"})
    assert chart.segments == ()
    assert chart.accessibleDescription()

    chart.set_values([FocusItemTotal(2, "Writing", 3600)], {2: "#3B82F6"})
    assert len(chart.segments) == 1
    assert chart.segments[0].span_degrees == pytest.approx(360)
    chart.resize(640, 320)
    chart.show()
    qt_application.processEvents()
    assert not chart.grab().isNull()
    chart.close()


@pytest.mark.parametrize(
    ("width", "expected_side"),
    ((420, 178.0), (760, 202.0), (1024, 202.0)),
)
def test_distribution_ring_size_is_independent_of_period_item_count(
    qt_application,
    width: int,
    expected_side: float,
) -> None:
    chart = FocusDistributionChart()
    geometries: list[tuple[float, float, float, float]] = []
    for count in (1, 2, 7):
        values = [
            FocusItemTotal(index, f"Item {index}", float((count - index) * 900))
            for index in range(count)
        ]
        chart.resize(width, max(300, chart.minimumHeight()))
        chart.set_values(values, {})
        chart.resize(width, chart.minimumHeight())
        donut = chart.donut_rect
        geometries.append((donut.x(), donut.y(), donut.width(), donut.height()))
        assert donut.width() == pytest.approx(expected_side)
        assert donut.height() == pytest.approx(expected_side)
        assert chart.inner_donut_rect.width() / donut.width() == pytest.approx(0.54)

    assert len(set(geometries)) == 1
    chart.close()


def test_distribution_reveal_sweeps_clockwise_from_twelve_oclock(
    qt_application,
) -> None:
    chart = FocusDistributionChart()
    chart.resize(760, 300)
    chart.set_values([FocusItemTotal(1, "Project", 3600)], {1: "#FF4D5A"})
    chart.show()
    qt_application.processEvents()
    chart._transition_phase = DistributionTransitionPhase.REVEAL
    chart._reveal_progress = 0.2
    chart._content_opacity = 1.0
    chart.repaint()
    qt_application.processEvents()

    image = chart.grab().toImage()
    donut = chart.donut_rect
    radius = donut.width() * 0.4
    clockwise_point = QPointF(
        donut.center().x() + radius * 0.707,
        donut.center().y() - radius * 0.707,
    ).toPoint()
    counterclockwise_point = QPointF(
        donut.center().x() - radius * 0.707,
        donut.center().y() - radius * 0.707,
    ).toPoint()
    clockwise_color = image.pixelColor(clockwise_point)
    counterclockwise_color = image.pixelColor(counterclockwise_point)

    assert _color_distance(clockwise_color, QColor("#FF4D5A")) < 20
    assert _color_distance(counterclockwise_color, QColor("#FF4D5A")) > 80
    chart.close()


def test_distribution_transition_has_exit_and_reveal_phases(qt_application) -> None:
    chart = FocusDistributionChart()
    chart.resize(760, 300)
    chart.set_values([FocusItemTotal(1, "Daily", 1800)], {1: "#FF4D5A"})
    chart.show()
    qt_application.processEvents()

    chart.set_values(
        [FocusItemTotal(2, "Weekly", 7200)],
        {2: "#4299E1"},
        animate=True,
    )
    assert chart.transition_phase is DistributionTransitionPhase.EXIT
    QTest.qWait(160)
    assert chart.transition_phase is DistributionTransitionPhase.REVEAL
    QTest.qWait(100)
    assert 0.0 < chart.reveal_progress < 1.0
    QTest.qWait(360)
    assert chart.transition_phase is DistributionTransitionPhase.IDLE
    assert chart.reveal_progress == pytest.approx(1.0)
    assert chart._display_segments[0].name == "Weekly"
    chart.close()


def test_distribution_rapid_switch_keeps_only_latest_target(qt_application) -> None:
    chart = FocusDistributionChart()
    chart.resize(760, 300)
    chart.set_values([FocusItemTotal(1, "Daily", 1800)], {})
    chart.show()
    qt_application.processEvents()

    chart.set_values([FocusItemTotal(2, "Weekly", 3600)], {}, animate=True)
    chart.set_values([FocusItemTotal(3, "Monthly", 7200)], {}, animate=True)
    assert chart.transition_phase is DistributionTransitionPhase.EXIT
    assert chart.segments[0].name == "Monthly"
    QTest.qWait(160)
    assert chart._display_segments[0].name == "Monthly"
    assert chart.transition_phase is DistributionTransitionPhase.REVEAL
    QTest.qWait(380)
    assert chart.transition_phase is DistributionTransitionPhase.IDLE
    assert chart._display_segments == chart.segments
    chart.close()


def test_distribution_transition_suspends_and_restores_ring_hover(
    qt_application,
) -> None:
    chart = FocusDistributionChart()
    chart.resize(760, 300)
    chart.set_values([FocusItemTotal(1, "Daily", 1800)], {})
    chart.show()
    qt_application.processEvents()
    hover_point = QPointF(
        chart.donut_rect.center().x() + chart.donut_rect.width() * 0.4,
        chart.donut_rect.center().y(),
    ).toPoint()

    QTest.mouseMove(chart, QPointF(1, 1).toPoint())
    QTest.mouseMove(chart, hover_point, delay=20)
    qt_application.processEvents()
    assert chart._hovered_index == 0

    chart.set_values([FocusItemTotal(2, "Weekly", 3600)], {}, animate=True)
    QTest.mouseMove(chart, hover_point)
    qt_application.processEvents()
    assert chart._hovered_index is None

    QTest.qWait(650)
    assert chart.transition_phase is DistributionTransitionPhase.IDLE
    assert chart._hovered_index == 0
    chart.close()


def _color_distance(first: QColor, second: QColor) -> int:
    return (
        abs(first.red() - second.red())
        + abs(first.green() - second.green())
        + abs(first.blue() - second.blue())
    )
