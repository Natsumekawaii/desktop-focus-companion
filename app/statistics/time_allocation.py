"""Allocate session duration across local calendar dates."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta, tzinfo

from app.data.models import FocusSession


def allocate_session_by_local_date(
    session: FocusSession,
    local_timezone: tzinfo,
) -> dict[date, float]:
    """Split effective duration proportionally across local midnight boundaries."""
    local_start = session.start_time.astimezone(local_timezone)
    local_end = session.end_time.astimezone(local_timezone)
    wall_seconds = (local_end - local_start).total_seconds()
    if wall_seconds <= 0 or session.duration_seconds == 0:
        return {local_start.date(): session.duration_seconds}

    allocation: dict[date, float] = {}
    cursor = local_start
    remaining_duration = session.duration_seconds
    while cursor.date() < local_end.date():
        next_midnight = datetime.combine(
            cursor.date() + timedelta(days=1),
            time.min,
            tzinfo=local_timezone,
        )
        overlap_seconds = (next_midnight - cursor).total_seconds()
        portion = session.duration_seconds * overlap_seconds / wall_seconds
        allocation[cursor.date()] = allocation.get(cursor.date(), 0.0) + portion
        remaining_duration -= portion
        cursor = next_midnight
    allocation[local_end.date()] = allocation.get(local_end.date(), 0.0) + max(0.0, remaining_duration)
    return allocation


def totals_by_local_date(
    sessions: Sequence[FocusSession],
    local_timezone: tzinfo,
) -> dict[date, float]:
    """Aggregate allocated durations for multiple sessions."""
    totals: defaultdict[date, float] = defaultdict(float)
    for session in sessions:
        for local_date, duration in allocate_session_by_local_date(session, local_timezone).items():
            totals[local_date] += duration
    return dict(totals)
