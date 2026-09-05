"""SQLite connection management and forward-only schema migrations."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

CURRENT_SCHEMA_VERSION = 5
logger = logging.getLogger(__name__)


class DatabaseError(RuntimeError):
    """Raised when Desktop Focus Companion cannot initialize or access its database."""


class Database:
    """Own SQLite connections and schema lifecycle."""

    def __init__(self, database_path: Path) -> None:
        self.path = database_path

    def initialize(self) -> None:
        """Create the database and apply every missing forward migration."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                version = int(connection.execute("PRAGMA user_version").fetchone()[0])
                if version > CURRENT_SCHEMA_VERSION:
                    raise DatabaseError(
                        f"Database schema {version} is newer than supported version "
                        f"{CURRENT_SCHEMA_VERSION}."
                    )
                for next_version in range(version + 1, CURRENT_SCHEMA_VERSION + 1):
                    logger.info("Applying database migration %s", next_version)
                    self._apply_migration(connection, next_version)
                    logger.info("Database migration %s applied", next_version)
                self._verify_connection(connection)
        except DatabaseError:
            raise
        except (OSError, sqlite3.Error) as error:
            logger.exception("Database initialization failed for %s", self.path)
            raise DatabaseError("Unable to initialize the Desktop Focus Companion database.") from error

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Yield a configured connection with automatic commit or rollback."""
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(self.path, timeout=5.0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            yield connection
            connection.commit()
        except sqlite3.Error as error:
            if connection is not None:
                connection.rollback()
            logger.exception("SQLite operation failed for %s", self.path)
            raise DatabaseError("Desktop Focus Companion database operation failed.") from error
        except Exception:
            if connection is not None:
                connection.rollback()
            raise
        finally:
            if connection is not None:
                connection.close()

    def schema_version(self) -> int:
        """Return the currently applied schema version."""
        with self.connect() as connection:
            return int(connection.execute("PRAGMA user_version").fetchone()[0])

    def quick_check(self) -> tuple[bool, str]:
        """Run SQLite's lightweight integrity check without modifying data."""
        try:
            with self.connect() as connection:
                rows = connection.execute("PRAGMA quick_check").fetchall()
            messages = tuple(str(row[0]) for row in rows)
            healthy = messages == ("ok",)
            return healthy, "\n".join(messages) if messages else "No result"
        except DatabaseError as error:
            return False, str(error)

    def _apply_migration(self, connection: sqlite3.Connection, version: int) -> None:
        statements: tuple[str, ...]
        if version == 1:
            statements = (
            """
            CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                is_archived INTEGER NOT NULL DEFAULT 0 CHECK (is_archived IN (0, 1)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS study_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id INTEGER NOT NULL,
                subject_name TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                duration_seconds REAL NOT NULL CHECK (duration_seconds >= 0),
                created_at TEXT NOT NULL,
                FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE RESTRICT
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_study_sessions_start_time
            ON study_sessions(start_time)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_study_sessions_subject_id
            ON study_sessions(subject_id)
            """,
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            )
        elif version == 2:
            statements = (
                """
                CREATE TABLE IF NOT EXISTS achievement_unlocks (
                    achievement_key TEXT PRIMARY KEY,
                    unlocked_at TEXT NOT NULL
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS goal_celebrations (
                    local_date TEXT PRIMARY KEY,
                    celebrated_at TEXT NOT NULL
                )
                """,
            )
        elif version == 3:
            statements = (
                """
                ALTER TABLE study_sessions
                ADD COLUMN recovery_token TEXT
                """,
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_study_sessions_recovery_token
                ON study_sessions(recovery_token)
                """,
                """
                CREATE INDEX IF NOT EXISTS idx_study_sessions_end_time
                ON study_sessions(end_time)
                """,
            )
        elif version == 4:
            statements = (
                """
                ALTER TABLE study_sessions
                ADD COLUMN study_mode TEXT NOT NULL DEFAULT 'stopwatch'
                CHECK (study_mode IN ('stopwatch', 'countdown'))
                """,
                """
                ALTER TABLE study_sessions
                ADD COLUMN target_duration_seconds REAL
                CHECK (
                    target_duration_seconds IS NULL
                    OR (target_duration_seconds > 0 AND target_duration_seconds <= 86400)
                )
                """,
            )
        elif version == 5:
            statements = (
                "ALTER TABLE subjects RENAME TO focus_items",
                """
                ALTER TABLE focus_items
                ADD COLUMN color TEXT NOT NULL DEFAULT '#7C5CFC'
                CHECK (length(color) = 7 AND substr(color, 1, 1) = '#')
                """,
                """
                ALTER TABLE focus_items
                ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0
                CHECK (is_favorite IN (0, 1))
                """,
                """
                UPDATE focus_items SET color = CASE ((id - 1) % 8)
                    WHEN 0 THEN '#7C5CFC'
                    WHEN 1 THEN '#3B82F6'
                    WHEN 2 THEN '#14B8A6'
                    WHEN 3 THEN '#22C55E'
                    WHEN 4 THEN '#F59E0B'
                    WHEN 5 THEN '#F97316'
                    WHEN 6 THEN '#EC4899'
                    ELSE '#8B5CF6'
                END
                """,
                "ALTER TABLE study_sessions RENAME TO focus_sessions",
                "ALTER TABLE focus_sessions RENAME COLUMN subject_id TO focus_item_id",
                "ALTER TABLE focus_sessions RENAME COLUMN subject_name TO focus_item_name",
                "ALTER TABLE focus_sessions RENAME COLUMN study_mode TO mode",
                "ALTER TABLE focus_sessions ADD COLUMN note TEXT NOT NULL DEFAULT ''",
                """
                ALTER TABLE focus_sessions
                ADD COLUMN source TEXT NOT NULL DEFAULT 'timer'
                CHECK (source IN ('timer', 'manual'))
                """,
                """
                ALTER TABLE focus_sessions
                ADD COLUMN updated_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00+00:00'
                """,
                "UPDATE focus_sessions SET updated_at = created_at",
                "DROP INDEX IF EXISTS idx_study_sessions_start_time",
                "DROP INDEX IF EXISTS idx_study_sessions_subject_id",
                "DROP INDEX IF EXISTS idx_study_sessions_recovery_token",
                "DROP INDEX IF EXISTS idx_study_sessions_end_time",
                """
                CREATE INDEX idx_focus_sessions_start_time
                ON focus_sessions(start_time)
                """,
                """
                CREATE INDEX idx_focus_sessions_focus_item_id
                ON focus_sessions(focus_item_id)
                """,
                """
                CREATE UNIQUE INDEX idx_focus_sessions_recovery_token
                ON focus_sessions(recovery_token)
                """,
                """
                CREATE INDEX idx_focus_sessions_end_time
                ON focus_sessions(end_time)
                """,
            )
        else:
            raise DatabaseError(f"No migration is available for schema version {version}.")
        for statement in statements:
            connection.execute(statement)
        connection.execute(f"PRAGMA user_version = {version}")
        if version == 1:
            initialized_at = datetime.now(timezone.utc).isoformat()
            connection.execute(
                "INSERT OR REPLACE INTO settings(key, value, updated_at) VALUES (?, ?, ?)",
                ("schema_initialized_at", initialized_at, initialized_at),
            )

    def _verify_connection(self, connection: sqlite3.Connection) -> None:
        quick_check = tuple(str(row[0]) for row in connection.execute("PRAGMA quick_check"))
        if quick_check != ("ok",):
            raise DatabaseError("SQLite integrity verification failed: " + "; ".join(quick_check))
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_errors:
            raise DatabaseError("SQLite foreign-key verification failed after migration.")
