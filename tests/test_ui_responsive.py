"""Responsive, bilingual, and accessible UI acceptance checks."""

from __future__ import annotations

from datetime import date, timedelta, timezone

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QScrollArea

from app.core.theme import COLOR_THEMES
from app.i18n import get_localization, tr
from app.statistics import FocusItemTotal, HeatmapData, HeatmapDay
from app.ui.analytics_widgets import FocusDistributionChart
from app.ui.dashboard import DashboardPage, DashboardWindow
from app.ui.heatmap_widget import FocusActivityMode, HeatmapWidget
from app.ui.quick_panel import FocusPanel
from app.ui.settings_dialog import SettingsDialog


def test_dashboard_reflows_without_horizontal_page_scrolling(qt_application) -> None:
    localization = get_localization()
    original_language = localization.language
    try:
        for language in ("en-US", "zh-CN"):
            localization.set_language(language)
            window = DashboardWindow(timezone.utc)
            for width, height, expected_sidebar in (
                (760, 520, 68),
                (1024, 640, 208),
                (1280, 800, 208),
            ):
                window.resize(width, height)
                window.show()
                qt_application.processEvents()
                assert window._sidebar.width() == expected_sidebar
                assert window._sidebar.findChild(QLabel, "sidebarBrand") is None
                overview = window._pages.widget(int(DashboardPage.OVERVIEW))
                assert overview.accessibleName() == tr("dashboard.tab.overview")
                assert all(
                    label.text() != tr("app.name")
                    for label in overview.findChildren(QLabel)
                )
                for page in DashboardPage:
                    window.set_current_page(page)
                    qt_application.processEvents()
                    assert window.current_page() is page
                    assert window._pages.currentWidget().graphicsEffect() is None
                    root = window._pages.widget(int(page))
                    if isinstance(root, QScrollArea):
                        assert root.horizontalScrollBar().maximum() == 0, (
                            language,
                            width,
                            page,
                            root.horizontalScrollBar().maximum(),
                        )
            window.close()
    finally:
        localization.set_language(original_language)


def test_settings_minimum_size_keeps_every_page_horizontally_accessible(
    qt_application,
) -> None:
    localization = get_localization()
    original_language = localization.language
    try:
        for language in ("en-US", "zh-CN"):
            localization.set_language(language)
            dialog = SettingsDialog()
            dialog.resize(620, 440)
            dialog.show()
            qt_application.processEvents()
            assert dialog.findChild(QLabel, "sidebarTitle") is None
            appearance_labels = [
                label
                for label in dialog._appearance_tab.findChildren(QLabel, "settingsRowTitle")
                if label.isVisible()
            ]
            assert len(appearance_labels) == 4
            assert all(label.text() and label.width() > 0 for label in appearance_labels)
            for index, button in enumerate(dialog._nav_buttons):
                button.click()
                qt_application.processEvents()
                scroll = dialog._pages.widget(index).findChild(QScrollArea)
                assert scroll is not None
                assert scroll.horizontalScrollBar().maximum() == 0
                assert scroll.verticalScrollBarPolicy() is not Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            assert len(dialog._theme_buttons) == len(COLOR_THEMES)
            dialog.close()
    finally:
        localization.set_language(original_language)


def test_heatmap_supports_keyboard_hover_browsing(qt_application) -> None:
    first = date(2026, 8, 14)
    days = tuple(
        HeatmapDay(first + timedelta(days=offset), offset * 900, int(offset > 0))
        for offset in range(10)
    )
    heatmap = HeatmapWidget()
    heatmap.set_data(HeatmapData(days[0].day, days[-1].day, days))
    heatmap.resize(420, 160)
    heatmap.show()
    qt_application.processEvents()
    heatmap.setFocus()
    QTest.keyClick(heatmap, Qt.Key.Key_Home)
    QTest.keyClick(heatmap, Qt.Key.Key_Right)
    qt_application.processEvents()

    assert heatmap._keyboard_target == (FocusActivityMode.DAILY, 1)
    assert heatmap._hover_target == (FocusActivityMode.DAILY, 1)
    assert heatmap._callout.isVisible()
    assert not hasattr(heatmap, "day_clicked")
    assert heatmap.accessibleName() == tr("dashboard.heatmap_title")
    assert heatmap.accessibleDescription()
    heatmap.close()


def test_heatmap_365_day_grid_fits_without_weekday_or_legend_gutters(
    qt_application,
) -> None:
    first = date(2025, 8, 24)
    days = tuple(
        HeatmapDay(first + timedelta(days=offset), offset % 5 * 900, int(offset % 5 > 0))
        for offset in range(365)
    )
    heatmap = HeatmapWidget()
    heatmap.set_data(HeatmapData(days[0].day, days[-1].day, days))
    heatmap.resize(420, 130)
    heatmap.show()
    heatmap.repaint()
    qt_application.processEvents()

    assert heatmap.minimumHeight() == 130
    assert len(heatmap._hit_regions) == 365
    assert min(rect.left() for rect, _value in heatmap._hit_regions) >= 0
    assert max(rect.right() for rect, _value in heatmap._hit_regions) <= heatmap.width()
    heatmap.close()


def test_distribution_compacts_long_legends_for_narrow_layouts(qt_application) -> None:
    chart = FocusDistributionChart()
    values = [
        FocusItemTotal(index, f"Long focus item name {index}", (10 - index) * 900)
        for index in range(10)
    ]
    chart.set_values(values, {})
    chart.resize(320, chart.minimumHeight())
    chart.show()
    qt_application.processEvents()

    assert len(chart.segments) == 7
    assert chart.segments[-1].name == tr("common.other")
    assert chart.minimumWidth() <= 320
    assert chart.accessibleDescription()
    assert not chart.grab().isNull()
    chart.close()


def test_focus_panel_supports_320_pixel_bilingual_layout(qt_application) -> None:
    localization = get_localization()
    original_language = localization.language
    try:
        for language in ("en-US", "zh-CN"):
            localization.set_language(language)
            panel = FocusPanel()
            panel.resize(320, 600)
            panel.show()
            qt_application.processEvents()
            assert panel.minimumWidth() <= 320
            assert panel.width() == 320
            for index in range(panel._panel_stack.count()):
                panel._panel_stack.setCurrentIndex(index)
                qt_application.processEvents()
                scroll = panel._panel_stack.currentWidget()
                assert isinstance(scroll, QScrollArea)
                assert scroll.horizontalScrollBar().maximum() == 0
            assert not panel.grab().isNull()
            panel.close()
    finally:
        localization.set_language(original_language)
