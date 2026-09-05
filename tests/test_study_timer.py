"""Unit tests for the UI-independent StudyTimer state machine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from app.timer import (
    ClockWentBackwardsError,
    InvalidTargetDurationError,
    InvalidTimerStateError,
    StudyMode,
    StudyTimer,
    TimerState,
)


@dataclass
class FakeClock:
    """Deterministic dual clock; advancing a test never sleeps."""

    monotonic_value: float = 1_000.0
    wall_value: datetime = datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc)

    def monotonic(self) -> float:
        return self.monotonic_value

    def now(self) -> datetime:
        return self.wall_value

    def advance(self, seconds: float) -> None:
        self.monotonic_value += seconds
        self.wall_value += timedelta(seconds=seconds)

    def shift_wall_time(self, seconds: float) -> None:
        self.wall_value += timedelta(seconds=seconds)


def test_normal_session_uses_real_time_difference() -> None:
    clock = FakeClock()
    timer = StudyTimer(clock)

    timer.start()
    clock.advance(90.25)

    assert timer.current_state is TimerState.FOCUSING
    assert timer.elapsed_seconds == pytest.approx(90.25)

    result = timer.finish()
    assert result.start_time == datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc)
    assert result.end_time == datetime(2026, 8, 14, 10, 1, 30, 250000, tzinfo=timezone.utc)
    assert result.duration_seconds == pytest.approx(90.25)
    assert result.study_mode is StudyMode.STOPWATCH
    assert result.target_duration_seconds is None
    assert timer.current_state is TimerState.IDLE
    assert timer.elapsed_seconds == 0


def test_pause_resume_excludes_paused_time() -> None:
    clock = FakeClock()
    timer = StudyTimer(clock)

    timer.start()
    clock.advance(30 * 60)
    timer.pause()
    clock.advance(30 * 60)

    assert timer.current_state is TimerState.PAUSED
    assert timer.elapsed_seconds == 30 * 60

    timer.resume()
    clock.advance(45 * 60)
    result = timer.finish()

    assert result.duration_seconds == 75 * 60
    assert result.end_time == datetime(2026, 8, 14, 11, 45, tzinfo=timezone.utc)


def test_multiple_pauses_accumulate_only_study_segments() -> None:
    clock = FakeClock()
    timer = StudyTimer(clock)

    timer.start()
    clock.advance(10 * 60)
    timer.pause()
    clock.advance(5 * 60)
    timer.resume()
    clock.advance(20 * 60)
    timer.pause()
    clock.advance(10 * 60)
    timer.resume()
    clock.advance(30 * 60)

    result = timer.finish()
    assert result.duration_seconds == 60 * 60


def test_finish_while_paused_does_not_add_pause_wait() -> None:
    clock = FakeClock()
    timer = StudyTimer(clock)

    timer.start()
    clock.advance(30 * 60)
    timer.pause()
    clock.advance(20 * 60)
    result = timer.finish()

    assert result.duration_seconds == 30 * 60
    assert result.end_time == datetime(2026, 8, 14, 10, 50, tzinfo=timezone.utc)
    assert timer.current_state is TimerState.IDLE


@pytest.mark.parametrize(
    ("initial_state", "operation"),
    [
        (TimerState.IDLE, "pause"),
        (TimerState.IDLE, "resume"),
        (TimerState.IDLE, "finish"),
        (TimerState.FOCUSING, "start"),
        (TimerState.FOCUSING, "resume"),
        (TimerState.PAUSED, "start"),
        (TimerState.PAUSED, "pause"),
    ],
)
def test_illegal_transitions_raise_without_changing_state(
    initial_state: TimerState,
    operation: str,
) -> None:
    clock = FakeClock()
    timer = StudyTimer(clock)
    if initial_state in (TimerState.FOCUSING, TimerState.PAUSED):
        timer.start()
    if initial_state is TimerState.PAUSED:
        timer.pause()
    elapsed_before_operation = timer.elapsed_seconds

    with pytest.raises(InvalidTimerStateError) as error_info:
        getattr(timer, operation)()

    assert error_info.value.operation == operation
    assert error_info.value.current_state is initial_state
    assert timer.current_state is initial_state
    assert timer.elapsed_seconds == elapsed_before_operation


def test_timer_can_start_fresh_after_finish() -> None:
    clock = FakeClock()
    timer = StudyTimer(clock)

    timer.start()
    clock.advance(40)
    first_result = timer.finish()

    clock.advance(100)
    timer.start()
    assert timer.elapsed_seconds == 0
    clock.advance(15)
    second_result = timer.finish()

    assert first_result.duration_seconds == 40
    assert second_result.duration_seconds == 15
    assert second_result.start_time > first_result.end_time


def test_wall_clock_changes_do_not_affect_duration() -> None:
    clock = FakeClock()
    timer = StudyTimer(clock)

    timer.start()
    clock.monotonic_value += 120
    clock.shift_wall_time(-60 * 60)
    result = timer.finish()

    assert result.duration_seconds == 120
    assert result.end_time < result.start_time


def test_backwards_injected_monotonic_clock_is_rejected() -> None:
    clock = FakeClock()
    timer = StudyTimer(clock)
    timer.start()
    clock.monotonic_value -= 1

    with pytest.raises(ClockWentBackwardsError):
        _ = timer.elapsed_seconds

    assert timer.current_state is TimerState.FOCUSING


def test_countdown_pause_resume_reaches_zero_without_counting_pause_time() -> None:
    clock = FakeClock()
    timer = StudyTimer(clock)
    timer.start(StudyMode.COUNTDOWN, 60 * 60)

    clock.advance(20 * 60)
    assert timer.remaining_seconds == 40 * 60
    timer.pause()
    clock.advance(30 * 60)
    assert timer.elapsed_seconds == 20 * 60
    assert timer.remaining_seconds == 40 * 60

    timer.resume()
    clock.advance(40 * 60)
    assert timer.has_reached_target
    assert timer.remaining_seconds == 0
    result = timer.finish()

    assert result.duration_seconds == 60 * 60
    assert result.study_mode is StudyMode.COUNTDOWN
    assert result.target_duration_seconds == 60 * 60


def test_countdown_early_finish_saves_actual_studied_duration() -> None:
    clock = FakeClock()
    timer = StudyTimer(clock)
    timer.start(StudyMode.COUNTDOWN, 60 * 60)
    clock.advance(25 * 60)

    result = timer.finish()

    assert result.duration_seconds == 25 * 60
    assert result.target_duration_seconds == 60 * 60


@pytest.mark.parametrize(
    "target",
    [None, True, "25", 0, -1, float("nan"), float("inf"), 24 * 60 * 60 + 1],
)
def test_countdown_rejects_missing_or_out_of_range_targets(target: object) -> None:
    timer = StudyTimer(FakeClock())

    with pytest.raises(InvalidTargetDurationError):
        timer.start(StudyMode.COUNTDOWN, target)  # type: ignore[arg-type]

    assert timer.current_state is TimerState.IDLE


def test_countdown_accepts_the_24_hour_upper_boundary() -> None:
    timer = StudyTimer(FakeClock())

    timer.start(StudyMode.COUNTDOWN, 24 * 60 * 60)

    assert timer.target_duration_seconds == 24 * 60 * 60
