"""Consistent timezone-aware datetime serialization helpers."""

from datetime import datetime, timezone


def to_storage_datetime(value: datetime) -> str:
    """Serialize an aware datetime as canonical UTC ISO 8601."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Desktop Focus Companion datetimes must include timezone information.")
    return value.astimezone(timezone.utc).isoformat()


def from_storage_datetime(value: str) -> datetime:
    """Parse a stored aware ISO datetime and normalize it to UTC."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Stored Desktop Focus Companion datetime is missing timezone information.")
    return parsed.astimezone(timezone.utc)


def utc_now() -> datetime:
    """Return the current aware UTC datetime."""
    return datetime.now(timezone.utc)

