"""Controller for the desktop-companion Focus Launcher."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QObject, QPoint, QRect, QTimer, Signal
from PySide6.QtGui import QGuiApplication

from app.data.focus_item_repository import (
    DEFAULT_FOCUS_COLOR,
    FocusItemError,
    FocusItemRepository,
)
from app.data.focus_session_repository import FocusSessionRepository
from app.data.models import FocusSession
from app.focus_mode import FocusMode, InvalidTargetDurationError
from app.i18n import get_localization, tr
from app.pet.pet_window import PetWindow
from app.statistics import StatisticsPeriod, StatisticsService
from app.timer.focus_session_manager import (
    FocusSessionManager,
    FocusSessionManagerError,
    PendingFocusSessionError,
)
from app.timer.focus_timer import InvalidTimerStateError
from app.timer.formatting import (
    format_compact_duration,
    format_duration,
    format_remaining_duration,
    format_stopwatch_clock,
)
from app.timer.timer_state import TimerState
from app.ui.message_boxes import ask_confirmation
from app.ui.quick_panel import FocusPanel
from app.ui.subject_dialog import FocusItemDialog


class FocusPanelController(QObject):
    """Translate Focus Launcher intents into domain and repository operations."""

    timer_state_changed = Signal(object)
    elapsed_changed = Signal(float)
    session_finished = Signal(object)
    focus_items_changed = Signal()

    def __init__(
        self,
        panel: FocusPanel,
        focus_item_dialog: FocusItemDialog,
        pet_window: PetWindow,
        session_manager: FocusSessionManager,
        focus_item_repository: FocusItemRepository,
        statistics_service: StatisticsService,
        focus_session_repository: FocusSessionRepository,
    ) -> None:
        super().__init__()
        self._panel = panel
        self._focus_item_dialog = focus_item_dialog
        self._pet_window = pet_window
        self._session_manager = session_manager
        self._focus_item_repository = focus_item_repository
        self._focus_session_repository = focus_session_repository
        self._statistics = statistics_service
        self._auto_finish_in_progress = False
        self._pair_offset: QPoint | None = None

        self._display_timer = QTimer(self)
        self._display_timer.setInterval(250)
        self._display_timer.timeout.connect(self._refresh_elapsed)
        self._checkpoint_timer = QTimer(self)
        self._checkpoint_timer.setInterval(30_000)
        self._checkpoint_timer.timeout.connect(self._session_manager.checkpoint)

        panel.focus_start_requested.connect(self.start_session)
        panel.pause_requested.connect(self.pause_session)
        panel.resume_requested.connect(self.resume_session)
        panel.finish_requested.connect(self.finish_session)
        panel.manage_focus_items_requested.connect(self.show_focus_items)
        panel.drag_delta_requested.connect(self._on_panel_dragged)
        panel.drag_finished.connect(self._on_panel_drag_finished)
        pet_window.drag_moved.connect(self._on_pet_dragged)
        focus_item_dialog.create_focus_item_requested.connect(self.create_focus_item)
        focus_item_dialog.rename_requested.connect(self.rename_focus_item)
        focus_item_dialog.delete_requested.connect(self.delete_focus_item)
        get_localization().language_changed.connect(self._on_language_changed)

        self.refresh_focus_items()
        self._refresh_today()
        self._sync_state()

    def toggle_panel(self) -> None:
        if self._panel.isVisible():
            self._panel.hide()
            return
        self.refresh_focus_items()
        self._refresh_today()
        self._sync_state()
        self._panel.show_near(self._pet_window)
        if self._panel.isVisible():
            self._capture_pair_offset()

    def show_panel(self) -> None:
        """Show the controls predictably for an application-level action."""
        self.refresh_focus_items()
        self._refresh_today()
        self._sync_state()
        self._panel.show_near(self._pet_window)
        self._capture_pair_offset()

    def refresh_summary(self) -> None:
        """Refresh Focus Item choices and today's total after external data edits."""
        self.refresh_focus_items()
        self._refresh_today()

    def start_session(
        self,
        focus_item_id: int,
        mode: FocusMode = FocusMode.STOPWATCH,
        target_duration_seconds: float | None = None,
        note: str = "",
    ) -> None:
        try:
            if self._session_manager.has_pending_session:
                self._session_manager.retry_pending_save()
            self._session_manager.start(
                focus_item_id, mode, target_duration_seconds, note
            )
        except (
            FocusItemError,
            FocusSessionManagerError,
            InvalidTimerStateError,
            InvalidTargetDurationError,
        ) as error:
            self._panel.show_error(str(error))
            return
        self._display_timer.start()
        self._checkpoint_timer.start()
        self._sync_state()

    def pause_session(self) -> None:
        try:
            self._session_manager.pause()
        except InvalidTimerStateError as error:
            self._panel.show_error(str(error))
            return
        self._display_timer.stop()
        self._checkpoint_timer.stop()
        self._refresh_elapsed()
        self._sync_state()

    def resume_session(self) -> None:
        try:
            self._session_manager.resume()
        except InvalidTimerStateError as error:
            self._panel.show_error(str(error))
            return
        self._display_timer.start()
        self._checkpoint_timer.start()
        self._sync_state()

    def finish_session(self) -> FocusSession | None:
        """Finish and save; return None while a recoverable error remains."""
        if (
            self._session_manager.current_state is not TimerState.IDLE
            and self._session_manager.elapsed_seconds < 60
        ):
            if not ask_confirmation(
                self._panel,
                tr("focus.short_session_title"),
                tr("focus.short_session_confirm"),
                accept_key="common.discard",
                destructive=True,
            ):
                return None
            try:
                self._session_manager.discard_active_session()
            except (InvalidTimerStateError, FocusSessionManagerError) as error:
                self._panel.show_error(str(error))
                return None
            self._display_timer.stop()
            self._checkpoint_timer.stop()
            self._sync_state()
            self._refresh_today()
            return None
        try:
            session = self._session_manager.finish()
        except (
            InvalidTimerStateError,
            FocusSessionManagerError,
        ) as error:
            self._panel.show_error(str(error))
            self._display_timer.stop()
            self._sync_state()
            return None
        self._after_session_saved(session)
        return session

    def recover_session(self) -> FocusSession | None:
        """Restore an interrupted timer as paused or save its pending result."""
        try:
            session = self._session_manager.recover_active_session()
        except (
            FocusItemError,
            FocusSessionManagerError,
            ValueError,
        ) as error:
            self._panel.show_error(str(error))
            return None
        self._checkpoint_timer.stop()
        if session is not None:
            self._after_session_saved(session)
        else:
            self._sync_state()
            if not self._panel.isVisible():
                self.toggle_panel()
        return session

    def discard_recovery(self) -> None:
        self._session_manager.discard_recovery()

    def retry_pending_save(self) -> FocusSession | None:
        try:
            session = self._session_manager.retry_pending_save()
        except (
            PendingFocusSessionError,
            FocusSessionManagerError,
        ) as error:
            self._panel.show_error(str(error))
            return None
        self._after_session_saved(session)
        return session

    def show_focus_items(self) -> None:
        self._focus_item_dialog.set_focus_items(self._focus_item_repository.list_active())
        self._focus_item_dialog.show()
        self._focus_item_dialog.raise_()
        self._focus_item_dialog.activateWindow()

    def create_focus_item(self, name: str, color: str = DEFAULT_FOCUS_COLOR) -> None:
        try:
            item = self._focus_item_repository.create(name, color)
        except FocusItemError as error:
            self._panel.show_error(str(error))
            return
        self.refresh_focus_items(item.id)
        self.focus_items_changed.emit()

    def rename_focus_item(self, focus_item_id: int, name: str) -> None:
        try:
            item = self._focus_item_repository.rename(focus_item_id, name)
        except FocusItemError as error:
            self._panel.show_error(str(error))
            return
        self.refresh_focus_items(item.id)
        self.focus_items_changed.emit()

    def delete_focus_item(self, focus_item_id: int) -> None:
        active = self._session_manager.active_focus_item
        checkpoint = self._session_manager.recovery_checkpoint
        if (active is not None and active.id == focus_item_id) or (
            checkpoint is not None and checkpoint.focus_item_id == focus_item_id
        ):
            self._panel.show_error(tr("error.focus_item_active_delete"))
            return
        try:
            item = self._focus_item_repository.get(focus_item_id)
            impact = self._focus_item_repository.deletion_impact(focus_item_id)
        except FocusItemError as error:
            self._panel.show_error(str(error))
            return
        if not ask_confirmation(
            self._focus_item_dialog,
            tr("focus_items.delete_title"),
            tr(
                "focus_items.delete_confirm_with_history",
                name=item.name,
                count=impact.session_count,
                duration=format_compact_duration(impact.total_seconds),
            ),
            destructive=True,
        ):
            return
        try:
            self._focus_item_repository.delete_with_history(focus_item_id)
        except FocusItemError as error:
            self._panel.show_error(str(error))
            return
        self.refresh_focus_items()
        self.focus_items_changed.emit()

    def refresh_focus_items(self, selected_id: int | None = None) -> None:
        self._panel.set_focus_items(
            self._focus_item_repository.list_active(), selected_id
        )
        self._focus_item_dialog.set_focus_items(self._focus_item_repository.list_active())
        totals = {
            total.focus_item_id: total.duration_seconds
            for total in self._statistics.focus_item_totals(StatisticsPeriod.ALL_TIME)
        }
        last_records: dict[int, datetime] = {}
        for session in self._focus_session_repository.list_sessions():
            last_records.setdefault(
                session.focus_item_id,
                session.start_time.astimezone(self._statistics.local_timezone),
            )
        self._focus_item_dialog.set_focus_item_metrics(totals, last_records)
    def _after_session_saved(self, session: FocusSession) -> None:
        self._display_timer.stop()
        self._checkpoint_timer.stop()
        self._sync_state()
        self._refresh_today()
        self.refresh_focus_items(session.focus_item_id)
        self.session_finished.emit(session)

    def _sync_state(self) -> None:
        state = self._session_manager.current_state
        item = self._session_manager.active_focus_item
        self._panel.set_timer_state(
            state,
            item.name if item else None,
            self._session_manager.mode,
            self._session_manager.target_duration_seconds,
        )
        self._refresh_elapsed()
        self.timer_state_changed.emit(state)

    def _refresh_elapsed(self) -> None:
        elapsed = self._session_manager.elapsed_seconds
        formatted_elapsed = (
            format_stopwatch_clock(elapsed)
            if self._session_manager.mode is FocusMode.STOPWATCH
            else format_duration(elapsed)
        )
        self._panel.set_elapsed(formatted_elapsed)
        self._panel.set_minimum_recording_hint_visible(elapsed < 60)
        remaining = self._session_manager.remaining_seconds
        if remaining is not None:
            self._panel.set_remaining(format_remaining_duration(remaining))
        self._panel.set_timer_progress(elapsed, remaining)
        self.elapsed_changed.emit(elapsed)
        if (
            self._session_manager.current_state is not TimerState.IDLE
            and self._session_manager.has_reached_target
            and not self._auto_finish_in_progress
        ):
            self._auto_finish_in_progress = True
            try:
                self.finish_session()
            finally:
                self._auto_finish_in_progress = False

    def _refresh_today(self) -> None:
        self._panel.set_today_total(format_compact_duration(self._statistics.today_total()))

    def _on_language_changed(self, _language: str) -> None:
        self.refresh_focus_items()
        self._refresh_today()
        self._refresh_elapsed()
        self._sync_state()

    def _capture_pair_offset(self) -> None:
        self._pair_offset = self._panel.pos() - self._pet_window.pos()

    def _on_pet_dragged(self, x: int, y: int) -> None:
        if not self._panel.isVisible():
            return
        if self._pair_offset is None:
            self._capture_pair_offset()
        offset = self._pair_offset or QPoint()
        self._move_linked_pair(QPoint(x, y), QPoint(x, y) + offset)

    def _on_panel_dragged(self, delta: QPoint) -> None:
        if not self._panel.isVisible():
            return
        self._move_linked_pair(
            self._pet_window.pos() + delta,
            self._panel.pos(),
        )

    def _on_panel_drag_finished(self) -> None:
        if self._panel.isVisible():
            self._pet_window.commit_position()

    def _move_linked_pair(self, pet_position: QPoint, panel_position: QPoint) -> None:
        """Move and clamp the two top-level windows as one compound rectangle."""

        pet_rect = QRect(pet_position, self._pet_window.size())
        panel_rect = QRect(panel_position, self._panel.size())
        pair_rect = pet_rect.united(panel_rect)
        screen = (
            QGuiApplication.screenAt(pair_rect.center())
            or QGuiApplication.screenAt(pet_rect.center())
            or QGuiApplication.primaryScreen()
        )
        correction = QPoint()
        if screen is not None:
            available = screen.availableGeometry()
            if pair_rect.width() <= available.width():
                if pair_rect.left() < available.left():
                    correction.setX(available.left() - pair_rect.left())
                elif pair_rect.right() > available.right():
                    correction.setX(available.right() - pair_rect.right())
            else:
                correction.setX(available.left() - pair_rect.left())
            if pair_rect.height() <= available.height():
                if pair_rect.top() < available.top():
                    correction.setY(available.top() - pair_rect.top())
                elif pair_rect.bottom() > available.bottom():
                    correction.setY(available.bottom() - pair_rect.bottom())
            else:
                correction.setY(available.top() - pair_rect.top())
        final_pet = pet_position + correction
        final_panel = panel_position + correction
        self._pet_window.move(final_pet)
        self._panel.move(final_panel)
        self._pair_offset = final_panel - final_pet


__all__ = ["FocusPanelController"]
