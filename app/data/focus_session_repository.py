"""Persistence for timer-created and manually entered focus records."""

from __future__ import annotations

import logging
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from app.data.database import Database
from app.data.datetime_utils import from_storage_datetime, to_storage_datetime, utc_now
from app.data.models import FocusItem, FocusSession, FocusSessionSource
from app.focus_mode import FocusMode, validate_target_duration
from app.i18n import tr

MIN_FOCUS_DURATION_SECONDS = 60
FOCUS_SESSION_MINUTE_PRECISION_V1_KEY = (
    "focus_session_minute_precision_v1_initialized"
)
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FocusSessionMinuteMigrationResult:
    """Rows changed by the one-time schema-v5 minute precision cleanup."""

    deleted_sessions: int
    normalized_sessions: int


class FocusSessionNotFoundError(RuntimeError):
    """Raised when a requested focus record does not exist."""


class InvalidFocusSessionError(ValueError):
    """Raised when focus record data is unsafe to persist."""


class FocusSessionRepository:
    """Canonical storage API for Focus history."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def ensure_minute_precision(self) -> FocusSessionMinuteMigrationResult:
        """Remove sub-minute rows and floor legacy durations atomically, once.

        The database remains schema v5. A settings marker makes the cleanup
        idempotent without introducing another migration or changing columns.
        """

        stored_now = to_storage_datetime(utc_now())
        with self._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            initialized = connection.execute(
                "SELECT 1 FROM settings WHERE key = ?",
                (FOCUS_SESSION_MINUTE_PRECISION_V1_KEY,),
            ).fetchone()
            if initialized is not None:
                return FocusSessionMinuteMigrationResult(0, 0)

            deleted_sessions = connection.execute(
                "DELETE FROM focus_sessions WHERE duration_seconds < ?",
                (MIN_FOCUS_DURATION_SECONDS,),
            ).rowcount
            normalized_sessions = connection.execute(
                """
                UPDATE focus_sessions
                SET duration_seconds = CAST(duration_seconds / 60 AS INTEGER) * 60.0,
                    target_duration_seconds = CASE
                        WHEN target_duration_seconds IS NULL THEN NULL
                        ELSE MAX(
                            60.0,
                            CAST(target_duration_seconds / 60 AS INTEGER) * 60.0
                        )
                    END,
                    updated_at = ?
                WHERE duration_seconds != CAST(duration_seconds / 60 AS INTEGER) * 60.0
                   OR (
                        target_duration_seconds IS NOT NULL
                        AND target_duration_seconds
                            != MAX(
                                60.0,
                                CAST(target_duration_seconds / 60 AS INTEGER) * 60.0
                            )
                   )
                """,
                (stored_now,),
            ).rowcount
            connection.execute(
                """
                INSERT INTO settings(key, value, updated_at)
                VALUES (?, '1', ?)
                """,
                (FOCUS_SESSION_MINUTE_PRECISION_V1_KEY, stored_now),
            )
        if deleted_sessions or normalized_sessions:
            logger.info(
                "Minute precision cleanup removed %s short sessions and "
                "normalized %s sessions",
                deleted_sessions,
                normalized_sessions,
            )
        return FocusSessionMinuteMigrationResult(
            deleted_sessions, normalized_sessions
        )

    def create(
        self,
        focus_item: FocusItem,
        start_time: datetime,
        end_time: datetime,
        duration_seconds: float,
        recovery_token: str | None = None,
        mode: FocusMode = FocusMode.STOPWATCH,
        target_duration_seconds: float | None = None,
        note: str = "",
        source: FocusSessionSource = FocusSessionSource.TIMER,
    ) -> FocusSession:
        """Persist a record while snapshotting the current focus-item name."""

        validate_focus_session(start_time, end_time, duration_seconds)
        target = validate_mode_target(mode, target_duration_seconds)
        normalized_note = normalize_note(note)
        if not isinstance(source, FocusSessionSource):
            raise InvalidFocusSessionError(tr("error.focus_source_invalid"))
        now = utc_now()
        stored_now = to_storage_datetime(now)
        with self._database.connect() as connection:
            item_name = validated_focus_item_name(connection, focus_item.id)
            insert_command = "INSERT OR IGNORE" if recovery_token else "INSERT"
            cursor = connection.execute(
                f"""
                {insert_command} INTO focus_sessions(
                    focus_item_id, focus_item_name, start_time, end_time,
                    duration_seconds, created_at, recovery_token, mode,
                    target_duration_seconds, note, source, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    focus_item.id,
                    item_name,
                    to_storage_datetime(start_time),
                    to_storage_datetime(end_time),
                    float(duration_seconds),
                    stored_now,
                    recovery_token,
                    mode.value,
                    target,
                    normalized_note,
                    source.value,
                    stored_now,
                ),
            )
            if cursor.rowcount == 0 and recovery_token:
                row = connection.execute(
                    "SELECT * FROM focus_sessions WHERE recovery_token = ?",
                    (recovery_token,),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT * FROM focus_sessions WHERE id = ?", (cursor.lastrowid,)
                ).fetchone()
        return focus_session_from_row(row)

    def get(self, session_id: int) -> FocusSession:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM focus_sessions WHERE id = ?", (session_id,)
            ).fetchone()
        if row is None:
            raise FocusSessionNotFoundError(tr("error.session_not_found_id", id=session_id))
        return focus_session_from_row(row)

    def list_sessions(
        self,
        start_at: datetime | None = None,
        end_before: datetime | None = None,
        focus_item_id: int | None = None,
        limit: int | None = None,
    ) -> list[FocusSession]:
        clauses: list[str] = []
        parameters: list[object] = []
        if start_at is not None:
            clauses.append("start_time >= ?")
            parameters.append(to_storage_datetime(start_at))
        if end_before is not None:
            clauses.append("start_time < ?")
            parameters.append(to_storage_datetime(end_before))
        if focus_item_id is not None:
            clauses.append("focus_item_id = ?")
            parameters.append(focus_item_id)

        query = "SELECT * FROM focus_sessions"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY start_time DESC, id DESC"
        if limit is not None:
            if limit <= 0:
                return []
            query += " LIMIT ?"
            parameters.append(limit)
        with self._database.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [focus_session_from_row(row) for row in rows]

    def list_overlapping(
        self, start_at: datetime, end_before: datetime
    ) -> list[FocusSession]:
        if end_before <= start_at:
            raise InvalidFocusSessionError(tr("error.session_query_order"))
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM focus_sessions
                WHERE end_time > ? AND start_time < ?
                ORDER BY start_time ASC, id ASC
                """,
                (to_storage_datetime(start_at), to_storage_datetime(end_before)),
            ).fetchall()
        return [focus_session_from_row(row) for row in rows]

    def update(
        self,
        session_id: int,
        focus_item: FocusItem,
        start_time: datetime,
        end_time: datetime,
        duration_seconds: float,
        note: str,
    ) -> FocusSession:
        """Update editable history fields while retaining source and timer metadata."""

        validate_focus_session(start_time, end_time, duration_seconds)
        normalized_note = normalize_note(note)
        with self._database.connect() as connection:
            item_name = validated_focus_item_name(connection, focus_item.id)
            cursor = connection.execute(
                """
                UPDATE focus_sessions
                SET focus_item_id = ?, focus_item_name = ?, start_time = ?,
                    end_time = ?, duration_seconds = ?, note = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    focus_item.id,
                    item_name,
                    to_storage_datetime(start_time),
                    to_storage_datetime(end_time),
                    float(duration_seconds),
                    normalized_note,
                    to_storage_datetime(utc_now()),
                    session_id,
                ),
            )
            if cursor.rowcount == 0:
                raise FocusSessionNotFoundError(
                    tr("error.session_not_found_id", id=session_id)
                )
            row = connection.execute(
                "SELECT * FROM focus_sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return focus_session_from_row(row)

    def delete(self, session_id: int) -> None:
        with self._database.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM focus_sessions WHERE id = ?", (session_id,)
            )
            if cursor.rowcount == 0:
                raise FocusSessionNotFoundError(tr("error.session_not_found_id", id=session_id))


def validate_focus_session(
    start_time: datetime, end_time: datetime, duration_seconds: float
) -> None:
    to_storage_datetime(start_time)
    to_storage_datetime(end_time)
    if end_time < start_time:
        raise InvalidFocusSessionError(tr("error.session_time_order"))
    if (
        isinstance(duration_seconds, bool)
        or not isinstance(duration_seconds, (int, float))
        or not math.isfinite(float(duration_seconds))
    ):
        raise InvalidFocusSessionError(tr("error.session_duration_numeric"))
    if duration_seconds < MIN_FOCUS_DURATION_SECONDS:
        raise InvalidFocusSessionError(tr("error.session_duration_minimum"))
    if not _is_complete_minute(float(duration_seconds)):
        raise InvalidFocusSessionError(tr("error.session_duration_precision"))


def validate_mode_target(
    mode: FocusMode, target_duration_seconds: float | None
) -> float | None:
    if not isinstance(mode, FocusMode):
        raise InvalidFocusSessionError(tr("error.focus_mode_invalid"))
    if mode is FocusMode.STOPWATCH:
        if target_duration_seconds is not None:
            raise InvalidFocusSessionError(tr("error.stopwatch_target"))
        return None
    try:
        target = validate_target_duration(target_duration_seconds)
    except ValueError as error:
        raise InvalidFocusSessionError(str(error)) from error
    if not _is_complete_minute(target):
        raise InvalidFocusSessionError(tr("error.session_target_precision"))
    return target


def _is_complete_minute(seconds: float) -> bool:
    return math.isclose(seconds % 60.0, 0.0, abs_tol=1e-7)


def normalize_note(note: str) -> str:
    if not isinstance(note, str):
        raise InvalidFocusSessionError(tr("error.focus_note_text"))
    normalized = note.strip()
    if len(normalized) > 2000:
        raise InvalidFocusSessionError(tr("error.focus_note_long"))
    return normalized


def validated_focus_item_name(connection: sqlite3.Connection, item_id: int) -> str:
    row = connection.execute(
        "SELECT name FROM focus_items WHERE id = ?", (item_id,)
    ).fetchone()
    if row is None:
        raise InvalidFocusSessionError(tr("error.subject_not_found"))
    return str(row["name"])


def focus_session_from_row(row: sqlite3.Row | None) -> FocusSession:
    if row is None:
        raise FocusSessionNotFoundError(tr("error.session_row_not_found"))
    try:
        mode = FocusMode(str(row["mode"]))
        source = FocusSessionSource(str(row["source"]))
    except ValueError as error:
        raise InvalidFocusSessionError(tr("error.focus_metadata_invalid")) from error
    return FocusSession(
        id=int(row["id"]),
        focus_item_id=int(row["focus_item_id"]),
        focus_item_name=str(row["focus_item_name"]),
        start_time=from_storage_datetime(str(row["start_time"])),
        end_time=from_storage_datetime(str(row["end_time"])),
        duration_seconds=float(row["duration_seconds"]),
        mode=mode,
        target_duration_seconds=(
            float(row["target_duration_seconds"])
            if row["target_duration_seconds"] is not None
            else None
        ),
        note=str(row["note"]),
        source=source,
        created_at=from_storage_datetime(str(row["created_at"])),
        updated_at=from_storage_datetime(str(row["updated_at"])),
    )
