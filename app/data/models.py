"""Data models shared by repositories and services."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from app.focus_mode import FocusMode


class FocusSessionSource(str, Enum):
    """Origin of a persisted focus record."""

    TIMER = "timer"
    MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class FocusItem:
    """A user-manageable activity that can receive recorded focus time."""

    id: int
    name: str
    color: str
    is_favorite: bool
    is_archived: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class FocusSession:
    """One focus record with an immutable item-name snapshot."""

    id: int
    focus_item_id: int
    focus_item_name: str
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    mode: FocusMode
    target_duration_seconds: float | None
    note: str
    source: FocusSessionSource
    created_at: datetime
    updated_at: datetime

    @property
    def subject_id(self) -> int:
        """Compatibility accessor for V1 analytics during the Focus transition."""

        return self.focus_item_id

    @property
    def subject_name(self) -> str:
        """Compatibility accessor for V1 analytics during the Focus transition."""

        return self.focus_item_name

    @property
    def study_mode(self) -> str:
        """Compatibility accessor for V1 UI during the Focus transition."""

        return self.mode.value


@dataclass(frozen=True, slots=True)
class Subject:
    """V1 subject model retained until the schema migration boundary."""

    id: int
    name: str
    is_archived: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class StudySession:
    """One persisted study session with a historical subject snapshot."""

    id: int
    subject_id: int
    subject_name: str
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    created_at: datetime
    study_mode: str = "stopwatch"
    target_duration_seconds: float | None = None
