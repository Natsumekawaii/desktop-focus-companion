"""Tests for goals, streak, XP, and levels."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.data.database import Database
from app.data.database_settings_repository import DatabaseSettingsRepository
from app.data.focus_item_repository import FocusItemRepository
from app.data.focus_session_repository import FocusSessionRepository
from app.data.gamification_repository import GamificationRepository
from app.gamification.gamification_service import GamificationService, calculate_level
from app.statistics import StatisticsService


def _services(tmp_path: Path):
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    focus_items = FocusItemRepository(database)
    sessions = FocusSessionRepository(database)
    statistics = StatisticsService(sessions, timezone.utc)
    gamification = GamificationService(
        statistics,
        DatabaseSettingsRepository(database),
        GamificationRepository(database),
    )
    return focus_items, sessions, gamification


def test_xp_and_level_formula_is_explainable() -> None:
    assert calculate_level(0).level == 1
    assert calculate_level(299).level == 1
    assert calculate_level(300).level == 2
    level_three = calculate_level(900)
    assert level_three.level == 3
    assert level_three.xp_into_level == 0
    assert level_three.xp_for_next_level == 900


def test_preferences_goal_progress_and_goal_celebration_once(tmp_path: Path) -> None:
    subjects, sessions, gamification = _services(tmp_path)
    subject = subjects.create("Goal")
    now = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)
    gamification.set_preferences(60 * 60, 20 * 60, 60 * 60)
    sessions.create(subject, now - timedelta(hours=1), now, 62 * 60)

    snapshot = gamification.snapshot(now)

    assert snapshot.goal_completed
    assert snapshot.goal_progress == 1.0
    assert snapshot.weekly_goal_completed
    assert snapshot.weekly_goal_progress == 1.0
    assert snapshot.weekly_seconds == 62 * 60
    assert snapshot.level.total_xp == 62
    assert snapshot.streak_days == 1
    assert gamification.mark_goal_celebrated_today(now)
    assert not gamification.mark_goal_celebrated_today(now)


def test_streak_handles_month_and_year_boundaries(tmp_path: Path) -> None:
    subjects, sessions, gamification = _services(tmp_path)
    subject = subjects.create("Daily")
    gamification.set_preferences(5 * 3600, 30 * 60)
    for day in (29, 30, 31):
        start = datetime(2025, 12, day, 10, 0, tzinfo=timezone.utc)
        sessions.create(subject, start, start + timedelta(minutes=30), 1800)
    january_first = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    sessions.create(subject, january_first, january_first + timedelta(minutes=30), 1800)

    january_second = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)
    january_third = datetime(2026, 1, 3, 12, 0, tzinfo=timezone.utc)
    assert gamification.snapshot(january_second).streak_days == 4
    assert gamification.snapshot(january_third).streak_days == 0


def test_weekly_focus_goal_uses_current_monday_to_sunday_window(tmp_path: Path) -> None:
    subjects, sessions, gamification = _services(tmp_path)
    subject = subjects.create("Weekly")
    gamification.set_preferences(3600, 1800, 7200)
    sunday = datetime(2026, 8, 9, 10, 0, tzinfo=timezone.utc)
    monday = datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc)
    sessions.create(subject, sunday, sunday + timedelta(hours=1), 3600)
    sessions.create(subject, monday, monday + timedelta(hours=1), 3600)

    snapshot = gamification.snapshot(monday + timedelta(hours=2))

    assert snapshot.weekly_seconds == 3600
    assert snapshot.weekly_goal_seconds == 7200
    assert snapshot.weekly_goal_progress == 0.5
    assert not snapshot.weekly_goal_completed
