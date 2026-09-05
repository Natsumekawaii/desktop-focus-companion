"""Tests for SQLite initialization, migrations, and legacy data safety."""

import sqlite3
from pathlib import Path

import pytest

from app.core.paths import ApplicationPaths
from app.data.database import CURRENT_SCHEMA_VERSION, Database, DatabaseError
from app.data.database_settings_repository import DatabaseSettingsRepository
from app.data.focus_item_repository import FocusItemRepository
from app.data.focus_session_repository import FocusSessionRepository
from app.data.session_repository import SessionRepository


def test_database_initializes_versioned_schema_idempotently(tmp_path: Path) -> None:
    database = Database(tmp_path / "data" / "desktop-focus-companion.sqlite3")

    database.initialize()
    database.initialize()

    assert database.schema_version() == CURRENT_SCHEMA_VERSION
    with database.connect() as connection:
        table_names = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert {"focus_items", "focus_sessions", "settings"}.issubset(table_names)
    assert "subjects" not in table_names
    assert "study_sessions" not in table_names


def test_database_settings_round_trip(tmp_path: Path) -> None:
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    settings = DatabaseSettingsRepository(database)

    assert settings.get("daily_goal", "7200") == "7200"
    settings.set("daily_goal", "3600")
    assert settings.get("daily_goal") == "3600"
    settings.delete("daily_goal")
    assert settings.get("daily_goal") is None


def test_prepare_data_directory_does_not_import_project_data(tmp_path: Path) -> None:
    project_data = tmp_path / "data"
    project_pet = project_data / "pets" / "custom" / "pet.png"
    project_pet.parent.mkdir(parents=True)
    project_pet.write_bytes(b"unrelated-pet")
    project_settings = project_data / "settings.json"
    project_settings.write_text('{"pet_size_percent": 125}', encoding="utf-8")
    paths = ApplicationPaths(
        project_root=tmp_path,
        assets_dir=tmp_path / "assets",
        data_dir=tmp_path / "local-app-data",
    )

    paths.prepare_data_directory()

    assert paths.data_dir.is_dir()
    assert not paths.settings_path.exists()
    assert not (paths.data_dir / "pets" / "custom" / "pet.png").exists()
    assert project_pet.read_bytes() == b"unrelated-pet"
    assert project_settings.exists()


def test_discovered_windows_paths_use_the_new_product_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    paths = ApplicationPaths.discover()

    assert paths.data_dir == tmp_path / "DesktopFocusCompanion"
    assert paths.database_path.name == "desktop-focus-companion.sqlite3"
    assert paths.instance_lock_path.name == "desktop-focus-companion.lock"
    assert paths.application_icon_path.name == "desktop-focus-companion.ico"


def test_version_two_database_migrates_to_current_session_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "version-two.sqlite3"
    database = Database(database_path)
    with database.connect() as connection:
        database._apply_migration(connection, 1)
        database._apply_migration(connection, 2)

    database.initialize()

    assert database.schema_version() == CURRENT_SCHEMA_VERSION
    with database.connect() as connection:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(focus_sessions)")}
        indexes = {row["name"] for row in connection.execute("PRAGMA index_list(focus_sessions)")}
    assert "recovery_token" in columns
    assert "mode" in columns
    assert "target_duration_seconds" in columns
    assert "note" in columns
    assert "source" in columns
    assert "updated_at" in columns
    assert "idx_focus_sessions_end_time" in indexes
    assert "idx_focus_sessions_recovery_token" in indexes


def test_existing_rows_migrate_to_stopwatch_without_a_target(tmp_path: Path) -> None:
    database_path = tmp_path / "version-three.sqlite3"
    database = Database(database_path)
    with database.connect() as connection:
        database._apply_migration(connection, 1)
        database._apply_migration(connection, 2)
        database._apply_migration(connection, 3)
        connection.execute(
            """
            INSERT INTO subjects(id, name, is_archived, created_at, updated_at)
            VALUES (1, 'Legacy', 0, ?, ?)
            """,
            ("2026-08-14T09:00:00+00:00", "2026-08-14T09:00:00+00:00"),
        )
        connection.execute(
            """
            INSERT INTO study_sessions(
                subject_id, subject_name, start_time, end_time,
                duration_seconds, created_at, recovery_token
            ) VALUES (1, 'Legacy', ?, ?, 1800, ?, NULL)
            """,
            (
                "2026-08-14T10:00:00+00:00",
                "2026-08-14T10:30:00+00:00",
                "2026-08-14T10:30:00+00:00",
            ),
        )

    database.initialize()
    session = SessionRepository(database).list_sessions()[0]

    assert database.schema_version() == CURRENT_SCHEMA_VERSION
    assert session.study_mode == "stopwatch"
    assert session.target_duration_seconds is None
    assert session.duration_seconds == 1800


def test_v1_fixture_migrates_without_losing_identity_history_or_preferences(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "desktop-focus-companion.sqlite3"
    settings_path = tmp_path / "settings.json"
    settings_json = (
        '{"language":"zh-CN","color_theme":"dark",'
        '"pet_path":"pets/custom/my-pet.png",'
        '"app_icon_path":"icons/custom/my-icon.png"}'
    )
    settings_path.write_text(settings_json, encoding="utf-8")
    database = Database(database_path)
    with database.connect() as connection:
        for version in range(1, 5):
            database._apply_migration(connection, version)
        created = "2026-08-14T08:00:00+00:00"
        connection.execute(
            """
            INSERT INTO subjects(id, name, is_archived, created_at, updated_at)
            VALUES (41, 'Legacy Reading', 0, ?, ?)
            """,
            (created, created),
        )
        connection.execute(
            """
            INSERT INTO study_sessions(
                id, subject_id, subject_name, start_time, end_time,
                duration_seconds, created_at, recovery_token, study_mode,
                target_duration_seconds
            ) VALUES (99, 41, 'Legacy Reading', ?, ?, 1800, ?, NULL, 'countdown', 3600)
            """,
            (
                "2026-08-14T08:00:00+00:00",
                "2026-08-14T08:30:00+00:00",
                "2026-08-14T08:30:00+00:00",
            ),
        )
        connection.execute(
            """
            INSERT OR REPLACE INTO settings(key, value, updated_at)
            VALUES ('daily_goal_seconds', '7200', ?),
                   ('weekly_goal_seconds', '28800', ?),
                   ('streak_minimum_seconds', '1500', ?)
            """,
            (created, created, created),
        )
        connection.execute(
            "INSERT INTO goal_celebrations(local_date, celebrated_at) VALUES (?, ?)",
            ("2026-08-14", created),
        )
        connection.execute(
            "INSERT INTO achievement_unlocks(achievement_key, unlocked_at) VALUES (?, ?)",
            ("legacy-achievement", created),
        )

    database.initialize()

    item = FocusItemRepository(database).get(41)
    session = FocusSessionRepository(database).get(99)
    preferences = DatabaseSettingsRepository(database)
    with database.connect() as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        goal_count = connection.execute("SELECT COUNT(*) FROM goal_celebrations").fetchone()[0]
        achievement_count = connection.execute(
            "SELECT COUNT(*) FROM achievement_unlocks"
        ).fetchone()[0]

    assert item.id == 41
    assert item.name == "Legacy Reading"
    assert item.color.startswith("#")
    assert session.id == 99
    assert session.focus_item_id == 41
    assert session.focus_item_name == "Legacy Reading"
    assert session.mode.value == "countdown"
    assert session.target_duration_seconds == 3600
    assert session.duration_seconds == 1800  # XP remains derivable from actual duration.
    assert session.note == ""
    assert session.source.value == "timer"
    assert preferences.get("daily_goal_seconds") == "7200"
    assert preferences.get("weekly_goal_seconds") == "28800"
    assert preferences.get("streak_minimum_seconds") == "1500"
    assert goal_count == 1
    assert achievement_count == 1
    assert {"focus_items", "focus_sessions"}.issubset(tables)
    assert settings_path.read_text(encoding="utf-8") == settings_json


def test_failed_migration_rolls_back_schema_and_version(tmp_path: Path) -> None:
    database_path = tmp_path / "rollback.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "CREATE TABLE study_sessions (id INTEGER PRIMARY KEY, end_time TEXT NOT NULL)"
        )
        connection.execute("PRAGMA user_version = 2")

    class FailingMigrationDatabase(Database):
        def _apply_migration(self, connection, version):
            connection.execute("ALTER TABLE study_sessions ADD COLUMN partial_change TEXT")
            raise sqlite3.OperationalError("simulated migration failure")

    with pytest.raises(DatabaseError):
        FailingMigrationDatabase(database_path).initialize()

    with sqlite3.connect(database_path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        columns = {row[1] for row in connection.execute("PRAGMA table_info(study_sessions)")}
    assert version == 2
    assert "partial_change" not in columns


def test_schema_v5_minute_precision_cleanup_is_atomic_and_idempotent(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "minute-precision.sqlite3")
    database.initialize()
    items = FocusItemRepository(database)
    item = items.create("Legacy")
    created = "2026-08-14T08:00:00+00:00"
    with database.connect() as connection:
        for session_id, duration in enumerate((30.0, 59.9, 119.0, 120.0), start=1):
            connection.execute(
                """
                INSERT INTO focus_sessions(
                    id, focus_item_id, focus_item_name, start_time, end_time,
                    duration_seconds, created_at, recovery_token, mode,
                    target_duration_seconds, note, source, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 'stopwatch', NULL, '', 'timer', ?)
                """,
                (
                    session_id,
                    item.id,
                    item.name,
                    created,
                    "2026-08-14T08:02:00+00:00",
                    duration,
                    created,
                    created,
                ),
            )
    repository = FocusSessionRepository(database)

    result = repository.ensure_minute_precision()

    assert result.deleted_sessions == 2
    assert result.normalized_sessions == 1
    assert [session.duration_seconds for session in repository.list_sessions()] == [
        120,
        60,
    ]
    assert repository.ensure_minute_precision().deleted_sessions == 0
    assert [session.duration_seconds for session in repository.list_sessions()] == [
        120,
        60,
    ]


def test_minute_precision_cleanup_rolls_back_when_any_step_fails(tmp_path: Path) -> None:
    database = Database(tmp_path / "minute-rollback.sqlite3")
    database.initialize()
    item = FocusItemRepository(database).create("Protected")
    created = "2026-08-14T08:00:00+00:00"
    with database.connect() as connection:
        connection.execute(
            """
            INSERT INTO focus_sessions(
                focus_item_id, focus_item_name, start_time, end_time,
                duration_seconds, created_at, recovery_token, mode,
                target_duration_seconds, note, source, updated_at
            ) VALUES (?, ?, ?, ?, 30, ?, NULL, 'stopwatch', NULL, '', 'timer', ?)
            """,
            (
                item.id,
                item.name,
                created,
                "2026-08-14T08:01:00+00:00",
                created,
                created,
            ),
        )
        connection.execute(
            """
            CREATE TRIGGER reject_short_session_cleanup
            BEFORE DELETE ON focus_sessions
            BEGIN SELECT RAISE(ABORT, 'simulated cleanup failure'); END
            """
        )

    with pytest.raises(DatabaseError):
        FocusSessionRepository(database).ensure_minute_precision()

    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM focus_sessions").fetchone()[0] == 1
        assert connection.execute(
            "SELECT 1 FROM settings WHERE key = 'focus_session_minute_precision_v1_initialized'"
        ).fetchone() is None
