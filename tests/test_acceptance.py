"""Cross-feature acceptance tests for Desktop Focus Companion acceptance."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.data.database import Database
from app.data.database_settings_repository import DatabaseSettingsRepository
from app.data.focus_item_repository import FocusItemRepository
from app.data.focus_session_repository import FocusSessionRepository
from app.data.gamification_repository import GamificationRepository
from app.data.models import FocusSessionSource
from app.focus import ManualFocusEntry, ManualFocusEntryService
from app.focus_mode import FocusMode
from app.gamification import GamificationService
from app.statistics import StatisticsPeriod, StatisticsService
from app.timer.active_session_store import (
    CHECKPOINT_VERSION,
    ActiveSessionCheckpoint,
    ActiveSessionStore,
)


def _repositories(tmp_path: Path):
    database = Database(tmp_path / "desktop-focus-companion.sqlite3")
    database.initialize()
    return database, FocusItemRepository(database), FocusSessionRepository(database)


def test_focus_item_lifecycle_is_immediately_durable(tmp_path: Path) -> None:
    database, items, _sessions = _repositories(tmp_path)
    created = items.create("Fitness", "#3B82F6")

    renamed = items.rename(created.id, "Strength Training")
    recolored = items.set_color(created.id, "#EC4899")
    favorite = items.set_favorite(created.id, True)
    items.archive(created.id)
    restored = items.restore(created.id)
    reopened = FocusItemRepository(database).get(created.id)

    assert renamed.name == "Strength Training"
    assert recolored.color == "#EC4899"
    assert favorite.is_favorite
    assert not restored.is_archived
    assert reopened == restored


def test_timer_and_manual_records_share_all_analytics_goals_and_streaks(
    tmp_path: Path,
) -> None:
    database, items, sessions = _repositories(tmp_path)
    reading = items.create("Reading", "#3B82F6")
    fitness = items.create("Fitness", "#14B8A6")
    monday = datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc)
    today = datetime(2026, 8, 12, 18, 0, tzinfo=timezone.utc)
    sessions.create(
        reading,
        monday,
        monday + timedelta(minutes=20),
        1200,
        mode=FocusMode.COUNTDOWN,
        target_duration_seconds=1500,
        note="Chapter 4",
    )
    manual = ManualFocusEntryService(items, sessions).create(
        ManualFocusEntry(
            fitness.id,
            today - timedelta(minutes=30),
            today,
            1800,
            "Evening workout",
        )
    )
    statistics = StatisticsService(sessions, timezone.utc)
    progression = GamificationService(
        statistics,
        DatabaseSettingsRepository(database),
        GamificationRepository(database),
    )
    progression.set_preferences(1800, 1800, 3000)

    month = statistics.monthly_statistics(2026, 8)
    heatmap = statistics.heatmap_data(7, today)
    snapshot = progression.snapshot(today)

    assert manual.source is FocusSessionSource.MANUAL
    assert manual.note == "Evening workout"
    assert statistics.today_total(today) == 1800
    assert sum(item.duration_seconds for item in statistics.daily_totals(7, today)) == 3000
    assert month.total_seconds == 3000
    assert sum(item.duration_seconds for item in heatmap.days) == 3000
    assert {
        item.focus_item_name: item.duration_seconds
        for item in statistics.focus_item_totals(StatisticsPeriod.ALL_TIME, today)
    } == {"Fitness": 1800, "Reading": 1200}
    assert snapshot.goal_completed
    assert snapshot.weekly_goal_completed
    assert snapshot.streak_days == 1


def test_active_item_list_uses_name_order_and_excludes_archived(
    tmp_path: Path,
) -> None:
    _database, items, sessions = _repositories(tmp_path)
    favorite = items.create("Favorite")
    recent_old = items.create("Older")
    recent_new = items.create("Newer")
    archived = items.create("Archived")
    items.set_favorite(favorite.id, True)
    items.archive(archived.id)
    start = datetime(2026, 8, 15, 8, 0, tzinfo=timezone.utc)
    sessions.create(recent_old, start, start + timedelta(minutes=10), 600)
    sessions.create(
        favorite,
        start + timedelta(hours=1),
        start + timedelta(hours=1, minutes=10),
        600,
    )
    sessions.create(
        recent_new,
        start + timedelta(hours=2),
        start + timedelta(hours=2, minutes=10),
        600,
    )

    active = items.list_active()

    assert [item.name for item in active] == ["Favorite", "Newer", "Older"]
    assert archived.id not in {item.id for item in active}


def test_checkpoint_v4_writes_canonical_fields_and_loads_v3(tmp_path: Path) -> None:
    path = tmp_path / "active-session.json"
    store = ActiveSessionStore(path)
    now = datetime(2026, 8, 15, 9, 0, tzinfo=timezone.utc)
    checkpoint = ActiveSessionCheckpoint(
        recovery_token="token-v4",
        focus_item_id=7,
        focus_item_name="Reading",
        start_time=now,
        accumulated_seconds=900,
        timer_state="PAUSED",
        last_checkpoint=now + timedelta(minutes=15),
        mode=FocusMode.COUNTDOWN.value,
        target_duration_seconds=1500,
        note="Chapter 4",
    )

    store.save(checkpoint)
    current_payload = json.loads(path.read_text(encoding="utf-8"))

    assert current_payload["version"] == CHECKPOINT_VERSION == 4
    assert current_payload["focus_item_id"] == 7
    assert current_payload["mode"] == "countdown"
    assert "subject_id" not in current_payload
    assert "study_mode" not in current_payload

    legacy_payload = dict(current_payload)
    legacy_payload["version"] = 3
    legacy_payload["subject_id"] = legacy_payload.pop("focus_item_id")
    legacy_payload["subject_name"] = legacy_payload.pop("focus_item_name")
    legacy_payload["study_mode"] = legacy_payload.pop("mode")
    path.write_text(json.dumps(legacy_payload), encoding="utf-8")

    recovered = store.load()

    assert recovered is not None
    assert recovered.focus_item_id == 7
    assert recovered.focus_item_name == "Reading"
    assert recovered.mode == FocusMode.COUNTDOWN.value
    assert recovered.note == "Chapter 4"
