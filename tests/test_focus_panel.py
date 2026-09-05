"""Focus Launcher integration tests."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QRadioButton,
    QScrollArea,
    QStackedWidget,
    QStyle,
    QStyleOptionButton,
)

from app.core.theme import COLOR_THEMES, get_theme_manager
from app.data.database import Database
from app.data.focus_item_repository import FocusItemRepository
from app.data.focus_session_repository import FocusSessionRepository
from app.data.models import FocusItem
from app.focus_mode import FocusMode
from app.i18n import tr
from app.pet.pet_window import PetWindow
from app.statistics import StatisticsService
from app.timer import FocusSessionManager, FocusTimer, TimerState
from app.ui import quick_panel_controller as quick_panel_controller_module
from app.ui.anchored_popup import PopupState
from app.ui.focus_item_selector import (
    _FOCUS_ITEM_COLOR_ROLE,
    _FOCUS_ITEM_KIND_MANAGE,
    _FOCUS_ITEM_KIND_ROLE,
    _FOCUS_ITEM_KIND_SEPARATOR,
)
from app.ui.quick_panel import FocusPanel
from app.ui.quick_panel_controller import FocusPanelController
from app.ui.rounded_selector import RoundedComboBox
from app.ui.subject_dialog import FocusItemDialog


@dataclass
class FakeClock:
    monotonic_value: float = 100.0
    wall_value: datetime = datetime(2026, 8, 15, 8, 0, tzinfo=timezone.utc)

    def monotonic(self) -> float:
        return self.monotonic_value

    def now(self) -> datetime:
        return self.wall_value

    def advance(self, seconds: float) -> None:
        self.monotonic_value += seconds
        self.wall_value += timedelta(seconds=seconds)


def _focus_ui(tmp_path: Path):
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    items = FocusItemRepository(database)
    sessions = FocusSessionRepository(database)
    clock = FakeClock()
    manager = FocusSessionManager(FocusTimer(clock), items, sessions)
    pet = PetWindow()
    panel = FocusPanel(pet, countdown_phase_duration_ms=10)
    dialog = FocusItemDialog(panel)
    controller = FocusPanelController(
        panel,
        dialog,
        pet,
        manager,
        items,
        StatisticsService(sessions, timezone.utc),
        sessions,
    )
    return items, sessions, clock, manager, pet, panel, dialog, controller


def test_focus_picker_lists_all_items_by_name_without_groups(
    qt_application, tmp_path: Path
) -> None:
    items, sessions, clock, _manager, pet, panel, dialog, controller = _focus_ui(tmp_path)
    favorite = items.create("Favorite", "#EC4899")
    recent = items.create("Recent", "#3B82F6")
    remaining = items.create("Remaining", "#14B8A6")
    items.set_favorite(favorite.id, True)
    sessions.create(
        recent,
        clock.now(),
        clock.now() + timedelta(minutes=10),
        600,
    )

    controller.refresh_focus_items()

    texts = [panel._focus_item_combo.itemText(i) for i in range(panel._focus_item_combo.count())]
    ids = [
        panel._focus_item_combo.itemData(i)
        for i in range(panel._focus_item_combo.count())
        if panel._focus_item_combo.itemData(i) is not None
    ]
    assert texts[:3] == ["Favorite", "Recent", "Remaining"]
    assert "All" not in texts
    assert ids == [favorite.id, recent.id, remaining.id]
    assert len(ids) == len(set(ids))
    assert [
        panel._focus_item_combo.itemData(index, _FOCUS_ITEM_COLOR_ROLE)
        for index in range(3)
    ] == [favorite.color, recent.color, remaining.color]
    panel.show()
    qt_application.processEvents()
    assert panel._focus_item_combo.height() == 48
    assert panel._focus_item_combo.objectName() == "focusItemSelector"
    assert all(
        panel._focus_item_combo.itemIcon(index).isNull()
        for index in range(panel._focus_item_combo.count())
    )
    assert texts[-1] == tr("focus.manage_items")
    assert not hasattr(panel, "_manage_focus_items_button")
    assert not hasattr(panel, "_continue_button")
    assert not hasattr(panel, "continue_requested")

    panel._focus_item_combo.setCurrentIndex(
        panel._focus_item_combo.findData(remaining.id)
    )
    requested = QSignalSpy(panel.manage_focus_items_requested)
    manage_index = panel._focus_item_combo.count() - 1
    panel._focus_item_combo.setCurrentIndex(manage_index)
    panel._focus_item_combo.activated.emit(manage_index)
    assert requested.count() == 1
    assert panel._focus_item_combo.currentData() == remaining.id
    assert panel._focus_item_combo.toolTip() == remaining.name

    dialog.close()
    panel.hide()
    pet.close()


def test_focus_picker_empty_state_keeps_management_action_available(
    qt_application,
) -> None:
    panel = FocusPanel()
    panel.set_focus_items([])

    assert panel._focus_item_combo.currentText() == tr("focus.no_items")
    assert not panel._start_button.isEnabled()
    manage_index = panel._focus_item_combo.count() - 1
    assert panel._focus_item_combo.itemText(manage_index) == tr("focus.manage_items")
    assert (
        panel._focus_item_combo.itemData(
            manage_index, Qt.ItemDataRole.AccessibleTextRole
        )
        == tr("focus.manage_items")
    )

    requested = QSignalSpy(panel.manage_focus_items_requested)
    panel._focus_item_combo.setCurrentIndex(manage_index)
    panel._focus_item_combo.activated.emit(manage_index)
    assert requested.count() == 1
    assert panel._focus_item_combo.currentText() == tr("focus.no_items")
    panel.move(20, 20)
    panel.show()
    qt_application.processEvents()
    panel._focus_item_combo.showPopup()
    _wait_for_popup_open(panel._focus_item_combo)
    assert [
        panel._focus_item_combo.view().sizeHintForRow(index)
        for index in range(panel._focus_item_combo.count())
    ] == [36, 9, 40]
    assert panel._focus_item_combo.view().window().height() == 97
    panel._focus_item_combo._popup_container.hide_immediately()
    panel.hide()


def test_focus_picker_draws_chevron_and_uses_a_transparent_rounded_popup(
    qt_application, tmp_path: Path
) -> None:
    items, _sessions, _clock, _manager, pet, panel, dialog, controller = _focus_ui(tmp_path)
    selected = items.create("Writing", "#9575CD")
    controller.refresh_focus_items(selected.id)
    panel.show()
    qt_application.processEvents()

    combo = panel._focus_item_combo
    combo.showPopup()
    _wait_for_popup_open(combo)
    popup = combo.view().window()
    surface = popup.findChild(QFrame, "focusItemSelectorPopupSurface")

    assert combo._popup_container is popup
    assert combo._popup_surface is not None
    assert popup.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert popup.mask().isEmpty()
    popup_image = popup.grab().toImage()
    assert popup_image.pixelColor(0, 0).alpha() == 0
    assert popup_image.pixelColor(
        popup_image.width() // 2,
        popup_image.height() // 2,
    ).alpha() > 0
    assert surface is combo._popup_surface
    assert [
        combo.view().sizeHintForRow(index)
        for index in range(combo.count())
    ] == [36, 9, 40]
    assert popup.height() == 97
    assert combo.itemText(0) == "Writing"
    assert combo.itemData(0, _FOCUS_ITEM_COLOR_ROLE) == "#9575CD"
    assert combo.itemData(1, _FOCUS_ITEM_KIND_ROLE) == _FOCUS_ITEM_KIND_SEPARATOR
    assert combo.itemData(2, _FOCUS_ITEM_KIND_ROLE) == _FOCUS_ITEM_KIND_MANAGE

    selected_rect = combo.view().visualRect(combo.model().index(0, 0))
    selected_origin = combo.view().viewport().mapTo(popup, selected_rect.topLeft())
    tokens = get_theme_manager().tokens
    selected_fill = popup_image.pixelColor(
        selected_origin.x() + selected_rect.width() // 2,
        selected_origin.y() + 5,
    )
    selected_corner = popup_image.pixelColor(
        selected_origin.x() + 4,
        selected_origin.y() + 2,
    )
    assert _maximum_channel_delta(selected_fill, QColor(tokens.primary_soft)) <= 3
    assert _maximum_channel_delta(
        selected_corner,
        QColor(tokens.surface_elevated),
    ) <= 3
    check_pixels = (
        popup_image.pixelColor(x, y)
        for x in range(
            selected_origin.x() + selected_rect.width() - 26,
            selected_origin.x() + selected_rect.width() - 8,
        )
        for y in range(
            selected_origin.y() + selected_rect.height() // 2 - 7,
            selected_origin.y() + selected_rect.height() // 2 + 8,
        )
    )
    assert any(
        _maximum_channel_delta(pixel, QColor(tokens.primary)) <= 16
        for pixel in check_pixels
    )

    requested = QSignalSpy(panel.manage_focus_items_requested)
    manage_index = combo.count() - 1
    combo.view().setCurrentIndex(combo.model().index(manage_index, 0))
    QTest.keyClick(combo.view(), Qt.Key.Key_Return)
    QTest.qWait(220)

    assert requested.count() == 1
    assert combo.currentData() == selected.id
    assert not combo.view().window().isVisible()

    combo.showPopup()
    _wait_for_popup_open(combo)
    combo.view().setCurrentIndex(combo.model().index(manage_index, 0))
    QTest.keyClick(combo.view(), Qt.Key.Key_Space)
    QTest.qWait(220)

    assert requested.count() == 2
    assert combo.currentData() == selected.id
    assert not combo.view().window().isVisible()

    dialog.close()
    panel.hide()
    pet.close()


def test_focus_picker_caps_visible_rows_and_scrolls_extra_items(
    qt_application,
) -> None:
    panel = FocusPanel()
    now = datetime.now(timezone.utc)
    panel.set_focus_items(
        [
            FocusItem(
                index,
                f"Focus Item {index:02d}",
                "#4299E1",
                False,
                False,
                now,
                now,
            )
            for index in range(1, 16)
        ]
    )
    panel.move(20, 20)
    panel.show()
    qt_application.processEvents()
    combo = panel._focus_item_combo
    combo.showPopup()
    _wait_for_popup_open(combo)

    assert combo.maxVisibleItems() == 12
    assert combo.view().window().height() == 12 * 36 + 12
    assert combo.view().verticalScrollBar().maximum() > 0

    combo._popup_container.hide_immediately()
    panel.close()


def test_focus_picker_uses_rounded_theme_selection_in_all_themes(
    qt_application,
) -> None:
    manager = get_theme_manager()
    original_theme = manager.theme_name
    panel = FocusPanel()
    now = datetime.now(timezone.utc)
    panel.set_focus_items(
        [
            FocusItem(1, "Writing", "#9575CD", False, False, now, now),
            FocusItem(2, "Reading", "#3B82F6", False, False, now, now),
        ]
    )
    panel.move(20, 20)
    combo = panel._focus_item_combo

    try:
        for theme_name in COLOR_THEMES:
            panel.hide()
            manager.set_theme(theme_name)
            panel.show()
            qt_application.processEvents()
            field_image = combo.grab().toImage()
            assert _count_pixels_close_to_color(
                field_image,
                QColor("#9575CD"),
                left=10,
                top=0,
                right=max(10, field_image.width() - 42),
                bottom=field_image.height(),
                tolerance=24,
            ) > 2
            combo.showPopup()
            _wait_for_popup_open(combo)

            popup = combo.view().window()
            image = popup.grab().toImage()
            item_rect = combo.view().visualRect(combo.model().index(0, 0))
            origin = combo.view().viewport().mapTo(popup, item_rect.topLeft())
            tokens = manager.tokens
            fill = image.pixelColor(
                origin.x() + item_rect.width() // 2,
                origin.y() + 5,
            )
            corner = image.pixelColor(origin.x() + 4, origin.y() + 2)
            assert _maximum_channel_delta(fill, QColor(tokens.primary_soft)) <= 3
            assert _maximum_channel_delta(
                corner,
                QColor(tokens.surface_elevated),
            ) <= 3
            next_rect = combo.view().visualRect(combo.model().index(1, 0))
            next_origin = combo.view().viewport().mapTo(popup, next_rect.topLeft())
            separator_y = next_origin.y()
            separator_pixel = image.pixelColor(
                next_origin.x() + next_rect.width() // 2,
                separator_y,
            )
            assert _maximum_channel_delta(
                separator_pixel,
                QColor(tokens.border),
            ) == 0
            combo._popup_container.hide_immediately()
    finally:
        combo._popup_container.hide_immediately()
        panel.hide()
        manager.set_theme(original_theme)


def test_focus_picker_syncs_closed_label_color_and_draws_item_separators(
    qt_application,
) -> None:
    panel = FocusPanel()
    now = datetime.now(timezone.utc)
    colors = ("#F97316", "#7C3AED", "#14B8A6")
    panel.set_focus_items(
        [
            FocusItem(index, f"Focus Item {index}", color, False, False, now, now)
            for index, color in enumerate(colors, start=1)
        ]
    )
    panel.move(20, 20)
    panel.show()
    qt_application.processEvents()
    combo = panel._focus_item_combo

    for index, color in enumerate(colors):
        combo.setCurrentIndex(index)
        combo.update()
        qt_application.processEvents()
        field_image = combo.grab().toImage()
        assert _count_pixels_close_to_color(
            field_image,
            QColor(color),
            left=10,
            top=0,
            right=max(10, field_image.width() - 42),
            bottom=field_image.height(),
            tolerance=24,
        ) > 2

    combo.showPopup()
    _wait_for_popup_open(combo)
    popup = combo.view().window()
    popup_image = popup.grab().toImage()
    tokens = get_theme_manager().tokens
    separator_color = QColor(tokens.border)
    popup_background = QColor(tokens.surface_elevated)
    item_rects = [
        combo.view().visualRect(combo.model().index(index, 0)) for index in range(3)
    ]
    item_origins = [
        combo.view().viewport().mapTo(popup, item_rect.topLeft())
        for item_rect in item_rects
    ]

    for item_rect, origin in zip(item_rects[1:], item_origins[1:], strict=True):
        separator_y = origin.y()
        assert _count_pixels_close_to_color(
            popup_image,
            separator_color,
            left=origin.x() + 6,
            top=separator_y,
            right=origin.x() + item_rect.width() - 6,
            bottom=separator_y + 1,
            tolerance=0,
        ) >= item_rect.width() - 12
        assert _maximum_channel_delta(
            popup_image.pixelColor(
                origin.x() + item_rect.width() // 2,
                separator_y - 1,
            ),
            popup_background,
        ) <= 3
        assert _maximum_channel_delta(
            popup_image.pixelColor(
                origin.x() + item_rect.width() // 2,
                separator_y + 1,
            ),
            popup_background,
        ) <= 3

    first_rect = item_rects[0]
    first_origin = item_origins[0]
    assert _count_pixels_close_to_color(
        popup_image,
        separator_color,
        left=first_origin.x() + 6,
        top=first_origin.y(),
        right=first_origin.x() + first_rect.width() - 6,
        bottom=first_origin.y() + 1,
        tolerance=0,
    ) < first_rect.width() // 4

    last_rect = item_rects[-1]
    last_origin = item_origins[-1]
    last_separator_y = last_origin.y() + last_rect.height() - 1
    assert _count_pixels_close_to_color(
        popup_image,
        separator_color,
        left=last_origin.x() + 6,
        top=last_separator_y,
        right=last_origin.x() + last_rect.width() - 6,
        bottom=last_separator_y + 1,
        tolerance=0,
    ) < last_rect.width() // 4
    assert [combo.view().sizeHintForRow(index) for index in range(combo.count())] == [
        36,
        36,
        36,
        9,
        40,
    ]
    assert popup.height() == 169

    combo._popup_container.hide_immediately()
    panel.close()


def _maximum_channel_delta(first: QColor, second: QColor) -> int:
    return max(
        abs(first.red() - second.red()),
        abs(first.green() - second.green()),
        abs(first.blue() - second.blue()),
    )


def _wait_for_popup_open(combo: RoundedComboBox) -> None:
    for _ in range(60):
        if combo._popup_container.popup_state is PopupState.OPEN:
            return
        QTest.qWait(10)
    raise AssertionError("Selector popup did not finish opening.")


def _count_pixels_close_to_color(
    image,
    target: QColor,
    *,
    left: int,
    top: int,
    right: int,
    bottom: int,
    tolerance: int,
) -> int:
    return sum(
        _maximum_channel_delta(image.pixelColor(x, y), target) <= tolerance
        for x in range(max(0, left), min(image.width(), right))
        for y in range(max(0, top), min(image.height(), bottom))
    )


def test_countdown_target_uses_shared_rounded_selectors(
    qt_application,
) -> None:
    panel = FocusPanel()
    panel._countdown_radio.setChecked(True)
    qt_application.processEvents()

    picker = panel._target_duration_picker
    selectors = (
        picker._hours_combo,
        picker._minutes_combo,
    )
    assert all(isinstance(selector, RoundedComboBox) for selector in selectors)
    assert all(selector.property("roundedSelector") for selector in selectors)
    assert tuple(
        picker._hours_combo.itemData(index)
        for index in range(picker._hours_combo.count())
    ) == tuple(range(25))
    assert tuple(
        picker._minutes_combo.itemData(index)
        for index in range(picker._minutes_combo.count())
    ) == tuple(range(0, 61, 5))

    for width in (320, 420):
        panel.resize(width, 650)
        panel.show()
        qt_application.processEvents()
        assert abs(
            picker._hours_combo.width() - picker._minutes_combo.width()
        ) <= 1
        assert picker.width() <= panel._target_controls.width()
        assert all(
            selector.height() == panel._focus_item_combo.height()
            for selector in selectors
        )

    picker.setValue(24 * 60)
    assert panel._selected_target_duration(FocusMode.COUNTDOWN) == 24 * 60 * 60
    picker.setValue(0)
    assert picker.value() == 5

    picker.setValue(3 * 60 + 55)
    picker._minutes_combo.setCurrentIndex(picker._minutes_combo.findData(60))
    assert picker.value() == 4 * 60
    assert picker._hours_combo.currentData() == 4
    assert picker._minutes_combo.currentData() == 0

    picker.setValue(24 * 60)
    picker._minutes_combo.setCurrentIndex(picker._minutes_combo.findData(60))
    assert picker.value() == 24 * 60
    assert picker._hours_combo.currentData() == 24
    assert picker._minutes_combo.currentData() == 0

    picker._minutes_combo.showPopup()
    QTest.qWait(180)
    popup = picker._minutes_combo.view().window()

    assert popup.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert popup.mask().isEmpty()
    popup_image = popup.grab().toImage()
    assert popup_image.pixelColor(0, 0).alpha() == 0
    assert popup_image.pixelColor(
        popup_image.width() // 2,
        popup_image.height() // 2,
    ).alpha() > 0

    picker._minutes_combo.hidePopup()
    QTest.qWait(220)
    panel.hide()


def test_timing_mode_segments_hide_only_their_radio_indicators(
    qt_application,
) -> None:
    panel = FocusPanel()
    ordinary_radio = QRadioButton("Ordinary")
    panel.show()
    ordinary_radio.show()
    qt_application.processEvents()

    def indicator_rect(button: QRadioButton):
        option = QStyleOptionButton()
        button.initStyleOption(option)
        return button.style().subElementRect(
            QStyle.SubElement.SE_RadioButtonIndicator,
            option,
            button,
        )

    for button in (panel._stopwatch_radio, panel._countdown_radio):
        rect = indicator_rect(button)
        assert rect.width() == 0
        assert rect.height() == 0

    ordinary_rect = indicator_rect(ordinary_radio)
    assert ordinary_rect.width() == 16
    assert ordinary_rect.height() == 16

    panel._countdown_radio.setChecked(True)
    assert panel._countdown_radio.isChecked()
    assert not panel._stopwatch_radio.isChecked()
    panel._stopwatch_radio.setChecked(True)
    assert panel._stopwatch_radio.isChecked()
    assert not panel._countdown_radio.isChecked()

    ordinary_radio.close()
    panel.close()


def test_active_focus_item_cannot_be_deleted(qt_application, tmp_path: Path, monkeypatch) -> None:
    items, _sessions, clock, manager, pet, panel, dialog, controller = _focus_ui(tmp_path)
    item = items.create("Active")
    errors: list[str] = []
    monkeypatch.setattr(panel, "show_error", errors.append)
    controller.start_session(item.id)

    controller.delete_focus_item(item.id)

    assert manager.active_focus_item is not None
    assert items.get(item.id).name == "Active"
    assert errors
    clock.advance(60)
    controller.finish_session()
    dialog.close()
    panel.hide()
    pet.close()


def test_confirmed_item_delete_removes_history_and_emits_refresh(
    qt_application, tmp_path: Path, monkeypatch
) -> None:
    items, sessions, clock, _manager, pet, panel, dialog, controller = _focus_ui(tmp_path)
    item = items.create("Remove me")
    sessions.create(item, clock.now(), clock.now() + timedelta(minutes=10), 600)
    confirmation: dict[str, str] = {}

    def confirm(_parent, title: str, message: str, **_kwargs) -> bool:
        confirmation["title"] = title
        confirmation["message"] = message
        return True

    monkeypatch.setattr(quick_panel_controller_module, "ask_confirmation", confirm)
    changed = QSignalSpy(controller.focus_items_changed)

    controller.delete_focus_item(item.id)

    assert items.list_all() == []
    assert sessions.list_sessions() == []
    assert changed.count() == 1
    assert "Remove me" in confirmation["message"]
    assert "1" in confirmation["message"]
    assert "10 min" in confirmation["message"] or "10分钟" in confirmation["message"]
    dialog.close()
    panel.hide()
    pet.close()


def test_focus_launcher_persists_note_without_quick_continue(
    qt_application, tmp_path: Path
) -> None:
    items, sessions, clock, manager, pet, panel, dialog, controller = _focus_ui(tmp_path)
    item = items.create("Writing", "#F97316")
    controller.refresh_focus_items(item.id)
    panel._note_input.setText("Draft introduction")
    panel._countdown_radio.setChecked(True)
    panel._target_duration_picker.setValue(25)

    panel._start_button.click()
    assert manager.current_state is TimerState.IDLE
    assert panel.is_prestart_active
    QTest.qWait(80)
    assert manager.current_state is TimerState.FOCUSING
    clock.advance(300)
    saved = controller.finish_session()

    assert saved is not None
    assert saved.note == "Draft introduction"
    assert saved.mode is FocusMode.COUNTDOWN
    assert saved.target_duration_seconds == 25 * 60
    assert sessions.get(saved.id).note == "Draft introduction"
    assert not hasattr(panel, "_continue_button")
    assert len(sessions.list_sessions()) == 1
    assert manager.current_state is TimerState.IDLE
    dialog.close()
    panel.hide()
    pet.close()


def test_prestart_cancelled_by_close_never_creates_a_session(
    qt_application, tmp_path: Path
) -> None:
    items, sessions, clock, manager, pet, panel, dialog, controller = _focus_ui(tmp_path)
    item = items.create("Writing", "#F97316")
    controller.refresh_focus_items(item.id)
    panel.show()
    qt_application.processEvents()

    panel._start_button.click()
    assert panel.is_prestart_active
    assert manager.current_state is TimerState.IDLE
    assert manager.recovery_checkpoint is None

    panel._close_button.click()
    clock.advance(10)
    QTest.qWait(80)

    assert not panel.isVisible()
    assert not panel.is_prestart_active
    assert manager.current_state is TimerState.IDLE
    assert manager.recovery_checkpoint is None
    assert sessions.list_sessions() == []
    dialog.close()
    pet.close()


def test_prestart_time_is_not_counted_by_stopwatch_or_countdown(
    qt_application, tmp_path: Path
) -> None:
    items, _sessions, clock, manager, pet, panel, dialog, controller = _focus_ui(tmp_path)
    item = items.create("Writing", "#F97316")
    controller.refresh_focus_items(item.id)
    panel._countdown_radio.setChecked(True)
    panel._target_duration_picker.setValue(25)

    panel._start_button.click()
    clock.advance(3)
    assert manager.current_state is TimerState.IDLE
    QTest.qWait(80)

    assert manager.current_state is TimerState.FOCUSING
    assert manager.elapsed_seconds == 0
    assert manager.remaining_seconds == 25 * 60
    manager.discard_active_session()
    dialog.close()
    panel.hide()
    pet.close()


def test_focus_launcher_contains_no_xp_or_level_presentation(qt_application, tmp_path: Path) -> None:
    _items, _sessions, _clock, _manager, pet, panel, dialog, _controller = _focus_ui(
        tmp_path
    )

    visible_text = " ".join(
        label.text() for label in panel.findChildren(QLabel)
    ).casefold()
    assert "xp" not in visible_text
    assert "level" not in visible_text
    assert "等级" not in visible_text

    dialog.close()
    panel.hide()
    pet.close()


def test_focus_panel_keeps_stable_idle_and_active_pages_for_long_items(
    qt_application,
) -> None:
    panel = FocusPanel()
    panel.resize(360, 590)
    panel.show()
    qt_application.processEvents()
    initial_size = panel.size()

    assert isinstance(panel._panel_stack, QStackedWidget)
    assert panel._panel_stack.currentWidget() is panel._idle_page
    assert isinstance(panel._idle_page, QScrollArea)

    long_name = "Architecture review and implementation planning " * 4
    panel.set_timer_state(
        TimerState.FOCUSING,
        long_name,
        FocusMode.COUNTDOWN,
        90 * 60,
    )
    qt_application.processEvents()
    assert panel._panel_stack.currentWidget() is panel._active_page
    assert isinstance(panel._active_page, QScrollArea)
    assert panel._active_focus_item_label.toolTip() == long_name
    assert panel.size() == initial_size
    assert panel.width() <= panel.maximumWidth()

    panel.set_timer_state(TimerState.IDLE, None)
    assert panel._panel_stack.currentWidget() is panel._idle_page
    assert panel.size() == initial_size
    panel.hide()


def test_focus_panel_optional_note_disclosure_preserves_text(qt_application) -> None:
    panel = FocusPanel()
    panel.show()
    qt_application.processEvents()
    assert not panel._note_input.isVisibleTo(panel)

    panel._note_toggle.click()
    panel._note_input.setText("Keep this note while the panel changes state")
    panel.set_timer_state(TimerState.FOCUSING, "Writing")
    panel.set_timer_state(TimerState.IDLE, None)
    qt_application.processEvents()

    assert panel._note_toggle.isChecked()
    assert panel._note_input.isVisibleTo(panel)
    assert panel._note_input.text() == "Keep this note while the panel changes state"
    panel.hide()
