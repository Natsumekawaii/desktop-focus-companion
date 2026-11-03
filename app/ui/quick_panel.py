"""Compact focus launcher opened from the desktop companion."""

from __future__ import annotations

from app.ui.components import CircularTimerWidget, DurationPicker
from app.ui.focus_item_selector import FocusItemSelector
from app.ui.focus_panel_motion import SmoothProgressBar
from app.ui.pre_focus_countdown import PreFocusCountdownWidget
from app.ui.rounded_selector import SelectorDensity

# Compatibility exports for existing integrations and focused UI tests.
__all__ = ["CircularTimerWidget", "DurationPicker", "FocusItemSelector", "FocusPanel", "PreFocusCountdownWidget", "SelectorDensity", "SmoothProgressBar"]

from dataclasses import dataclass

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, Signal
from PySide6.QtGui import (
    QCloseEvent,
    QFont,
    QGuiApplication,
    QHideEvent,
    QKeyEvent,
    QMouseEvent,
    QStandardItemModel,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QWidget,
)

from app.data.models import FocusItem
from app.focus_mode import (
    FocusMode,
    InvalidTargetDurationError,
    validate_target_duration,
)
from app.gamification import GamificationSnapshot
from app.i18n import get_localization, tr
from app.pet.pet_window import PetWindow
from app.timer.formatting import format_compact_duration
from app.timer.timer_state import TimerState
from app.ui.focus_item_selector import (
    _FOCUS_ITEM_COLOR_ROLE,
    _FOCUS_ITEM_KIND_EMPTY,
    _FOCUS_ITEM_KIND_ITEM,
    _FOCUS_ITEM_KIND_MANAGE,
    _FOCUS_ITEM_KIND_ROLE,
    _FOCUS_ITEM_KIND_SEPARATOR,
)
from app.ui.focus_panel_motion import (
    FocusPanelButtonFeedback,
    PanelButtonRole,
)
from app.ui.quick_panel_builders import _FocusPanelBuilders


@dataclass(frozen=True)
class _PendingFocusStart:
    focus_item_id: int
    mode: FocusMode
    target_duration_seconds: float | None
    note: str


class FocusPanel(_FocusPanelBuilders, QDialog):
    """A lightweight focus launcher; persistence stays in its controller."""

    focus_start_requested = Signal(int, object, object, str)
    pause_requested = Signal()
    resume_requested = Signal()
    finish_requested = Signal()
    manage_focus_items_requested = Signal()
    drag_delta_requested = Signal(QPoint)
    drag_finished = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        countdown_phase_duration_ms: int = 1_000,
    ) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setObjectName("quickPanel")
        self.setMinimumWidth(320)
        self.setMaximumWidth(420)
        self.setMinimumHeight(430)
        self.setMaximumHeight(720)
        self.resize(360, 540)
        self._timer_state = TimerState.IDLE
        self._active_focus_item: str | None = None
        self._mode = FocusMode.STOPWATCH
        self._target_duration_seconds: float | None = None
        self._pending_start: _PendingFocusStart | None = None
        self._last_focus_item_id: int | None = None
        self._gamification: GamificationSnapshot | None = None
        self._header_press_global: QPoint | None = None
        self._header_last_global: QPoint | None = None
        self._header_is_dragging = False
        self._build_header()
        self._build_idle_page()
        self._build_active_page()
        self._build_prestart_page(countdown_phase_duration_ms)
        self._build_panel_surface()
        self._install_button_feedback()
        get_localization().language_changed.connect(self.retranslate_ui)
        self.retranslate_ui()
        self.set_timer_state(TimerState.IDLE, None)

    def _install_button_feedback(self) -> None:
        self._button_feedback = {
            self._start_button: FocusPanelButtonFeedback(
                self._start_button, PanelButtonRole.PRIMARY
            ),
            self._pause_button: FocusPanelButtonFeedback(
                self._pause_button, PanelButtonRole.PRIMARY
            ),
            self._resume_button: FocusPanelButtonFeedback(
                self._resume_button, PanelButtonRole.PRIMARY
            ),
            self._finish_button: FocusPanelButtonFeedback(
                self._finish_button, PanelButtonRole.DANGER
            ),
            self._close_button: FocusPanelButtonFeedback(
                self._close_button, PanelButtonRole.ICON
            ),
            self._note_toggle: FocusPanelButtonFeedback(
                self._note_toggle, PanelButtonRole.DISCLOSURE
            ),
            self._stopwatch_radio: FocusPanelButtonFeedback(
                self._stopwatch_radio, PanelButtonRole.SEGMENT
            ),
            self._countdown_radio: FocusPanelButtonFeedback(
                self._countdown_radio, PanelButtonRole.SEGMENT
            ),
        }

    def retranslate_ui(self, _language: str | None = None) -> None:
        self._today_caption.setText(tr("common.today"))
        self._close_button.setToolTip(tr("quick.close_tooltip"))
        self._close_button.setAccessibleName(tr("quick.close_tooltip"))
        self._focus_item_caption.setText(tr("focus.item"))
        self._focus_item_combo.setAccessibleName(tr("focus.item"))
        self._retranslate_focus_item_rows()
        self._refresh_note_toggle_text()
        self._note_input.setPlaceholderText(tr("focus.note_placeholder"))
        self._mode_caption.setText(tr("quick.timing_mode"))
        self._stopwatch_radio.setText(tr("quick.mode.stopwatch"))
        self._countdown_radio.setText(tr("quick.mode.countdown"))
        self._target_caption.setText(tr("quick.target_duration"))
        self._start_button.setText(tr("quick.start"))
        self._pause_button.setText(tr("common.pause"))
        self._resume_button.setText(tr("common.resume"))
        self._finish_button.setText(tr("common.finish"))
        self._minimum_recording_hint.setText(tr("focus.minimum_recording_hint"))
        self._daily_goal_label.setText(tr("focus.daily_goal"))
        self._weekly_goal_label.setText(tr("focus.weekly_goal"))
        self._refresh_state_text()
        self._refresh_mode_text()
        if self._gamification is not None:
            self.set_gamification(self._gamification)
        self._refresh_focus_item_tooltip()

    def set_focus_items(
        self,
        items: list[FocusItem],
        selected_id: int | None = None,
    ) -> None:
        """Show every active item in the repository's stable name order."""

        current_data = self._focus_item_combo.currentData()
        current_id = (
            selected_id
            if selected_id is not None
            else current_data
            if isinstance(current_data, int)
            else self._last_focus_item_id
        )
        blocked = self._focus_item_combo.blockSignals(True)
        self._focus_item_combo.clear()
        for item in items:
            item_index = self._focus_item_combo.count()
            self._focus_item_combo.addItem(item.name, item.id)
            self._set_focus_item_row_kind(item_index, _FOCUS_ITEM_KIND_ITEM)
            self._focus_item_combo.setItemData(
                item_index, item.name, Qt.ItemDataRole.ToolTipRole
            )
            self._focus_item_combo.setItemData(
                item_index, item.color, _FOCUS_ITEM_COLOR_ROLE
            )

        has_items = bool(items)
        if not has_items:
            empty_index = self._focus_item_combo.count()
            self._focus_item_combo.addItem(tr("focus.no_items"), None)
            self._set_focus_item_row_kind(empty_index, _FOCUS_ITEM_KIND_EMPTY)
            model = self._focus_item_combo.model()
            if isinstance(model, QStandardItemModel):
                empty_item = model.item(empty_index)
                if empty_item is not None:
                    empty_item.setEnabled(False)

        separator_index = self._focus_item_combo.count()
        self._focus_item_combo.insertSeparator(separator_index)
        self._set_focus_item_row_kind(
            separator_index,
            _FOCUS_ITEM_KIND_SEPARATOR,
        )
        manage_index = self._focus_item_combo.count()
        self._focus_item_combo.addItem(tr("focus.manage_items"), None)
        self._set_focus_item_row_kind(manage_index, _FOCUS_ITEM_KIND_MANAGE)
        self._focus_item_combo.setItemData(
            manage_index,
            tr("focus.manage_items"),
            Qt.ItemDataRole.AccessibleTextRole,
        )
        model = self._focus_item_combo.model()
        if isinstance(model, QStandardItemModel):
            manage_item = model.item(manage_index)
            if manage_item is not None:
                font = manage_item.font()
                font.setWeight(QFont.Weight.DemiBold)
                manage_item.setFont(font)

        selected_index = -1
        if current_id is not None:
            selected_index = self._focus_item_combo.findData(current_id)
        if selected_index < 0:
            for index in range(self._focus_item_combo.count()):
                if (
                    self._focus_item_combo.itemData(index, _FOCUS_ITEM_KIND_ROLE)
                    == _FOCUS_ITEM_KIND_ITEM
                ):
                    selected_index = index
                    break
        if selected_index < 0:
            for index in range(self._focus_item_combo.count()):
                if (
                    self._focus_item_combo.itemData(index, _FOCUS_ITEM_KIND_ROLE)
                    == _FOCUS_ITEM_KIND_EMPTY
                ):
                    selected_index = index
                    break
        self._focus_item_combo.setCurrentIndex(selected_index)
        selected_data = self._focus_item_combo.currentData()
        self._last_focus_item_id = (
            selected_data if isinstance(selected_data, int) else None
        )
        self._focus_item_combo.blockSignals(blocked)
        self._start_button.setEnabled(has_items)
        self._refresh_focus_item_tooltip()

    def set_default_focus(
        self, mode: FocusMode, target_duration_seconds: int
    ) -> None:
        """Apply persisted defaults to the next fresh Focus Launcher form."""

        self._countdown_radio.setChecked(mode is FocusMode.COUNTDOWN)
        self._stopwatch_radio.setChecked(mode is FocusMode.STOPWATCH)
        target_minutes = max(1, target_duration_seconds // 60)
        self._target_duration_picker.setValue(target_minutes)
        self._update_target_controls_visibility()

    def set_today_total(self, formatted_duration: str) -> None:
        self._today_value.setText(formatted_duration)

    @property
    def today_text(self) -> str:
        return self._today_value.text()

    def set_elapsed(self, formatted_duration: str) -> None:
        self._timer_value.setText(formatted_duration)

    def set_remaining(self, formatted_duration: str) -> None:
        self._remaining_value.setText(formatted_duration)

    def set_timer_progress(
        self, elapsed_seconds: float, remaining_seconds: float | None
    ) -> None:
        """Update the visual ring from controller-provided timer values."""

        if self._mode is not FocusMode.COUNTDOWN or not self._target_duration_seconds:
            return
        progress = elapsed_seconds / self._target_duration_seconds
        self._timer_ring.set_display(
            progress,
            self._remaining_value.text(),
            tr("quick.remaining"),
        )

    def set_minimum_recording_hint_visible(self, visible: bool) -> None:
        self._minimum_recording_hint.setVisible(visible and self._timer_state is not TimerState.IDLE)

    @property
    def elapsed_text(self) -> str:
        return self._timer_value.text()

    @property
    def remaining_text(self) -> str:
        return self._remaining_value.text()

    def set_timer_state(
        self,
        state: TimerState,
        focus_item_name: str | None,
        mode: FocusMode = FocusMode.STOPWATCH,
        target_duration_seconds: float | None = None,
    ) -> None:
        """Show only operations legal for the current timer state."""
        self._timer_state = state
        self._active_focus_item = focus_item_name
        self._mode = mode
        self._target_duration_seconds = target_duration_seconds
        is_idle = state is TimerState.IDLE
        prestart_active = self.is_prestart_active and is_idle
        if not is_idle and self.is_prestart_active:
            self._pending_start = None
            self._prestart_animation.cancel()
            prestart_active = False
        countdown_active = not is_idle and mode is FocusMode.COUNTDOWN
        if not prestart_active:
            self._panel_stack.setCurrentWidget(
                self._idle_page if is_idle else self._active_page
            )
        self._selection_widget.setVisible(is_idle)
        self._start_button.setVisible(is_idle and not prestart_active)
        self._state_label.setVisible(not is_idle)
        self._active_focus_item_label.setVisible(not is_idle)
        self._mode_status_label.setVisible(not is_idle)
        self._target_summary_label.setVisible(countdown_active)
        self._timer_visual_stack.setVisible(not is_idle)
        self._timer_visual_stack.setCurrentWidget(
            self._countdown_visual if countdown_active else self._stopwatch_visual
        )
        self._timer_ring.setVisible(countdown_active)
        self._remaining_value.setVisible(False)
        self._timer_value.setVisible(not is_idle and not countdown_active)
        self._pause_button.setVisible(state is TimerState.FOCUSING)
        self._resume_button.setVisible(state is TimerState.PAUSED)
        self._finish_button.setVisible(not is_idle)
        self._minimum_recording_hint.setVisible(not is_idle)
        self._refresh_state_text()
        self._refresh_mode_text()
        self.set_timer_progress(0.0, target_duration_seconds)

    def set_gamification(self, snapshot: GamificationSnapshot) -> None:
        self._gamification = snapshot
        self._goal_progress.setValue(round(snapshot.goal_progress * 1000))
        self._daily_goal_label.setText(
            tr(
                "focus.daily_goal_value",
                current=format_compact_duration(snapshot.today_seconds),
                goal=format_compact_duration(snapshot.daily_goal_seconds),
            )
        )
        self._weekly_goal_progress.setValue(round(snapshot.weekly_goal_progress * 1000))
        self._weekly_goal_label.setText(
            tr(
                "focus.weekly_goal_value",
                current=format_compact_duration(snapshot.weekly_seconds),
                goal=format_compact_duration(snapshot.weekly_goal_seconds),
            )
        )
        streak_key = "quick.streak.one" if snapshot.streak_days == 1 else "quick.streak.other"
        self._streak_label.setText(tr(streak_key, count=snapshot.streak_days))

    @property
    def is_prestart_active(self) -> bool:
        return self._pending_start is not None or self._prestart_animation.is_active

    def begin_prestart(
        self,
        focus_item_id: int,
        mode: FocusMode,
        target_duration_seconds: float | None,
        note: str = "",
    ) -> bool:
        """Freeze a start request and animate before emitting the real start."""

        if self._timer_state is not TimerState.IDLE or self.is_prestart_active:
            return False
        self._pending_start = _PendingFocusStart(
            focus_item_id=int(focus_item_id),
            mode=mode,
            target_duration_seconds=target_duration_seconds,
            note=note,
        )
        self._panel_stack.setCurrentWidget(self._prestart_page)
        self._selection_widget.setVisible(False)
        self._start_button.setVisible(False)
        if not self._prestart_animation.start():
            self._pending_start = None
            self._panel_stack.setCurrentWidget(self._idle_page)
            return False
        return True

    def cancel_prestart(self) -> bool:
        """Return to Idle without creating a Session or recovery checkpoint."""

        was_prestart = self.is_prestart_active or (
            self._panel_stack.currentWidget() is self._prestart_page
        )
        if not was_prestart:
            return False
        self._pending_start = None
        self._prestart_animation.cancel()
        if self._timer_state is TimerState.IDLE:
            self._panel_stack.setCurrentWidget(self._idle_page)
            self._selection_widget.setVisible(True)
            self._start_button.setVisible(True)
        return True

    def toggle_near(self, pet_window: PetWindow) -> None:
        """Toggle visibility and place the panel next to the pet."""
        if self.isVisible():
            self.hide()
            return
        self.show_near(pet_window)

    def show_near(self, pet_window: PetWindow) -> None:
        """Show and focus the panel next to the pet without toggling it closed."""
        pet_rect = pet_window.frameGeometry()
        screen = QGuiApplication.screenAt(pet_rect.center()) or QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            preferred_height = min(
                540, max(self.minimumHeight(), available.height() - 24)
            )
            self.resize(max(360, self.width()), preferred_height)
            x = pet_rect.right() + 12
            if x + self.width() > available.right():
                x = pet_rect.left() - self.width() - 12
            x = max(available.left(), min(x, available.right() - self.width() + 1))
            y = max(available.top(), min(pet_rect.top(), available.bottom() - self.height() + 1))
            self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()

    def show_error(self, message: str) -> None:
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.warning(self, tr("app.name"), message)

    def hideEvent(self, event: QHideEvent) -> None:
        self.cancel_prestart()
        super().hideEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Closing the panel only hides it; Desktop Focus Companion keeps running."""
        event.ignore()
        self._hide_panel()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape and self.is_prestart_active:
            event.accept()
            self._hide_panel()
            return
        super().keyPressEvent(event)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched not in (self._header_drag_surface, self._title):
            return super().eventFilter(watched, event)
        if event.type() == QEvent.Type.MouseButtonPress and isinstance(
            event, QMouseEvent
        ):
            if event.button() == Qt.MouseButton.LeftButton:
                global_position = event.globalPosition().toPoint()
                self._header_press_global = global_position
                self._header_last_global = global_position
                self._header_is_dragging = False
                self._header_drag_surface.setCursor(Qt.CursorShape.ClosedHandCursor)
                return True
        elif event.type() == QEvent.Type.MouseMove and isinstance(event, QMouseEvent):
            if (
                self._header_press_global is not None
                and event.buttons() & Qt.MouseButton.LeftButton
            ):
                current = event.globalPosition().toPoint()
                if not self._header_is_dragging:
                    if (
                        current - self._header_press_global
                    ).manhattanLength() < QApplication.startDragDistance():
                        return True
                    self._header_is_dragging = True
                previous = self._header_last_global or current
                delta = current - previous
                self._header_last_global = current
                if not delta.isNull():
                    self.move(self.pos() + delta)
                    self.drag_delta_requested.emit(delta)
                return True
        elif (
            event.type() == QEvent.Type.MouseButtonRelease
            and isinstance(event, QMouseEvent)
            and event.button() == Qt.MouseButton.LeftButton
            and self._header_press_global is not None
        ):
            was_dragging = self._header_is_dragging
            self._header_press_global = None
            self._header_last_global = None
            self._header_is_dragging = False
            self._header_drag_surface.setCursor(Qt.CursorShape.OpenHandCursor)
            if was_dragging:
                self.drag_finished.emit()
            return True
        return super().eventFilter(watched, event)

    def _request_start(self) -> None:
        focus_item_id = self._focus_item_combo.currentData()
        if isinstance(focus_item_id, int):
            mode = (
                FocusMode.COUNTDOWN
                if self._countdown_radio.isChecked()
                else FocusMode.STOPWATCH
            )
            try:
                target = self._selected_target_duration(mode)
            except InvalidTargetDurationError as error:
                self.show_error(str(error))
                return
            self.begin_prestart(
                int(focus_item_id), mode, target, self._note_input.text()
            )

    def _complete_prestart(self) -> None:
        pending = self._pending_start
        if pending is None:
            return
        self._pending_start = None
        self.focus_start_requested.emit(
            pending.focus_item_id,
            pending.mode,
            pending.target_duration_seconds,
            pending.note,
        )
        if self._timer_state is TimerState.IDLE:
            self._panel_stack.setCurrentWidget(self._idle_page)
            self._selection_widget.setVisible(True)
            self._start_button.setVisible(True)

    def _hide_panel(self) -> None:
        self.cancel_prestart()
        self.hide()

    def _selected_target_duration(self, mode: FocusMode) -> float | None:
        if mode is FocusMode.STOPWATCH:
            return None
        target_seconds = self._target_duration_picker.value() * 60
        return validate_target_duration(target_seconds)

    def _update_target_controls_visibility(self) -> None:
        countdown = self._countdown_radio.isChecked()
        self._target_controls.setVisible(countdown)

    def _refresh_state_text(self) -> None:
        state_keys = {
            TimerState.IDLE: "state.idle",
            TimerState.FOCUSING: "state.focusing",
            TimerState.PAUSED: "state.paused",
        }
        title_keys = {
            TimerState.IDLE: "quick.start_heading",
            TimerState.FOCUSING: "state.focusing",
            TimerState.PAUSED: "state.paused",
        }
        self._title.setText(tr(title_keys[self._timer_state]))
        self._state_label.setText(tr(state_keys[self._timer_state]))
        self._active_focus_item_label.setText(
            self._active_focus_item or tr("focus.session_fallback")
        )
        self._active_focus_item_label.setToolTip(self._active_focus_item or "")

    def _refresh_mode_text(self) -> None:
        mode_key = (
            "quick.mode.countdown"
            if getattr(self, "_mode", FocusMode.STOPWATCH) is FocusMode.COUNTDOWN
            else "quick.mode.stopwatch"
        )
        self._mode_status_label.setText(tr(mode_key))
        target = getattr(self, "_target_duration_seconds", None)
        self._target_summary_label.setText(
            tr("quick.target_value", duration=format_compact_duration(target))
            if target is not None
            else ""
        )

    def _toggle_note(self, expanded: bool) -> None:
        self._note_input.setVisible(expanded)
        if expanded:
            self._note_input.setFocus(Qt.FocusReason.MouseFocusReason)
        self._refresh_note_toggle_text()

    def _refresh_note_toggle_text(self) -> None:
        marker = "−" if self._note_toggle.isChecked() else "+"
        self._note_toggle.setText(f"{marker}  {tr('focus.note_optional')}")
        self._note_toggle.setAccessibleName(tr("focus.note_optional"))

    def _refresh_focus_item_tooltip(self, _index: int | None = None) -> None:
        index = self._focus_item_combo.currentIndex()
        text = (
            self._focus_item_combo.itemData(index, Qt.ItemDataRole.ToolTipRole)
            if index >= 0
            else ""
        )
        if not isinstance(text, str) or not text:
            text = self._focus_item_combo.itemText(index) if index >= 0 else ""
        self._focus_item_combo.setToolTip(text)

    def _set_focus_item_row_kind(self, index: int, kind: str) -> None:
        self._focus_item_combo.setItemData(index, kind, _FOCUS_ITEM_KIND_ROLE)
        self._focus_item_combo.setItemData(
            index,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            Qt.ItemDataRole.TextAlignmentRole,
        )

    def _on_focus_item_index_changed(self, _index: int) -> None:
        focus_item_id = self._focus_item_combo.currentData()
        if isinstance(focus_item_id, int):
            self._last_focus_item_id = focus_item_id
        self._refresh_focus_item_tooltip()

    def _on_focus_item_activated(self, index: int) -> None:
        if (
            self._focus_item_combo.itemData(index, _FOCUS_ITEM_KIND_ROLE)
            != _FOCUS_ITEM_KIND_MANAGE
        ):
            return
        self._restore_focus_item_selection()
        self.manage_focus_items_requested.emit()

    def _restore_focus_item_selection(self) -> None:
        target_index = (
            self._focus_item_combo.findData(self._last_focus_item_id)
            if self._last_focus_item_id is not None
            else -1
        )
        if target_index < 0:
            for index in range(self._focus_item_combo.count()):
                kind = self._focus_item_combo.itemData(index, _FOCUS_ITEM_KIND_ROLE)
                if kind in {_FOCUS_ITEM_KIND_ITEM, _FOCUS_ITEM_KIND_EMPTY}:
                    target_index = index
                    break
        blocked = self._focus_item_combo.blockSignals(True)
        self._focus_item_combo.setCurrentIndex(target_index)
        self._focus_item_combo.blockSignals(blocked)
        self._refresh_focus_item_tooltip()

    def _retranslate_focus_item_rows(self) -> None:
        translations = {
            _FOCUS_ITEM_KIND_EMPTY: "focus.no_items",
            _FOCUS_ITEM_KIND_MANAGE: "focus.manage_items",
        }
        for index in range(self._focus_item_combo.count()):
            kind = self._focus_item_combo.itemData(index, _FOCUS_ITEM_KIND_ROLE)
            key = translations.get(kind)
            if key is None:
                continue
            text = tr(key)
            self._focus_item_combo.setItemText(index, text)
            if kind == _FOCUS_ITEM_KIND_MANAGE:
                self._focus_item_combo.setItemData(
                    index, text, Qt.ItemDataRole.AccessibleTextRole
                )

# V1 import compatibility while the public name is FocusPanel.
__all__ = ["FocusPanel"]
