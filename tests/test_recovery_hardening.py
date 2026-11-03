"""Recovery validation is atomic, including error paths during file cleanup."""
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.data.database import Database
from app.data.focus_item_repository import FocusItemRepository
from app.data.focus_session_repository import FocusSessionRepository
from app.timer.active_session_store import (
    ActiveSessionCheckpoint,
    ActiveSessionStore,
    ActiveSessionStoreError,
)
from app.timer.focus_session_manager import FocusSessionManager
from app.timer.focus_timer import FocusTimer, InvalidTimerStateError
from app.timer.timer_state import TimerState


def checkpoint(item_id=1):
    return ActiveSessionCheckpoint('token', item_id, 'Synthetic', datetime.now(timezone.utc),
                                   60, 'PAUSED', datetime.now(timezone.utc))


def test_checkpoint_save_rejects_mutated_nonfinite_value_without_replacing_file(tmp_path):
    value = checkpoint()
    store = ActiveSessionStore(tmp_path / 'active-session.json')
    store.save(value)
    original = store.path.read_bytes()
    object.__setattr__(value, 'accumulated_seconds', float('nan'))
    with pytest.raises(ValueError):
        store.save(value)
    assert store.path.read_bytes() == original


def test_failed_checkpoint_cleanup_keeps_original_exception(tmp_path, monkeypatch):
    failure = OSError('replace failed')
    def fail_replace(*_args):
        raise failure
    def fail_unlink(*_args, **_kwargs):
        raise OSError('cleanup failed')
    with monkeypatch.context() as scope:
        scope.setattr(os, 'replace', fail_replace)
        scope.setattr(Path, 'unlink', fail_unlink)
        with pytest.raises(ActiveSessionStoreError) as error:
            ActiveSessionStore(tmp_path / 'active-session.json').save(checkpoint())
        assert error.value.__cause__ is failure


@pytest.mark.parametrize('invalid', [True, float('nan'), -1])
def test_invalid_recovery_does_not_assign_active_identity(tmp_path, invalid):
    database = Database(tmp_path / 'test.sqlite3')
    database.initialize()
    items = FocusItemRepository(database)
    item = items.create('Synthetic')
    store = ActiveSessionStore(tmp_path / 'active-session.json')
    store.save(checkpoint(item.id))
    manager = FocusSessionManager(FocusTimer(), items, FocusSessionRepository(database), store)
    object.__setattr__(manager.recovery_checkpoint, 'accumulated_seconds', invalid)
    with pytest.raises((TypeError, ValueError)):
        manager.recover_active_session()
    assert manager.active_focus_item is None
    assert manager.current_state is TimerState.IDLE
    assert manager.has_recoverable_session


def test_recovery_cannot_mutate_a_running_timer(tmp_path):
    database = Database(tmp_path / 'test.sqlite3')
    database.initialize()
    items = FocusItemRepository(database)
    item = items.create('Synthetic')
    store = ActiveSessionStore(tmp_path / 'active-session.json')
    store.save(checkpoint(item.id))
    timer = FocusTimer()
    manager = FocusSessionManager(timer, items, FocusSessionRepository(database), store)
    original = manager.recovery_checkpoint
    timer.start()
    with pytest.raises(InvalidTimerStateError):
        manager.recover_active_session()
    assert manager.recovery_checkpoint is original
    assert manager.active_focus_item is None
    assert timer.current_state is TimerState.FOCUSING
