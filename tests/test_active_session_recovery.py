"""Crash-recovery checkpoints never count time while Desktop Focus Companion was not running."""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.data.database import Database
from app.data.session_repository import SessionRepository
from app.data.subject_repository import SubjectRepository
from app.timer import (
    ActiveSessionStore,
    SessionManager,
    StudyMode,
    StudyTimer,
    TimerState,
)


@dataclass
class FakeClock:
    monotonic_value: float = 100.0
    wall_value: datetime = datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc)

    def monotonic(self) -> float:
        return self.monotonic_value

    def now(self) -> datetime:
        return self.wall_value

    def advance(self, seconds: float) -> None:
        self.monotonic_value += seconds
        self.wall_value += timedelta(seconds=seconds)


def test_running_session_recovers_paused_without_crash_downtime(tmp_path: Path) -> None:
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    subjects = SubjectRepository(database)
    sessions = SessionRepository(database)
    subject = subjects.create("Recovery")
    store = ActiveSessionStore(tmp_path / "active-session.json")
    first_clock = FakeClock()
    first = SessionManager(StudyTimer(first_clock), subjects, sessions, store)
    first.start(subject.id)
    first_clock.advance(600)
    first.checkpoint()

    restarted_clock = FakeClock(wall_value=first_clock.wall_value + timedelta(hours=8))
    restarted = SessionManager(StudyTimer(restarted_clock), subjects, sessions, store)
    assert restarted.has_recoverable_session

    assert restarted.recover_active_session() is None
    assert restarted.current_state is TimerState.PAUSED
    assert restarted.elapsed_seconds == 600
    saved = restarted.finish()
    assert saved.duration_seconds == 600
    assert not store.path.exists()


def test_discard_removes_recovery_without_creating_session(tmp_path: Path) -> None:
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    subjects = SubjectRepository(database)
    sessions = SessionRepository(database)
    subject = subjects.create("Discard")
    store = ActiveSessionStore(tmp_path / "active-session.json")
    first = SessionManager(StudyTimer(FakeClock()), subjects, sessions, store)
    first.start(subject.id)
    restarted = SessionManager(StudyTimer(FakeClock()), subjects, sessions, store)

    restarted.discard_recovery()

    assert not restarted.has_recoverable_session
    assert not store.path.exists()
    assert sessions.list_sessions() == []


def test_countdown_recovery_preserves_target_and_excludes_crash_downtime(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    subjects = SubjectRepository(database)
    sessions = SessionRepository(database)
    subject = subjects.create("Countdown Recovery")
    store = ActiveSessionStore(tmp_path / "active-session.json")
    first_clock = FakeClock()
    first = SessionManager(StudyTimer(first_clock), subjects, sessions, store)
    first.start(subject.id, StudyMode.COUNTDOWN, 60 * 60)
    first_clock.advance(32 * 60)
    first.checkpoint()

    restarted_clock = FakeClock(wall_value=first_clock.wall_value + timedelta(hours=8))
    restarted = SessionManager(StudyTimer(restarted_clock), subjects, sessions, store)
    assert restarted.recover_active_session() is None
    assert restarted.current_state is TimerState.PAUSED
    assert restarted.study_mode is StudyMode.COUNTDOWN
    assert restarted.target_duration_seconds == 60 * 60
    assert restarted.elapsed_seconds == 32 * 60
    assert restarted.remaining_seconds == 28 * 60

    restarted_clock.advance(90 * 60)
    assert restarted.elapsed_seconds == 32 * 60
    assert restarted.remaining_seconds == 28 * 60
    saved = restarted.finish()
    assert saved.duration_seconds == 32 * 60
    assert saved.study_mode == StudyMode.COUNTDOWN.value
    assert saved.target_duration_seconds == 60 * 60


def test_version_one_checkpoint_loads_as_stopwatch(tmp_path: Path) -> None:
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    subjects = SubjectRepository(database)
    sessions = SessionRepository(database)
    subject = subjects.create("Legacy Recovery")
    store = ActiveSessionStore(tmp_path / "active-session.json")
    manager = SessionManager(StudyTimer(FakeClock()), subjects, sessions, store)
    manager.start(subject.id)
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    payload["subject_id"] = payload.pop("focus_item_id")
    payload["subject_name"] = payload.pop("focus_item_name")
    payload["version"] = 1
    payload.pop("mode")
    payload.pop("target_duration_seconds")
    store.path.write_text(json.dumps(payload), encoding="utf-8")

    checkpoint = store.load()

    assert checkpoint is not None
    assert checkpoint.mode == StudyMode.STOPWATCH.value
    assert checkpoint.target_duration_seconds is None
