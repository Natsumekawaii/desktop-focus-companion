"""Presentation modes for a general-purpose focus session."""

from __future__ import annotations

import math
from enum import Enum

from app.i18n import tr

MAX_TARGET_DURATION_SECONDS = 24 * 60 * 60


class FocusMode(str, Enum):
    """Describe how elapsed focus time is presented to the user."""

    STOPWATCH = "stopwatch"
    COUNTDOWN = "countdown"


class InvalidTargetDurationError(ValueError):
    """Raised when a countdown target is absent or outside safe limits."""


def validate_target_duration(value: object) -> float:
    """Return a finite countdown duration within the supported 24-hour limit."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidTargetDurationError(tr("error.countdown_target_invalid"))
    duration = float(value)
    if not math.isfinite(duration) or duration <= 0:
        raise InvalidTargetDurationError(tr("error.countdown_target_invalid"))
    if duration > MAX_TARGET_DURATION_SECONDS:
        raise InvalidTargetDurationError(tr("error.countdown_target_limit"))
    return duration
