"""Failure injection, request snapshots and legacy compatibility contracts."""

from __future__ import annotations

from datetime import timezone

import pytest
from PySide6.QtWidgets import QMessageBox

from app import application
from app.core.paths import ApplicationPaths
from app.data.database import Database, DatabaseError
from app.data.focus_item_repository import FocusItemRepository
from app.data.focus_session_repository import FocusSessionRepository
from app.statistics import StatisticsService


@pytest.mark.parametrize("stage", ["directory", "logging", "lock", "runtime"])
def test_startup_failure_is_reported_and_acquired_lock_is_released(
    tmp_path, monkeypatch, stage
):
    errors, releases = [], []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: errors.append(args[-1]))
    monkeypatch.setattr(application, "configure_logging", lambda *_: None)

    def fail(*_args, **_kwargs):
        raise OSError("synthetic startup failure")

    class Guard:
        def __init__(self, *args, **kwargs):
            pass

        def acquire(self):
            if stage == "lock":
                fail()
            return True

        def release(self):
            releases.append(True)

    monkeypatch.setattr(application, "SingleInstanceGuard", Guard)
    monkeypatch.setattr(application, "build_runtime", fail)
    if stage == "directory":
        monkeypatch.setattr(ApplicationPaths, "prepare_data_directory", fail)
    if stage == "logging":
        monkeypatch.setattr(application, "configure_logging", fail)
    paths = ApplicationPaths(tmp_path, tmp_path, tmp_path / "data")
    assert application.run_application(paths=paths) == 1
    assert len(errors) == 1
    assert bool(releases) == (stage in ("lock", "runtime"))


def test_timezone_snapshot_changes_only_between_operations(tmp_path, monkeypatch):
    from zoneinfo import ZoneInfo

    import app.statistics.statistics_service as module

    database = Database(tmp_path / "test.sqlite3")
    database.initialize()
    current = ZoneInfo("Etc/UTC")
    monkeypatch.setattr(module, "_system_local_timezone", lambda: current)
    service = StatisticsService(FocusSessionRepository(database))
    with service.timezone_context():
        assert service.local_timezone.key == "Etc/UTC"
        current = ZoneInfo("Asia/Shanghai")
        assert service.local_timezone.key == "Etc/UTC"
        service.progress_snapshot()
    assert service.local_timezone.key == "Asia/Shanghai"
    explicit = StatisticsService(FocusSessionRepository(database), timezone.utc)
    assert explicit.local_timezone == timezone.utc


def test_metrics_and_progress_each_read_once_and_are_not_cached(tmp_path, monkeypatch):
    database = Database(tmp_path / "test.sqlite3")
    database.initialize()
    items = FocusItemRepository(database)
    items.ensure_defaults()
    repository = FocusSessionRepository(database)
    original = repository.list_sessions
    calls = []

    def read(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(repository, "list_sessions", read)
    service = StatisticsService(repository, timezone.utc)
    service.focus_item_metrics()
    assert len(calls) == 1
    service.progress_snapshot()
    assert len(calls) == 2
    service.progress_snapshot()
    assert len(calls) == 3


def test_refresh_database_errors_remain_recoverable(tmp_path, monkeypatch):
    paths = ApplicationPaths(
        tmp_path, application.ApplicationPaths.discover().assets_dir, tmp_path / "data"
    )
    runtime = application.build_runtime(paths, development=True)
    errors = []
    monkeypatch.setattr(
        runtime.dashboard_window, "show_data_error", lambda *args: errors.append(args)
    )
    monkeypatch.setattr(
        runtime.quick_panel, "show_error", lambda *args: errors.append(args)
    )

    def fail(*args, **kwargs):
        raise DatabaseError("synthetic database failure")

    original = runtime.focus_session_repository.list_sessions
    monkeypatch.setattr(runtime.focus_session_repository, "list_sessions", fail)
    runtime.dashboard_controller.refresh()
    runtime.quick_panel_controller.refresh_summary()
    runtime.gamification_controller.refresh()
    assert errors
    monkeypatch.setattr(runtime.focus_session_repository, "list_sessions", original)
    runtime.dashboard_controller.refresh()
    runtime.quick_panel_controller.refresh_summary()
    runtime.gamification_controller.refresh()


def test_legacy_aliases_remain_identical():
    from app.data.focus_item_repository import DuplicateFocusItemError
    from app.data.subject_repository import DuplicateSubjectError
    from app.focus_mode import FocusMode
    from app.study_mode import StudyMode
    from app.timer.focus_timer import FocusTimer
    from app.timer.study_timer import StudyTimer

    assert StudyTimer is FocusTimer
    assert StudyMode is FocusMode
    assert DuplicateSubjectError is DuplicateFocusItemError


def test_internal_splits_keep_original_import_identities():
    from app.core import theme, theme_tokens
    from app.ui import activity_layout, heatmap_widget

    assert theme.ThemeTokens is theme_tokens.ThemeTokens
    assert theme.THEME_TOKENS is theme_tokens.THEME_TOKENS
    assert heatmap_widget.FocusActivityMode is activity_layout.FocusActivityMode
    assert heatmap_widget._GridGeometry is activity_layout._GridGeometry
