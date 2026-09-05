from __future__ import annotations

from datetime import timezone

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QLineEdit, QVBoxLayout, QWidget

from app.ui.dashboard import DashboardPage, DashboardWindow
from app.ui.page_transition import AnimatedPageStack
from app.ui.settings_dialog import SettingsDialog


def _shown_stack(qt_application) -> tuple[QWidget, AnimatedPageStack]:
    host = QWidget()
    host.resize(480, 320)
    layout = QVBoxLayout(host)
    stack = AnimatedPageStack()
    for text in ("first", "second", "third"):
        stack.addWidget(QLabel(text))
    layout.addWidget(stack)
    host.show()
    QTest.qWait(10)
    return host, stack


def test_hidden_page_switch_is_immediate_without_animation(qt_application) -> None:
    stack = AnimatedPageStack()
    stack.addWidget(QWidget())
    stack.addWidget(QWidget())

    stack.setCurrentIndex(1)

    assert stack.currentIndex() == 1
    assert not stack.is_transition_active
    assert stack.transition_progress == 1.0


def test_visible_page_switch_fades_and_rises_to_stable_geometry(qt_application) -> None:
    host, stack = _shown_stack(qt_application)
    original_geometry = stack.geometry()

    stack.setCurrentIndex(1)

    assert stack.currentIndex() == 1
    assert stack.is_transition_active
    assert stack.transition_progress == 0.0
    assert stack.transition_offset_y == stack.transition_rise_distance

    stack._transition_animation.setCurrentTime(stack.transition_duration_ms // 2)
    assert 0.0 < stack.transition_progress < 1.0
    assert 0.0 < stack.transition_offset_y < stack.transition_rise_distance
    assert stack.geometry() == original_geometry

    stack._transition_animation.setCurrentTime(stack.transition_duration_ms)
    assert not stack.is_transition_active
    assert stack.transition_progress == 1.0
    assert stack.transition_offset_y == 0.0
    assert stack.geometry() == original_geometry
    host.close()


def test_rapid_switch_retargets_without_queue_or_state_loss(qt_application) -> None:
    host, stack = _shown_stack(qt_application)
    field = QLineEdit(stack.widget(2))
    field.setText("preserved")

    stack.setCurrentIndex(1)
    stack._transition_animation.setCurrentTime(55)
    stack.setCurrentIndex(2)

    assert stack.currentIndex() == 2
    assert stack.is_transition_active
    assert field.text() == "preserved"
    assert sum(
        overlay.isVisible()
        for overlay in host.findChildren(QWidget, "pageTransitionOverlay")
    ) == 1

    stack._transition_animation.setCurrentTime(stack.transition_duration_ms)
    assert not stack.is_transition_active
    assert not any(
        overlay.isVisible()
        for overlay in stack.parentWidget().findChildren(
            QWidget, "pageTransitionOverlay"
        )
    )
    host.close()


def test_repeat_resize_and_hide_finish_safely(qt_application) -> None:
    host, stack = _shown_stack(qt_application)

    stack.setCurrentIndex(0)
    assert not stack.is_transition_active
    stack.setCurrentIndex(1)
    assert stack.is_transition_active

    host.resize(520, 340)
    QTest.qWait(5)
    assert not stack.is_transition_active

    stack.setCurrentIndex(2)
    assert stack.is_transition_active
    host.hide()
    QTest.qWait(5)
    assert not stack.is_transition_active
    host.close()


def test_dashboard_navigation_updates_immediately(qt_application) -> None:
    window = DashboardWindow(timezone.utc)
    window.show()
    QTest.qWait(10)

    window.set_current_page(DashboardPage.ANALYTICS)

    assert window.current_page() is DashboardPage.ANALYTICS
    assert window._nav_buttons[DashboardPage.ANALYTICS].isChecked()
    assert window._pages.is_transition_active
    window._pages.finish_transition()
    window.close()


def test_settings_title_and_form_share_one_transition_region(qt_application) -> None:
    dialog = SettingsDialog()
    dialog.show()
    QTest.qWait(10)

    dialog._select_page(2)

    assert dialog._tabs.currentIndex() == 2
    assert dialog._nav_buttons[2].isChecked()
    assert dialog._page_title.text() == dialog._tabs.tabText(2)
    assert dialog._tabs.is_transition_active
    assert dialog._tabs._transition_target is dialog._page_title.parentWidget()
    dialog._tabs.finish_transition()
    dialog.close()
