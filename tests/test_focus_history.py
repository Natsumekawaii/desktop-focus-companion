"""Focus History persistence and presentation tests."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView

from app.data.database import Database
from app.data.focus_item_repository import FocusItemRepository
from app.data.focus_session_repository import FocusSessionRepository
from app.data.models import FocusSessionSource
from app.focus_mode import FocusMode
from app.ui.dashboard import DashboardWindow


def test_focus_history_edit_preserves_source_and_timer_metadata(tmp_path: Path) -> None:
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    items = FocusItemRepository(database)
    sessions = FocusSessionRepository(database)
    original_item = items.create("Original")
    replacement = items.create("Replacement")
    start = datetime(2026, 8, 15, 8, 0, tzinfo=timezone.utc)
    saved = sessions.create(
        original_item,
        start,
        start + timedelta(minutes=25),
        1500,
        mode=FocusMode.COUNTDOWN,
        target_duration_seconds=1800,
        note="Before",
        source=FocusSessionSource.TIMER,
    )

    updated = sessions.update(
        saved.id,
        replacement,
        start + timedelta(hours=1),
        start + timedelta(hours=1, minutes=20),
        1200,
        "After",
    )

    assert updated.focus_item_id == replacement.id
    assert updated.focus_item_name == "Replacement"
    assert updated.duration_seconds == 1200
    assert updated.note == "After"
    assert updated.source is FocusSessionSource.TIMER
    assert updated.mode is FocusMode.COUNTDOWN
    assert updated.target_duration_seconds == 1800


def test_focus_history_shows_note_and_color_without_source_or_continue_action(
    qt_application, tmp_path: Path
) -> None:
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    items = FocusItemRepository(database)
    sessions = FocusSessionRepository(database)
    item = items.create("Reading", "#EC4899")
    start = datetime(2026, 8, 15, 8, 0, tzinfo=timezone.utc)
    session = sessions.create(
        item,
        start,
        start + timedelta(minutes=30),
        1800,
        note="Chapter 4",
        source=FocusSessionSource.MANUAL,
    )
    window = DashboardWindow(timezone.utc)
    window.set_focus_item_colors({item.id: item.color})
    window.set_history([session])

    assert window._history_table.columnCount() == 6
    assert window._history_table.item(0, 3).text() == "Reading"
    assert window._history_table.item(0, 3).foreground().color().name().upper() == "#EC4899"
    assert window._history_table.item(0, 5).text() == "Chapter 4"
    assert not hasattr(window, "_export_button")
    assert not hasattr(window, "_continue_button")
    assert not hasattr(window, "continue_session_requested")

    window._history_table.selectRow(0)
    assert (
        window._history_table.selectionMode()
        is QAbstractItemView.SelectionMode.SingleSelection
    )
    assert not window._history_table.alternatingRowColors()
    assert window._history_table.objectName() == "sessionDataTable"
    assert len(window._history_table.selectedIndexes()) == 6
    assert (
        window._history_table.item(0, 3).foreground().color().name().upper()
        == "#EC4899"
    )
    assert window._history_table.item(0, 0).data(Qt.ItemDataRole.UserRole) == session.id
    window.close()
