"""Shared animated information bubble behavior and native-tooltip interception."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QHelpEvent, QImage
from PySide6.QtWidgets import (
    QApplication,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QWidget,
)

from app.core.theme import COLOR_THEMES, get_theme_manager
from app.ui.info_bubble import AnimatedInfoBubble, install_animated_tooltips


def test_info_bubble_has_short_fade_and_two_pixel_rise(qt_application) -> None:
    host = QWidget()
    host.resize(400, 240)
    host.show()
    bubble = AnimatedInfoBubble(host)
    bubble.set_text("2026-09-01 · 1h 30min")

    bubble.show_animated()
    bubble._animation.setCurrentTime(40)
    assert bubble.isVisible()
    assert 0.0 < bubble.animation_progress < 1.0
    assert 0.0 < bubble.vertical_offset < 2.0

    bubble._animation.setCurrentTime(100)
    assert bubble.animation_progress == pytest.approx(1.0)
    assert bubble.vertical_offset == pytest.approx(0.0)

    bubble.hide_animated()
    bubble._animation.setCurrentTime(35)
    assert 0.0 < bubble.animation_progress < 1.0
    assert bubble.vertical_offset == pytest.approx(0.0)
    bubble._animation.setCurrentTime(70)
    qt_application.processEvents()
    assert not bubble.isVisible()
    host.close()


def test_info_bubble_reverses_without_queuing_or_restarting_visible_content(
    qt_application,
) -> None:
    host = QWidget()
    host.show()
    bubble = AnimatedInfoBubble(host)
    bubble.set_text("First")
    bubble.show_animated()
    bubble._animation.setCurrentTime(45)
    partial = bubble.animation_progress
    current_time = bubble._animation.currentTime()
    bubble.show_animated()
    assert bubble._animation.currentTime() == current_time

    bubble.hide_animated()
    bubble._animation.setCurrentTime(20)
    fading = bubble.animation_progress
    assert fading < partial
    bubble.set_text("Second")
    bubble.show_animated()
    assert bubble.animation_progress == pytest.approx(fading)
    bubble._animation.setCurrentTime(bubble._animation.duration())
    qt_application.processEvents()
    assert bubble.animation_progress == pytest.approx(1.0)
    assert bubble.text == "Second"

    bubble.show_animated()
    assert bubble.animation_progress == pytest.approx(1.0)
    host.close()


def test_info_bubble_is_rounded_opaque_rgb_across_themes(qt_application) -> None:
    manager = get_theme_manager()
    original_theme = manager.theme_name
    host = QWidget()
    host.show()
    bubble = AnimatedInfoBubble(host)
    bubble.set_text("Rounded information")
    bubble.show_animated()
    bubble._animation.setCurrentTime(50)
    try:
        for theme in COLOR_THEMES:
            manager.set_theme(theme)
            manager._transition.finish_all()
            image = QImage(
                bubble.size(),
                QImage.Format.Format_ARGB32_Premultiplied,
            )
            image.fill(Qt.GlobalColor.transparent)
            bubble.render(image)
            center = image.pixelColor(bubble.rect().center())
            corner = image.pixelColor(0, 0)
            assert 0 < center.alpha() < 255
            assert (center.red(), center.green(), center.blue()) != (0, 0, 0)
            assert corner.alpha() == 0
            assert bubble.surface_radius == 10.0
    finally:
        bubble.close()
        host.close()
        manager.set_theme(original_theme)
        manager._transition.finish_all()


def test_application_tooltip_event_uses_shared_bubble_and_fades_on_leave(
    qt_application,
) -> None:
    tooltip_manager = install_animated_tooltips(qt_application)
    tooltip_manager.hide_immediately()
    button = QPushButton("Control")
    button.setToolTip("A shared rounded tooltip")
    button.resize(160, 40)
    button.show()
    qt_application.processEvents()
    local_position = QPoint(12, 12)
    global_position = button.mapToGlobal(local_position)
    event = QHelpEvent(
        QEvent.Type.ToolTip,
        local_position,
        global_position,
    )

    QApplication.sendEvent(button, event)

    bubble = tooltip_manager.bubble
    assert event.isAccepted()
    assert tooltip_manager.owner is button
    assert bubble.isVisible()
    assert bubble.text == button.toolTip()
    bubble._animation.setCurrentTime(bubble._animation.duration())
    assert bubble.animation_progress == pytest.approx(1.0)

    QApplication.sendEvent(button, QEvent(QEvent.Type.Leave))
    assert bubble.isVisible()
    bubble._animation.setCurrentTime(bubble._animation.duration())
    qt_application.processEvents()
    assert not bubble.isVisible()
    assert tooltip_manager.owner is None
    button.close()


def test_tooltip_updates_in_place_wraps_text_and_clamps_to_screen(
    qt_application,
) -> None:
    tooltip_manager = install_animated_tooltips(qt_application)
    tooltip_manager.hide_immediately()
    owner = QWidget()
    owner.resize(120, 40)
    owner.show()
    screen = owner.screen().availableGeometry()
    text = (
        "This is a deliberately long tooltip description that should wrap "
        "inside the shared rounded information bubble."
    )
    position = screen.bottomRight()
    tooltip_manager.show_for(owner, text, position)
    bubble = tooltip_manager.bubble
    bubble._animation.setCurrentTime(bubble._animation.duration())
    original_progress = bubble.animation_progress
    original_height = bubble.height()

    tooltip_manager.show_for(owner, "Updated", position)

    assert bubble.animation_progress == pytest.approx(original_progress)
    assert original_height > bubble.fontMetrics().lineSpacing() + 16
    assert bubble.width() <= 320 + 2 * bubble.shadow_margin
    assert bubble.geometry().right() <= screen.right()
    assert bubble.geometry().bottom() <= screen.bottom()
    tooltip_manager.hide_immediately(owner=owner)
    owner.close()


def test_item_view_tooltip_role_is_also_intercepted(qt_application) -> None:
    tooltip_manager = install_animated_tooltips(qt_application)
    tooltip_manager.hide_immediately()
    view = QListWidget()
    item = QListWidgetItem("Project")
    item.setToolTip("Full project name")
    view.addItem(item)
    view.resize(220, 100)
    view.show()
    qt_application.processEvents()
    position = view.visualItemRect(item).center()
    global_position = view.viewport().mapToGlobal(position)
    event = QHelpEvent(QEvent.Type.ToolTip, position, global_position)

    QApplication.sendEvent(view.viewport(), event)

    assert event.isAccepted()
    assert tooltip_manager.owner is view.viewport()
    assert tooltip_manager.bubble.text == "Full project name"
    tooltip_manager.hide_immediately(owner=view.viewport())
    view.close()


def test_theme_switch_repaints_global_bubble_without_resetting_animation(
    qt_application,
) -> None:
    theme_manager = get_theme_manager()
    original_theme = theme_manager.theme_name
    target_theme = "pink" if original_theme != "pink" else "blue"
    tooltip_manager = install_animated_tooltips(qt_application)
    tooltip_manager.hide_immediately()
    owner = QWidget()
    owner.show()
    tooltip_manager.show_for(owner, "Theme-aware", owner.mapToGlobal(QPoint()))
    bubble = tooltip_manager.bubble
    bubble._animation.setCurrentTime(35)
    progress = bubble.animation_progress
    try:
        theme_manager.set_theme(target_theme)
        theme_manager._transition.finish_all()
        assert bubble.isVisible()
        assert bubble.animation_progress == pytest.approx(progress)
    finally:
        tooltip_manager.hide_immediately(owner=owner)
        owner.close()
        theme_manager.set_theme(original_theme)
        theme_manager._transition.finish_all()


def test_window_move_hides_global_bubble_immediately(qt_application) -> None:
    tooltip_manager = install_animated_tooltips(qt_application)
    tooltip_manager.hide_immediately()
    window = QWidget()
    owner = QPushButton("Hover", window)
    window.resize(240, 120)
    window.show()
    qt_application.processEvents()
    tooltip_manager.show_for(owner, "Moving window", owner.mapToGlobal(QPoint()))
    tooltip_manager.bubble._animation.setCurrentTime(
        tooltip_manager.bubble._animation.duration()
    )
    assert tooltip_manager.bubble.isVisible()

    window.move(window.x() + 15, window.y() + 10)
    qt_application.processEvents()

    assert not tooltip_manager.bubble.isVisible()
    assert tooltip_manager.owner is None
    window.close()
