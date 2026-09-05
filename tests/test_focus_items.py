"""Focus Item lifecycle and management UI tests."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QEnterEvent, QImage
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QGridLayout, QLabel

from app.core.theme import COLOR_THEMES, get_theme_manager
from app.data.database import Database, DatabaseError
from app.data.focus_item_repository import (
    DEFAULT_FOCUS_ITEMS,
    FOCUS_ITEM_LIFECYCLE_KEY,
    FocusItemInUseError,
    FocusItemRepository,
)
from app.data.focus_session_repository import FocusSessionRepository
from app.data.models import FocusItem
from app.i18n import get_localization
from app.ui import subject_dialog as subject_dialog_module
from app.ui.subject_dialog import (
    DEFAULT_FOCUS_SWATCH_COLOR,
    FOCUS_COLORS,
    ColorSwatchButton,
    ColorSwatchPicker,
    FocusItemDialog,
)

EXPECTED_FOCUS_COLORS = (
    "#8B97A8",
    "#FF4D5A",
    "#FF6B4A",
    "#FFAA1F",
    "#FFD21F",
    "#9AD82B",
    "#55C52B",
    "#35C8B0",
    "#55C4E6",
    "#4299E1",
    "#5B83D6",
    "#9575CD",
    "#F47FA7",
    "#F36F82",
)


def test_focus_item_metadata_archive_restore_and_safe_delete(tmp_path: Path) -> None:
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    items = FocusItemRepository(database)
    sessions = FocusSessionRepository(database)
    used = items.create("Used", "#3B82F6")
    unused = items.create("Unused", "#14B8A6")

    favorite = items.set_favorite(used.id, True)
    recolored = items.set_color(used.id, "#ec4899")
    items.archive(used.id)
    restored = items.restore(used.id)

    assert favorite.is_favorite
    assert recolored.color == "#EC4899"
    assert not restored.is_archived

    start = datetime(2026, 8, 15, tzinfo=timezone.utc)
    sessions.create(used, start, start + timedelta(minutes=5), 300)
    with pytest.raises(FocusItemInUseError):
        items.delete_if_unused(used.id)
    items.delete_if_unused(unused.id)
    assert [item.id for item in items.list_all()] == [used.id]


def test_empty_profile_gets_minimal_general_focus_defaults(tmp_path: Path) -> None:
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    items = FocusItemRepository(database)

    items.ensure_defaults()

    assert [(item.name, item.color) for item in items.list_all()] == list(
        DEFAULT_FOCUS_ITEMS
    )


def test_focus_item_dialog_uses_visual_color_intents_without_lifecycle_controls(
    qt_application, monkeypatch
) -> None:
    class FakeCreateDialog:
        focus_item_name = "Creative work"
        selected_color = "#35C8B0"

        def __init__(self, parent) -> None:
            del parent

        def exec(self):
            return subject_dialog_module.QDialog.DialogCode.Accepted

    monkeypatch.setattr(subject_dialog_module, "FocusItemCreateDialog", FakeCreateDialog)
    dialog = FocusItemDialog()
    create_spy = QSignalSpy(dialog.create_focus_item_requested)

    dialog._add_button.click()

    assert create_spy.count() == 1
    assert create_spy.at(0) == ["Creative work", "#35C8B0"]
    assert not hasattr(dialog, "_favorite_check")
    assert not hasattr(dialog, "_archive_button")
    assert not hasattr(dialog, "_restore_button")
    dialog.close()


def test_visual_color_picker_emits_named_swatch_without_hex_text(qt_application) -> None:
    picker = ColorSwatchPicker()
    spy = QSignalSpy(picker.color_selected)

    picker._buttons["#35C8B0"].click()

    assert spy.at(0) == ["#35C8B0"]
    assert picker._buttons["#35C8B0"].text() == ""
    assert picker._buttons["#35C8B0"].accessibleName() == "Teal"
    assert FOCUS_COLORS == EXPECTED_FOCUS_COLORS
    assert len(FOCUS_COLORS) == len(picker._buttons) == 14
    assert picker.selected_color == "#35C8B0"
    picker.close()


def test_color_picker_uses_four_four_four_two_layout_and_purple_default(
    qt_application,
) -> None:
    picker = ColorSwatchPicker()
    layout = picker.layout()

    assert isinstance(layout, QGridLayout)
    assert picker.selected_color == DEFAULT_FOCUS_SWATCH_COLOR == "#9575CD"
    assert layout.itemAtPosition(0, 0).widget() is picker._buttons["#8B97A8"]
    assert layout.itemAtPosition(2, 3).widget() is picker._buttons["#9575CD"]
    assert layout.itemAtPosition(3, 0).widget() is picker._buttons["#F47FA7"]
    assert layout.itemAtPosition(3, 1).widget() is picker._buttons["#F36F82"]
    assert layout.itemAtPosition(3, 2) is None
    assert layout.itemAtPosition(3, 3) is None
    picker.close()


def test_color_swatch_is_circular_with_subtle_gradient_and_selection_gap(
    qt_application,
) -> None:
    button = ColorSwatchButton("#FF4D5A")
    button.setChecked(True)
    button.show()
    qt_application.processEvents()

    image = QImage(button.size(), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    button.render(image)
    center_x = round(button.disc_rect.center().x())
    top_color = image.pixelColor(center_x, round(button.disc_rect.top() + 8))
    bottom_color = image.pixelColor(center_x, round(button.disc_rect.bottom() - 8))

    assert image.pixelColor(0, 0).alpha() == 0
    assert image.pixelColor(button.width() - 1, 0).alpha() == 0
    assert image.pixelColor(center_x, 2).alpha() > 0
    assert image.pixelColor(center_x, 3).alpha() == 0
    assert top_color.alpha() == bottom_color.alpha() == 255
    assert top_color.lightness() > bottom_color.lightness()
    button.close()


def test_color_swatch_hover_and_keyboard_keep_geometry_stable(qt_application) -> None:
    button = ColorSwatchButton("#55C4E6")
    button.show()
    button.setFocus()
    qt_application.processEvents()
    original_geometry = button.geometry()
    spy = QSignalSpy(button.clicked)

    center = QPointF(button.width() / 2, button.height() / 2)
    button.enterEvent(QEnterEvent(center, center, center))
    QTest.qWait(45)
    assert 0.0 < button.hover_progress < 1.0
    assert button.geometry() == original_geometry

    QTest.keyClick(button, Qt.Key.Key_Space)
    assert button.isChecked()
    assert spy.count() == 1
    assert button.geometry() == original_geometry
    button.close()


def test_color_swatch_stays_circular_in_every_theme(qt_application) -> None:
    manager = get_theme_manager()
    original_theme = manager.theme_name
    button = ColorSwatchButton("#9575CD")
    button.setChecked(True)
    try:
        for theme_name in COLOR_THEMES:
            manager.set_theme(theme_name)
            image = QImage(button.size(), QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(Qt.GlobalColor.transparent)
            button.render(image)
            assert image.pixelColor(0, 0).alpha() == 0
            assert image.pixelColor(button.width() - 1, 0).alpha() == 0
            assert image.pixelColor(button.width() // 2, 2).alpha() > 0
            assert image.pixelColor(
                button.width() // 2,
                button.height() // 2,
            ).alpha() == 255
    finally:
        manager.set_theme(original_theme)
        button.close()


def test_color_picker_retranslates_coral_accessibility_name(qt_application) -> None:
    localization = get_localization()
    original_language = localization.language
    picker = ColorSwatchPicker()
    try:
        localization.set_language("en-US")
        assert picker._buttons["#FF6B4A"].accessibleName() == "Coral"
        localization.set_language("zh-CN")
        assert picker._buttons["#FF6B4A"].accessibleName() == "珊瑚色"
    finally:
        localization.set_language(original_language)
        picker.close()


def test_main_item_dialog_has_no_runtime_color_editor_and_renames_separately(
    qt_application, monkeypatch
) -> None:
    class FakeRenameDialog:
        focus_item_name = "New name"

        def __init__(self, current_name: str, parent) -> None:
            assert current_name == "Writing"
            del parent

        def exec(self):
            return subject_dialog_module.QDialog.DialogCode.Accepted

    monkeypatch.setattr(subject_dialog_module, "FocusItemRenameDialog", FakeRenameDialog)
    now = datetime(2026, 8, 15, tzinfo=timezone.utc)
    item = FocusItem(7, "Writing", "#7C5CFC", False, False, now, now)
    dialog = FocusItemDialog()
    dialog.set_focus_items([item])
    spy = QSignalSpy(dialog.rename_requested)

    dialog._rename_button.click()

    assert spy.at(0) == [7, "New name"]
    assert not hasattr(dialog, "color_requested")
    assert not hasattr(dialog, "_color_picker")
    assert not hasattr(dialog, "_name_input")
    dialog.close()


def test_focus_item_cards_are_centered_and_bounded_with_scrollbar(
    qt_application,
) -> None:
    now = datetime(2026, 8, 15, tzinfo=timezone.utc)
    items = [
        FocusItem(
            index,
            "A very long Focus Item name " * (index + 1),
            FOCUS_COLORS[index % len(FOCUS_COLORS)],
            False,
            False,
            now,
            now,
        )
        for index in range(1, 10)
    ]
    dialog = FocusItemDialog()
    dialog.resize(460, 420)
    dialog.set_focus_items(items)
    dialog.show()
    qt_application.processEvents()
    dialog._item_list.sync_item_widths()

    hosts = [
        dialog._item_list.itemWidget(dialog._item_list.item(row))
        for row in range(dialog._item_list.count())
    ]
    assert all(host is not None for host in hosts)
    cards = [host.findChild(subject_dialog_module.QFrame, "focusItemManagementCard") for host in hosts]
    assert all(card is not None for card in cards)
    assert {card.width() for card in cards} == {350}
    for host, card in zip(hosts, cards, strict=True):
        assert abs(card.geometry().center().x() - host.rect().center().x()) <= 1
        assert host.width() <= dialog._item_list.viewport().width()
    dialog.close()


def test_focus_item_cards_show_color_total_and_recent_record(qt_application) -> None:
    now = datetime(2026, 8, 15, 8, 0, tzinfo=timezone.utc)
    item = FocusItem(9, "Writing", "#EC4899", True, False, now, now)
    dialog = FocusItemDialog()
    dialog.set_focus_items([item])
    dialog.set_focus_item_metrics({9: 5400}, {9: now})
    dialog.show()
    qt_application.processEvents()
    dialog._item_list.sync_item_widths()
    qt_application.processEvents()

    host = dialog._item_list.itemWidget(dialog._item_list.item(0))
    assert host is not None
    card = host.findChild(subject_dialog_module.QFrame, "focusItemManagementCard")
    assert card is not None
    labels = card.findChildren(QLabel)
    texts = [label.text() for label in labels]
    assert "Writing" in texts
    assert "●" not in texts
    assert all("★" not in text for text in texts)
    assert any("1h 30min" in text and "Last" in text for text in texts)
    title = next(label for label in labels if label.text() == "Writing")
    assert "#EC4899" in title.styleSheet()
    assert card.objectName() == "focusItemManagementCard"
    assert card.layout().contentsMargins().top() == 4
    assert card.layout().contentsMargins().bottom() == 4
    assert card.layout().spacing() == 1
    assert host._minimum_card_height == 48
    assert card.height() >= host._minimum_card_height
    dialog.close()


def test_focus_item_card_selection_stays_on_the_rounded_card(qt_application) -> None:
    now = datetime(2026, 8, 15, 8, 0, tzinfo=timezone.utc)
    items = [
        FocusItem(1, "Writing", "#EC4899", False, False, now, now),
        FocusItem(2, "Reading", "#4299E1", False, False, now, now),
    ]
    dialog = FocusItemDialog()
    dialog.set_focus_items(items)

    first_host = dialog._item_list.itemWidget(dialog._item_list.item(0))
    second_host = dialog._item_list.itemWidget(dialog._item_list.item(1))
    assert first_host is not None and second_host is not None
    first = first_host.findChild(subject_dialog_module.QFrame, "focusItemManagementCard")
    second = second_host.findChild(subject_dialog_module.QFrame, "focusItemManagementCard")
    assert first is not None and second is not None
    assert first.property("selected") is True
    assert second.property("selected") is False

    dialog._item_list.setCurrentRow(1)

    assert first.property("selected") is False
    assert second.property("selected") is True
    dialog.close()


def test_selected_focus_item_card_has_no_rectangular_row_background(
    qt_application,
) -> None:
    now = datetime(2026, 8, 15, 8, 0, tzinfo=timezone.utc)
    dialog = FocusItemDialog()
    dialog.set_focus_items(
        [FocusItem(1, "Writing", "#EC4899", False, False, now, now)]
    )
    dialog.show()
    qt_application.processEvents()
    dialog._item_list.sync_item_widths()
    qt_application.processEvents()

    host = dialog._item_list.itemWidget(dialog._item_list.item(0))
    assert host is not None
    card = host.findChild(subject_dialog_module.QFrame, "focusItemManagementCard")
    assert card is not None
    viewport = dialog._item_list.viewport()
    origin = card.mapTo(viewport, QPoint(0, 0))
    image = viewport.grab().toImage()

    corner = image.pixelColor(origin)
    outside = image.pixelColor(origin + QPoint(-5, 0))
    top_border = image.pixelColor(origin + QPoint(card.width() // 2, 0))
    assert corner == outside
    assert top_border != outside
    dialog.close()


def test_delete_with_history_is_atomic_and_reports_impact(tmp_path: Path) -> None:
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    items = FocusItemRepository(database)
    sessions = FocusSessionRepository(database)
    item = items.create("Disposable")
    start = datetime(2026, 8, 15, tzinfo=timezone.utc)
    sessions.create(item, start, start + timedelta(minutes=5), 300)
    sessions.create(item, start + timedelta(hours=1), start + timedelta(hours=1, minutes=7), 420)

    impact = items.deletion_impact(item.id)
    deleted = items.delete_with_history(item.id)

    assert impact == deleted
    assert deleted.session_count == 2
    assert deleted.total_seconds == 720
    assert items.list_all() == []
    assert sessions.list_sessions() == []


def test_delete_with_history_rolls_back_sessions_when_item_delete_fails(tmp_path: Path) -> None:
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    items = FocusItemRepository(database)
    sessions = FocusSessionRepository(database)
    item = items.create("Protected")
    start = datetime(2026, 8, 15, tzinfo=timezone.utc)
    session = sessions.create(item, start, start + timedelta(minutes=5), 300)
    with database.connect() as connection:
        connection.execute(
            """
            CREATE TRIGGER reject_focus_item_delete
            BEFORE DELETE ON focus_items
            BEGIN SELECT RAISE(ABORT, 'simulated delete failure'); END
            """
        )

    with pytest.raises(DatabaseError):
        items.delete_with_history(item.id)

    assert items.get(item.id).name == "Protected"
    assert sessions.get(session.id).duration_seconds == 300


def test_legacy_archived_cleanup_deletes_history_once_and_prevents_reseeding(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    items = FocusItemRepository(database)
    sessions = FocusSessionRepository(database)
    active = items.create("Active")
    archived = items.create("Archived")
    items.set_favorite(active.id, True)
    items.archive(archived.id)
    start = datetime(2026, 8, 15, tzinfo=timezone.utc)
    sessions.create(archived, start, start + timedelta(minutes=10), 600)

    items.ensure_defaults()

    assert [item.id for item in items.list_all()] == [active.id]
    assert not items.get(active.id).is_favorite
    assert sessions.list_sessions() == []
    items.delete_with_history(active.id)
    items.ensure_defaults()
    assert items.list_all() == []
    with database.connect() as connection:
        assert connection.execute(
            "SELECT value FROM settings WHERE key = ?",
            (FOCUS_ITEM_LIFECYCLE_KEY,),
        ).fetchone()["value"] == "1"
