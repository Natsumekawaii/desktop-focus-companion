"""Unified theme-aware icon language tests."""

from datetime import timezone

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QIcon

from app.core.icon_system import IconName, IconSystem
from app.core.theme import COLOR_THEMES, get_theme_manager
from app.ui.dashboard import DashboardWindow
from app.ui.settings_dialog import SettingsDialog


def test_every_semantic_icon_renders(qt_application) -> None:
    for name in IconName:
        icon = IconSystem.icon(name)
        assert not icon.isNull()
        assert not icon.pixmap(20, 20).isNull()


@pytest.mark.parametrize("theme", COLOR_THEMES)
@pytest.mark.parametrize("size", [16, 20, 24, 32])
def test_assistant_bot_is_crisp_themed_and_has_no_bubble_tail(qt_application, theme, size):
    manager = get_theme_manager()
    manager.set_theme(theme)
    icon = IconSystem.icon(IconName.ASSISTANT, size)
    for mode, color in (
        (QIcon.Mode.Normal, manager.tokens.primary),
        (QIcon.Mode.Selected, manager.tokens.primary),
        (QIcon.Mode.Disabled, manager.tokens.disabled),
    ):
        image = icon.pixmap(QSize(size, size), 2.0, mode).toImage()
        extent = image.width()
        assert extent == size * 2 and image.height() == extent
        solid = [image.pixelColor(x, y) for x in range(extent) for y in range(extent)
                 if image.pixelColor(x, y).alpha() == 255]
        expected = QColor(color)
        assert expected in solid
        # Overlapping antialiased strokes can round one premultiplied channel.
        assert all(abs(actual - target) <= 1 for pixel in solid
                   for actual, target in zip(pixel.getRgb(), expected.getRgb(), strict=True))
        assert all(image.pixelColor(x, y).alpha() == 0
                   for x in range(extent) for y in (0, extent - 1))
        assert all(image.pixelColor(x, y).alpha() == 0
                   for y in range(extent) for x in (0, extent - 1))
        # Central antenna and two eyes, without the old speech-bubble tail.
        assert all(image.pixelColor(int(x * extent / 20), int(y * extent / 20)).alpha() > 0
                   for x, y in ((10, 3), (7.5, 10.5), (12.5, 10.5)))
        assert image.pixelColor(int(5 * extent / 20), int(18 * extent / 20)).alpha() == 0


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
