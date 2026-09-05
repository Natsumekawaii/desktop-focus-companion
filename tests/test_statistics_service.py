"""Tests for local-day, weekly, subject, and midnight statistics."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.data.database import Database
from app.data.focus_item_repository import FocusItemRepository
from app.data.focus_session_repository import FocusSessionRepository
from app.statistics import StatisticsPeriod, StatisticsService


def test_cross_midnight_session_splits_between_local_dates(tmp_path: Path) -> None:
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    focus_items = FocusItemRepository(database)
    sessions = FocusSessionRepository(database)
    focus_item = focus_items.create("Night Focus")
    local_timezone = timezone(timedelta(hours=8))
    local_start = datetime(2026, 8, 14, 23, 30, tzinfo=local_timezone)
    sessions.create(focus_item, local_start, local_start + timedelta(hours=1), 3600)
    statistics = StatisticsService(sessions, local_timezone)
    now = datetime(2026, 8, 15, 12, 0, tzinfo=local_timezone)

    daily = statistics.daily_totals(2, now)

    assert [item.duration_seconds for item in daily] == pytest.approx([1800, 1800])
    assert statistics.today_total(now) == pytest.approx(1800)
    assert len(statistics.sessions_for_day(local_start.date())) == 1
    assert len(statistics.sessions_for_day((local_start + timedelta(days=1)).date())) == 1


def test_focus_item_periods_and_total_focus_time(tmp_path: Path) -> None:
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    focus_items = FocusItemRepository(database)
    sessions = FocusSessionRepository(database)
    math = focus_items.create("Math")
    writing = focus_items.create("Writing")
    local_timezone = timezone(timedelta(hours=8))
    now = datetime(2026, 8, 14, 12, 0, tzinfo=local_timezone)
    sessions.create(math, now - timedelta(hours=2), now - timedelta(hours=1), 3600)
    sessions.create(writing, now - timedelta(days=2), now - timedelta(days=2) + timedelta(minutes=30), 1800)
    sessions.create(math, now - timedelta(days=10), now - timedelta(days=10) + timedelta(minutes=20), 1200)
    statistics = StatisticsService(sessions, local_timezone)

    today = statistics.focus_item_totals(StatisticsPeriod.TODAY, now)
    week = statistics.focus_item_totals(StatisticsPeriod.THIS_WEEK, now)
    all_time = statistics.focus_item_totals(StatisticsPeriod.ALL_TIME, now)

    assert [(item.focus_item_name, item.duration_seconds) for item in today] == [("Math", 3600)]
    assert {item.focus_item_name: item.duration_seconds for item in week} == {"Math": 3600, "Writing": 1800}
    assert {item.focus_item_name: item.duration_seconds for item in all_time} == {
        "Math": 4800,
        "Writing": 1800,
    }
    assert statistics.total_focus_time() == 6600


def test_dashboard_snapshot_matches_existing_statistics_methods(tmp_path: Path) -> None:
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    focus_items = FocusItemRepository(database)
    sessions = FocusSessionRepository(database)
    writing = focus_items.create("Writing", "#4299E1")
    reading = focus_items.create("Reading", "#55C52B")
    local_timezone = timezone(timedelta(hours=8))
    now = datetime(2026, 8, 16, 12, 0, tzinfo=local_timezone)
    entries = (
        (writing, datetime(2026, 8, 16, 9, 0, tzinfo=local_timezone), 3600),
        (reading, datetime(2026, 8, 15, 23, 30, tzinfo=local_timezone), 3600),
        (writing, datetime(2026, 8, 10, 14, 0, tzinfo=local_timezone), 1800),
        (reading, datetime(2026, 7, 1, 8, 0, tzinfo=local_timezone), 1200),
    )
    for item, start, duration in entries:
        sessions.create(item, start, start + timedelta(seconds=duration), duration)
    statistics = StatisticsService(sessions, local_timezone)

    expected_today_total = statistics.today_total(now)
    expected_today_sessions = tuple(statistics.sessions_for_day(now.date()))
    expected_weekly = tuple(statistics.daily_totals(7, now))
    expected_today_items = tuple(
        statistics.focus_item_totals(StatisticsPeriod.TODAY, now)
    )
    expected_weekly_items = tuple(
        statistics.focus_item_totals(StatisticsPeriod.THIS_WEEK, now)
    )
    expected_all_time_items = tuple(
        statistics.focus_item_totals(StatisticsPeriod.ALL_TIME, now)
    )
    expected_analytics = statistics.analytics_snapshot(now)
    expected_recent = tuple(sessions.list_sessions(limit=6))
    expected_history = tuple(sessions.list_sessions(limit=1000))

    snapshot = statistics.dashboard_snapshot(now)

    assert snapshot.today_total == expected_today_total
    assert snapshot.today_sessions == expected_today_sessions
    assert snapshot.weekly_daily_totals == expected_weekly
    assert snapshot.today_focus_item_totals == expected_today_items
    assert snapshot.weekly_focus_item_totals == expected_weekly_items
    assert snapshot.all_time_focus_item_totals == expected_all_time_items
    assert snapshot.analytics == expected_analytics
    assert snapshot.recent_sessions == expected_recent
    assert snapshot.history_sessions == expected_history
    assert snapshot.focus_item_totals_for(StatisticsPeriod.TODAY) == expected_today_items
    assert (
        snapshot.focus_item_totals_for(StatisticsPeriod.THIS_WEEK)
        == expected_weekly_items
    )
    assert (
        snapshot.focus_item_totals_for(StatisticsPeriod.ALL_TIME)
        == expected_all_time_items
    )
