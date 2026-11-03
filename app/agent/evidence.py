"""Conservative value grounding for automatically executable record fields.

Unrecognized natural-language dates/times require clarification, not guesses. This
is a client-side guard in addition to (not a substitute for) the system prompt.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta


def has_time(text: str, value: datetime) -> bool:
    for match in re.finditer(r"(?<!\d)(\d{1,2})[:：](\d{2})(?!\d)", text):
        hour, minute = map(int, match.groups())
        if minute == value.minute and hour == value.hour:
            return True
    for match in re.finditer(r"(?<!\d)(\d{1,2})\s*(?:点|时)(?:(\d{1,2})分?)?", text):
        hour = int(match[1])
        minute = int(match[2] or 0)
        if minute == value.minute and (
            hour == value.hour
            or (
                hour + 12 == value.hour
                and any(s in text for s in ("下午", "晚上", "晚间"))
            )
        ):
            return True
    for match in re.finditer(
        r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text, re.IGNORECASE
    ):
        hour = int(match[1]) % 12 + (12 if match[3].lower() == "pm" else 0)
        if hour == value.hour and int(match[2] or 0) == value.minute:
            return True
    return False


def require_time_evidence(
    text: str,
    context: str,
    value: datetime,
    now: datetime,
    original: datetime | None = None,
) -> None:
    day = value.date()
    dates = {
        f"{day.year}-{day.month:02}-{day.day:02}",
        f"{day.year}/{day.month}/{day.day}",
        f"{day.year}年{day.month}月{day.day}日",
    }
    explicit = any(d in context for d in dates)
    for offset, words in (
        (0, ("今天", "今日", "today")),
        (-1, ("昨天", "昨日", "yesterday")),
    ):
        if day == now.date() + timedelta(days=offset) and any(
            w in context.lower() for w in words
        ):
            explicit = True
    if original is not None and day == original.date():
        explicit = True  # Editing a time without changing its existing local date.
    if not explicit or not has_time(text, value):
        raise ValueError(
            "Ask for an explicit date (YYYY-MM-DD or today/yesterday) and HH:MM time; the quoted user text does not establish this value."
        )


def require_duration_evidence(
    text: str, seconds: float, start: datetime, end: datetime, elapsed: float
) -> None:
    total = 0.0
    units = {
        "h": 3600,
        "hour": 3600,
        "hours": 3600,
        "小时": 3600,
        "min": 60,
        "minute": 60,
        "minutes": 60,
        "分钟": 60,
        "s": 1,
        "sec": 1,
        "seconds": 1,
        "秒": 1,
    }
    for match in re.finditer(
        r"(\d+(?:\.\d+)?)\s*(hours?|minutes?|seconds|小时|分钟|秒|min|sec|h\b|s\b)",
        text,
        re.IGNORECASE,
    ):
        total += float(match[1]) * units[match[2].lower()]
    if total and abs(total - seconds) < 0.001:
        if seconds > elapsed:
            raise ValueError(
                "Effective duration exceeds the interval; clarify the conflicting times/duration."
            )
        return
    if (
        not total
        and seconds == elapsed
        and has_time(text, start)
        and has_time(text, end)
        and not any(
            word in text.lower() for word in ("暂停", "休息", "中断", "pause", "break")
        )
    ):
        return
    raise ValueError(
        "Ask for the effective duration or an unambiguous continuous interval; do not infer through pauses or conflicts."
    )
