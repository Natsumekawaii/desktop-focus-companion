"""Presentation utilities for timer durations."""

from __future__ import annotations

import math

from app.i18n import tr


def format_duration(seconds: float) -> str:
    """Format elapsed focus time using completed minutes only."""
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        raise TypeError("seconds must be an int or float")
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("seconds must be finite and non-negative")

    if seconds < 60:
        return tr("duration.less_than_minute")
    return format_compact_duration(seconds)


def format_stopwatch_clock(seconds: float) -> str:
    """Format a live stopwatch as an unbounded ``HH:MM:SS`` clock."""

    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        raise TypeError("seconds must be an int or float")
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("seconds must be finite and non-negative")
    total_seconds = int(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, display_seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{display_seconds:02d}"


def format_compact_duration(seconds: float) -> str:
    """Format a duration for summaries such as ``2h 17min``."""
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        raise TypeError("seconds must be an int or float")
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("seconds must be finite and non-negative")
    total_minutes = int(seconds) // 60
    hours, minutes = divmod(total_minutes, 60)
    if hours:
        return (
            tr("duration.hours_minutes", hours=hours, minutes=minutes)
            if minutes
            else tr("duration.hours", hours=hours)
        )
    return tr("duration.minutes", minutes=minutes)


def format_remaining_duration(seconds: float) -> str:
    """Format countdown time as complete display minutes, rounding upward."""
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        raise TypeError("seconds must be an int or float")
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("seconds must be finite and non-negative")
    total_minutes = math.ceil(seconds / 60)
    return format_compact_duration(total_minutes * 60)
