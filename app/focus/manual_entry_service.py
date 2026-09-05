"""Validated creation of manually entered focus records."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from app.data.focus_item_repository import FocusItemRepository
from app.data.focus_session_repository import (
    MIN_FOCUS_DURATION_SECONDS,
    FocusSessionRepository,
)
from app.data.models import FocusSession, FocusSessionSource
from app.focus_mode import FocusMode
from app.i18n import tr


@dataclass(frozen=True, slots=True)
class ManualFocusEntry:
    focus_item_id: int
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    note: str = ""


class ManualFocusEntryService:
    """Persist manual records through the same history repository as timers."""

    def __init__(
        self,
        focus_items: FocusItemRepository,
        focus_sessions: FocusSessionRepository,
    ) -> None:
        self._focus_items = focus_items
        self._focus_sessions = focus_sessions

    def create(self, entry: ManualFocusEntry) -> FocusSession:
        if (
            isinstance(entry.duration_seconds, bool)
            or not math.isfinite(entry.duration_seconds)
        ):
            raise ValueError(tr("error.session_duration_numeric"))
        if entry.duration_seconds < MIN_FOCUS_DURATION_SECONDS:
            raise ValueError(tr("error.session_duration_minimum"))
        if entry.duration_seconds % 60 != 0:
            raise ValueError(tr("error.session_duration_precision"))
        if entry.end_time <= entry.start_time:
            raise ValueError(tr("error.session_time_order"))
        if any(
            value.second != 0 or value.microsecond != 0
            for value in (entry.start_time, entry.end_time)
        ):
            raise ValueError(tr("error.session_time_precision"))
        item = self._focus_items.get(entry.focus_item_id, include_archived=False)
        return self._focus_sessions.create(
            item,
            entry.start_time,
            entry.end_time,
            entry.duration_seconds,
            mode=FocusMode.STOPWATCH,
            note=entry.note,
            source=FocusSessionSource.MANUAL,
        )
