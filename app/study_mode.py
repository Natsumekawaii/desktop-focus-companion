"""Compatibility imports for the V1 study-mode API.

New application code uses :mod:`app.focus_mode`.
"""

from __future__ import annotations

from app.focus_mode import (
    MAX_TARGET_DURATION_SECONDS,
    FocusMode,
    InvalidTargetDurationError,
    validate_target_duration,
)

# Explicit compatibility alias for V1 imports and persisted enum values.
StudyMode = FocusMode

__all__ = [
    "MAX_TARGET_DURATION_SECONDS",
    "InvalidTargetDurationError",
    "StudyMode",
    "validate_target_duration",
]
