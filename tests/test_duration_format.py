"""Tests for presentation-only duration formatting."""

import pytest

from app.i18n import tr
from app.timer import (
    format_duration,
    format_remaining_duration,
    format_stopwatch_clock,
)


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "less"),
        (65, "1min"),
        (3661, "1h1min"),
        (65.999, "1min"),
        (360_000, "100h"),
    ],
)
def test_format_duration(seconds: float, expected: str) -> None:
    localized = {
        "less": tr("duration.less_than_minute"),
        "1min": tr("duration.minutes", minutes=1),
        "1h1min": tr("duration.hours_minutes", hours=1, minutes=1),
        "100h": tr("duration.hours", hours=100),
    }
    assert format_duration(seconds) == localized[expected]


@pytest.mark.parametrize("seconds", [-1, float("inf"), float("nan")])
def test_format_duration_rejects_invalid_numeric_values(seconds: float) -> None:
    with pytest.raises(ValueError):
        format_duration(seconds)


@pytest.mark.parametrize("seconds", [True, "65", None])
def test_format_duration_rejects_non_duration_types(seconds: object) -> None:
    with pytest.raises(TypeError):
        format_duration(seconds)  # type: ignore[arg-type]


def test_remaining_duration_rounds_up_to_complete_display_minutes() -> None:
    assert format_remaining_duration(0) == tr("duration.minutes", minutes=0)
    assert format_remaining_duration(59.01) == tr("duration.minutes", minutes=1)
    assert format_remaining_duration(59 * 60 + 59.2) == tr("duration.hours", hours=1)
    assert format_remaining_duration(90 * 60) == tr(
        "duration.hours_minutes", hours=1, minutes=30
    )


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "00:00:00"),
        (59.999, "00:00:59"),
        (65, "00:01:05"),
        (3600, "01:00:00"),
        (100 * 3600 + 2, "100:00:02"),
    ],
)
def test_stopwatch_clock_uses_unbounded_hours_and_complete_seconds(
    seconds: float, expected: str
) -> None:
    assert format_stopwatch_clock(seconds) == expected


@pytest.mark.parametrize("seconds", [-1, float("inf"), float("nan")])
def test_stopwatch_clock_rejects_invalid_numeric_values(seconds: float) -> None:
    with pytest.raises(ValueError):
        format_stopwatch_clock(seconds)


@pytest.mark.parametrize("seconds", [True, "65", None])
def test_stopwatch_clock_rejects_non_duration_types(seconds: object) -> None:
    with pytest.raises(TypeError):
        format_stopwatch_clock(seconds)  # type: ignore[arg-type]
