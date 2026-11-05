"""Manual navigation sizing, single-owner persistence and live-page invariants."""

from datetime import timezone
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QScrollArea, QTableWidgetItem
from test_agent import FakeClient

from app.application import build_runtime
from app.core.paths import ApplicationPaths
from app.core.theme import COLOR_THEMES, get_theme_manager
from app.data.settings_repository import (
    AppSettings,
    SettingsRepository,
    SettingsSaveError,
)
from app.i18n import get_localization, tr
from app.ui.dashboard import DashboardPage, DashboardWindow


@pytest.mark.parametrize("value", [None, "", "hidden", "COLLAPSED", True, 1, [], {}])
def test_invalid_or_missing_sidebar_mode_uses_legacy_auto(value):
    assert AppSettings().dashboard_sidebar_mode == "auto"
    assert AppSettings.from_mapping({}).dashboard_sidebar_mode == "auto"
    assert (
        AppSettings.from_mapping(
            {"dashboard_sidebar_mode": value}
        ).dashboard_sidebar_mode
        == "auto"
    )


@pytest.mark.parametrize("mode", ["auto", "expanded", "collapsed"])
def test_sidebar_setting_round_trip_in_separate_profiles(tmp_path, mode):
    development = SettingsRepository(tmp_path / "dev" / "settings.json")
    production = SettingsRepository(tmp_path / "production" / "settings.json")
    production.save(AppSettings(color_theme="charcoal"))
    development.save(AppSettings(dashboard_sidebar_mode=mode))
    assert development.load().dashboard_sidebar_mode == mode
    assert production.load().dashboard_sidebar_mode == "auto"
    assert production.load().color_theme == "charcoal"


def runtime_for(tmp_path):
    root = Path(__file__).resolve().parents[1]
    paths = ApplicationPaths(root, root / "assets", tmp_path / "profile")
    return build_runtime(paths, development=True), paths


def test_manual_sidebar_state_outlives_resize_close_and_restart(
    qt_application, tmp_path, monkeypatch
):
    runtime, paths = runtime_for(tmp_path)
    window = runtime.dashboard_window
    saved = []
    repository = runtime.pet_controller._settings_repository
    original_save = repository.save

    def save(settings):
        saved.append(settings)
        original_save(settings)

    monkeypatch.setattr(repository, "save", save)
    window.show()
    for width, expected in [(760, 52), (1024, 160), (1280, 160)]:
        window.resize(width, 520)
        qt_application.processEvents()
        window._sidebar.finish()
        assert window._sidebar.width() == expected
    assert not saved
    runtime.pet_window.position_changed.emit(51, 62)
    position_saves = len(saved)
    window._sidebar_toggle.click()
    assert window.sidebar_mode == "collapsed" and len(saved) == position_saves + 1
    assert saved[-1].pet_x == 51 and saved[-1].pet_y == 62
    for width in (760, 1024, 1280):
        window.resize(width, 520)
        qt_application.processEvents()
        window._sidebar.finish()
        assert window._sidebar.width() == 52
    runtime.pet_controller.update_color_theme("pink")
    runtime.pet_controller.update_language("en-US")
    runtime.pet_controller.flush_settings()
    assert repository.load().dashboard_sidebar_mode == "collapsed"
    window.close()
    window.show()
    qt_application.processEvents()
    assert window.sidebar_mode == "collapsed"
    window.resize(760, 520)
    window._sidebar_toggle.click()
    qt_application.processEvents()
    window._sidebar.finish()
    assert window.sidebar_mode == "expanded" and window._sidebar.width() == 160
    restarted = build_runtime(paths, development=True)
    restarted.dashboard_window.resize(760, 520)
    restarted.dashboard_window.show()
    qt_application.processEvents()
    assert restarted.dashboard_window.sidebar_mode == "expanded"
    assert restarted.dashboard_window._sidebar.width() == 160
    assert restarted.pet_controller.settings.color_theme == "pink"


@pytest.mark.parametrize("previous", ["auto", "expanded", "collapsed"])
def test_failed_save_rolls_back_in_dashboard_without_clobbering_settings(
    qt_application, tmp_path, monkeypatch, previous
):
    runtime, paths = runtime_for(tmp_path)
    pet = runtime.pet_controller
    assert pet.update_dashboard_sidebar_mode(previous)
    window = runtime.dashboard_window
    window.set_sidebar_mode(previous)
    window.resize(1024, 520)
    window.show()
    qt_application.processEvents()
    before = pet.settings
    width = window._sidebar.width()

    def fail(settings):
        raise SettingsSaveError("simulated write failure")

    monkeypatch.setattr(pet._settings_repository, "save", fail)
    monkeypatch.setattr(
        runtime.settings_dialog,
        "show_error",
        lambda _: pytest.fail("Wrong error window"),
    )
    window._sidebar_toggle.click()
    qt_application.processEvents()
    assert window.sidebar_mode == previous and window._sidebar.width() == width
    assert pet.settings == before
    assert SettingsRepository(paths.settings_path).load() == before
    assert window.statusBar().currentMessage() == tr("dashboard.sidebar.save_error")


def test_toggle_mouse_keyboard_tooltips_and_no_rebuilt_pages(qt_application):
    window = DashboardWindow(timezone.utc)
    window.resize(1024, 640)
    window.show()
    qt_application.processEvents()
    pages = [window._pages.widget(i) for i in range(window._pages.count())]
    signal = QSignalSpy(window.sidebar_mode_changed)
    button = window._sidebar_toggle
    assert button.size().width() == button.size().height() == 32
    assert button.iconSize().width() == 20
    assert (
        button.toolTip() == button.accessibleName() == tr("dashboard.sidebar.collapse")
    )
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    qt_application.processEvents()
    window._sidebar.finish()
    qt_application.processEvents()
    assert window._sidebar.width() == 52 and button.isChecked()
    center = button.mapTo(window._sidebar, button.rect().center()).x()
    assert abs(center - window._sidebar.rect().center().x()) <= 1
    assert button.toolTip() == tr("dashboard.sidebar.expand")
    button.setFocus()
    for key, expected in [
        (Qt.Key.Key_Space, 160),
        (Qt.Key.Key_Return, 52),
        (Qt.Key.Key_Enter, 160),
    ]:
        QTest.keyClick(button, key)
        qt_application.processEvents()
        window._sidebar.finish()
        assert window._sidebar.width() == expected
    assert signal.count() == 4
    assert pages == [window._pages.widget(i) for i in range(window._pages.count())]
    QTest.keyClick(button, Qt.Key.Key_Tab)
    assert window.focusWidget() is window._nav_buttons[DashboardPage.OVERVIEW]


@pytest.mark.parametrize("language", ["zh-CN", "en-US"])
@pytest.mark.parametrize("theme", COLOR_THEMES)
def test_sidebar_layout_in_all_pages_themes_and_languages(
    qt_application, language, theme
):
    get_localization().set_language(language)
    get_theme_manager().set_theme(theme)
    get_theme_manager()._transition.finish_all()
    window = DashboardWindow(timezone.utc)
    window.show()
    for width in (760, 1024, 1280):
        window.resize(width, 520)
        for mode, sidebar_width in [("expanded", 160), ("collapsed", 52)]:
            window.set_sidebar_mode(mode)
            qt_application.processEvents()
            assert window.width() == width and window.height() == 520
            assert window._sidebar.width() == sidebar_width
            assert (window._nav_focus_label.height() > 0) == (mode == "expanded")
            for page, nav in window._nav_buttons.items():
                assert nav.isVisible()
                assert window._sidebar.rect().contains(nav.geometry())
                assert (
                    nav.toolTip()
                    == nav.accessibleName()
                    == tr(window._nav_text_keys[page])
                )
                assert bool(nav.text()) == (mode == "expanded")
                # Some Windows offscreen runners have no font database at all;
                # the screenshot matrix explicitly loads real system glyphs.
                if mode == "expanded" and QFontDatabase.families():
                    assert (
                        nav.fontMetrics().horizontalAdvance(nav.full_text)
                        <= nav.label_rect().width()
                    )
                nav.click()
                window._pages.finish_transition()
                qt_application.processEvents()
                assert window.current_page() == page and nav.isChecked()
                root = window._pages.currentWidget()
                if isinstance(root, QScrollArea):
                    assert root.horizontalScrollBar().maximum() == 0


def test_page_state_and_scroll_preserved_when_toggling(qt_application):
    window = DashboardWindow(timezone.utc)
    window.show()
    window.set_current_page(DashboardPage.OVERVIEW)
    qt_application.processEvents()
    overview = window._pages.currentWidget()
    bar = overview.verticalScrollBar()
    bar.setValue(min(100, bar.maximum()))
    scroll = bar.value()
    for _ in range(2):
        window._sidebar_toggle.click()
        window._sidebar.finish()
        qt_application.processEvents()
        assert bar.value() == scroll
    window.set_current_page(DashboardPage.HISTORY)
    table = window._history_table
    table.setRowCount(3)
    for row in range(3):
        table.setItem(row, 0, QTableWidgetItem(str(row)))
    table.selectRow(1)
    window.agent_page.input.setPlainText("Unsent draft 未发送")
    window._sidebar_toggle.click()
    qt_application.processEvents()
    assert not window._pages.is_transition_active
    assert window.current_page() == DashboardPage.HISTORY
    assert table.currentRow() == 1
    assert window.agent_page.input.toPlainText() == "Unsent draft 未发送"


def test_sidebar_does_not_cancel_or_restart_streaming_agent(
    qt_application, qt_wait_until, tmp_path, monkeypatch
):
    import app.agent.controller as agent_module

    monkeypatch.setattr(agent_module, "DeepSeekClient", FakeClient)
    runtime, _ = runtime_for(tmp_path)
    window, agent = runtime.dashboard_window, runtime.agent_controller
    window.show()
    window.set_current_page(DashboardPage.AI_ASSISTANT)
    agent.credentials._session_key = "test-only-key"
    agent.preferences.update(enabled=True, models=["deepseek-flash"])
    agent.send("Hello")
    turn = agent.turn
    agent.client.cancelled = False
    agent.client.text_delta.emit("First ")
    window.agent_page.input.setPlainText("draft")
    for _ in range(2):
        window._sidebar_toggle.click()
        window._sidebar.animation.setCurrentTime(65)
        qt_application.processEvents()
    assert not agent.client.cancelled and agent.busy
    assert agent.turn is turn and len(agent.client.requests) == 1
    assert window.current_page() == DashboardPage.AI_ASSISTANT
    assert window.agent_page.input.toPlainText() == "draft"
    agent.client.text_delta.emit("second")
    agent.client.completed.emit({"role": "assistant", "content": "First second"}, {})
    qt_wait_until(lambda: not agent.busy)
    assert agent.turn["answer"] == "First second"
    assert not agent.client.cancelled and len(agent.client.requests) == 1
    agent.shutdown()
