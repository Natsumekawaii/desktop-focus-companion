"""Immutable values returned by the focus timer domain."""

from dataclasses import dataclass
from datetime import datetime

from app.focus_mode import FocusMode


@dataclass(frozen=True, slots=True)
class FocusTimerResult:
    """Core time information for one finished focus session."""

    start_time: datetime
    end_time: datetime
    duration_seconds: float
    mode: FocusMode = FocusMode.STOPWATCH
    target_duration_seconds: float | None = None

    @property
    def study_mode(self) -> FocusMode:
        """Compatibility alias for V1 callers."""

        return self.mode


StudyTimerResult = FocusTimerResult

__all__ = ["FocusTimerResult", "StudyTimerResult"]
