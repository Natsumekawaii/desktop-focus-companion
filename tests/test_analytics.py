"""Tests for the V1.1 heatmap and monthly analytics domain."""

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pytest

from app.data.database import Database
from app.data.focus_item_repository import FocusItemRepository
from app.data.focus_session_repository import FocusSessionRepository
from app.focus_mode import FocusMode
from app.statistics import StatisticsPeriod, StatisticsService


def _analytics(tmp_path: Path):
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    focus_items = FocusItemRepository(database)
    sessions = FocusSessionRepository(database)
    local_timezone = timezone(timedelta(hours=8))
    return focus_items, sessions, StatisticsService(sessions, local_timezone), local_timezone


def test_heatmap_is_dense_counts_sessions_and_splits_midnight(tmp_path: Path) -> None:
    subjects, sessions, statistics, local_timezone = _analytics(tmp_path)
    subject = subjects.create("Algorithms")
    day = datetime(2026, 8, 14, 9, tzinfo=local_timezone)
    sessions.create(subject, day, day + timedelta(minutes=20), 1200)
    sessions.create(subject, day + timedelta(hours=2), day + timedelta(hours=2, minutes=40), 2400)
    midnight = datetime(2026, 8, 14, 23, 30, tzinfo=local_timezone)
    sessions.create(subject, midnight, midnight + timedelta(hours=1), 3600)

    heatmap = statistics.heatmap_data(
        3,
        datetime(2026, 8, 15, 12, tzinfo=local_timezone),
    )

    assert [item.day.isoformat() for item in heatmap.days] == [
        "2026-08-13",
        "2026-08-14",
        "2026-08-15",
    ]
    assert [item.duration_seconds for item in heatmap.days] == pytest.approx([0, 5400, 1800])
    assert [item.session_count for item in heatmap.days] == [0, 3, 1]


def test_heatmap_365_day_boundary_and_cross_year(tmp_path: Path) -> None:
    subjects, sessions, statistics, local_timezone = _analytics(tmp_path)
    subject = subjects.create("Math")
    now = datetime(2026, 1, 1, 12, tzinfo=local_timezone)
    included = datetime(2025, 1, 2, 10, tzinfo=local_timezone)
    excluded = included - timedelta(days=1)
    sessions.create(subject, included, included + timedelta(minutes=10), 600)
    sessions.create(subject, excluded, excluded + timedelta(minutes=30), 1800)

    heatmap = statistics.heatmap_data(365, now)

    assert len(heatmap.days) == 365
    assert heatmap.start_day.isoformat() == "2025-01-02"
    assert heatmap.end_day.isoformat() == "2026-01-01"
    assert heatmap.days[0].duration_seconds == 600
    assert sum(item.duration_seconds for item in heatmap.days) == 600


@pytest.mark.parametrize(
    ("end_day", "expected_days"),
    [
        (date(2026, 8, 24), 365),
        (date(2026, 8, 25), 366),
        (date(2026, 8, 26), 367),
        (date(2026, 8, 27), 368),
        (date(2026, 8, 28), 369),
        (date(2026, 8, 29), 370),
        (date(2026, 8, 30), 371),
    ],
)
def test_focus_activity_completes_its_first_week(
    tmp_path: Path,
    end_day: date,
    expected_days: int,
) -> None:
    _items, _sessions, statistics, local_timezone = _analytics(tmp_path)
    reference = datetime.combine(
        end_day,
        time(hour=12),
        tzinfo=local_timezone,
    )

    heatmap = statistics.heatmap_data(
        365,
        reference,
        complete_start_week=True,
    )

    assert len(heatmap.days) == expected_days
    assert heatmap.start_day.weekday() == 0
    assert heatmap.end_day == end_day
    assert (len(heatmap.days) + 6) // 7 == 53


def test_completed_start_week_queries_real_padded_dates(tmp_path: Path) -> None:
    items, sessions, statistics, local_timezone = _analytics(tmp_path)
    item = items.create("Writing")
    reference = datetime(2026, 8, 29, 12, tzinfo=local_timezone)
    padded_day = datetime(2025, 8, 26, 9, tzinfo=local_timezone)
    excluded_day = datetime(2025, 8, 24, 9, tzinfo=local_timezone)
    sessions.create(item, padded_day, padded_day + timedelta(minutes=30), 1800)
    sessions.create(item, excluded_day, excluded_day + timedelta(minutes=45), 2700)

    heatmap = statistics.heatmap_data(
        365,
        reference,
        complete_start_week=True,
    )

    assert heatmap.start_day.isoformat() == "2025-08-25"
    assert heatmap.days[1].day == padded_day.date()
    assert heatmap.days[1].duration_seconds == 1800
    assert sum(day.duration_seconds for day in heatmap.days) == 1800


def test_daily_replay_uses_actual_sessions_and_hour_distribution(tmp_path: Path) -> None:
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    items = FocusItemRepository(database)
    sessions = FocusSessionRepository(database)
    writing = items.create("Writing")
    reading = items.create("Reading")
    first = datetime(2026, 8, 15, 9, 0, tzinfo=timezone.utc)
    sessions.create(writing, first, first + timedelta(minutes=50), 3000)
    later = first + timedelta(hours=10)
    sessions.create(reading, later, later + timedelta(minutes=30), 1800)
    statistics = StatisticsService(sessions, timezone.utc)

    replay = statistics.daily_replay(first.date())

    assert replay.total_seconds == 4800
    assert replay.session_count == 2
    assert replay.longest_session_seconds == 3000
    assert replay.top_focus_item is not None
    assert replay.top_focus_item.focus_item_name == "Writing"
    assert replay.hourly_seconds[9] == 3000
    assert replay.hourly_seconds[19] == 1800
    assert len(replay.hourly_seconds) == 24


def test_monthly_statistics_empty_and_leap_february(tmp_path: Path) -> None:
    _, _, statistics, _ = _analytics(tmp_path)

    month = statistics.monthly_statistics(2024, 2)

    assert len(month.daily_totals) == 29
    assert month.total_seconds == 0
    assert month.daily_average_seconds == 0
    assert month.focus_days == 0
    assert month.total_sessions == 0
    assert month.best_day is None
    assert month.top_focus_item is None
    assert month.comparison_percent is None


def test_monthly_overview_subjects_best_day_and_previous_comparison(tmp_path: Path) -> None:
    subjects, sessions, statistics, local_timezone = _analytics(tmp_path)
    math = subjects.create("Math")
    english = subjects.create("English")
    december = datetime(2025, 12, 20, 9, tzinfo=local_timezone)
    sessions.create(math, december, december + timedelta(hours=2), 7200)
    jan_first = datetime(2026, 1, 1, 9, tzinfo=local_timezone)
    sessions.create(math, jan_first, jan_first + timedelta(hours=1), 3600)
    sessions.create(english, jan_first + timedelta(hours=2), jan_first + timedelta(hours=2, minutes=30), 1800)
    jan_second = datetime(2026, 1, 2, 22, tzinfo=local_timezone)
    sessions.create(math, jan_second, jan_second + timedelta(hours=3), 10800)

    month = statistics.monthly_statistics(2026, 1)

    assert month.total_seconds == pytest.approx(16200)
    assert month.focus_days == 3
    assert month.daily_average_seconds == pytest.approx(5400)
    assert month.total_sessions == 3
    assert month.longest_session_seconds == pytest.approx(10800)
    assert month.best_day is not None
    assert month.best_day.day.isoformat() == "2026-01-02"
    assert month.best_day.duration_seconds == pytest.approx(7200)
    assert month.top_focus_item is not None
    assert month.top_focus_item.focus_item_name == "Math"
    assert month.top_focus_item.duration_seconds == pytest.approx(14400)
    assert month.previous_month_total_seconds == pytest.approx(7200)
    assert month.comparison_percent == pytest.approx(125.0)


def test_monthly_cross_month_session_is_allocated_to_both_months(tmp_path: Path) -> None:
    subjects, sessions, statistics, local_timezone = _analytics(tmp_path)
    subject = subjects.create("Night Study")
    start = datetime(2026, 2, 28, 23, 30, tzinfo=local_timezone)
    sessions.create(subject, start, start + timedelta(hours=1), 3600)

    february = statistics.monthly_statistics(2026, 2)
    march = statistics.monthly_statistics(2026, 3)

    assert february.total_seconds == pytest.approx(1800)
    assert march.total_seconds == pytest.approx(1800)
    assert march.previous_month_total_seconds == pytest.approx(1800)
    assert march.comparison_percent == pytest.approx(0.0)


def test_focus_analytics_uses_actual_duration_not_countdown_target(tmp_path: Path) -> None:
    database = Database(tmp_path / "focus.sqlite3")
    database.initialize()
    items = FocusItemRepository(database)
    sessions = FocusSessionRepository(database)
    item = items.create("Deep Work", "#EC4899")
    start = datetime(2026, 8, 15, 9, 0, tzinfo=timezone.utc)
    sessions.create(
        item,
        start,
        start + timedelta(minutes=10),
        600,
        mode=FocusMode.COUNTDOWN,
        target_duration_seconds=3600,
    )
    statistics = StatisticsService(sessions, timezone.utc)

    monthly = statistics.monthly_statistics(2026, 8)
    totals = statistics.focus_item_totals(StatisticsPeriod.ALL_TIME, start)

    assert monthly.total_seconds == 600
    assert monthly.focus_days == 1
    assert monthly.top_focus_item is not None
    assert monthly.top_focus_item.focus_item_id == item.id
    assert monthly.focus_item_totals[0].duration_seconds == 600
    assert totals[0].duration_seconds == 600
    assert statistics.total_focus_time() == 600
