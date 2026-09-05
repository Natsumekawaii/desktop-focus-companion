"""Compatibility adapter for the V1 study-session repository API."""

from __future__ import annotations

from datetime import datetime

from app.data.database import Database
from app.data.focus_item_repository import FocusItemRepository
from app.data.focus_session_repository import (
    FocusSessionNotFoundError,
    FocusSessionRepository,
    InvalidFocusSessionError,
)
from app.data.models import FocusSession, FocusSessionSource, StudySession, Subject
from app.study_mode import StudyMode

SessionNotFoundError = FocusSessionNotFoundError
InvalidSessionError = InvalidFocusSessionError


class SessionRepository:
    """V1-shaped adapter; new runtime code uses FocusSessionRepository directly."""

    def __init__(self, database: Database) -> None:
        self._focus_items = FocusItemRepository(database)
        self._focus_sessions = FocusSessionRepository(database)

    def create(
        self,
        subject: Subject,
        start_time: datetime,
        end_time: datetime,
        duration_seconds: float,
        recovery_token: str | None = None,
        study_mode: StudyMode = StudyMode.STOPWATCH,
        target_duration_seconds: float | None = None,
    ) -> StudySession:
        item = self._focus_items.get(subject.id)
        session = self._focus_sessions.create(
            item,
            start_time,
            end_time,
            duration_seconds,
            recovery_token,
            study_mode,
            target_duration_seconds,
            source=FocusSessionSource.TIMER,
        )
        return _as_study_session(session)

    def get(self, session_id: int) -> StudySession:
        return _as_study_session(self._focus_sessions.get(session_id))

    def list_sessions(
        self,
        start_at: datetime | None = None,
        end_before: datetime | None = None,
        subject_id: int | None = None,
        limit: int | None = None,
    ) -> list[StudySession]:
        return [
            _as_study_session(session)
            for session in self._focus_sessions.list_sessions(
                start_at, end_before, subject_id, limit
            )
        ]

    def list_overlapping(
        self, start_at: datetime, end_before: datetime
    ) -> list[StudySession]:
        return [
            _as_study_session(session)
            for session in self._focus_sessions.list_overlapping(start_at, end_before)
        ]

    def update(
        self,
        session_id: int,
        subject: Subject,
        start_time: datetime,
        end_time: datetime,
        duration_seconds: float,
    ) -> StudySession:
        existing = self._focus_sessions.get(session_id)
        item = self._focus_items.get(subject.id)
        return _as_study_session(
            self._focus_sessions.update(
                session_id,
                item,
                start_time,
                end_time,
                duration_seconds,
                existing.note,
            )
        )

    def delete(self, session_id: int) -> None:
        self._focus_sessions.delete(session_id)


def _as_study_session(session: FocusSession) -> StudySession:
    return StudySession(
        id=session.id,
        subject_id=session.focus_item_id,
        subject_name=session.focus_item_name,
        start_time=session.start_time,
        end_time=session.end_time,
        duration_seconds=session.duration_seconds,
        created_at=session.created_at,
        study_mode=session.mode.value,
        target_duration_seconds=session.target_duration_seconds,
    )


__all__ = [
    "InvalidSessionError",
    "SessionNotFoundError",
    "SessionRepository",
]
