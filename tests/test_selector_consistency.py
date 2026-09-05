"""Application-wide checks for the shared selector design system."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QDate, QPoint, QPointF, Qt, QTime
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import (
    QApplication,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.data.models import FocusItem
from app.ui.anchored_popup import PopupState
from app.ui.components import ThemedDateEdit
from app.ui.dashboard import DashboardWindow
from app.ui.rounded_selector import RoundedComboBox, SelectorDensity
from app.ui.session_editor_dialog import SessionEditorDialog
from app.ui.settings_dialog import SettingsDialog
from app.ui.time_picker import RoundedTimePicker


def _send_wheel(
    widget: QWidget,
    angle_delta_y: int = -120,
    *,
    pixel_delta_y: int = 0,
) -> QWheelEvent:
    local_position = QPointF(widget.rect().center())
    global_position = QPointF(widget.mapToGlobal(widget.rect().center()))
    event = QWheelEvent(
        local_position,
        global_position,
        QPoint(0, pixel_delta_y),
        QPoint(0, angle_delta_y),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )
    QApplication.sendEvent(widget, event)
    return event


def _send_native_window_wheel(
    widget: QWidget,
    angle_delta_y: int = -120,
    *,
    pixel_delta_y: int = 0,
) -> None:
    top_level = widget.window()
    window = top_level.windowHandle()
    assert window is not None
    global_position = widget.mapToGlobal(widget.rect().center())
    local_position = top_level.mapFromGlobal(global_position)
    QTest.wheelEvent(
        window,
        QPointF(local_position),
        QPoint(0, angle_delta_y),
        QPoint(0, pixel_delta_y),
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate,
    )


def test_ui_modules_do_not_instantiate_native_selector_controls() -> None:
    ui_root = Path(__file__).resolve().parents[1] / "app" / "ui"
    forbidden = {"QComboBox", "QDateEdit", "QTimeEdit", "QSpinBox"}
    violations: list[str] = []
    for path in sorted(ui_root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id in forbidden:
                violations.append(f"{path.name}:{node.lineno}:{node.func.id}")
    assert violations == []


def test_shared_selector_densities_and_popup_are_consistent(qt_application) -> None:
    large = RoundedComboBox(density=SelectorDensity.LARGE)
    compact = RoundedComboBox(density=SelectorDensity.COMPACT)
    for selector in (large, compact):
        selector.addItems(["First", "Second", "Third"])
        selector.show()
    qt_application.processEvents()

    assert large.height() == 48
    assert compact.height() == 40
    assert large.property("roundedSelector")
    assert compact.property("roundedSelector")

    activated = QSignalSpy(compact.activated)
    compact.showPopup()
    QTest.qWait(180)
    popup = compact.view().window()
    image = popup.grab().toImage()
    assert popup is compact._popup_container
    assert popup.mask().isEmpty()
    assert image.pixelColor(0, 0).alpha() == 0
    compact.view().setCurrentIndex(compact.model().index(1, 0))
    QTest.keyClick(compact.view(), Qt.Key.Key_Return)
    QTest.qWait(220)
    assert compact.currentIndex() == 1
    assert activated.count() == 1
    assert not popup.isVisible()

    large.close()
    compact.close()


def test_closed_selector_ignores_wheel_without_changing_or_activating(
    qt_application,
) -> None:
    selector = RoundedComboBox(density=SelectorDensity.COMPACT)
    selector.addItems(["First", "Second", "Third"])
    selector.setCurrentIndex(1)
    selector.show()
    qt_application.processEvents()
    changed = QSignalSpy(selector.currentIndexChanged)
    activated = QSignalSpy(selector.activated)

    event = _send_wheel(selector)
    qt_application.processEvents()

    assert not event.isAccepted()
    assert selector.currentIndex() == 1
    assert changed.count() == 0
    assert activated.count() == 0
    assert not selector._popup_container.isVisible()
    selector.close()


def test_wheel_over_closed_selector_continues_scrolling_its_page(
    qt_application,
) -> None:
    scroll = QScrollArea()
    scroll.setWidgetResizable(False)
    content = QWidget()
    content.setFixedSize(320, 1200)
    layout = QVBoxLayout(content)
    selector = RoundedComboBox(density=SelectorDensity.COMPACT)
    selector.addItems(["First", "Second", "Third"])
    selector.setCurrentIndex(1)
    layout.addSpacing(300)
    layout.addWidget(selector)
    layout.addStretch()
    scroll.setWidget(content)
    scroll.resize(340, 300)
    scroll.show()
    qt_application.processEvents()
    before = scroll.verticalScrollBar().value()

    _send_wheel(selector)
    qt_application.processEvents()

    assert selector.currentIndex() == 1
    assert scroll.verticalScrollBar().value() > before
    scroll.close()


def test_external_page_wheel_immediately_closes_popup_and_keeps_scrolling(
    qt_application,
) -> None:
    scroll = QScrollArea()
    scroll.setWidgetResizable(False)
    content = QWidget()
    content.setFixedSize(320, 1200)
    layout = QVBoxLayout(content)
    selector = RoundedComboBox(density=SelectorDensity.COMPACT)
    selector.addItems([f"Item {index}" for index in range(20)])
    selector.setCurrentIndex(4)
    layout.addSpacing(300)
    layout.addWidget(selector)
    layout.addStretch()
    scroll.setWidget(content)
    scroll.resize(340, 300)
    scroll.show()
    qt_application.processEvents()
    selector.showPopup()
    # The popup animation is 160 ms; leave headroom for Windows' timer tick
    # and the scroll area's first layout pass before asserting its final state.
    QTest.qWait(240)
    assert selector._popup_container.popup_state is PopupState.OPEN
    assert selector._popup_container.isVisible()
    before = scroll.verticalScrollBar().value()

    _send_wheel(scroll.viewport())
    qt_application.processEvents()

    assert selector.currentIndex() == 4
    assert selector._popup_container.popup_state is PopupState.CLOSED
    assert not selector._popup_container.isVisible()
    assert not selector.property("popupExpanded")
    assert scroll.verticalScrollBar().value() > before

    selector.showPopup()
    QTest.qWait(240)
    assert selector._popup_container.popup_state is PopupState.OPEN
    before_native = scroll.verticalScrollBar().value()
    _send_native_window_wheel(scroll.viewport())
    qt_application.processEvents()
    assert selector._popup_container.popup_state is PopupState.CLOSED
    assert not selector._popup_container.isVisible()
    assert scroll.verticalScrollBar().value() > before_native

    selector.showPopup()
    QTest.qWait(240)
    assert selector._popup_container.popup_state is PopupState.OPEN
    scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().value() + 40)
    qt_application.processEvents()
    assert selector._popup_container.popup_state is PopupState.CLOSED
    assert not selector._popup_container.isVisible()
    scroll.close()


def test_open_selector_wheel_over_field_and_popup_scrolls_without_committing(
    qt_application,
) -> None:
    selector = RoundedComboBox(density=SelectorDensity.COMPACT)
    selector.setMaxVisibleItems(4)
    selector.addItems([f"Item {index}" for index in range(20)])
    selector.setCurrentIndex(0)
    selector.resize(220, 40)
    selector.show()
    qt_application.processEvents()
    changed = QSignalSpy(selector.currentIndexChanged)
    activated = QSignalSpy(selector.activated)
    selector.showPopup()
    QTest.qWait(180)
    scroll_bar = selector.view().verticalScrollBar()
    popup = selector._popup_container
    wheel_targets = (
        selector,
        popup,
        popup.surface,
        selector.view(),
        selector.view().viewport(),
    )
    for target in wheel_targets:
        scroll_bar.setValue(0)
        _send_wheel(target)
        qt_application.processEvents()

        assert scroll_bar.value() > 0
        assert popup.popup_state is PopupState.OPEN
        assert popup.isVisible()
        assert selector.currentIndex() == 0
        assert changed.count() == 0
        assert activated.count() == 0

    scroll_bar.setValue(0)
    _send_wheel(selector.view().viewport(), 0, pixel_delta_y=-24)
    qt_application.processEvents()
    assert scroll_bar.value() == 24
    assert selector.currentIndex() == 0
    assert changed.count() == activated.count() == 0
    selector.close()


def test_native_window_wheel_over_field_and_popup_browses_without_closing(
    qt_application,
) -> None:
    selector = RoundedComboBox(density=SelectorDensity.LARGE)
    selector.setMaxVisibleItems(5)
    selector.addItems([f"Item {index}" for index in range(30)])
    selector.setCurrentIndex(0)
    selector.resize(240, 48)
    selector.show()
    qt_application.processEvents()
    changed = QSignalSpy(selector.currentIndexChanged)
    activated = QSignalSpy(selector.activated)
    selector.showPopup()
    QTest.qWait(180)
    popup = selector._popup_container
    scroll_bar = selector.view().verticalScrollBar()

    for target in (selector, popup, popup.surface, selector.view().viewport()):
        scroll_bar.setValue(0)
        _send_native_window_wheel(target)
        qt_application.processEvents()
        assert scroll_bar.value() > 0
        assert popup.popup_state is PopupState.OPEN
        assert popup.isVisible()
        assert selector.currentIndex() == 0
        assert changed.count() == activated.count() == 0

    selector.close()


def test_moving_owner_window_immediately_closes_every_selector_popup(
    qt_application,
) -> None:
    host = QWidget()
    layout = QVBoxLayout(host)
    combo = RoundedComboBox(density=SelectorDensity.COMPACT)
    combo.addItems(["First", "Second", "Third"])
    combo.setCurrentIndex(1)
    date_edit = ThemedDateEdit(QDate(2026, 8, 26))
    time_picker = RoundedTimePicker(QTime(20, 39))
    selectors_and_popups = (
        (combo, combo._popup_container),
        (date_edit, date_edit._popup),
        (time_picker, time_picker._popup),
    )
    for selector, _popup in selectors_and_popups:
        layout.addWidget(selector)
    host.resize(320, 240)
    host.show()
    qt_application.processEvents()

    original_values = (combo.currentIndex(), date_edit.date(), time_picker.time())
    for index, (selector, popup) in enumerate(selectors_and_popups, start=1):
        selector.showPopup()
        QTest.qWait(180)
        assert popup.popup_state in {PopupState.OPENING, PopupState.OPEN}
        assert popup.isVisible()

        host.move(host.x() + 12 * index, host.y() + 8 * index)
        qt_application.processEvents()

        assert popup.popup_state is PopupState.CLOSED
        assert not popup.isVisible()
        assert not selector.property("popupExpanded")

    assert (combo.currentIndex(), date_edit.date(), time_picker.time()) == original_values
    host.close()


def test_resizing_owner_closes_popup_but_local_anchor_move_reanchors(
    qt_application,
) -> None:
    host = QWidget()
    selector = RoundedComboBox(host, density=SelectorDensity.COMPACT)
    selector.addItems(["First", "Second", "Third"])
    selector.setGeometry(30, 30, 220, 40)
    host.resize(320, 200)
    host.show()
    qt_application.processEvents()

    selector.showPopup()
    QTest.qWait(180)
    popup = selector._popup_container
    selector.move(42, 48)
    qt_application.processEvents()
    assert popup.popup_state is PopupState.OPEN
    assert popup.isVisible()
    assert popup.pos() == selector.mapToGlobal(
        QPoint(0, selector.height() + popup._gap)
    )

    host.resize(360, 240)
    qt_application.processEvents()
    assert popup.popup_state is PopupState.CLOSED
    assert not popup.isVisible()
    assert not selector.property("popupExpanded")
    host.close()


def test_date_and_time_selectors_use_compact_fields_and_rounded_popups(
    qt_application,
) -> None:
    date_edit = ThemedDateEdit(QDate(2026, 8, 26))
    time_picker = RoundedTimePicker(QTime(20, 39))
    date_edit.show()
    time_picker.show()
    qt_application.processEvents()

    assert date_edit.height() == 40
    assert time_picker.height() == 40
    assert date_edit.property("selectorDensity") == "compact"
    assert time_picker.property("selectorDensity") == "compact"
    assert date_edit.calendarWidget().objectName() == "themedCalendar"
    assert date_edit.calendarWidget().window().objectName() == "themedCalendarPopup"

    QTest.mouseClick(
        date_edit,
        Qt.MouseButton.LeftButton,
        pos=QPoint(date_edit.width() - 18, date_edit.height() // 2),
    )
    QTest.qWait(180)
    calendar_popup = date_edit.calendarWidget().window()
    calendar_image = calendar_popup.grab().toImage()
    assert calendar_popup.isVisible()
    assert calendar_image.pixelColor(0, 0).alpha() == 0
    assert calendar_image.pixelColor(
        calendar_image.width() // 2,
        calendar_image.height() // 2,
    ).alpha() > 0
    date_edit.hidePopup()
    QTest.qWait(220)

    changed = QSignalSpy(time_picker.timeChanged)
    time_picker.showPopup()
    QTest.qWait(180)
    popup = time_picker._popup
    popup._hour_list.setCurrentRow(23)
    popup._minute_list.setCurrentRow(59)
    assert time_picker.time() == QTime(23, 59)
    assert changed.count() >= 1
    popup_image = popup.grab().toImage()
    assert popup_image.pixelColor(0, 0).alpha() == 0
    QTest.keyClick(popup, Qt.Key.Key_Escape)
    QTest.qWait(220)
    assert not popup.isVisible()

    date_edit.close()
    time_picker.close()


def test_date_and_time_fields_do_not_change_from_wheel_input(qt_application) -> None:
    original_date = QDate(2026, 8, 26)
    original_time = QTime(20, 39)
    date_edit = ThemedDateEdit(original_date)
    time_picker = RoundedTimePicker(original_time)
    date_changed = QSignalSpy(date_edit.dateChanged)
    time_changed = QSignalSpy(time_picker.timeChanged)
    date_edit.show()
    time_picker.show()
    qt_application.processEvents()

    _send_wheel(date_edit)
    _send_wheel(time_picker)
    qt_application.processEvents()

    assert date_edit.date() == original_date
    assert time_picker.time() == original_time
    assert date_changed.count() == 0
    assert time_changed.count() == 0
    date_edit.close()
    time_picker.close()


def test_wheel_inside_date_and_time_popups_keeps_them_open(qt_application) -> None:
    original_date = QDate(2026, 8, 26)
    original_time = QTime(0, 0)
    date_edit = ThemedDateEdit(original_date)
    time_picker = RoundedTimePicker(original_time)
    date_changed = QSignalSpy(date_edit.dateChanged)
    time_changed = QSignalSpy(time_picker.timeChanged)
    date_edit.show()
    time_picker.show()
    qt_application.processEvents()

    date_edit.showPopup()
    QTest.qWait(180)
    for target in (
        date_edit,
        date_edit._popup,
        date_edit._popup._scroll,
        date_edit.calendarWidget(),
    ):
        shown_month = (
            date_edit.calendarWidget().yearShown(),
            date_edit.calendarWidget().monthShown(),
        )
        _send_wheel(target)
        qt_application.processEvents()
        assert (
            date_edit.calendarWidget().yearShown(),
            date_edit.calendarWidget().monthShown(),
        ) != shown_month
        assert date_edit._popup.popup_state is PopupState.OPEN
        assert date_edit._popup.isVisible()
        assert date_edit.date() == original_date
        assert date_changed.count() == 0

    for target in (date_edit, date_edit._popup, date_edit.calendarWidget()):
        shown_month = (
            date_edit.calendarWidget().yearShown(),
            date_edit.calendarWidget().monthShown(),
        )
        _send_native_window_wheel(target)
        qt_application.processEvents()
        assert (
            date_edit.calendarWidget().yearShown(),
            date_edit.calendarWidget().monthShown(),
        ) != shown_month
        assert date_edit._popup.popup_state is PopupState.OPEN
        assert date_edit.date() == original_date
        assert date_changed.count() == 0
    date_edit.hidePopup()
    QTest.qWait(140)

    time_picker.showPopup()
    QTest.qWait(180)
    popup = time_picker._popup
    hour_scroll = popup._hour_list.verticalScrollBar()
    minute_scroll = popup._minute_list.verticalScrollBar()
    for target in (time_picker, popup._hour_list, popup._hour_list.viewport()):
        hour_scroll.setValue(0)
        _send_wheel(target)
        qt_application.processEvents()
        assert hour_scroll.value() > 0
        assert popup.popup_state is PopupState.OPEN
        assert time_picker.time() == original_time
        assert time_changed.count() == 0

    popup._minute_list.setFocus(Qt.FocusReason.MouseFocusReason)
    minute_scroll.setValue(0)
    _send_wheel(time_picker)
    qt_application.processEvents()
    assert minute_scroll.value() > 0

    for target in (popup._minute_list, popup._minute_list.viewport()):
        minute_scroll.setValue(0)
        _send_wheel(target)
        qt_application.processEvents()
        assert minute_scroll.value() > 0
        assert popup.popup_state is PopupState.OPEN
        assert time_picker.time() == original_time
        assert time_changed.count() == 0

    hour_scroll.setValue(0)
    minute_scroll = time_picker._popup._minute_list.verticalScrollBar()
    minute_scroll.setValue(0)
    for target in (popup, popup.surface):
        _send_wheel(target)
        qt_application.processEvents()
        assert hour_scroll.value() > 0 or minute_scroll.value() > 0
        hour_scroll.setValue(0)
        minute_scroll.setValue(0)

    popup._hour_list.setFocus(Qt.FocusReason.MouseFocusReason)
    for target in (time_picker, popup, popup.surface, popup._hour_list.viewport()):
        hour_scroll.setValue(0)
        minute_scroll.setValue(0)
        _send_native_window_wheel(target)
        qt_application.processEvents()
        assert hour_scroll.value() > 0 or minute_scroll.value() > 0
        assert popup.popup_state is PopupState.OPEN
        assert time_picker.time() == original_time
        assert time_changed.count() == 0
    assert popup.isVisible()
    assert time_picker.time() == original_time
    assert time_changed.count() == 0
    date_edit.close()
    time_picker.close()


def test_selector_popups_toggle_once_animate_and_stay_below(
    qt_application,
) -> None:
    combo = RoundedComboBox(density=SelectorDensity.COMPACT)
    combo.addItems([f"Item {index}" for index in range(20)])
    combo.resize(220, 40)
    combo.show()
    qt_application.processEvents()

    expected_top = combo.mapToGlobal(QPoint(0, combo.height() + 4)).y()
    QTest.mouseClick(combo, Qt.MouseButton.LeftButton)
    qt_application.processEvents()
    popup = combo._popup_container
    assert popup.isVisible()
    assert popup.y() == expected_top
    opening_height = popup.height()
    QTest.qWait(70)
    assert popup.height() > opening_height

    QTest.mouseClick(combo, Qt.MouseButton.LeftButton)
    QTest.qWait(220)
    assert not popup.isVisible()

    QTest.mouseClick(combo, Qt.MouseButton.LeftButton)
    QTest.qWait(35)
    QTest.mouseClick(combo, Qt.MouseButton.LeftButton)
    QTest.qWait(20)
    QTest.mouseClick(combo, Qt.MouseButton.LeftButton)
    QTest.qWait(180)
    assert popup.isVisible()
    assert popup.y() == expected_top
    combo.close()


def test_all_selector_types_toggle_once_and_open_below(qt_application) -> None:
    combo = RoundedComboBox(density=SelectorDensity.COMPACT)
    combo.addItems(["First", "Second"])
    date_edit = ThemedDateEdit(QDate(2026, 8, 26))
    time_picker = RoundedTimePicker(QTime(20, 39))
    selectors_and_popups = (
        (combo, combo._popup_container),
        (date_edit, date_edit._popup),
        (time_picker, time_picker._popup),
    )
    for selector, _popup in selectors_and_popups:
        selector.resize(220, 40)
        selector.show()
    qt_application.processEvents()

    for selector, popup in selectors_and_popups:
        expected_top = selector.mapToGlobal(QPoint(0, selector.height() + 4)).y()
        QTest.mouseClick(selector, Qt.MouseButton.LeftButton)
        QTest.qWait(180)
        assert popup.isVisible()
        assert popup.y() == expected_top
        QTest.mouseClick(selector, Qt.MouseButton.LeftButton)
        QTest.qWait(220)
        assert not popup.isVisible()
        QTest.mouseClick(selector, Qt.MouseButton.LeftButton)
        QTest.qWait(180)
        assert popup.isVisible()
        _send_wheel(selector)
        qt_application.processEvents()
        assert popup.popup_state is PopupState.OPEN
        assert popup.isVisible()
        popup.hide_immediately()
        selector.close()


def test_popup_height_is_compressed_below_screen_instead_of_flipping(
    qt_application,
) -> None:
    combo = RoundedComboBox(density=SelectorDensity.COMPACT)
    combo.addItems([f"Item {index}" for index in range(30)])
    combo.resize(220, 40)
    available = qt_application.primaryScreen().availableGeometry()
    combo.move(available.left() + 20, available.bottom() - combo.height() - 72)
    combo.show()
    qt_application.processEvents()

    expected_top = combo.mapToGlobal(QPoint(0, combo.height() + 4)).y()
    combo.showPopup()
    QTest.qWait(180)
    popup = combo._popup_container
    assert popup.y() == expected_top
    assert popup.geometry().bottom() <= available.bottom()
    assert popup.height() < popup._ideal_size().height()
    assert combo.view().verticalScrollBar().maximum() > 0
    combo.close()


def test_outside_click_closes_and_another_selector_opens_in_one_click(
    qt_application,
) -> None:
    first = RoundedComboBox(density=SelectorDensity.COMPACT)
    second = RoundedComboBox(density=SelectorDensity.COMPACT)
    outside = QPushButton("Outside")
    for index, widget in enumerate((first, second, outside)):
        widget.resize(180, 40)
        widget.move(40 + index * 220, 80)
        widget.show()
    first.addItems(["One", "Two"])
    second.addItems(["Three", "Four"])
    qt_application.processEvents()

    QTest.mouseClick(first, Qt.MouseButton.LeftButton)
    QTest.qWait(180)
    assert first._popup_container.isVisible()

    QTest.mouseClick(second, Qt.MouseButton.LeftButton)
    QTest.qWait(180)
    assert not first._popup_container.isVisible()
    assert second._popup_container.isVisible()

    QTest.mouseClick(outside, Qt.MouseButton.LeftButton)
    QTest.qWait(220)
    assert not second._popup_container.isVisible()
    first.close()
    second.close()
    outside.close()


def test_every_visible_application_selector_uses_the_expected_density(
    qt_application,
) -> None:
    settings = SettingsDialog()
    dashboard = DashboardWindow(timezone.utc)
    editor = SessionEditorDialog(timezone.utc)
    editor.set_focus_items(
        [
            FocusItem(
                1,
                "Deep Work",
                "#7C5CFC",
                False,
                False,
                datetime.now(timezone.utc),
                datetime.now(timezone.utc),
            )
        ]
    )
    for widget in (settings, dashboard, editor):
        widget.show()
    qt_application.processEvents()

    compact_selectors = (
        settings._language_combo,
        settings._default_focus_mode,
        settings._daily_goal_minutes._hours_combo,
        settings._daily_goal_minutes._minutes_combo,
        dashboard._period_combo,
        dashboard._timeline_date_edit,
        editor._date_edit,
        editor._focus_item_combo,
        editor._entry_method,
        editor._start_edit,
        editor._end_edit,
    )
    assert all(
        selector.property("selectorDensity") == "compact"
        for selector in compact_selectors
    )
    assert all(selector.height() == 40 for selector in compact_selectors)

    editor._entry_method.setCurrentIndex(1)
    editor._duration_picker.setValue(999 * 60 + 59)
    assert editor._duration_picker.value() == 999 * 60 + 59
    assert editor.focus_values()[3] == float((999 * 60 + 59) * 60)
    editor._duration_picker.setValue(0)
    assert editor._duration_picker.value() == 1

    editor.close()
    dashboard.close()
    settings.close()
