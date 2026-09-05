"""Persistence for one-time study progress events."""

from __future__ import annotations

from datetime import date

from app.data.database import Database
from app.data.datetime_utils import to_storage_datetime, utc_now


class GamificationRepository:
    """Persist per-day goal celebration guards."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def mark_goal_celebrated(self, local_day: date) -> bool:
        """Record a local goal celebration once per calendar day."""
        with self._database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO goal_celebrations(local_date, celebrated_at)
                VALUES (?, ?)
                """,
                (local_day.isoformat(), to_storage_datetime(utc_now())),
            )
            return cursor.rowcount == 1
