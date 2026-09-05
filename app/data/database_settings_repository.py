"""Small key/value settings repository backed by SQLite."""

from __future__ import annotations

from app.data.database import Database
from app.data.datetime_utils import to_storage_datetime, utc_now


class DatabaseSettingsRepository:
    """Persist non-visual product preferences and durable flags."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def get(self, key: str, default: str | None = None) -> str | None:
        """Return a setting value or a caller-provided default."""
        with self._database.connect() as connection:
            row = connection.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return default if row is None else str(row["value"])

    def set(self, key: str, value: str) -> None:
        """Upsert one setting value."""
        normalized_key = key.strip()
        if not normalized_key:
            raise ValueError("Setting key cannot be empty.")
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO settings(key, value, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (normalized_key, str(value), to_storage_datetime(utc_now())),
            )

    def delete(self, key: str) -> None:
        """Remove a setting without affecting unrelated values."""
        with self._database.connect() as connection:
            connection.execute("DELETE FROM settings WHERE key = ?", (key,))

