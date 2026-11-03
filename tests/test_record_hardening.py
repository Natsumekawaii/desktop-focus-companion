"""Regression coverage for lossless editing, recovery boundaries and DST."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from PySide6.QtCore import QDate, QTime

from app.core.timezones import elapsed_seconds, local_candidates
from app.data.models import FocusItem, FocusSession, FocusSessionSource
from app.focus_mode import FocusMode
from app.statistics.time_allocation import allocate_session_by_local_date
from app.timer.active_session_store import ActiveSessionCheckpoint, ActiveSessionStore
from app.timer.focus_timer import FocusTimer
from app.timer.timer_state import TimerState
from app.ui.session_editor_dialog import SessionEditorDialog


def record(*, hours=2, duration=3600, zone=timezone.utc):
    start = datetime(2026, 1, 3, 10, 0, 23, 4567, tzinfo=zone)
    return FocusSession(1, 1, 'Synthetic', start, start + timedelta(hours=hours), duration,
                        FocusMode.STOPWATCH, None, 'note', FocusSessionSource.TIMER, start, start)


def editor(session, zone=timezone.utc):
    dialog = SessionEditorDialog(zone)
    item = FocusItem(1, 'Synthetic', '#7C5CFC', False, False, session.created_at, session.created_at)
    dialog.set_focus_items([item])
    dialog.set_session(session)
    return dialog


@pytest.mark.parametrize('hours,duration', [(2, 3600), (30, 108000), (1100, 3960000)])
def test_editor_roundtrip_preserves_seconds_multi_day_and_long_duration(qt_application, hours, duration):
    session = record(hours=hours, duration=duration)
    dialog = editor(session)
    assert dialog.focus_values()[1:4] == (session.start_time, session.end_time, session.duration_seconds)
    dialog._note_edit.setPlainText('changed')
    assert dialog.focus_values()[1:4] == (session.start_time, session.end_time, session.duration_seconds)
    dialog._start_edit.setTime(QTime(9, 0))
    assert dialog.focus_values()[2:4] == (session.end_time, session.duration_seconds)
    dialog._duration_picker.setValue(30)
    assert dialog.focus_values()[2:4] == (session.end_time, 1800)


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf'), -1, True, False])
def test_restore_rejects_invalid_elapsed_without_changing_state(value):
    timer = FocusTimer()
    with pytest.raises((ValueError, TypeError)):
        timer.restore_paused(datetime.now(timezone.utc), value)
    assert timer.current_state is TimerState.IDLE
    assert timer.start_time is None
    with pytest.raises((ValueError, TypeError)):
        ActiveSessionCheckpoint('token', 1, 'Synthetic', datetime.now(timezone.utc), value,
                                'PAUSED', datetime.now(timezone.utc))


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-Infinity', 'true', '-1'])
def test_invalid_json_checkpoint_is_preserved(tmp_path, value):
    path = tmp_path / 'active-session.json'
    path.write_text('{"version":4,"recovery_token":"token","focus_item_id":1,"focus_item_name":"Synthetic",'
                    '"start_time":"2026-01-01T00:00:00+00:00","last_checkpoint":"2026-01-01T00:00:00+00:00",'
                    '"timer_state":"PAUSED","accumulated_seconds":' + value + '}', encoding='utf-8')
    assert ActiveSessionStore(path).load() is None
    assert not path.exists()
    assert len(list(tmp_path.glob('active-session.corrupt-*.json'))) == 1


def test_dst_allocation_preserves_actual_seconds():
    zone = ZoneInfo('America/New_York')
    start = datetime(2026, 3, 7, 23, tzinfo=zone)
    end = datetime(2026, 3, 9, 1, tzinfo=zone)
    session = replace(record(), start_time=start, end_time=end, duration_seconds=elapsed_seconds(start, end))
    totals = allocate_session_by_local_date(session, zone)
    assert list(totals.values()) == [3600, 23 * 3600, 3600]
    assert sum(totals.values()) == session.duration_seconds
    assert len(local_candidates(datetime(2026, 3, 8, 2, 30, tzinfo=timezone.utc).replace(tzinfo=None), zone)) == 0
    assert len(local_candidates(datetime(2026, 11, 1, 1, 30, tzinfo=timezone.utc).replace(tzinfo=None), zone)) == 2


def test_editor_preserves_fold_and_requires_selection_for_ambiguous_input(qt_application):
    zone = ZoneInfo('America/New_York')
    start = datetime(2026, 11, 1, 1, 30, 17, tzinfo=zone, fold=1)
    session = replace(record(), start_time=start, end_time=datetime(2026, 11, 1, 3, 0, tzinfo=zone))
    dialog = editor(session, zone)
    assert dialog.focus_values()[1].timestamp() == start.timestamp()
    dialog._start_edit.setTime(QTime(1, 45))
    with pytest.raises(ValueError):
        dialog.focus_values()
    dialog._start_fold.setCurrentIndex(dialog._start_fold.findData(1))
    assert dialog.focus_values()[1].fold == 1
    dialog._date_edit.setDate(QDate(2026, 3, 8))
    dialog._start_edit.setTime(QTime(2, 30))
    with pytest.raises(ValueError):
        dialog.focus_values()
