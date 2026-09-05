"""End-to-end core flow from timer controls through progression updates."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.data.database import Database
from app.data.database_settings_repository import DatabaseSettingsRepository
from app.data.focus_item_repository import FocusItemRepository
from app.data.focus_session_repository import FocusSessionRepository
from app.data.gamification_repository import GamificationRepository
from app.gamification import GamificationService
from app.statistics import StatisticsService
from app.timer.focus_session_manager import FocusSessionManager
from app.timer.focus_timer import FocusTimer


@dataclass
class FakeClock:
    monotonic_value: float = 0.0
    wall_value: datetime = datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc)

    def monotonic(self) -> float:
        return self.monotonic_value

    def now(self) -> datetime:
        return self.wall_value

    def advance(self, seconds: float) -> None:
        self.monotonic_value += seconds
        self.wall_value += timedelta(seconds=seconds)


def test_start_pause_resume_finish_updates_data_statistics_xp_and_goal(tmp_path: Path) -> None:
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    focus_items = FocusItemRepository(database)
    sessions = FocusSessionRepository(database)
    focus_item = focus_items.create("Integration")
    clock = FakeClock()
    manager = FocusSessionManager(FocusTimer(clock), focus_items, sessions)
    statistics = StatisticsService(sessions, timezone.utc)
    gamification = GamificationService(
        statistics,
        DatabaseSettingsRepository(database),
        GamificationRepository(database),
    )
    gamification.set_preferences(60 * 60, 30 * 60)

    manager.start(focus_item.id)
    clock.advance(30 * 60)
    manager.pause()
    clock.advance(20 * 60)
    manager.resume()
    clock.advance(35 * 60)
    stored = manager.finish()
    snapshot = gamification.snapshot(clock.wall_value)

    assert stored.duration_seconds == 65 * 60
    assert statistics.today_total(clock.wall_value) == 65 * 60
    assert snapshot.today_seconds == 65 * 60
    assert snapshot.goal_completed
    assert snapshot.level.total_xp == 65
