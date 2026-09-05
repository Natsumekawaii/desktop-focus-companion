"""Regression gates for request-scoped Dashboard statistics reads."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.data.database import Database
from app.data.focus_item_repository import FocusItemRepository
from app.data.focus_session_repository import FocusSessionRepository
from app.statistics import StatisticsService
from app.ui.dashboard import DashboardWindow
from app.ui.dashboard_controller import DashboardController


class _CountingFocusSessionRepository(FocusSessionRepository):
    def __init__(self, database: Database) -> None:
        super().__init__(database)
        self.unbounded_reads = 0
        self.overlap_ranges: list[tuple[datetime, datetime]] = []

    def list_sessions(
        self,
        start_at=None,
        end_before=None,
        focus_item_id=None,
        limit=None,
    ):
        if (
            start_at is None
            and end_before is None
            and focus_item_id is None
            and limit is None
        ):
            self.unbounded_reads += 1
        return super().list_sessions(start_at, end_before, focus_item_id, limit)

    def list_overlapping(self, start_at: datetime, end_before: datetime):
        self.overlap_ranges.append((start_at, end_before))
        return super().list_overlapping(start_at, end_before)


def test_complete_dashboard_refresh_uses_one_unbounded_history_read(
    qt_application, tmp_path: Path
) -> None:
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    focus_items = FocusItemRepository(database)
    focus_items.ensure_defaults()
    sessions = _CountingFocusSessionRepository(database)
    window = DashboardWindow(timezone.utc)
    controller = DashboardController(
        window, StatisticsService(sessions, timezone.utc), focus_items, sessions
    )

    controller.refresh()

    assert sessions.unbounded_reads == 1
    activity_ranges = [
        (start, end)
        for start, end in sessions.overlap_ranges
        if (end - start).days >= 365
    ]
    assert len(activity_ranges) == 1
    controller._replay_dialog.close()
    window.close()
