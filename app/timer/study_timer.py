"""Compatibility imports for the V1 StudyTimer API."""

from app.timer.focus_timer import (
    ClockWentBackwardsError,
    FocusTimer,
    InvalidTimerStateError,
)

StudyTimer = FocusTimer

__all__ = [
    "ClockWentBackwardsError",
    "InvalidTimerStateError",
    "StudyTimer",
]
