"""Application service connecting StudyTimer results to session storage."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from app.data.models import StudySession, Subject
from app.data.session_repository import SessionRepository
from app.data.subject_repository import SubjectRepository
from app.i18n import tr
from app.study_mode import StudyMode
from app.timer.active_session_store import (
    ActiveSessionCheckpoint,
    ActiveSessionStore,
    ActiveSessionStoreError,
)
from app.timer.models import StudyTimerResult
from app.timer.study_timer import StudyTimer
from app.timer.timer_state import TimerState

logger = logging.getLogger(__name__)


class SessionManagerError(RuntimeError):
    """Base error for study session workflow failures."""


class PendingSessionError(SessionManagerError):
    """Raised when an unsaved finished result must be handled first."""


class SessionPersistenceError(SessionManagerError):
    """Raised when a finished timer result could not be persisted."""


class SessionManager:
    """Coordinate subject selection, timer state, and durable Finish behavior."""

    def __init__(
        self,
        timer: StudyTimer,
        subject_repository: SubjectRepository,
        session_repository: SessionRepository,
        active_session_store: ActiveSessionStore | None = None,
    ) -> None:
        self._timer = timer
        self._subject_repository = subject_repository
        self._session_repository = session_repository
        self._active_subject: Subject | None = None
        self._pending_result: StudyTimerResult | None = None
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
    def study_mode(self) -> StudyMode:
        return self._timer.study_mode

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
    def active_subject(self) -> Subject | None:
        return self._active_subject

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
        subject_id: int,
        study_mode: StudyMode = StudyMode.STOPWATCH,
        target_duration_seconds: float | None = None,
    ) -> None:
        """Start a session for an active subject."""
        if self._pending_result is not None:
            raise PendingSessionError(tr("error.previous_session_pending"))
        if self._recovery_checkpoint is not None:
            raise PendingSessionError(tr("error.recovery_pending"))
        subject = self._subject_repository.get(subject_id, include_archived=False)
        self._timer.start(study_mode, target_duration_seconds)
        self._active_subject = subject
        self._recovery_token = uuid4().hex
        self.checkpoint()

    def pause(self) -> None:
        self._timer.pause()
        self.checkpoint()

    def resume(self) -> None:
        self._timer.resume()
        self.checkpoint()

    def finish(self) -> StudySession:
        """Finish the timer and persist its result exactly once."""
        if self._active_subject is None:
            raise SessionManagerError(tr("error.timer_no_subject"))
        result = self._timer.finish()
        self._pending_result = result
        self._write_checkpoint("PENDING", result.end_time)
        return self.retry_pending_save()

    def retry_pending_save(self) -> StudySession:
        """Retry a failed persistence without rerunning or losing timer data."""
        if self._pending_result is None or self._active_subject is None:
            raise PendingSessionError(tr("error.no_pending_session"))
        try:
            session = self._session_repository.create(
                subject=self._active_subject,
                start_time=self._pending_result.start_time,
                end_time=self._pending_result.end_time,
                duration_seconds=self._pending_result.duration_seconds,
                recovery_token=self._recovery_token,
                study_mode=self._pending_result.study_mode,
                target_duration_seconds=self._pending_result.target_duration_seconds,
            )
        except Exception as error:
            raise SessionPersistenceError(
                tr("error.session_save")
            ) from error
        self._pending_result = None
        self._active_subject = None
        self._recovery_token = None
        self._clear_checkpoint()
        return session

    def checkpoint(self) -> None:
        """Persist current elapsed time without treating crash downtime as study."""
        if self._timer.current_state is TimerState.IDLE or self._active_subject is None:
            return
        self._write_checkpoint(self._timer.current_state.name)

    def recover_active_session(self) -> StudySession | None:
        """Restore active work as paused, or idempotently save a pending result."""
        checkpoint = self._recovery_checkpoint
        if checkpoint is None:
            raise SessionManagerError(tr("error.no_recovery"))
        subject = self._subject_repository.get(
            checkpoint.focus_item_id, include_archived=True
        )
        self._active_subject = subject
        self._recovery_token = checkpoint.recovery_token
        self._recovery_checkpoint = None
        if checkpoint.timer_state == "PENDING":
            if checkpoint.end_time is None:
                raise SessionManagerError(tr("error.recovery_incomplete"))
            self._pending_result = StudyTimerResult(
                start_time=checkpoint.start_time,
                end_time=checkpoint.end_time,
                duration_seconds=checkpoint.accumulated_seconds,
                mode=StudyMode(checkpoint.mode),
                target_duration_seconds=checkpoint.target_duration_seconds,
            )
            return self.retry_pending_save()
        self._timer.restore_paused(
            checkpoint.start_time,
            checkpoint.accumulated_seconds,
            StudyMode(checkpoint.mode),
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
        if self._active_session_store is None or self._active_subject is None:
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
                    focus_item_id=self._active_subject.id,
                    focus_item_name=self._active_subject.name,
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
                        self._pending_result.study_mode.value
                        if self._pending_result is not None
                        else self._timer.study_mode.value
                    ),
                    target_duration_seconds=(
                        self._pending_result.target_duration_seconds
                        if self._pending_result is not None
                        else self._timer.target_duration_seconds
                    ),
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
