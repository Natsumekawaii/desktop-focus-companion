"""Atomic, optimistic and idempotent assistant record mutations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.core.timezones import elapsed_seconds, system_timezone
from app.data.database import Database
from app.data.datetime_utils import to_storage_datetime, utc_now
from app.data.focus_session_repository import (
    _validate_focus_session_values,
    focus_session_from_row,
    normalize_note,
)
from app.data.models import FocusSession


@dataclass(frozen=True)
class RecordChange:
    kind: str
    original: FocusSession | None
    item_id: int
    item_version: str
    start: datetime
    end: datetime
    duration: float
    note: str
    overlaps: tuple[tuple[int, str], ...] = ()


@dataclass(frozen=True)
class RecordChangePlan:
    operation_id: str
    timezone: str
    changes: tuple[RecordChange, ...]
    requires_confirmation: bool


def _json_value(value: Any) -> str:
    if isinstance(value, datetime):
        return to_storage_datetime(value)
    raise TypeError(type(value).__name__)


def snapshot(record: FocusSession) -> dict[str, Any]:
    return json.loads(json.dumps(asdict(record), default=_json_value))


def apply_changes(
    database: Database,
    plan: RecordChangePlan,
    *,
    confirmed: bool = False,
    cancelled: Callable[[], bool] = lambda: False,
    timezone_name: Callable[[], str] = lambda: str(system_timezone()),
) -> dict[str, Any]:
    """Commit both records and a minimal receipt, or commit nothing."""
    UUID(plan.operation_id)
    if not 1 <= len(plan.changes) <= 50:
        raise ValueError("Expected 1–50 changes.")
    if (
        plan.requires_confirmation
        or len(plan.changes) > 1
        or any(c.kind != "create" or c.overlaps for c in plan.changes)
    ) and not confirmed:
        raise ValueError("Confirmation is required.")
    payload = json.dumps(
        asdict(plan), default=_json_value, sort_keys=True, allow_nan=False
    )
    fingerprint = hashlib.sha256(payload.encode()).hexdigest()
    key = f"agent.operation.{plan.operation_id}"
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        previous = connection.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        if previous:
            receipt = json.loads(previous["value"])
            if receipt["fingerprint"] != fingerprint:
                raise ValueError("Operation ID was reused with different changes.")
            return dict(receipt["result"])
        if cancelled():
            raise ValueError("Operation cancelled before commit.")
        if timezone_name() != plan.timezone:
            raise ValueError("System time zone changed; prepare a new preview.")
        seen_ids: set[int] = set()
        for change in plan.changes:
            if change.kind not in {"create", "update", "delete"}:
                raise ValueError("Unsupported record operation.")
            if change.kind != "create" and change.original is None:
                raise ValueError("An existing record snapshot is required.")
            if change.original is not None:
                original_id = change.original.id
                if original_id in seen_ids:
                    raise ValueError("A record can occur only once in a change plan.")
                seen_ids.add(original_id)
                row = connection.execute(
                    "SELECT * FROM focus_sessions WHERE id = ?", (original_id,)
                ).fetchone()
                if row is None or snapshot(focus_session_from_row(row)) != snapshot(
                    change.original
                ):
                    raise ValueError("A record changed; prepare a new preview.")
            if change.kind == "delete":
                continue
            item = connection.execute(
                "SELECT * FROM focus_items WHERE id = ?", (change.item_id,)
            ).fetchone()
            if (
                item is None
                or item["is_archived"]
                or item["updated_at"] != change.item_version
            ):
                raise ValueError("A focus item changed; prepare a new preview.")
            _validate_focus_session_values(
                change.start,
                change.end,
                change.duration,
                preserve_duration=change.original is not None
                and change.duration == change.original.duration_seconds,
            )
            normalize_note(change.note)
            if change.kind == "create":
                if elapsed_seconds(change.start, change.end) <= 0 or any(
                    d.second or d.microsecond for d in (change.start, change.end)
                ):
                    raise ValueError(
                        "New records require a positive, minute-precision range."
                    )
                rows = connection.execute(
                    "SELECT id, updated_at FROM focus_sessions WHERE end_time > ? AND start_time < ? ORDER BY id",
                    (
                        to_storage_datetime(change.start),
                        to_storage_datetime(change.end),
                    ),
                ).fetchall()
                if (
                    tuple((int(r["id"]), str(r["updated_at"])) for r in rows)
                    != change.overlaps
                ):
                    raise ValueError(
                        "Overlapping records changed; prepare a new preview."
                    )
        results = []
        now = to_storage_datetime(utc_now())
        for index, change in enumerate(plan.changes):
            if cancelled():
                raise ValueError("Operation cancelled before commit.")
            if change.kind == "delete":
                assert change.original is not None
                connection.execute(
                    "DELETE FROM focus_sessions WHERE id = ?", (change.original.id,)
                )
                record_id = change.original.id
            else:
                item_name = str(
                    connection.execute(
                        "SELECT name FROM focus_items WHERE id = ?", (change.item_id,)
                    ).fetchone()[0]
                )
                if change.kind == "create":
                    cursor = connection.execute(
                        """INSERT INTO focus_sessions(focus_item_id, focus_item_name, start_time,
                        end_time, duration_seconds, created_at, recovery_token, mode,
                        target_duration_seconds, note, source, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 'stopwatch', NULL, ?, 'manual', ?)""",
                        (
                            change.item_id,
                            item_name,
                            to_storage_datetime(change.start),
                            to_storage_datetime(change.end),
                            change.duration,
                            now,
                            f"agent:{plan.operation_id}:{index}",
                            normalize_note(change.note),
                            now,
                        ),
                    )
                    assert cursor.lastrowid is not None
                    record_id = cursor.lastrowid
                else:
                    assert change.original is not None
                    record_id = change.original.id
                    if change.item_id == change.original.focus_item_id:
                        item_name = change.original.focus_item_name
                    if change.item_id == change.original.focus_item_id:
                        item_name = change.original.focus_item_name
                    connection.execute(
                        """UPDATE focus_sessions SET focus_item_id = ?, focus_item_name = ?,
                        start_time = ?, end_time = ?, duration_seconds = ?, note = ?, updated_at = ? WHERE id = ?""",
                        (
                            change.item_id,
                            item_name,
                            to_storage_datetime(change.start),
                            to_storage_datetime(change.end),
                            change.duration,
                            change.note
                            if change.note == change.original.note
                            else normalize_note(change.note),
                            now,
                            record_id,
                        ),
                    )
            results.append({"kind": change.kind, "record_id": record_id})
        if cancelled():
            raise ValueError("Operation cancelled before commit.")
        result = {
            "status": "committed",
            "operation_id": plan.operation_id,
            "changes": results,
            "completed_at": now,
        }
        connection.execute(
            "INSERT INTO settings(key, value, updated_at) VALUES (?, ?, ?)",
            (key, json.dumps({"fingerprint": fingerprint, "result": result}), now),
        )
    return result
