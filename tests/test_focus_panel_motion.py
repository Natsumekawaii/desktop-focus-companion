"""Focused tests for the restrained motion used by the Focus Panel."""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest

from app.core.theme import COLOR_THEMES, get_theme_manager
from app.ui.components import CircularTimerWidget
from app.ui.focus_panel_motion import SmoothProgressBar
from app.ui.quick_panel import FocusPanel


def test_focus_panel_button_hover_animates_without_moving_geometry(
    qt_application,
) -> None:
    panel = FocusPanel()
    panel.resize(360, 680)
    panel.show()
    qt_application.processEvents()
    button = panel._note_toggle
    feedback = panel._button_feedback[button]
    original_geometry = button.geometry()

    qt_application.sendEvent(button, QEvent(QEvent.Type.Enter))
    QTest.qWait(45)

    assert feedback.is_running
    assert 0.0 < feedback.progress < 1.0
    assert button.geometry() == original_geometry

    QTest.qWait(110)
    assert not feedback.is_running
    assert feedback.progress == 1.0
    hover_style = button.styleSheet()

    qt_application.sendEvent(button, QEvent(QEvent.Type.Leave))
    QTest.qWait(45)
    assert feedback.is_running
    assert button.geometry() == original_geometry
    QTest.qWait(120)
    assert button.styleSheet() != hover_style
    assert button.geometry() == original_geometry
    panel.close()


def test_focus_panel_button_motion_never_renders_transparent_black_frames(
    qt_application,
) -> None:
    manager = get_theme_manager()
    original_theme = manager.theme_name
    manager.set_theme("dark")
    panel = FocusPanel()
    panel.resize(360, 680)
    panel.show()
    qt_application.processEvents()
    try:
        buttons = (
            panel._note_toggle,
            panel._close_button,
            panel._finish_button,
            panel._start_button,
            panel._stopwatch_radio,
            panel._countdown_radio,
        )
        for button in buttons:
            feedback = panel._button_feedback[button]
            qt_application.sendEvent(button, QEvent(QEvent.Type.Enter))
            QTest.qWait(45)
            assert "rgba(" not in button.styleSheet()
            assert feedback._current_colors.background.alpha() == 255
            assert feedback._current_colors.border.alpha() == 255

            qt_application.sendEvent(button, QEvent(QEvent.Type.Leave))
            QTest.qWait(125)
            assert "rgba(" not in button.styleSheet()
            assert feedback._current_colors.background.alpha() == 255
            assert feedback._current_colors.border.alpha() == 255

        # This samples the exact late leave frame that previously became an
        # opaque black rectangle when Qt reparsed rgba(..., 1).
        note = panel._note_toggle
        qt_application.sendEvent(note, QEvent(QEvent.Type.Enter))
        QTest.qWait(130)
        qt_application.sendEvent(note, QEvent(QEvent.Type.Leave))
        QTest.qWait(130)
        image = note.grab().toImage()
        sampled = image.pixelColor(max(1, image.width() - 18), image.height() // 2)
        assert sampled != QColor(Qt.GlobalColor.black)
        assert sampled.alpha() == 255
    finally:
        panel.close()
        manager.set_theme(original_theme)


def test_focus_panel_button_motion_stays_opaque_during_rapid_reversal_and_press(
    qt_application,
) -> None:
    panel = FocusPanel()
    panel.resize(360, 680)
    panel.show()
    qt_application.processEvents()
    button = panel._note_toggle
    feedback = panel._button_feedback[button]

    qt_application.sendEvent(button, QEvent(QEvent.Type.Enter))
    QTest.qWait(25)
    qt_application.sendEvent(button, QEvent(QEvent.Type.Leave))
    QTest.qWait(25)
    qt_application.sendEvent(button, QEvent(QEvent.Type.Enter))
    QTest.qWait(25)
    assert feedback._current_colors.background.alpha() == 255

    QTest.mousePress(button, Qt.MouseButton.LeftButton)
    assert feedback._current_colors.background.alpha() == 255
    assert "rgba(" not in button.styleSheet()
    QTest.mouseRelease(button, Qt.MouseButton.LeftButton)
    panel.close()


def test_focus_panel_button_feedback_covers_roles_and_respects_disabled_state(
    qt_application,
) -> None:
    panel = FocusPanel()
    expected_buttons = {
        panel._start_button,
        panel._pause_button,
        panel._resume_button,
        panel._finish_button,
        panel._close_button,
        panel._note_toggle,
        panel._stopwatch_radio,
        panel._countdown_radio,
    }
    assert set(panel._button_feedback) == expected_buttons

    panel._start_button.setEnabled(False)
    feedback = panel._button_feedback[panel._start_button]
    qt_application.sendEvent(panel._start_button, QEvent(QEvent.Type.Enter))
    qt_application.processEvents()
    assert not feedback.is_running
    assert feedback.progress == 1.0
    panel.close()


def test_smooth_progress_bar_interpolates_and_retargets(qt_application) -> None:
    progress = SmoothProgressBar(duration_ms=200)
    progress.setRange(0, 1000)
    progress.setValue(0)
    progress.resize(240, 10)
    progress.show()
    qt_application.processEvents()
    original_geometry = progress.geometry()

    progress.setValue(1000)
    QTest.qWait(55)
    assert progress.is_animating
    assert 0.0 < progress.visual_value < 1000.0
    assert progress.target_value == 1000
    assert progress.geometry() == original_geometry

    progress.setValue(400)
    assert progress.target_value == 400
    QTest.qWait(220)
    assert not progress.is_animating
    assert progress.value() == 400
    assert progress.visual_value == 400.0
    progress.close()


def test_countdown_ring_smooths_visual_progress_but_keeps_true_value(
    qt_application,
) -> None:
    ring = CircularTimerWidget()
    ring.show()
    qt_application.processEvents()
    ring.set_display(0.0, "25:00", "Remaining")
    ring.set_display(0.8, "20:00", "Remaining")
    QTest.qWait(55)

    assert ring.progress == 0.8
    assert ring.is_progress_animating
    assert 0.0 < ring.display_progress < 0.8
    assert ring._primary_text == "20:00"

    ring.set_display(0.9, "18:00", "Remaining")
    QTest.qWait(200)
    assert not ring.is_progress_animating
    assert ring.progress == ring.display_progress == 0.9

    ring.set_display(1.0, "0:00", "Remaining")
    assert not ring.is_progress_animating
    assert ring.progress == ring.display_progress == 1.0
    ring.close()


def test_focus_panel_motion_recolors_for_every_theme(qt_application) -> None:
    manager = get_theme_manager()
    original_theme = manager.theme_name
    panel = FocusPanel()
    panel.show()
    qt_application.processEvents()
    try:
        styles: set[str] = set()
        for theme_name in COLOR_THEMES:
            manager.set_theme(theme_name)
            qt_application.processEvents()
            styles.add(panel._start_button.styleSheet())
            assert panel._button_feedback[panel._start_button].progress == 1.0
            for button, feedback in panel._button_feedback.items():
                assert "rgba(" not in button.styleSheet()
                assert feedback._current_colors.background.alpha() == 255
                assert feedback._current_colors.border.alpha() == 255
            qt_application.sendEvent(panel._note_toggle, QEvent(QEvent.Type.Enter))
            QTest.qWait(45)
            assert "rgba(" not in panel._note_toggle.styleSheet()
            qt_application.sendEvent(panel._note_toggle, QEvent(QEvent.Type.Leave))
            QTest.qWait(45)
            assert "rgba(" not in panel._note_toggle.styleSheet()
        assert len(styles) == len(COLOR_THEMES)
    finally:
        panel.close()
        manager.set_theme(original_theme)
