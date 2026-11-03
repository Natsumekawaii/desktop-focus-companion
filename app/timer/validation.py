"""Shared validation at checkpoint and timer state boundaries."""

import math

from app.i18n import tr


def validate_elapsed_seconds(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(tr('error.recovery_duration'))
    if not math.isfinite(value) or value < 0:
        raise ValueError(tr('error.recovery_duration'))
    return float(value)


def checkpoint_seconds(value: object) -> float:
    # Older JSON checkpoints accepted numeric strings. Preserve that compatibility,
    # but do not coerce booleans into numbers before validating.
    return validate_elapsed_seconds(float(value) if isinstance(value, str) else value)
