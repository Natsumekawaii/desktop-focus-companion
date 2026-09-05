"""Tests for subject and study-session repositories."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.data.database import Database
from app.data.session_repository import (
    InvalidSessionError,
    SessionNotFoundError,
    SessionRepository,
)
from app.data.subject_repository import (
    DEFAULT_SUBJECT_NAMES,
    DuplicateSubjectError,
    SubjectNotFoundError,
    SubjectRepository,
)
from app.timer import StudyMode


@pytest.fixture
def repositories(tmp_path: Path) -> tuple[SubjectRepository, SessionRepository]:
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    subjects = SubjectRepository(database)
    sessions = SessionRepository(database)
    return subjects, sessions


def test_subjects_support_defaults_create_rename_archive_and_restore(repositories) -> None:
    subjects, _ = repositories
    subjects.ensure_defaults()

    assert {subject.name for subject in subjects.list_active()} == set(DEFAULT_SUBJECT_NAMES)
    physics = subjects.create("  Physics   Lab  ")
    assert physics.name == "Physics Lab"
    renamed = subjects.rename(physics.id, "Physics")
    assert renamed.name == "Physics"

    with pytest.raises(DuplicateSubjectError):
        subjects.create("physics")

    subjects.archive(physics.id)
    with pytest.raises(SubjectNotFoundError):
        subjects.get(physics.id, include_archived=False)
    restored = subjects.create("PHYSICS")
    assert restored.id == physics.id
    assert not restored.is_archived


def test_archiving_or_renaming_subject_preserves_historical_snapshot(repositories) -> None:
    subjects, sessions = repositories
    subject = subjects.create("Original Name")
    start = datetime(2026, 8, 14, 1, 0, tzinfo=timezone.utc)
    session = sessions.create(subject, start, start + timedelta(hours=1), 3600)

    subjects.rename(subject.id, "New Name")
    subjects.archive(subject.id)
    stored = sessions.get(session.id)

    assert stored.subject_id == subject.id
    assert stored.subject_name == "Original Name"
    assert stored.duration_seconds == 3600


def test_session_repository_lists_updates_and_deletes(repositories) -> None:
    subjects, sessions = repositories
    first_subject = subjects.create("Math")
    second_subject = subjects.create("Writing")
    start = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)
    first = sessions.create(first_subject, start, start + timedelta(minutes=30), 1800)
    second = sessions.create(second_subject, start + timedelta(hours=2), start + timedelta(hours=3), 3600)

    listed = sessions.list_sessions(start_at=start, end_before=start + timedelta(days=1))
    assert [session.id for session in listed] == [second.id, first.id]

    updated = sessions.update(
        first.id,
        second_subject,
        start,
        start + timedelta(minutes=45),
        2700,
    )
    assert updated.subject_name == "Writing"
    assert updated.duration_seconds == 2700

    sessions.delete(first.id)
    with pytest.raises(SessionNotFoundError):
        sessions.get(first.id)


def test_session_repository_requires_aware_datetime_and_non_negative_duration(repositories) -> None:
    subjects, sessions = repositories
    subject = subjects.create("Safety")
    aware = datetime(2026, 8, 14, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="timezone"):
        sessions.create(subject, aware.replace(tzinfo=None), aware, 10)
    with pytest.raises(InvalidSessionError):
        sessions.create(subject, aware, aware, -1)


def test_session_repository_persists_countdown_mode_and_target(repositories) -> None:
    subjects, sessions = repositories
    subject = subjects.create("Timed Focus")
    start = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)

    created = sessions.create(
        subject,
        start,
        start + timedelta(minutes=25),
        25 * 60,
        study_mode=StudyMode.COUNTDOWN,
        target_duration_seconds=50 * 60,
    )
    stored = sessions.get(created.id)

    assert stored.study_mode == StudyMode.COUNTDOWN.value
    assert stored.target_duration_seconds == 50 * 60
