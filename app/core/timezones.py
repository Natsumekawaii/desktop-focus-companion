"""IANA local-time resolution; elapsed intervals always use UTC arithmetic."""

from __future__ import annotations

from datetime import datetime, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from PySide6.QtCore import QTimeZone

from app.i18n import tr


def system_timezone() -> ZoneInfo:
    name = bytes(QTimeZone.systemTimeZoneId().data()).decode('utf-8')
    try:
        return ZoneInfo(name)
    except (ValueError, ZoneInfoNotFoundError) as error:
        raise RuntimeError(tr('error.timezone_unavailable', name=name)) from error


def elapsed_seconds(start: datetime, end: datetime) -> float:
    return (end.astimezone(timezone.utc) - start.astimezone(timezone.utc)).total_seconds()


def local_candidates(naive: datetime, zone: tzinfo) -> tuple[datetime, ...]:
    """Return 0/1/2 instants for a missing/ordinary/ambiguous wall-clock time."""
    candidates: list[datetime] = []
    for fold in (0, 1):
        candidate = naive.replace(tzinfo=zone, fold=fold)
        restored = candidate.astimezone(timezone.utc).astimezone(zone)
        if restored.replace(tzinfo=None) != naive.replace(tzinfo=None):
            continue
        if not any(c.astimezone(timezone.utc) == candidate.astimezone(timezone.utc) for c in candidates):
            candidates.append(candidate)
    return tuple(candidates)
