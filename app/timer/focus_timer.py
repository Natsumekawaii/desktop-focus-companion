"""Reliable, UI-independent focus timer state machine."""

from __future__ import annotations

from datetime import datetime

from app.focus_mode import FocusMode, validate_target_duration
from app.i18n import tr
from app.timer.clock import Clock, SystemClock
from app.timer.models import FocusTimerResult
from app.timer.timer_state import TimerState


class InvalidTimerStateError(RuntimeError):
    """Raised when an operation is invalid for the current timer state."""

    def __init__(
        self,
        operation: str,
        current_state: TimerState,
        allowed_states: tuple[TimerState, ...],
    ) -> None:
        allowed = ", ".join(tr(f"state.{state.name.lower()}") for state in allowed_states)
        super().__init__(
            tr(
                "error.timer_invalid_state",
                operation=tr(f"timer.operation.{operation}"),
                state=tr(f"state.{current_state.name.lower()}"),
                allowed=allowed,
            )
        )
        self.operation = operation
        self.current_state = current_state
        self.allowed_states = allowed_states


class ClockWentBackwardsError(RuntimeError):
    """Raised when an injected clock violates the monotonic contract."""


class FocusTimer:
    """Track one focus session with monotonic duration and explicit states."""

    def __init__(self, clock: Clock | None = None) -> None:
        self._clock = clock or SystemClock()
        self._state = TimerState.IDLE
        self._start_time: datetime | None = None
        self._running_since: float | None = None
        self._accumulated_seconds = 0.0
        self._mode = FocusMode.STOPWATCH
        self._target_duration_seconds: float | None = None

    @property
    def current_state(self) -> TimerState:
        return self._state

    @property
    def elapsed_seconds(self) -> float:
        elapsed = self._elapsed_unbounded()
        if self._mode is FocusMode.COUNTDOWN and self._target_duration_seconds is not None:
            return min(elapsed, self._target_duration_seconds)
        return elapsed

    @property
    def start_time(self) -> datetime | None:
        return self._start_time

    @property
    def mode(self) -> FocusMode:
        return self._mode

    @property
    def study_mode(self) -> FocusMode:
        """Compatibility alias for V1 UI code."""

        return self._mode

    @property
    def target_duration_seconds(self) -> float | None:
        return self._target_duration_seconds

    @property
    def remaining_seconds(self) -> float | None:
        if self._mode is not FocusMode.COUNTDOWN:
            return None
        if self._target_duration_seconds is None:
            raise RuntimeError(tr("error.countdown_target_missing"))
        return max(0.0, self._target_duration_seconds - self.elapsed_seconds)

    @property
    def has_reached_target(self) -> bool:
        remaining = self.remaining_seconds
        return remaining is not None and remaining <= 0

    def start(
        self,
        mode: FocusMode = FocusMode.STOPWATCH,
        target_duration_seconds: float | None = None,
    ) -> None:
        self._require_state("start", TimerState.IDLE)
        if not isinstance(mode, FocusMode):
            raise TypeError("mode must be a FocusMode")
        if mode is FocusMode.COUNTDOWN:
            target_duration_seconds = validate_target_duration(target_duration_seconds)
        elif target_duration_seconds is not None:
            raise ValueError(tr("error.stopwatch_target"))
        self._accumulated_seconds = 0.0
        self._start_time = self._clock.now()
        self._running_since = self._clock.monotonic()
        self._mode = mode
        self._target_duration_seconds = target_duration_seconds
        self._state = TimerState.FOCUSING

    def pause(self) -> None:
        self._require_state("pause", TimerState.FOCUSING)
        self._accumulated_seconds += self._current_segment_seconds()
        self._running_since = None
        self._state = TimerState.PAUSED

    def resume(self) -> None:
        self._require_state("resume", TimerState.PAUSED)
        self._running_since = self._clock.monotonic()
        self._state = TimerState.FOCUSING

    def finish(self) -> FocusTimerResult:
        self._require_state("finish", TimerState.FOCUSING, TimerState.PAUSED)
        if self._state is TimerState.FOCUSING:
            self._accumulated_seconds += self._current_segment_seconds()
        if self._start_time is None:
            raise RuntimeError(tr("error.timer_missing_timestamp"))
        result = FocusTimerResult(
            start_time=self._start_time,
            end_time=self._clock.now(),
            duration_seconds=(
                min(self._accumulated_seconds, self._target_duration_seconds)
                if self._mode is FocusMode.COUNTDOWN
                and self._target_duration_seconds is not None
                else self._accumulated_seconds
            ),
            mode=self._mode,
            target_duration_seconds=self._target_duration_seconds,
        )
        self._reset()
        return result

    def restore_paused(
        self,
        start_time: datetime,
        accumulated_seconds: float,
        mode: FocusMode = FocusMode.STOPWATCH,
        target_duration_seconds: float | None = None,
    ) -> None:
        self._require_state("restore", TimerState.IDLE)
        if start_time.tzinfo is None or start_time.utcoffset() is None:
            raise ValueError(tr("error.recovery_timezone"))
        if accumulated_seconds < 0:
            raise ValueError(tr("error.recovery_duration"))
        if mode is FocusMode.COUNTDOWN:
            target_duration_seconds = validate_target_duration(target_duration_seconds)
        elif target_duration_seconds is not None:
            raise ValueError(tr("error.stopwatch_target"))
        self._start_time = start_time
        self._accumulated_seconds = float(accumulated_seconds)
        self._running_since = None
        self._mode = mode
        self._target_duration_seconds = target_duration_seconds
        self._state = TimerState.PAUSED

    def _elapsed_unbounded(self) -> float:
        if self._state is TimerState.FOCUSING:
            return self._accumulated_seconds + self._current_segment_seconds()
        return self._accumulated_seconds

    def _current_segment_seconds(self) -> float:
        if self._running_since is None:
            raise RuntimeError(tr("error.timer_missing_monotonic"))
        segment_seconds = self._clock.monotonic() - self._running_since
        if segment_seconds < 0:
            raise ClockWentBackwardsError(tr("error.clock_backwards"))
        return segment_seconds

    def _require_state(self, operation: str, *allowed_states: TimerState) -> None:
        if self._state not in allowed_states:
            raise InvalidTimerStateError(operation, self._state, allowed_states)

    def _reset(self) -> None:
        self._state = TimerState.IDLE
        self._start_time = None
        self._running_since = None
        self._accumulated_seconds = 0.0
        self._mode = FocusMode.STOPWATCH
        self._target_duration_seconds = None
