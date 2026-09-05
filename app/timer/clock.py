"""Time sources used by the study timer domain."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """Provide separate monotonic duration and wall-clock timestamps."""

    def monotonic(self) -> float:
        """Return a non-decreasing clock value in fractional seconds."""
        ...

    def now(self) -> datetime:
        """Return the current user-facing date and time."""
        ...


class SystemClock:
    """Production clock backed by the Python standard library."""

    def monotonic(self) -> float:
        """Return the operating system monotonic clock value."""
        return time.monotonic()

    def now(self) -> datetime:
        """Return an aware datetime in the machine's local timezone."""
        return datetime.now().astimezone()

