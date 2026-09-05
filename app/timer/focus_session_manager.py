"""Application service connecting FocusTimer results to durable focus history."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from app.data.focus_item_repository import FocusItemRepository
from app.data.focus_session_repository import (
    MIN_FOCUS_DURATION_SECONDS,
    FocusSessionRepository,
)
from app.data.models import FocusItem, FocusSession, FocusSessionSource
from app.focus_mode import FocusMode
from app.i18n import tr
from app.timer.active_session_store import (
    ActiveSessionCheckpoint,
    ActiveSessionStore,
    ActiveSessionStoreError,
)
from app.timer.focus_timer import FocusTimer
from app.timer.models import FocusTimerResult
from app.timer.timer_state import TimerState

logger = logging.getLogger(__name__)


class FocusSessionManagerError(RuntimeError):
    """Base error for focus-session workflow failures."""


class PendingFocusSessionError(FocusSessionManagerError):
    """Raised when an unsaved or recoverable focus record must be handled first."""


class FocusSessionPersistenceError(FocusSessionManagerError):
    """Raised when a finished timer result cannot be persisted."""


class FocusSessionTooShortError(FocusSessionManagerError):
    """Raised when an active timer has not completed one focus minute."""


class FocusSessionManager:
    """Coordinate item selection, focus timing, recovery, and exactly-once save."""

    def __init__(
        self,
        timer: FocusTimer,
        focus_item_repository: FocusItemRepository,
        focus_session_repository: FocusSessionRepository,
        active_session_store: ActiveSessionStore | None = None,
    ) -> None:
        self._timer = timer
        self._focus_items = focus_item_repository
        self._focus_sessions = focus_session_repository
        self._active_focus_item: FocusItem | None = None
        self._active_note = ""
        self._pending_result: FocusTimerResult | None = None
        self._active_session_store = active_session_store
        self._recovery_checkpoint = active_session_store.load() if active_session_store else None
        self._recovery_token: str | None = None

    @property
    def current_state(self) -> TimerState:
        return self._timer.current_state

    @property
    def elapsed_seconds(self) -> float:
        return self._timer.elapsed_seconds

    @property
    def mode(self) -> FocusMode:
        return self._timer.mode

    @property
    def target_duration_seconds(self) -> float | None:
        return self._timer.target_duration_seconds

    @property
    def remaining_seconds(self) -> float | None:
        return self._timer.remaining_seconds

    @property
    def has_reached_target(self) -> bool:
        return self._timer.has_reached_target

    @property
    def active_focus_item(self) -> FocusItem | None:
        return self._active_focus_item

    @property
    def active_note(self) -> str:
        return self._active_note

    @property
    def has_pending_session(self) -> bool:
        return self._pending_result is not None

    @property
    def has_recoverable_session(self) -> bool:
        return self._recovery_checkpoint is not None

    @property
    def recovery_checkpoint(self) -> ActiveSessionCheckpoint | None:
        return self._recovery_checkpoint

    def start(
        self,
        focus_item_id: int,
        mode: FocusMode = FocusMode.STOPWATCH,
        target_duration_seconds: float | None = None,
        note: str = "",
    ) -> None:
        if self._pending_result is not None:
            raise PendingFocusSessionError(tr("error.previous_session_pending"))
        if self._recovery_checkpoint is not None:
            raise PendingFocusSessionError(tr("error.recovery_pending"))
        item = self._focus_items.get(focus_item_id, include_archived=False)
        normalized_note = note.strip()
        if len(normalized_note) > 2000:
            raise ValueError(tr("error.focus_note_long"))
        self._timer.start(mode, target_duration_seconds)
        self._active_focus_item = item
        self._active_note = normalized_note
        self._recovery_token = uuid4().hex
        self.checkpoint()

    def pause(self) -> None:
        self._timer.pause()
        self.checkpoint()

    def resume(self) -> None:
        self._timer.resume()
        self.checkpoint()

    def finish(self) -> FocusSession:
        if self._active_focus_item is None:
            raise FocusSessionManagerError(tr("error.timer_no_subject"))
        if self._timer.elapsed_seconds < MIN_FOCUS_DURATION_SECONDS:
            raise FocusSessionTooShortError(tr("error.session_duration_minimum"))
        result = self._timer.finish()
        self._pending_result = _quantize_timer_result(result)
        self._write_checkpoint("PENDING", result.end_time)
        return self.retry_pending_save()

    def discard_active_session(self) -> None:
        """End an active sub-minute timer without creating history."""

        if self._active_focus_item is None:
            raise FocusSessionManagerError(tr("error.timer_no_subject"))
        if self._timer.current_state is not TimerState.IDLE:
            self._timer.finish()
        self._pending_result = None
        self._active_focus_item = None
        self._active_note = ""
        self._recovery_token = None
        self._clear_checkpoint()

    def retry_pending_save(self) -> FocusSession:
        if self._pending_result is None or self._active_focus_item is None:
            raise PendingFocusSessionError(tr("error.no_pending_session"))
        try:
            session = self._focus_sessions.create(
                focus_item=self._active_focus_item,
                start_time=self._pending_result.start_time,
                end_time=self._pending_result.end_time,
                duration_seconds=self._pending_result.duration_seconds,
                recovery_token=self._recovery_token,
                mode=self._pending_result.mode,
                target_duration_seconds=self._pending_result.target_duration_seconds,
                note=self._active_note,
                source=FocusSessionSource.TIMER,
            )
        except Exception as error:
            raise FocusSessionPersistenceError(tr("error.session_save")) from error
        self._pending_result = None
        self._active_focus_item = None
        self._active_note = ""
        self._recovery_token = None
        self._clear_checkpoint()
        return session

    def checkpoint(self) -> None:
        if self._timer.current_state is TimerState.IDLE or self._active_focus_item is None:
            return
        self._write_checkpoint(self._timer.current_state.name)

    def recover_active_session(self) -> FocusSession | None:
        checkpoint = self._recovery_checkpoint
        if checkpoint is None:
            raise FocusSessionManagerError(tr("error.no_recovery"))
        self._active_focus_item = self._focus_items.get(
            checkpoint.focus_item_id, include_archived=True
        )
        self._active_note = checkpoint.note
        self._recovery_token = checkpoint.recovery_token
        self._recovery_checkpoint = None
        mode = FocusMode(checkpoint.mode)
        if checkpoint.timer_state == "PENDING":
            if checkpoint.end_time is None:
                raise FocusSessionManagerError(tr("error.recovery_incomplete"))
            recovered_result = FocusTimerResult(
                start_time=checkpoint.start_time,
                end_time=checkpoint.end_time,
                duration_seconds=checkpoint.accumulated_seconds,
                mode=mode,
                target_duration_seconds=checkpoint.target_duration_seconds,
            )
            if recovered_result.duration_seconds < MIN_FOCUS_DURATION_SECONDS:
                self.discard_active_session()
                return None
            self._pending_result = _quantize_timer_result(recovered_result)
            return self.retry_pending_save()
        self._timer.restore_paused(
            checkpoint.start_time,
            checkpoint.accumulated_seconds,
            mode,
            checkpoint.target_duration_seconds,
        )
        if self._timer.has_reached_target:
            return self.finish()
        self.checkpoint()
        return None

    def discard_recovery(self) -> None:
        self._recovery_checkpoint = None
        self._recovery_token = None
        self._clear_checkpoint()

    def _write_checkpoint(self, timer_state: str, end_time: datetime | None = None) -> None:
        if self._active_session_store is None or self._active_focus_item is None:
            return
        start_time = self._timer.start_time
        if start_time is None and self._pending_result is not None:
            start_time = self._pending_result.start_time
        if start_time is None:
            return
        try:
            self._active_session_store.save(
                ActiveSessionCheckpoint(
                    recovery_token=self._recovery_token or uuid4().hex,
                    focus_item_id=self._active_focus_item.id,
                    focus_item_name=self._active_focus_item.name,
                    start_time=start_time,
                    accumulated_seconds=(
                        self._pending_result.duration_seconds
                        if self._pending_result is not None
                        else self._timer.elapsed_seconds
                    ),
                    timer_state=timer_state,
                    last_checkpoint=datetime.now(timezone.utc),
                    end_time=end_time,
                    mode=(
                        self._pending_result.mode.value
                        if self._pending_result is not None
                        else self._timer.mode.value
                    ),
                    target_duration_seconds=(
                        self._pending_result.target_duration_seconds
                        if self._pending_result is not None
                        else self._timer.target_duration_seconds
                    ),
                    note=self._active_note,
                )
            )
        except ActiveSessionStoreError:
            logger.exception("Active-session checkpoint could not be written")

    def _clear_checkpoint(self) -> None:
        if self._active_session_store is None:
            return
        try:
            self._active_session_store.clear()
        except ActiveSessionStoreError:
            logger.exception("Active-session checkpoint could not be cleared")


def _quantize_timer_result(result: FocusTimerResult) -> FocusTimerResult:
    """Convert a completed timer result to durable whole-minute precision."""

    complete_seconds = float(int(result.duration_seconds // 60) * 60)
    return FocusTimerResult(
        start_time=result.start_time,
        end_time=result.end_time,
        duration_seconds=complete_seconds,
        mode=result.mode,
        target_duration_seconds=result.target_duration_seconds,
    )
