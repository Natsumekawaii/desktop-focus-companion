"""Derived focus goals, streaks, XP, and levels."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.data.database_settings_repository import DatabaseSettingsRepository
from app.data.gamification_repository import GamificationRepository
from app.i18n import tr
from app.statistics import StatisticsService

DAILY_GOAL_KEY = "daily_goal_seconds"
WEEKLY_GOAL_KEY = "weekly_goal_seconds"
STREAK_MINIMUM_KEY = "streak_minimum_seconds"
DEFAULT_DAILY_GOAL_SECONDS = 5 * 60 * 60
DEFAULT_WEEKLY_GOAL_SECONDS = 25 * 60 * 60
DEFAULT_STREAK_MINIMUM_SECONDS = 30 * 60


@dataclass(frozen=True, slots=True)
class LevelProgress:
    level: int
    total_xp: int
    xp_into_level: int
    xp_for_next_level: int


@dataclass(frozen=True, slots=True)
class GamificationSnapshot:
    today_seconds: float
    daily_goal_seconds: int
    goal_progress: float
    goal_completed: bool
    weekly_seconds: float
    weekly_goal_seconds: int
    weekly_goal_progress: float
    weekly_goal_completed: bool
    streak_days: int
    streak_minimum_seconds: int
    level: LevelProgress


class GamificationService:
    """Derive progression from sessions and persist only durable one-time flags."""

    def __init__(
        self,
        statistics_service: StatisticsService,
        settings_repository: DatabaseSettingsRepository,
        gamification_repository: GamificationRepository,
    ) -> None:
        self._statistics = statistics_service
        self._settings = settings_repository
        self._repository = gamification_repository

    def daily_goal_seconds(self) -> int:
        return _positive_setting(
            self._settings.get(DAILY_GOAL_KEY),
            DEFAULT_DAILY_GOAL_SECONDS,
        )

    def streak_minimum_seconds(self) -> int:
        return _positive_setting(
            self._settings.get(STREAK_MINIMUM_KEY),
            DEFAULT_STREAK_MINIMUM_SECONDS,
        )

    def weekly_goal_seconds(self) -> int:
        return _positive_setting(
            self._settings.get(WEEKLY_GOAL_KEY),
            DEFAULT_WEEKLY_GOAL_SECONDS,
        )

    def set_preferences(
        self,
        daily_goal_seconds: int,
        streak_minimum_seconds: int,
        weekly_goal_seconds: int | None = None,
    ) -> None:
        weekly = weekly_goal_seconds or self.weekly_goal_seconds()
        if daily_goal_seconds <= 0 or streak_minimum_seconds <= 0 or weekly <= 0:
            raise ValueError(tr("error.study_goals_positive"))
        self._settings.set(DAILY_GOAL_KEY, str(int(daily_goal_seconds)))
        self._settings.set(WEEKLY_GOAL_KEY, str(int(weekly)))
        self._settings.set(STREAK_MINIMUM_KEY, str(int(streak_minimum_seconds)))

    def snapshot(self, now: datetime | None = None) -> GamificationSnapshot:
        local_now = now or datetime.now(tz=self._statistics.local_timezone)
        if local_now.tzinfo is None or local_now.utcoffset() is None:
            raise ValueError("Gamification reference datetime must be timezone-aware.")
        local_day = local_now.astimezone(self._statistics.local_timezone).date()
        daily_totals = self._statistics.totals_by_date()
        today_seconds = daily_totals.get(local_day, 0.0)
        goal_seconds = self.daily_goal_seconds()
        week_start = local_day - timedelta(days=local_day.weekday())
        weekly_seconds = sum(
            daily_totals.get(week_start + timedelta(days=offset), 0.0)
            for offset in range(7)
        )
        weekly_goal = self.weekly_goal_seconds()
        minimum_seconds = self.streak_minimum_seconds()
        streak = calculate_current_streak(daily_totals, local_day, minimum_seconds)
        total_seconds = self._statistics.total_focus_time()
        total_xp = int(total_seconds // 60)
        level = calculate_level(total_xp)
        return GamificationSnapshot(
            today_seconds=today_seconds,
            daily_goal_seconds=goal_seconds,
            goal_progress=min(1.0, today_seconds / goal_seconds),
            goal_completed=today_seconds >= goal_seconds,
            weekly_seconds=weekly_seconds,
            weekly_goal_seconds=weekly_goal,
            weekly_goal_progress=min(1.0, weekly_seconds / weekly_goal),
            weekly_goal_completed=weekly_seconds >= weekly_goal,
            streak_days=streak,
            streak_minimum_seconds=minimum_seconds,
            level=level,
        )

    def mark_goal_celebrated_today(self, now: datetime | None = None) -> bool:
        local_now = now or datetime.now(tz=self._statistics.local_timezone)
        local_day = local_now.astimezone(self._statistics.local_timezone).date()
        return self._repository.mark_goal_celebrated(local_day)


def calculate_current_streak(
    daily_totals: dict[date, float],
    current_day: date,
    minimum_seconds: int,
) -> int:
    """Count consecutive qualifying local dates ending today or yesterday."""
    cursor = current_day
    if daily_totals.get(cursor, 0.0) < minimum_seconds:
        cursor -= timedelta(days=1)
    streak = 0
    while daily_totals.get(cursor, 0.0) >= minimum_seconds:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def calculate_level(total_xp: int) -> LevelProgress:
    """Calculate level using threshold 150 × (level−1) × level."""
    level = 1
    while total_xp >= _level_threshold(level + 1):
        level += 1
    current_threshold = _level_threshold(level)
    next_threshold = _level_threshold(level + 1)
    return LevelProgress(
        level=level,
        total_xp=total_xp,
        xp_into_level=total_xp - current_threshold,
        xp_for_next_level=next_threshold - current_threshold,
    )


def _level_threshold(level: int) -> int:
    return 150 * (level - 1) * level


def _positive_setting(value: str | None, default: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except ValueError:
        return default
    return parsed if parsed > 0 else default
