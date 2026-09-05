"""Integration tests from StudyTimer through SQLite persistence."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.data.database import Database
from app.data.session_repository import SessionRepository
from app.data.subject_repository import SubjectRepository
from app.timer import (
    PendingSessionError,
    SessionManager,
    SessionPersistenceError,
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


def test_full_timer_finish_flow_persists_session(tmp_path: Path) -> None:
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    subjects = SubjectRepository(database)
    sessions = SessionRepository(database)
    subject = subjects.create("Algorithms")
    clock = FakeClock()
    manager = SessionManager(StudyTimer(clock), subjects, sessions)

    manager.start(subject.id)
    clock.advance(30 * 60)
    manager.pause()
    clock.advance(15 * 60)
    manager.resume()
    clock.advance(45 * 60)
    stored = manager.finish()

    assert stored.subject_name == "Algorithms"
    assert stored.duration_seconds == 75 * 60
    assert manager.current_state is TimerState.IDLE
    assert manager.active_subject is None
    assert sessions.get(stored.id) == stored


def test_failed_save_retains_result_for_retry(tmp_path: Path) -> None:
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    subjects = SubjectRepository(database)
    real_sessions = SessionRepository(database)
    subject = subjects.create("Resilient")
    clock = FakeClock()

    class FailingSessionRepository:
        should_fail = True

        def create(self, *args, **kwargs):
            if self.should_fail:
                raise RuntimeError("database unavailable")
            return real_sessions.create(*args, **kwargs)

    failing_sessions = FailingSessionRepository()
    manager = SessionManager(StudyTimer(clock), subjects, failing_sessions)  # type: ignore[arg-type]
    manager.start(subject.id)
    clock.advance(60)

    with pytest.raises(SessionPersistenceError):
        manager.finish()
    assert manager.has_pending_session
    with pytest.raises(PendingSessionError):
        manager.start(subject.id)

    failing_sessions.should_fail = False
    stored = manager.retry_pending_save()
    assert stored.duration_seconds == 60
    assert not manager.has_pending_session
