"""Tests for the UI-only countdown that precedes a real Focus Session."""

from PySide6.QtTest import QSignalSpy, QTest

from app.ui.pre_focus_countdown import PreFocusCountdownWidget


def test_pre_focus_countdown_completes_once_and_rejects_duplicate_start(
    qt_application,
) -> None:
    widget = PreFocusCountdownWidget(phase_duration_ms=20)
    completed = QSignalSpy(widget.completed)

    assert widget.start()
    assert not widget.start()
    assert widget.is_active
    assert completed.wait(300)

    assert completed.count() == 1
    assert not widget.is_active
    assert widget.current_number == 1
    widget.close()


def test_pre_focus_countdown_cancel_never_completes(qt_application) -> None:
    widget = PreFocusCountdownWidget(phase_duration_ms=80)
    completed = QSignalSpy(widget.completed)
    cancelled = QSignalSpy(widget.cancelled)

    assert widget.start()
    QTest.qWait(30)
    assert widget.cancel()
    QTest.qWait(300)

    assert cancelled.count() == 1
    assert completed.count() == 0
    assert not widget.is_active
    assert widget.current_number == 3
    widget.close()
