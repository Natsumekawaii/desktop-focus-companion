"""UI-independent focus timer domain package."""

from app.focus_mode import (
    MAX_TARGET_DURATION_SECONDS,
    FocusMode,
    InvalidTargetDurationError,
    validate_target_duration,
)
from app.study_mode import StudyMode
from app.timer.active_session_store import (
    ActiveSessionCheckpoint,
    ActiveSessionStore,
    ActiveSessionStoreError,
)
from app.timer.clock import Clock, SystemClock
from app.timer.focus_session_manager import (
    FocusSessionManager,
    FocusSessionManagerError,
    FocusSessionPersistenceError,
    FocusSessionTooShortError,
    PendingFocusSessionError,
)
from app.timer.focus_timer import FocusTimer
from app.timer.formatting import (
    format_compact_duration,
    format_duration,
    format_remaining_duration,
    format_stopwatch_clock,
)
from app.timer.models import FocusTimerResult, StudyTimerResult
from app.timer.session_manager import (
    PendingSessionError,
    SessionManager,
    SessionManagerError,
    SessionPersistenceError,
)
from app.timer.study_timer import (
    ClockWentBackwardsError,
    InvalidTimerStateError,
    StudyTimer,
)
from app.timer.timer_state import TimerState

__all__ = [
    "MAX_TARGET_DURATION_SECONDS",
    "ActiveSessionCheckpoint",
    "ActiveSessionStore",
    "ActiveSessionStoreError",
    "Clock",
    "ClockWentBackwardsError",
    "FocusMode",
    "FocusSessionManager",
    "FocusSessionManagerError",
    "FocusSessionPersistenceError",
    "FocusSessionTooShortError",
    "FocusTimer",
    "FocusTimerResult",
    "InvalidTargetDurationError",
    "InvalidTimerStateError",
    "PendingFocusSessionError",
    "PendingSessionError",
    "SessionManager",
    "SessionManagerError",
    "SessionPersistenceError",
    "StudyMode",
    "StudyTimer",
    "StudyTimerResult",
    "SystemClock",
    "TimerState",
    "format_compact_duration",
    "format_duration",
    "format_remaining_duration",
    "format_stopwatch_clock",
    "validate_target_duration",
]
