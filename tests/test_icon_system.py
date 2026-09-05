"""Unified theme-aware icon language tests."""

from datetime import timezone

from app.core.icon_system import IconName, IconSystem
from app.core.theme import get_theme_manager
from app.ui.dashboard import DashboardWindow
from app.ui.settings_dialog import SettingsDialog


def test_every_semantic_icon_renders(qt_application) -> None:
    for name in IconName:
        icon = IconSystem.icon(name)
        assert not icon.isNull()
        assert not icon.pixmap(20, 20).isNull()


def test_settings_and_dashboard_use_one_theme_aware_icon_system(qt_application) -> None:
    manager = get_theme_manager()
    previous = manager.theme_name
    settings = SettingsDialog()
    dashboard = DashboardWindow(timezone.utc)

    assert all(
        not settings._tabs.tabIcon(index).isNull()
        for index in range(settings._tabs.count())
    )
    assert all(
        not dashboard._tabs.tabIcon(index).isNull()
        for index in range(dashboard._tabs.count())
    )
    old_settings_key = settings._tabs.tabIcon(0).cacheKey()
    old_dashboard_key = dashboard._tabs.tabIcon(0).cacheKey()

    manager.set_theme("pink" if previous != "pink" else "blue")

    assert settings._tabs.tabIcon(0).cacheKey() != old_settings_key
    assert dashboard._tabs.tabIcon(0).cacheKey() != old_dashboard_key
    settings.close()
    dashboard.close()
    manager.set_theme(previous)
