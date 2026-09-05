"""Tests for the canonical Focus domain primitives."""

from datetime import datetime, timezone

import pytest

from app.data.models import FocusItem, FocusSession, FocusSessionSource
from app.focus_mode import (
    FocusMode,
    InvalidTargetDurationError,
    validate_target_duration,
)
from app.study_mode import StudyMode


def test_focus_item_carries_general_activity_metadata() -> None:
    now = datetime(2026, 8, 15, tzinfo=timezone.utc)
    item = FocusItem(7, "阅读", "#7C5CFC", True, False, now, now)

    assert item.name == "阅读"
    assert item.color == "#7C5CFC"
    assert item.is_favorite
    assert not item.is_archived


def test_focus_mode_uses_stable_persisted_values() -> None:
    assert FocusMode.STOPWATCH.value == "stopwatch"
    assert FocusMode.COUNTDOWN.value == "countdown"
    assert StudyMode is FocusMode


@pytest.mark.parametrize("value", [True, 0, -1, float("nan"), 86401])
def test_focus_countdown_target_validation_rejects_unsafe_values(value: object) -> None:
    with pytest.raises(InvalidTargetDurationError):
        validate_target_duration(value)


def test_focus_countdown_target_accepts_24_hour_boundary() -> None:
    assert validate_target_duration(86400) == 86400


def test_focus_session_preserves_snapshot_note_and_source() -> None:
    started = datetime(2026, 8, 15, 9, 30, tzinfo=timezone.utc)
    ended = datetime(2026, 8, 15, 10, 15, tzinfo=timezone.utc)
    session = FocusSession(
        id=11,
        focus_item_id=7,
        focus_item_name="阅读",
        start_time=started,
        end_time=ended,
        duration_seconds=2700,
        mode=FocusMode.COUNTDOWN,
        target_duration_seconds=3600,
        note="第 3 章",
        source=FocusSessionSource.TIMER,
        created_at=ended,
        updated_at=ended,
    )

    assert session.focus_item_name == "阅读"
    assert session.duration_seconds == 2700
    assert session.mode is FocusMode.COUNTDOWN
    assert session.target_duration_seconds == 3600
    assert session.note == "第 3 章"
    assert session.source is FocusSessionSource.TIMER


def test_focus_session_sources_have_stable_database_values() -> None:
    assert FocusSessionSource.TIMER.value == "timer"
    assert FocusSessionSource.MANUAL.value == "manual"
