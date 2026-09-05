"""Focused GUI tests for the static pet window."""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QContextMenuEvent, QPixmap
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QLabel

from app.pet.pet_window import PetWindow


def _window_with_image() -> PetWindow:
    window = PetWindow()
    source = QPixmap(200, 100)
    source.fill(QColor(120, 80, 200, 255))
    window.set_pet_image(source, 100)
    return window


def test_pet_window_flags_transparency_and_aspect_ratio(qt_application) -> None:
    window = _window_with_image()

    assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert window._image_label.size().width() == 192
    assert window._image_label.size().height() == 96
    assert window.size() == window._image_label.size()
    assert window.size().width() == 192
    assert window.size().height() == 96
    assert window.findChildren(QLabel) == [window._image_label]
    assert not hasattr(window, "_status_label")
    assert not hasattr(window, "set_ready_status")
    assert not hasattr(window, "set_paused_status")
    assert not hasattr(window, "set_completed_status")

    window.set_pet_size(150)
    assert window._image_label.size().width() == 288
    assert window._image_label.size().height() == 144
    assert window.size().width() == 288
    assert window.size().height() == 144
    window.close()


def test_left_mouse_drag_moves_pet_and_emits_final_position(qt_application) -> None:
    window = _window_with_image()
    window.move(100, 100)
    window.show()
    position_spy = QSignalSpy(window.position_changed)
    panel_spy = QSignalSpy(window.focus_panel_requested)

    QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
    QTest.mouseMove(window, QPoint(50, 45), delay=1)
    QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=QPoint(50, 45))

    assert window.pos() == QPoint(130, 125)
    assert position_spy.count() == 1
    assert position_spy.at(0) == [130, 125]
    assert panel_spy.count() == 0
    window.close()


def test_left_click_requests_study_panel_without_moving_pet(qt_application) -> None:
    window = _window_with_image()
    window.move(100, 100)
    window.show()
    position_spy = QSignalSpy(window.position_changed)
    panel_spy = QSignalSpy(window.focus_panel_requested)

    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=QPoint(40, 40))

    assert window.pos() == QPoint(100, 100)
    assert position_spy.count() == 0
    assert panel_spy.count() == 1
    window.close()


def test_small_pointer_jitter_still_counts_as_a_click(qt_application) -> None:
    window = _window_with_image()
    window.move(100, 100)
    window.show()
    position_spy = QSignalSpy(window.position_changed)
    panel_spy = QSignalSpy(window.focus_panel_requested)

    QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=QPoint(40, 40))
    QTest.mouseMove(window, QPoint(43, 42), delay=1)
    QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=QPoint(43, 42))

    assert window.pos() == QPoint(100, 100)
    assert position_spy.count() == 0
    assert panel_spy.count() == 1
    window.close()


def test_right_click_requests_shared_context_menu_without_moving_pet(qt_application) -> None:
    window = _window_with_image()
    window.move(100, 100)
    menu_spy = QSignalSpy(window.context_menu_requested)
    event = QContextMenuEvent(
        QContextMenuEvent.Reason.Mouse,
        QPoint(40, 40),
        QPoint(140, 140),
    )

    window.contextMenuEvent(event)

    assert menu_spy.count() == 1
    assert menu_spy.at(0) == [QPoint(140, 140)]
    assert window.pos() == QPoint(100, 100)
    window.close()
