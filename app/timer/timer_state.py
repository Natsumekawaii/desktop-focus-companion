"""Focus timer state identifiers."""

from enum import Enum


class TimerState(Enum):
    """Mutually exclusive states of a FocusTimer."""

    IDLE = "idle"
    FOCUSING = "focusing"
    PAUSED = "paused"
    STUDYING = "studying"  # Legacy checkpoint/test compatibility only.
