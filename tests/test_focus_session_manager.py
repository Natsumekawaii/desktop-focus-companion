"""Tests for the canonical Focus timer and session manager."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.data.database import Database
from app.data.focus_item_repository import FocusItemRepository
from app.data.focus_session_repository import FocusSessionRepository
from app.data.models import FocusSessionSource
from app.focus_mode import FocusMode
from app.timer import ActiveSessionStore, FocusSessionManager, FocusTimer, TimerState


@dataclass
class FakeClock:
    monotonic_value: float = 1000.0
    wall_value: datetime = datetime(2026, 8, 15, 8, 0, tzinfo=timezone.utc)

    def monotonic(self) -> float:
        return self.monotonic_value

    def now(self) -> datetime:
        return self.wall_value

    def advance(self, seconds: float) -> None:
        self.monotonic_value += seconds
        self.wall_value += timedelta(seconds=seconds)


def _manager(tmp_path: Path, clock: FakeClock):
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    items = FocusItemRepository(database)
    sessions = FocusSessionRepository(database)
    store = ActiveSessionStore(tmp_path / "active-session.json")
    return items, sessions, store, FocusSessionManager(FocusTimer(clock), items, sessions, store)


def test_focus_manager_persists_actual_duration_note_mode_and_source(tmp_path: Path) -> None:
    clock = FakeClock()
    items, sessions, _store, manager = _manager(tmp_path, clock)
    item = items.create("创作", "#EC4899")

    manager.start(item.id, FocusMode.COUNTDOWN, 3600, "  chapter outline  ")
    clock.advance(1200)
    manager.pause()
    clock.advance(600)
    manager.resume()
    clock.advance(300)
    saved = manager.finish()

    assert saved == sessions.get(saved.id)
    assert saved.focus_item_id == item.id
    assert saved.duration_seconds == 1500
    assert saved.mode is FocusMode.COUNTDOWN
    assert saved.target_duration_seconds == 3600
    assert saved.note == "chapter outline"
    assert saved.source is FocusSessionSource.TIMER
    assert manager.current_state is TimerState.IDLE


def test_focus_recovery_v3_preserves_note_without_counting_downtime(tmp_path: Path) -> None:
    clock = FakeClock()
    items, sessions, store, manager = _manager(tmp_path, clock)
    item = items.create("工作")
    manager.start(item.id, note="Release checklist")
    clock.advance(900)
    manager.checkpoint()

    restarted_clock = FakeClock(wall_value=clock.wall_value + timedelta(hours=4))
    restarted = FocusSessionManager(FocusTimer(restarted_clock), items, sessions, store)

    assert restarted.recover_active_session() is None
    assert restarted.current_state is TimerState.PAUSED
    assert restarted.elapsed_seconds == 900
    assert restarted.active_note == "Release checklist"
    saved = restarted.finish()
    assert saved.duration_seconds == 900
    assert saved.note == "Release checklist"


@pytest.mark.parametrize(
    ("elapsed_seconds", "saved_seconds"),
    ((60, 60), (119, 60), (120, 120)),
)
def test_focus_manager_saves_only_completed_minutes(
    tmp_path: Path, elapsed_seconds: int, saved_seconds: int
) -> None:
    clock = FakeClock()
    items, sessions, _store, manager = _manager(tmp_path, clock)
    item = items.create("Minute precision")
    manager.start(item.id)
    clock.advance(elapsed_seconds)

    saved = manager.finish()

    assert saved.duration_seconds == saved_seconds
    assert sessions.get(saved.id).duration_seconds == saved_seconds
