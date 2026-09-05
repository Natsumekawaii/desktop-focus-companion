"""Runtime font-stack and narrow bilingual layout acceptance tests."""

from __future__ import annotations

from datetime import timezone

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QScrollArea

from app.core.theme import (
    THEME_TOKENS,
    font_families_for_language,
    get_theme_manager,
)
from app.i18n import get_localization
from app.ui.dashboard import DashboardPage, DashboardWindow
from app.ui.quick_panel import FocusPanel
from app.ui.settings_dialog import SettingsDialog


def _primary_application_font(qt_application) -> str:
    families = qt_application.font().families()
    assert families
    return families[0]


def test_font_stacks_keep_chinese_on_common_sans_serif_fallbacks() -> None:
    chinese = font_families_for_language("zh-CN")
    english = font_families_for_language("en-US")

    assert chinese == (
        "Microsoft YaHei UI",
        "Microsoft YaHei",
        "DengXian",
        "Noto Sans SC",
        "SimHei",
        "sans-serif",
    )
    assert english[0] == "Segoe UI"
    assert "Microsoft YaHei UI" in english
    assert "SimSun" not in chinese
    assert font_families_for_language(None) == english


def test_runtime_language_switch_updates_font_stack_without_changing_theme(
    qt_application,
) -> None:
    localization = get_localization()
    theme_manager = get_theme_manager()
    original_language = localization.language
    original_theme = theme_manager.theme_name

    try:
        theme_manager.set_theme("dark")
        localization.set_language("en-US")
        qt_application.processEvents()
        initial_palette = qt_application.palette().color(QPalette.ColorRole.Window)
        assert _primary_application_font(qt_application) == "Segoe UI"

        localization.set_language("zh-CN")
        qt_application.processEvents()
        assert _primary_application_font(qt_application) == "Microsoft YaHei UI"
        assert theme_manager.theme_name == "dark"
        assert qt_application.palette().color(QPalette.ColorRole.Window) == initial_palette
        assert initial_palette.name() == THEME_TOKENS["dark"].canvas

        localization.set_language("en-US")
        qt_application.processEvents()
        assert _primary_application_font(qt_application) == "Segoe UI"
        assert theme_manager.theme_name == "dark"
        assert qt_application.palette().color(QPalette.ColorRole.Window) == initial_palette
    finally:
        localization.set_language(original_language)
        theme_manager.set_theme(original_theme)


def test_live_bilingual_font_switch_keeps_all_narrow_surfaces_overflow_free(
    qt_application,
) -> None:
    localization = get_localization()
    original_language = localization.language
    dashboard = DashboardWindow(timezone.utc)
    settings = SettingsDialog()
    panel = FocusPanel()
    dashboard.resize(760, 520)
    settings.resize(620, 440)
    panel.resize(320, 600)
    dashboard.show()
    settings.show()
    panel.show()

    try:
        for language, primary_font in (
            ("en-US", "Segoe UI"),
            ("zh-CN", "Microsoft YaHei UI"),
            ("en-US", "Segoe UI"),
        ):
            localization.set_language(language)
            qt_application.processEvents()
            assert _primary_application_font(qt_application) == primary_font

            for page in DashboardPage:
                dashboard.set_current_page(page)
                qt_application.processEvents()
                root = dashboard._pages.widget(int(page))
                if isinstance(root, QScrollArea):
                    assert root.horizontalScrollBar().maximum() == 0

            for index in range(settings._pages.count()):
                settings._select_page(index)
                qt_application.processEvents()
                scroll = settings._pages.widget(index).findChild(QScrollArea)
                assert scroll is not None
                assert scroll.horizontalScrollBar().maximum() == 0

            for index in range(panel._panel_stack.count()):
                panel._panel_stack.setCurrentIndex(index)
                qt_application.processEvents()
                scroll = panel._panel_stack.currentWidget()
                assert isinstance(scroll, QScrollArea)
                assert scroll.horizontalScrollBar().maximum() == 0
    finally:
        panel.close()
        settings.close()
        dashboard.close()
        localization.set_language(original_language)
