"""Integration tests for the canonical Focus Panel workflow."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtTest import QSignalSpy, QTest

from app.data.database import Database
from app.data.focus_item_repository import FocusItemRepository
from app.data.focus_session_repository import FocusSessionRepository
from app.focus_mode import FocusMode
from app.gamification import GamificationSnapshot, LevelProgress
from app.pet.pet_window import PetWindow
from app.statistics import StatisticsService
from app.timer import FocusSessionManager, FocusTimer, TimerState
from app.ui import quick_panel_controller as quick_panel_controller_module
from app.ui.quick_panel import FocusPanel
from app.ui.quick_panel_controller import FocusPanelController
from app.ui.subject_dialog import FocusItemDialog


@dataclass
class FakeClock:
    monotonic_value: float = 0.0
    wall_value: datetime = datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc)

    def monotonic(self) -> float:
        return self.monotonic_value

    def now(self) -> datetime:
        return self.wall_value

    def advance(self, seconds: float) -> None:
        self.monotonic_value += seconds
        self.wall_value += timedelta(seconds=seconds)


def test_quick_panel_full_flow_saves_and_updates_summary(qt_application, tmp_path: Path) -> None:
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    focus_items = FocusItemRepository(database)
    sessions = FocusSessionRepository(database)
    focus_item = focus_items.create("C++")
    clock = FakeClock()
    manager = FocusSessionManager(FocusTimer(clock), focus_items, sessions)
    pet = PetWindow()
    panel = FocusPanel(pet, countdown_phase_duration_ms=10)
    focus_item_dialog = FocusItemDialog(panel)
    controller = FocusPanelController(
        panel,
        focus_item_dialog,
        pet,
        manager,
        focus_items,
        StatisticsService(sessions, timezone.utc),
        sessions,
    )

    controller.start_session(focus_item.id)
    assert panel.elapsed_text == "00:00:00"
    controller.show_panel()
    qt_application.processEvents()
    assert panel.isVisible()
    controller.toggle_panel()
    qt_application.processEvents()
    assert not panel.isVisible()
    assert manager.current_state is TimerState.FOCUSING
    controller.toggle_panel()
    qt_application.processEvents()
    assert panel.isVisible()
    assert manager.current_state is TimerState.FOCUSING
    clock.advance(30 * 60)
    controller.pause_session()
    assert manager.current_state is TimerState.PAUSED
    assert panel.elapsed_text == "00:30:00"
    clock.advance(15 * 60)
    controller._refresh_elapsed()
    assert panel.elapsed_text == "00:30:00"
    controller.resume_session()
    clock.advance(45 * 60)
    stored = controller.finish_session()

    assert stored is not None
    assert stored.duration_seconds == 75 * 60
    assert stored.mode is FocusMode.STOPWATCH
    assert stored.target_duration_seconds is None
    assert sessions.get(stored.id) == stored
    assert manager.current_state is TimerState.IDLE

    focus_item_dialog.close()
    panel.hide()
    pet.close()


def test_focus_item_changes_refresh_focus_panel(qt_application, tmp_path: Path) -> None:
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    focus_items = FocusItemRepository(database)
    sessions = FocusSessionRepository(database)
    manager = FocusSessionManager(FocusTimer(FakeClock()), focus_items, sessions)
    pet = PetWindow()
    panel = FocusPanel(pet)
    dialog = FocusItemDialog(panel)
    controller = FocusPanelController(
        panel,
        dialog,
        pet,
        manager,
        focus_items,
        StatisticsService(sessions, timezone.utc),
        sessions,
    )

    controller.create_focus_item("Physics")
    created = focus_items.list_active()[0]
    controller.rename_focus_item(created.id, "Physics Lab")

    assert focus_items.get(created.id).name == "Physics Lab"
    pet.close()


def test_quick_panel_emits_direct_countdown_target(qt_application, tmp_path: Path) -> None:
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    focus_items = FocusItemRepository(database)
    focus_item = focus_items.create("Deep Work")
    pet = PetWindow()
    panel = FocusPanel(pet, countdown_phase_duration_ms=10)
    panel.set_focus_items([focus_item])
    start_spy = QSignalSpy(panel.focus_start_requested)

    panel._countdown_radio.setChecked(True)
    panel._target_duration_picker.setValue(90)
    panel._start_button.click()

    assert start_spy.count() == 0
    assert panel.is_prestart_active
    QTest.qWait(80)
    assert start_spy.count() == 1
    assert start_spy.at(0) == [focus_item.id, FocusMode.COUNTDOWN, 90 * 60, ""]
    panel.hide()
    pet.close()


def test_daily_and_weekly_goal_values_are_labels_above_compact_bars(
    qt_application,
) -> None:
    panel = FocusPanel()
    snapshot = GamificationSnapshot(
        today_seconds=3600,
        daily_goal_seconds=7200,
        goal_progress=0.5,
        goal_completed=False,
        weekly_seconds=3 * 3600,
        weekly_goal_seconds=8 * 3600,
        weekly_goal_progress=0.375,
        weekly_goal_completed=False,
        streak_days=2,
        streak_minimum_seconds=1800,
        level=LevelProgress(1, 0, 0, 300),
    )

    panel.set_gamification(snapshot)

    assert "1h" in panel._daily_goal_label.text()
    assert "2h" in panel._daily_goal_label.text()
    assert "3h" in panel._weekly_goal_label.text()
    assert "8h" in panel._weekly_goal_label.text()
    assert panel._goal_progress.value() == 500
    assert panel._weekly_goal_progress.value() == 375
    assert not panel._goal_progress.isTextVisible()
    assert not panel._weekly_goal_progress.isTextVisible()
    assert panel._goal_progress.height() == panel._weekly_goal_progress.height() == 10
    panel.close()


def test_countdown_reaching_zero_uses_unified_finish_and_persists_metadata(
    qt_application, tmp_path: Path
) -> None:
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    focus_items = FocusItemRepository(database)
    sessions = FocusSessionRepository(database)
    focus_item = focus_items.create("Countdown")
    clock = FakeClock()
    manager = FocusSessionManager(FocusTimer(clock), focus_items, sessions)
    pet = PetWindow()
    panel = FocusPanel(pet)
    dialog = FocusItemDialog(panel)
    controller = FocusPanelController(
        panel,
        dialog,
        pet,
        manager,
        focus_items,
        StatisticsService(sessions, timezone.utc),
        sessions,
    )
    finished_spy = QSignalSpy(controller.session_finished)

    controller.start_session(focus_item.id, FocusMode.COUNTDOWN, 60)
    clock.advance(60)
    controller._refresh_elapsed()

    stored = sessions.list_sessions()
    assert manager.current_state is TimerState.IDLE
    assert len(stored) == 1
    assert stored[0].duration_seconds == 60
    assert stored[0].mode is FocusMode.COUNTDOWN
    assert stored[0].target_duration_seconds == 60
    assert finished_spy.count() == 1
    assert panel.remaining_text in {"0 min", "0分钟"}

    dialog.close()
    panel.hide()
    pet.close()


def test_pausing_at_countdown_target_still_auto_finishes(
    qt_application, tmp_path: Path
) -> None:
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    focus_items = FocusItemRepository(database)
    sessions = FocusSessionRepository(database)
    focus_item = focus_items.create("Target Race")
    clock = FakeClock()
    manager = FocusSessionManager(FocusTimer(clock), focus_items, sessions)
    pet = PetWindow()
    panel = FocusPanel(pet)
    dialog = FocusItemDialog(panel)
    controller = FocusPanelController(
        panel,
        dialog,
        pet,
        manager,
        focus_items,
        StatisticsService(sessions, timezone.utc),
        sessions,
    )

    controller.start_session(focus_item.id, FocusMode.COUNTDOWN, 60)
    clock.advance(60)
    controller.pause_session()

    assert manager.current_state is TimerState.IDLE
    assert len(sessions.list_sessions()) == 1
    assert sessions.list_sessions()[0].duration_seconds == 60
    dialog.close()
    panel.hide()
    pet.close()


def test_stopwatch_uses_plain_clock_while_countdown_keeps_timer_ring(
    qt_application,
) -> None:
    panel = FocusPanel()

    panel.set_timer_state(TimerState.FOCUSING, "Writing", FocusMode.STOPWATCH)
    panel.set_elapsed("00:30:00")
    panel.set_timer_progress(1800, None)
    assert not panel._timer_ring.isVisibleTo(panel)
    assert panel._timer_value.isVisibleTo(panel)
    assert panel._timer_value.text() == "00:30:00"
    assert panel._timer_visual_stack.currentWidget() is panel._stopwatch_visual

    panel.set_timer_state(TimerState.FOCUSING, "Writing", FocusMode.COUNTDOWN, 1500)
    panel.set_elapsed("00:05:00")
    panel.set_remaining("20:00")
    panel.set_timer_progress(300, 1200)
    assert panel._timer_ring.progress == 0.2
    assert panel._timer_ring._primary_text == "20:00"
    assert panel._timer_ring.isVisibleTo(panel)
    assert not panel._timer_value.isVisibleTo(panel)
    assert panel._timer_visual_stack.currentWidget() is panel._countdown_visual
    assert panel._active_focus_item_label.text() == "Writing"
    panel.hide()


def test_sub_minute_finish_can_continue_or_discard_without_saving(
    qt_application, tmp_path: Path, monkeypatch
) -> None:
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    focus_items = FocusItemRepository(database)
    sessions = FocusSessionRepository(database)
    focus_item = focus_items.create("Short focus")
    clock = FakeClock()
    manager = FocusSessionManager(FocusTimer(clock), focus_items, sessions)
    pet = PetWindow()
    panel = FocusPanel(pet)
    dialog = FocusItemDialog(panel)
    controller = FocusPanelController(
        panel,
        dialog,
        pet,
        manager,
        focus_items,
        StatisticsService(sessions, timezone.utc),
        sessions,
    )
    controller.start_session(focus_item.id)
    clock.advance(30)
    controller._refresh_elapsed()

    monkeypatch.setattr(
        quick_panel_controller_module, "ask_confirmation", lambda *args, **kwargs: False
    )
    assert controller.finish_session() is None
    assert manager.current_state is TimerState.FOCUSING
    assert sessions.list_sessions() == []
    assert panel.elapsed_text == "00:00:30"

    monkeypatch.setattr(
        quick_panel_controller_module, "ask_confirmation", lambda *args, **kwargs: True
    )
    assert controller.finish_session() is None
    assert manager.current_state is TimerState.IDLE
    assert sessions.list_sessions() == []
    dialog.close()
    panel.hide()
    pet.close()


def test_pet_and_visible_focus_panel_move_as_one_linked_pair(
    qt_application, tmp_path: Path
) -> None:
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    focus_items = FocusItemRepository(database)
    sessions = FocusSessionRepository(database)
    pet = PetWindow()
    pixmap = QPixmap(120, 120)
    pixmap.fill(QColor("#7C5CFC"))
    pet.set_pet_image(pixmap, 80)
    pet.move(220, 180)
    panel = FocusPanel(pet)
    dialog = FocusItemDialog(panel)
    controller = FocusPanelController(
        panel,
        dialog,
        pet,
        FocusSessionManager(FocusTimer(FakeClock()), focus_items, sessions),
        focus_items,
        StatisticsService(sessions, timezone.utc),
        sessions,
    )
    controller.show_panel()
    qt_application.processEvents()
    initial_offset = panel.pos() - pet.pos()

    pet_target = pet.pos() + QPoint(24, 18)
    pet.move(pet_target)
    pet.drag_moved.emit(pet_target.x(), pet_target.y())
    assert panel.pos() - pet.pos() == initial_offset

    pet_before = pet.pos()
    delta = QPoint(-12, 14)
    panel.move(panel.pos() + delta)
    panel.drag_delta_requested.emit(delta)
    assert pet.pos() == pet_before + delta
    assert panel.pos() - pet.pos() == initial_offset

    position_spy = QSignalSpy(pet.position_changed)
    panel.drag_finished.emit()
    assert position_spy.count() == 1
    assert position_spy.at(0) == [pet.x(), pet.y()]

    panel.hide()
    hidden_panel_position = panel.pos()
    independent_target = pet.pos() + QPoint(20, 20)
    pet.move(independent_target)
    pet.drag_moved.emit(independent_target.x(), independent_target.y())
    assert panel.pos() == hidden_panel_position
    dialog.close()
    pet.close()
