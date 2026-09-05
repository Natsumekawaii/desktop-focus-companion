"""Project-level localization, runtime switching, and persistence tests."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.application import build_runtime
from app.core.paths import ApplicationPaths
from app.data.settings_repository import AppSettings, SettingsRepository
from app.i18n import format_date, format_weekday, get_localization, tr


@pytest.fixture(autouse=True)
def restore_english_language():
    get_localization().set_language("en-US")
    yield
    get_localization().set_language("en-US")


def test_translation_switches_immediately_and_formats_locale_dates() -> None:
    localization = get_localization()

    assert tr("settings.language") == "Language:"
    assert format_date(date(2026, 8, 14)) == "August 14, 2026"
    assert format_weekday(date(2026, 8, 14), short=False) == "Friday"

    assert localization.set_language("zh-CN")
    assert tr("settings.language") == "语言："
    assert format_date(date(2026, 8, 14)) == "2026年8月14日"
    assert format_weekday(date(2026, 8, 14), short=False) == "星期五"


def test_focus_streak_copy_is_natural_and_uses_dashboard_value_hierarchy() -> None:
    localization = get_localization()

    localization.set_language("en-US")
    assert tr("dashboard.goal_streak") == "Focus Streak"
    assert tr("dashboard.streak.one", count=1) == "1 day"
    assert tr("dashboard.streak.other", count=3) == "3 days"
    assert tr("quick.streak.other", count=3) == "3-day focus streak"
    assert tr("analytics.consistency_title") == "Focus Streaks"
    assert tr("analytics.current_consistency") == "Current streak"
    assert tr("analytics.longest_consistency") == "Longest streak"

    localization.set_language("zh-CN")
    assert tr("dashboard.goal_streak") == "连续专注"
    assert tr("dashboard.streak.one", count=1) == "1 天"
    assert tr("dashboard.streak.other", count=3) == "3 天"
    assert tr("quick.streak.other", count=3) == "连续专注 3 天"
    assert tr("analytics.consistency_title") == "连续专注记录"
    assert tr("analytics.current_consistency") == "当前连续天数"
    assert tr("analytics.longest_consistency") == "最长连续天数"


def test_language_setting_round_trip_and_invalid_value_falls_back(tmp_path: Path) -> None:
    repository = SettingsRepository(tmp_path / "settings.json")
    repository.save(AppSettings(language="zh-CN"))
    assert repository.load().language == "zh-CN"

    (tmp_path / "settings.json").write_text(
        json.dumps({"language": "not-a-locale"}), encoding="utf-8"
    )
    assert repository.load().language == "en-US"


def test_runtime_language_change_updates_all_primary_views_and_persists(
    qt_application, tmp_path: Path
) -> None:
    project_root = Path(__file__).resolve().parents[1]
    paths = ApplicationPaths(project_root, project_root / "assets", tmp_path / "profile")
    runtime = build_runtime(paths)

    assert runtime.settings_dialog.windowTitle() == "Settings"
    assert runtime.dashboard_window.windowTitle() == "Focus Center"
    assert runtime.dashboard_window._tabs.tabText(0) == "Overview"
    assert runtime.quick_panel._focus_item_caption.text() == "Focus item"
    assert runtime.pet_window.accessibleName() == "Desktop Focus Companion desktop companion"

    runtime.settings_dialog._language_combo.setCurrentIndex(
        runtime.settings_dialog._language_combo.findData("zh-CN")
    )
    qt_application.processEvents()

    assert runtime.settings_dialog.windowTitle() == "设置"
    assert runtime.dashboard_window.windowTitle() == "专注中心"
    assert runtime.dashboard_window._tabs.tabText(0) == "概览"
    assert "历史记录" in [
        runtime.dashboard_window._tabs.tabText(index)
        for index in range(runtime.dashboard_window._tabs.count())
    ]
    assert "Good " not in runtime.dashboard_window._greeting_label.text()
    assert runtime.quick_panel._focus_item_caption.text() == "专注项目"
    assert runtime.pet_window.accessibleName() == "Desktop Focus Companion 桌面伙伴"
    assert SettingsRepository(paths.settings_path).load().language == "zh-CN"

    runtime.settings_dialog.close()
    runtime.focus_item_dialog.close()
    runtime.quick_panel.hide()
    runtime.dashboard_window.close()
    runtime.pet_window.close()

    restarted = build_runtime(paths)
    assert get_localization().language == "zh-CN"
    assert restarted.settings_dialog.windowTitle() == "设置"
    assert restarted.dashboard_window.windowTitle() == "专注中心"
    assert "月度" in [
        restarted.dashboard_window._tabs.tabText(index)
        for index in range(restarted.dashboard_window._tabs.count())
    ]

    restarted.settings_dialog.close()
    restarted.focus_item_dialog.close()
    restarted.quick_panel.hide()
    restarted.dashboard_window.close()
    restarted.pet_window.close()
