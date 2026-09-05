"""Persistence for user-manageable focus items."""

from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass

from app.data.database import Database, DatabaseError
from app.data.datetime_utils import from_storage_datetime, to_storage_datetime, utc_now
from app.data.models import FocusItem
from app.i18n import tr

DEFAULT_FOCUS_ITEMS = (
    ("学习", "#7C5CFC"),
    ("阅读", "#3B82F6"),
    ("工作", "#14B8A6"),
    ("其他", "#F59E0B"),
)
DEFAULT_FOCUS_COLOR = "#7C5CFC"
FOCUS_ITEM_LIFECYCLE_KEY = "focus_item_lifecycle_initialized"
_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FocusItemDeletionImpact:
    """History that will be removed with one Focus Item."""

    session_count: int
    total_seconds: float


class FocusItemError(RuntimeError):
    """Base error for focus-item operations."""


class InvalidFocusItemError(FocusItemError):
    """Raised when a focus-item name or color is invalid."""


class DuplicateFocusItemError(FocusItemError):
    """Raised when an active focus item already uses a requested name."""


class FocusItemNotFoundError(FocusItemError):
    """Raised when a focus item does not exist or is unavailable."""


class FocusItemInUseError(FocusItemError):
    """Raised when physical deletion would orphan focus history."""


class FocusItemRepository:
    """Persist FocusItem entities with history-safe archiving."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def ensure_defaults(self) -> None:
        """Seed once and apply the one-time legacy lifecycle cleanup atomically."""

        stored_now = to_storage_datetime(utc_now())
        with self._database.connect() as connection:
            initialized = connection.execute(
                "SELECT 1 FROM settings WHERE key = ?",
                (FOCUS_ITEM_LIFECYCLE_KEY,),
            ).fetchone()
            if initialized is not None:
                return

            item_count = int(
                connection.execute("SELECT COUNT(*) FROM focus_items").fetchone()[0]
            )
            if item_count == 0:
                connection.executemany(
                    """
                    INSERT INTO focus_items(
                        name, color, is_favorite, is_archived, created_at, updated_at
                    ) VALUES (?, ?, 0, 0, ?, ?)
                    """,
                    (
                        (name, color, stored_now, stored_now)
                        for name, color in DEFAULT_FOCUS_ITEMS
                    ),
                )

            archived_rows = connection.execute(
                "SELECT id FROM focus_items WHERE is_archived = 1"
            ).fetchall()
            archived_ids = tuple(int(row["id"]) for row in archived_rows)
            deleted_sessions = 0
            if archived_ids:
                placeholders = ", ".join("?" for _ in archived_ids)
                deleted_sessions = connection.execute(
                    f"DELETE FROM focus_sessions WHERE focus_item_id IN ({placeholders})",
                    archived_ids,
                ).rowcount
                connection.execute(
                    f"DELETE FROM focus_items WHERE id IN ({placeholders})",
                    archived_ids,
                )

            connection.execute(
                "UPDATE focus_items SET is_favorite = 0 WHERE is_favorite != 0"
            )
            connection.execute(
                """
                INSERT INTO settings(key, value, updated_at)
                VALUES (?, '1', ?)
                """,
                (FOCUS_ITEM_LIFECYCLE_KEY, stored_now),
            )
        if archived_ids:
            logger.info(
                "Removed %s legacy archived Focus Items and %s linked sessions",
                len(archived_ids),
                deleted_sessions,
            )

    def create(self, name: str, color: str = DEFAULT_FOCUS_COLOR) -> FocusItem:
        """Create a Focus Item with a human-selected display color."""

        normalized_name = normalize_focus_item_name(name)
        normalized_color = normalize_focus_color(color)
        now = utc_now()
        stored_now = to_storage_datetime(now)
        with self._database.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM focus_items WHERE name = ? COLLATE NOCASE",
                (normalized_name,),
            ).fetchone()
            if existing is not None:
                if bool(existing["is_archived"]):
                    connection.execute(
                        """
                        UPDATE focus_items
                        SET name = ?, color = ?, is_archived = 0, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            normalized_name,
                            normalized_color,
                            stored_now,
                            existing["id"],
                        ),
                    )
                    row = connection.execute(
                        "SELECT * FROM focus_items WHERE id = ?", (existing["id"],)
                    ).fetchone()
                    return focus_item_from_row(row)
                raise DuplicateFocusItemError(
                    tr("error.subject_duplicate_name", name=normalized_name)
                )

            cursor = connection.execute(
                """
                INSERT INTO focus_items(
                    name, color, is_favorite, is_archived, created_at, updated_at
                ) VALUES (?, ?, 0, 0, ?, ?)
                """,
                (normalized_name, normalized_color, stored_now, stored_now),
            )
            row = connection.execute(
                "SELECT * FROM focus_items WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        return focus_item_from_row(row)

    def get(self, item_id: int, include_archived: bool = True) -> FocusItem:
        query = "SELECT * FROM focus_items WHERE id = ?"
        if not include_archived:
            query += " AND is_archived = 0"
        with self._database.connect() as connection:
            row = connection.execute(query, (item_id,)).fetchone()
        if row is None:
            raise FocusItemNotFoundError(tr("error.subject_not_found_id", id=item_id))
        return focus_item_from_row(row)

    def list_active(self) -> list[FocusItem]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM focus_items
                WHERE is_archived = 0
                ORDER BY name COLLATE NOCASE, id
                """
            ).fetchall()
        return [focus_item_from_row(row) for row in rows]

    def list_all(self) -> list[FocusItem]:
        with self._database.connect() as connection:
            rows = connection.execute("SELECT * FROM focus_items ORDER BY id").fetchall()
        return [focus_item_from_row(row) for row in rows]

    def rename(self, item_id: int, new_name: str) -> FocusItem:
        normalized_name = normalize_focus_item_name(new_name)
        try:
            with self._database.connect() as connection:
                cursor = connection.execute(
                    """
                    UPDATE focus_items SET name = ?, updated_at = ?
                    WHERE id = ? AND is_archived = 0
                    """,
                    (normalized_name, to_storage_datetime(utc_now()), item_id),
                )
                if cursor.rowcount == 0:
                    raise FocusItemNotFoundError(
                        tr("error.subject_active_not_found", id=item_id)
                    )
                row = connection.execute(
                    "SELECT * FROM focus_items WHERE id = ?", (item_id,)
                ).fetchone()
            return focus_item_from_row(row)
        except DatabaseError as error:
            if "UNIQUE" in str(error.__cause__).upper():
                raise DuplicateFocusItemError(
                    tr("error.subject_duplicate_name", name=normalized_name)
                ) from error
            raise

    def set_color(self, item_id: int, color: str) -> FocusItem:
        return self._update_metadata(item_id, "color", normalize_focus_color(color))

    def set_favorite(self, item_id: int, is_favorite: bool) -> FocusItem:
        return self._update_metadata(item_id, "is_favorite", int(bool(is_favorite)))

    def archive(self, item_id: int) -> None:
        self._set_archived(item_id, True)

    def restore(self, item_id: int) -> FocusItem:
        self._set_archived(item_id, False)
        return self.get(item_id)

    def delete_if_unused(self, item_id: int) -> None:
        """Physically delete only an item that has no historical focus records."""

        with self._database.connect() as connection:
            used = connection.execute(
                "SELECT 1 FROM focus_sessions WHERE focus_item_id = ? LIMIT 1", (item_id,)
            ).fetchone()
            if used is not None:
                raise FocusItemInUseError(tr("error.focus_item_in_use"))
            cursor = connection.execute("DELETE FROM focus_items WHERE id = ?", (item_id,))
            if cursor.rowcount == 0:
                raise FocusItemNotFoundError(tr("error.subject_not_found_id", id=item_id))

    def deletion_impact(self, item_id: int) -> FocusItemDeletionImpact:
        """Return the exact history affected by permanent item deletion."""

        with self._database.connect() as connection:
            item = connection.execute(
                "SELECT 1 FROM focus_items WHERE id = ?", (item_id,)
            ).fetchone()
            if item is None:
                raise FocusItemNotFoundError(tr("error.subject_not_found_id", id=item_id))
            row = connection.execute(
                """
                SELECT COUNT(*) AS session_count,
                       COALESCE(SUM(duration_seconds), 0) AS total_seconds
                FROM focus_sessions
                WHERE focus_item_id = ?
                """,
                (item_id,),
            ).fetchone()
        return FocusItemDeletionImpact(
            session_count=int(row["session_count"]),
            total_seconds=float(row["total_seconds"]),
        )

    def delete_with_history(self, item_id: int) -> FocusItemDeletionImpact:
        """Permanently delete one Focus Item and all of its sessions atomically."""

        with self._database.connect() as connection:
            item = connection.execute(
                "SELECT 1 FROM focus_items WHERE id = ?", (item_id,)
            ).fetchone()
            if item is None:
                raise FocusItemNotFoundError(tr("error.subject_not_found_id", id=item_id))
            row = connection.execute(
                """
                SELECT COUNT(*) AS session_count,
                       COALESCE(SUM(duration_seconds), 0) AS total_seconds
                FROM focus_sessions
                WHERE focus_item_id = ?
                """,
                (item_id,),
            ).fetchone()
            impact = FocusItemDeletionImpact(
                session_count=int(row["session_count"]),
                total_seconds=float(row["total_seconds"]),
            )
            connection.execute(
                "DELETE FROM focus_sessions WHERE focus_item_id = ?", (item_id,)
            )
            cursor = connection.execute(
                "DELETE FROM focus_items WHERE id = ?", (item_id,)
            )
            if cursor.rowcount == 0:
                raise FocusItemNotFoundError(
                    tr("error.subject_not_found_id", id=item_id)
                )
        return impact

    def _update_metadata(self, item_id: int, column: str, value: object) -> FocusItem:
        if column not in {"color", "is_favorite"}:
            raise ValueError("Unsupported focus-item metadata column.")
        with self._database.connect() as connection:
            cursor = connection.execute(
                f"UPDATE focus_items SET {column} = ?, updated_at = ? WHERE id = ?",
                (value, to_storage_datetime(utc_now()), item_id),
            )
            if cursor.rowcount == 0:
                raise FocusItemNotFoundError(tr("error.subject_not_found_id", id=item_id))
            row = connection.execute(
                "SELECT * FROM focus_items WHERE id = ?", (item_id,)
            ).fetchone()
        return focus_item_from_row(row)

    def _set_archived(self, item_id: int, archived: bool) -> None:
        with self._database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE focus_items SET is_archived = ?, updated_at = ?
                WHERE id = ? AND is_archived != ?
                """,
                (int(archived), to_storage_datetime(utc_now()), item_id, int(archived)),
            )
            if cursor.rowcount == 0:
                raise FocusItemNotFoundError(tr("error.subject_not_found_id", id=item_id))


def normalize_focus_item_name(name: str) -> str:
    normalized = " ".join(name.strip().split()) if isinstance(name, str) else ""
    if not normalized or len(normalized) > 80:
        raise InvalidFocusItemError(tr("error.subject_name_invalid"))
    return normalized


def normalize_focus_color(color: str) -> str:
    normalized = color.strip().upper() if isinstance(color, str) else ""
    if not _COLOR_PATTERN.fullmatch(normalized):
        raise InvalidFocusItemError(tr("error.focus_item_color"))
    return normalized


def focus_item_from_row(row: sqlite3.Row | None) -> FocusItem:
    if row is None:
        raise FocusItemNotFoundError(tr("error.subject_row_not_found"))
    return FocusItem(
        id=int(row["id"]),
        name=str(row["name"]),
        color=str(row["color"]),
        is_favorite=bool(row["is_favorite"]),
        is_archived=bool(row["is_archived"]),
        created_at=from_storage_datetime(str(row["created_at"])),
        updated_at=from_storage_datetime(str(row["updated_at"])),
    )
