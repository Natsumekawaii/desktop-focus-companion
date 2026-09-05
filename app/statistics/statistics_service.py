"""Central focus statistics calculations independent from Qt UI."""

from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo
from enum import Enum

from app.data.focus_session_repository import FocusSessionRepository
from app.data.models import FocusSession
from app.statistics.time_allocation import (
    allocate_session_by_local_date,
    totals_by_local_date,
)


class StatisticsPeriod(Enum):
    TODAY = "today"
    THIS_WEEK = "this_week"
    ALL_TIME = "all_time"


class AnalyticsDistributionPeriod(Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


@dataclass(frozen=True, slots=True)
class DailyTotal:
    day: date
    duration_seconds: float


@dataclass(frozen=True, slots=True)
class FocusItemTotal:
    focus_item_id: int
    focus_item_name: str
    duration_seconds: float


@dataclass(frozen=True, slots=True)
class HeatmapDay:
    day: date
    duration_seconds: float
    session_count: int


@dataclass(frozen=True, slots=True)
class HeatmapData:
    start_day: date
    end_day: date
    days: tuple[HeatmapDay, ...]


@dataclass(frozen=True, slots=True)
class DailyReplaySummary:
    day: date
    total_seconds: float
    session_count: int
    longest_session_seconds: float
    top_focus_item: FocusItemTotal | None
    hourly_seconds: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class TrendPoint:
    label: str
    duration_seconds: float


@dataclass(frozen=True, slots=True)
class FocusPatternSummary:
    best_start_hour: int | None
    best_end_hour: int | None
    average_session_seconds: float
    common_start_hour: int | None


@dataclass(frozen=True, slots=True)
class ConsistencySummary:
    current_streak_days: int
    longest_streak_days: int
    active_days: int


@dataclass(frozen=True, slots=True)
class FocusAnalyticsSnapshot:
    daily_trend: tuple[TrendPoint, ...]
    weekly_trend: tuple[TrendPoint, ...]
    monthly_trend: tuple[TrendPoint, ...]
    pattern: FocusPatternSummary
    consistency: ConsistencySummary


@dataclass(frozen=True, slots=True)
class DashboardStatisticsSnapshot:
    """One request-scoped, internally consistent Dashboard read model."""

    today_total: float
    today_sessions: tuple[FocusSession, ...]
    weekly_daily_totals: tuple[DailyTotal, ...]
    today_focus_item_totals: tuple[FocusItemTotal, ...]
    weekly_focus_item_totals: tuple[FocusItemTotal, ...]
    all_time_focus_item_totals: tuple[FocusItemTotal, ...]
    analytics: FocusAnalyticsSnapshot
    recent_sessions: tuple[FocusSession, ...]
    history_sessions: tuple[FocusSession, ...]

    def focus_item_totals_for(
        self, period: StatisticsPeriod
    ) -> tuple[FocusItemTotal, ...]:
        """Return the precomputed totals for a Dashboard period selector."""

        if period is StatisticsPeriod.TODAY:
            return self.today_focus_item_totals
        if period is StatisticsPeriod.THIS_WEEK:
            return self.weekly_focus_item_totals
        return self.all_time_focus_item_totals


@dataclass(frozen=True, slots=True)
class MonthlyStatistics:
    year: int
    month: int
    total_seconds: float
    daily_average_seconds: float
    focus_days: int
    total_sessions: int
    longest_session_seconds: float
    best_day: DailyTotal | None
    top_focus_item: FocusItemTotal | None
    daily_totals: tuple[DailyTotal, ...]
    focus_item_totals: tuple[FocusItemTotal, ...]
    previous_month_total_seconds: float
    comparison_percent: float | None


class StatisticsService:
    """Calculate date- and Focus Item-based totals from actual focus duration."""

    def __init__(
        self,
        focus_session_repository: FocusSessionRepository,
        local_timezone: tzinfo | None = None,
    ) -> None:
        self._focus_sessions = focus_session_repository
        self._local_timezone = local_timezone or _system_local_timezone()

    @property
    def local_timezone(self) -> tzinfo:
        return self._local_timezone

    def today_total(self, now: datetime | None = None) -> float:
        target_day = self._local_day(now)
        sessions = self._focus_sessions.list_sessions()
        return self._totals_by_date_from_sessions(sessions).get(target_day, 0.0)

    def daily_totals(self, days: int = 7, now: datetime | None = None) -> list[DailyTotal]:
        """Return a dense sequence ending on the user's current local date."""
        if days <= 0:
            return []
        end_day = self._local_day(now)
        sessions = self._focus_sessions.list_sessions()
        return list(self._daily_totals_from_sessions(sessions, days, end_day))

    def dashboard_snapshot(
        self, now: datetime | None = None
    ) -> DashboardStatisticsSnapshot:
        """Build all unbounded Dashboard statistics from one repository read."""

        current_day = self._local_day(now)
        sessions = tuple(self._focus_sessions.list_sessions())
        daily_totals = self._totals_by_date_from_sessions(sessions)
        today_sessions = self._sessions_for_day_from_sessions(sessions, current_day)
        today_focus_items = self._focus_item_totals_from_sessions(
            sessions, StatisticsPeriod.TODAY, current_day
        )
        weekly_focus_items = self._focus_item_totals_from_sessions(
            sessions, StatisticsPeriod.THIS_WEEK, current_day
        )
        all_time_focus_items = self._focus_item_totals_from_sessions(
            sessions, StatisticsPeriod.ALL_TIME, current_day
        )
        return DashboardStatisticsSnapshot(
            today_total=daily_totals.get(current_day, 0.0),
            today_sessions=today_sessions,
            weekly_daily_totals=self._daily_totals_from_totals(
                daily_totals, 7, current_day
            ),
            today_focus_item_totals=today_focus_items,
            weekly_focus_item_totals=weekly_focus_items,
            all_time_focus_item_totals=all_time_focus_items,
            analytics=self._analytics_snapshot_from_sessions(
                sessions, daily_totals, current_day
            ),
            recent_sessions=sessions[:6],
            history_sessions=sessions[:1000],
        )

    def heatmap_data(
        self,
        days: int = 365,
        now: datetime | None = None,
        *,
        complete_start_week: bool = False,
    ) -> HeatmapData:
        """Aggregate a dense local-day heatmap from one bounded repository query."""
        if days <= 0:
            raise ValueError("Heatmap day count must be positive.")
        end_day = self._local_day(now)
        start_day = end_day - timedelta(days=days - 1)
        if complete_start_week:
            start_day -= timedelta(days=start_day.weekday())
        sessions = self._sessions_overlapping_local_days(start_day, end_day)
        totals: defaultdict[date, float] = defaultdict(float)
        counts: defaultdict[date, int] = defaultdict(int)
        for session in sessions:
            for local_day, duration in allocate_session_by_local_date(
                session, self._local_timezone
            ).items():
                if start_day <= local_day <= end_day and duration > 0:
                    totals[local_day] += duration
                    counts[local_day] += 1
        range_days = (end_day - start_day).days + 1
        values = tuple(
            HeatmapDay(
                day=start_day + timedelta(days=offset),
                duration_seconds=totals.get(start_day + timedelta(days=offset), 0.0),
                session_count=counts.get(start_day + timedelta(days=offset), 0),
            )
            for offset in range(range_days)
        )
        return HeatmapData(start_day=start_day, end_day=end_day, days=values)

    def monthly_statistics(self, year: int, month: int) -> MonthlyStatistics:
        """Return one calendar month's focus overview and item distribution."""
        if not 1 <= month <= 12:
            raise ValueError("Month must be between 1 and 12.")
        first_day = date(year, month, 1)
        day_count = monthrange(year, month)[1]
        last_day = date(year, month, day_count)
        previous_last = first_day - timedelta(days=1)
        previous_first = date(previous_last.year, previous_last.month, 1)
        sessions = self._sessions_overlapping_local_days(previous_first, last_day)

        current_totals: defaultdict[date, float] = defaultdict(float)
        previous_total = 0.0
        focus_item_totals: defaultdict[int, float] = defaultdict(float)
        focus_item_names: dict[int, str] = {}
        current_session_ids: set[int] = set()
        longest_session = 0.0
        for session in sessions:
            allocation = allocate_session_by_local_date(session, self._local_timezone)
            current_contribution = 0.0
            for local_day, duration in allocation.items():
                if first_day <= local_day <= last_day:
                    current_totals[local_day] += duration
                    focus_item_totals[session.focus_item_id] += duration
                    current_contribution += duration
                elif previous_first <= local_day <= previous_last:
                    previous_total += duration
            if current_contribution > 0:
                current_session_ids.add(session.id)
                longest_session = max(
                    longest_session,
                    min(session.duration_seconds, current_contribution),
                )
                focus_item_names.setdefault(
                    session.focus_item_id, session.focus_item_name
                )

        dense_daily = tuple(
            DailyTotal(
                first_day + timedelta(days=offset),
                current_totals.get(first_day + timedelta(days=offset), 0.0),
            )
            for offset in range(day_count)
        )
        focus_items = tuple(
            sorted(
                (
                    FocusItemTotal(item_id, focus_item_names[item_id], duration)
                    for item_id, duration in focus_item_totals.items()
                    if duration > 0
                ),
                key=lambda item: (-item.duration_seconds, item.focus_item_name.casefold()),
            )
        )
        total = sum(item.duration_seconds for item in dense_daily)
        focus_days = sum(item.duration_seconds > 0 for item in dense_daily)
        best_day = max(dense_daily, key=lambda item: item.duration_seconds) if focus_days else None
        comparison = None if previous_total <= 0 else (total - previous_total) / previous_total * 100.0
        return MonthlyStatistics(
            year=year,
            month=month,
            total_seconds=total,
            daily_average_seconds=total / focus_days if focus_days else 0.0,
            focus_days=focus_days,
            total_sessions=len(current_session_ids),
            longest_session_seconds=longest_session,
            best_day=best_day,
            top_focus_item=focus_items[0] if focus_items else None,
            daily_totals=dense_daily,
            focus_item_totals=focus_items,
            previous_month_total_seconds=previous_total,
            comparison_percent=comparison,
        )

    def focus_item_totals(
        self,
        period: StatisticsPeriod = StatisticsPeriod.ALL_TIME,
        now: datetime | None = None,
    ) -> list[FocusItemTotal]:
        """Aggregate actual duration by stable Focus Item id."""
        current_day = self._local_day(now)
        return list(
            self._focus_item_totals_from_sessions(
                self._focus_sessions.list_sessions(), period, current_day
            )
        )

    def _focus_item_totals_from_sessions(
        self,
        sessions: tuple[FocusSession, ...] | list[FocusSession],
        period: StatisticsPeriod,
        current_day: date,
    ) -> tuple[FocusItemTotal, ...]:
        allowed_days: set[date] | None
        if period is StatisticsPeriod.TODAY:
            allowed_days = {current_day}
        elif period is StatisticsPeriod.THIS_WEEK:
            week_start = current_day - timedelta(days=current_day.weekday())
            allowed_days = {week_start + timedelta(days=offset) for offset in range(7)}
        else:
            allowed_days = None

        totals: defaultdict[int, float] = defaultdict(float)
        names: dict[int, str] = {}
        for session in sessions:
            names.setdefault(session.focus_item_id, session.focus_item_name)
            for local_day, duration in allocate_session_by_local_date(session, self._local_timezone).items():
                if allowed_days is None or local_day in allowed_days:
                    totals[session.focus_item_id] += duration
        return tuple(sorted(
            (
                FocusItemTotal(item_id, names[item_id], duration)
                for item_id, duration in totals.items()
                if duration > 0
            ),
            key=lambda item: (-item.duration_seconds, item.focus_item_name.casefold()),
        ))

    def sessions_for_day(
        self, target_day: date | None = None
    ) -> list[FocusSession]:
        """Return sessions contributing any effective time to a local day."""
        selected_day = target_day or self._local_day(None)
        sessions = self._sessions_overlapping_local_days(selected_day, selected_day)
        return list(self._sessions_for_day_from_sessions(sessions, selected_day))

    def total_focus_time(self) -> float:
        return sum(session.duration_seconds for session in self._focus_sessions.list_sessions())

    def daily_replay(self, target_day: date | None = None) -> DailyReplaySummary:
        """Derive one factual daily summary without storing secondary data."""

        selected_day = target_day or self._local_day(None)
        sessions = self.sessions_for_day(selected_day)
        item_seconds: defaultdict[int, float] = defaultdict(float)
        item_names: dict[int, str] = {}
        hourly = [0.0] * 24
        longest = 0.0
        total = 0.0
        for session in sessions:
            contribution = allocate_session_by_local_date(
                session, self._local_timezone
            ).get(selected_day, 0.0)
            if contribution <= 0:
                continue
            total += contribution
            longest = max(longest, contribution)
            item_seconds[session.focus_item_id] += contribution
            item_names.setdefault(session.focus_item_id, session.focus_item_name)
            local_start = session.start_time.astimezone(self._local_timezone)
            hour = local_start.hour if local_start.date() == selected_day else 0
            hourly[hour] += contribution
        ranked = sorted(
            (
                FocusItemTotal(item_id, item_names[item_id], seconds)
                for item_id, seconds in item_seconds.items()
            ),
            key=lambda item: (-item.duration_seconds, item.focus_item_name.casefold()),
        )
        return DailyReplaySummary(
            day=selected_day,
            total_seconds=total,
            session_count=len(sessions),
            longest_session_seconds=longest,
            top_focus_item=ranked[0] if ranked else None,
            hourly_seconds=tuple(hourly),
        )

    def analytics_snapshot(
        self, now: datetime | None = None
    ) -> FocusAnalyticsSnapshot:
        """Derive trend, pattern, and consistency from canonical Focus Sessions."""

        current_day = self._local_day(now)
        sessions = tuple(self._focus_sessions.list_sessions())
        totals = self._totals_by_date_from_sessions(sessions)
        return self._analytics_snapshot_from_sessions(sessions, totals, current_day)

    def _analytics_snapshot_from_sessions(
        self,
        sessions: tuple[FocusSession, ...],
        totals: dict[date, float],
        current_day: date,
    ) -> FocusAnalyticsSnapshot:
        daily_start = current_day - timedelta(days=13)
        daily = tuple(
            TrendPoint(
                (daily_start + timedelta(days=offset)).isoformat(),
                totals.get(daily_start + timedelta(days=offset), 0.0),
            )
            for offset in range(14)
        )
        current_week = current_day - timedelta(days=current_day.weekday())
        weekly_points: list[TrendPoint] = []
        for reverse in range(7, -1, -1):
            week_start = current_week - timedelta(weeks=reverse)
            seconds = sum(
                totals.get(week_start + timedelta(days=offset), 0.0)
                for offset in range(7)
            )
            weekly_points.append(TrendPoint(week_start.isoformat(), seconds))
        monthly_points: list[TrendPoint] = []
        cursor_year, cursor_month = current_day.year, current_day.month
        months: list[tuple[int, int]] = []
        for _ in range(6):
            months.append((cursor_year, cursor_month))
            if cursor_month == 1:
                cursor_year -= 1
                cursor_month = 12
            else:
                cursor_month -= 1
        for year, month in reversed(months):
            seconds = sum(
                value
                for day_value, value in totals.items()
                if day_value.year == year and day_value.month == month
            )
            monthly_points.append(TrendPoint(f"{year:04d}-{month:02d}", seconds))

        bucket_seconds: defaultdict[int, float] = defaultdict(float)
        start_counts: defaultdict[int, int] = defaultdict(int)
        for session in sessions:
            local_start = session.start_time.astimezone(self._local_timezone)
            bucket_seconds[(local_start.hour // 3) * 3] += session.duration_seconds
            start_counts[local_start.hour] += 1
        best_start = (
            max(bucket_seconds, key=lambda hour: bucket_seconds[hour])
            if bucket_seconds
            else None
        )
        common_hour = (
            max(start_counts, key=lambda hour: (start_counts[hour], -hour))
            if start_counts
            else None
        )
        active_days = sorted(day_value for day_value, value in totals.items() if value > 0)
        active_set = set(active_days)
        streak_anchor = current_day if current_day in active_set else current_day - timedelta(days=1)
        current_streak = 0
        cursor = streak_anchor
        while cursor in active_set:
            current_streak += 1
            cursor -= timedelta(days=1)
        longest = 0
        running = 0
        previous: date | None = None
        for active_day in active_days:
            running = running + 1 if previous and active_day == previous + timedelta(days=1) else 1
            longest = max(longest, running)
            previous = active_day
        return FocusAnalyticsSnapshot(
            daily_trend=daily,
            weekly_trend=tuple(weekly_points),
            monthly_trend=tuple(monthly_points),
            pattern=FocusPatternSummary(
                best_start_hour=best_start,
                best_end_hour=(best_start + 3) % 24 if best_start is not None else None,
                average_session_seconds=(
                    sum(session.duration_seconds for session in sessions) / len(sessions)
                    if sessions
                    else 0.0
                ),
                common_start_hour=common_hour,
            ),
            consistency=ConsistencySummary(
                current_streak_days=current_streak,
                longest_streak_days=longest,
                active_days=len(active_days),
            ),
        )

    def totals_by_date(self) -> dict[date, float]:
        """Return all known local-day totals for streak and progress logic."""
        return self._totals_by_date_from_sessions(self._focus_sessions.list_sessions())

    def _totals_by_date_from_sessions(
        self, sessions: tuple[FocusSession, ...] | list[FocusSession]
    ) -> dict[date, float]:
        return totals_by_local_date(sessions, self._local_timezone)

    def _daily_totals_from_sessions(
        self,
        sessions: tuple[FocusSession, ...] | list[FocusSession],
        days: int,
        end_day: date,
    ) -> tuple[DailyTotal, ...]:
        return self._daily_totals_from_totals(
            self._totals_by_date_from_sessions(sessions), days, end_day
        )

    @staticmethod
    def _daily_totals_from_totals(
        totals: dict[date, float], days: int, end_day: date
    ) -> tuple[DailyTotal, ...]:
        first_day = end_day - timedelta(days=days - 1)
        return tuple(
            DailyTotal(
                first_day + timedelta(days=offset),
                totals.get(first_day + timedelta(days=offset), 0.0),
            )
            for offset in range(days)
        )

    def _sessions_for_day_from_sessions(
        self,
        sessions: tuple[FocusSession, ...] | list[FocusSession],
        selected_day: date,
    ) -> tuple[FocusSession, ...]:
        matching = (
            session
            for session in sessions
            if allocate_session_by_local_date(session, self._local_timezone).get(
                selected_day, 0.0
            )
            > 0
        )
        return tuple(sorted(matching, key=lambda session: session.start_time))

    def _local_day(self, now: datetime | None) -> date:
        current = now or datetime.now(tz=self._local_timezone)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("Statistics reference datetime must be timezone-aware.")
        return current.astimezone(self._local_timezone).date()

    def _sessions_overlapping_local_days(
        self,
        first_day: date,
        last_day: date,
    ) -> list[FocusSession]:
        local_start = datetime.combine(first_day, time.min, tzinfo=self._local_timezone)
        local_end = datetime.combine(last_day + timedelta(days=1), time.min, tzinfo=self._local_timezone)
        return list(self._focus_sessions.list_overlapping(local_start, local_end))


def _system_local_timezone() -> tzinfo:
    timezone_value = datetime.now().astimezone().tzinfo
    if timezone_value is None:
        raise RuntimeError("Unable to determine the local timezone.")
    return timezone_value
