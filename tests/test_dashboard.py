"""Focused GUI tests for Dashboard and manual session input."""

from datetime import date, datetime, timedelta, timezone

import pytest
from PySide6.QtCore import QDate, QTime

from app.data.database import Database
from app.data.focus_item_repository import FocusItemRepository
from app.data.focus_session_repository import FocusSessionRepository
from app.data.models import FocusItem, FocusSessionSource
from app.focus import ManualFocusEntry, ManualFocusEntryService
from app.ui.session_editor_dialog import SessionEditorDialog


def test_manual_session_treats_earlier_end_as_next_day(qt_application) -> None:
    dialog = SessionEditorDialog(timezone(timedelta(hours=8)))
    focus_item = FocusItem(
        id=7,
        name="Math",
        color="#7C5CFC",
        is_favorite=False,
        is_archived=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    dialog.set_focus_items([focus_item])
    dialog._date_edit.setDate(QDate(2026, 8, 14))
    dialog._start_edit.setTime(QTime(23, 30))
    dialog._end_edit.setTime(QTime(0, 30))

    subject_id, start, end, duration = dialog.values()

    assert subject_id == 7
    assert start.date() == date(2026, 8, 14)
    assert end.date() == date(2026, 8, 15)
    assert duration == 3600
    dialog.close()


def test_manual_focus_dialog_accepts_direct_duration_and_note(qt_application) -> None:
    dialog = SessionEditorDialog(timezone(timedelta(hours=8)))
    now = datetime.now(timezone.utc)
    focus_item = FocusItem(8, "Writing", "#7C5CFC", False, False, now, now)
    dialog.set_focus_items([focus_item])
    dialog._date_edit.setDate(QDate(2026, 8, 15))
    dialog._start_edit.setTime(QTime(9, 15))
    dialog._entry_method.setCurrentIndex(1)
    dialog._duration_picker.setValue(80)
    dialog._note_edit.setPlainText("Draft chapter")

    item_id, start, end, duration, note = dialog.focus_values()

    assert item_id == 8
    assert end - start == timedelta(minutes=80)
    assert duration == 4800
    assert note == "Draft chapter"
    dialog.close()


def test_manual_focus_entry_uses_shared_history_and_rejects_zero_duration(
    tmp_path,
) -> None:
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    items = FocusItemRepository(database)
    sessions = FocusSessionRepository(database)
    item = items.create("Exercise")
    service = ManualFocusEntryService(items, sessions)
    start = datetime(2026, 8, 15, 7, 0, tzinfo=timezone.utc)

    saved = service.create(
        ManualFocusEntry(item.id, start, start + timedelta(minutes=45), 2700, "Cardio")
    )

    assert sessions.get(saved.id).source is FocusSessionSource.MANUAL
    assert saved.note == "Cardio"
    with pytest.raises(ValueError):
        service.create(ManualFocusEntry(item.id, start, start, 0))
