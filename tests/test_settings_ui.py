"""Five-section Settings and Focus preference tests."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QLabel, QScrollArea, QStackedWidget

from app.application import build_runtime
from app.core.paths import ApplicationPaths
from app.core.theme import COLOR_THEMES, get_theme_manager
from app.data.settings_repository import SettingsRepository
from app.focus_mode import FocusMode
from app.i18n import get_localization
from app.ui.components import RoundedCheckBox
from app.ui.settings_dialog import SettingsDialog, _theme_swatch_icon


def test_settings_has_five_localized_sections_and_emits_focus_preferences(
    qt_application,
) -> None:
    localization = get_localization()
    previous_language = localization.language
    localization.set_language("en-US")
    dialog = SettingsDialog()
    goal_spy = QSignalSpy(dialog.focus_goal_preferences_changed)
    timer_spy = QSignalSpy(dialog.focus_timer_preferences_changed)

    assert [dialog._tabs.tabText(i) for i in range(dialog._tabs.count())] == [
        "Appearance",
        "Companion",
        "Timer",
        "Data",
        "About",
    ]
    assert dialog._tabs.tabPosition() is dialog._tabs.TabPosition.North
    dialog._weekly_goal_minutes.setValue(600)
    dialog._default_focus_mode.setCurrentIndex(
        dialog._default_focus_mode.findData(FocusMode.COUNTDOWN.value)
    )
    dialog._default_focus_target_minutes.setValue(90)

    assert goal_spy.count() >= 1
    assert goal_spy.at(goal_spy.count() - 1)[1] == 600
    assert timer_spy.count() >= 1
    assert timer_spy.at(timer_spy.count() - 1) == ["countdown", 90]
    dialog.close()
    localization.set_language(previous_language)


def test_theme_picker_shows_six_localized_single_row_swatches(qt_application) -> None:
    localization = get_localization()
    previous_language = localization.language
    dialog = SettingsDialog()
    dialog.resize(620, 440)
    dialog.show()
    qt_application.processEvents()

    try:
        assert tuple(
            dialog._color_theme_combo.itemData(index)
            for index in range(dialog._color_theme_combo.count())
        ) == COLOR_THEMES
        assert len(dialog._theme_buttons) == len(COLOR_THEMES) == 6
        parent = dialog._theme_buttons[0].parentWidget()
        assert parent is not None
        assert all(button.parentWidget() is parent for button in dialog._theme_buttons)
        assert dialog._theme_buttons[-1].geometry().right() <= parent.rect().right()

        localization.set_language("zh-CN")
        assert dialog._theme_buttons[-1].toolTip() == "炭黑"
        localization.set_language("en-US")
        assert dialog._theme_buttons[-1].toolTip() == "Charcoal"

        dark_preview = _theme_swatch_icon("dark").pixmap(34, 34).toImage()
        charcoal_preview = _theme_swatch_icon("charcoal").pixmap(34, 34).toImage()
        assert charcoal_preview != dark_preview

        dialog._theme_buttons[-1].click()
        assert dialog._color_theme_combo.currentData() == "charcoal"
        assert dialog._theme_buttons[-1].isChecked()
    finally:
        dialog.close()
        localization.set_language(previous_language)


def test_timer_duration_settings_use_scrollable_hour_and_five_minute_pickers(
    qt_application,
) -> None:
    localization = get_localization()
    previous_language = localization.language
    dialog = SettingsDialog()
    pickers = (
        dialog._daily_goal_minutes,
        dialog._weekly_goal_minutes,
        dialog._streak_minutes,
        dialog._default_focus_target_minutes,
    )

    try:
        for picker in pickers:
            assert tuple(
                picker._hours_combo.itemData(index)
                for index in range(picker._hours_combo.count())
            ) == tuple(range(25))
            assert tuple(
                picker._minutes_combo.itemData(index)
                for index in range(picker._minutes_combo.count())
            ) == tuple(range(0, 61, 5))
            assert picker._hours_combo.maxVisibleItems() == 8
            assert picker._minutes_combo.maxVisibleItems() == 8
            assert (
                picker._hours_combo.view().verticalScrollBarPolicy()
                is Qt.ScrollBarPolicy.ScrollBarAlwaysOn
            )
            assert (
                picker._minutes_combo.view().verticalScrollBarPolicy()
                is Qt.ScrollBarPolicy.ScrollBarAlwaysOn
            )

        dialog.set_focus_goal_preferences(495, 1380, 1)
        dialog.set_focus_timer_preferences(FocusMode.COUNTDOWN, 90)
        assert dialog._daily_goal_minutes.value() == 495
        assert dialog._daily_goal_minutes._hours_combo.currentData() == 8
        assert dialog._daily_goal_minutes._minutes_combo.currentData() == 15
        assert dialog._weekly_goal_minutes.value() == 1380
        assert dialog._weekly_goal_minutes._hours_combo.currentData() == 23
        assert dialog._weekly_goal_minutes._minutes_combo.currentData() == 0
        assert dialog._streak_minutes.value() == 5
        assert dialog._default_focus_target_minutes.value() == 90
        assert dialog._default_focus_target_minutes._hours_combo.currentData() == 1
        assert dialog._default_focus_target_minutes._minutes_combo.currentData() == 30

        localization.set_language("en-US")
        assert dialog._daily_goal_minutes._hours_combo.accessibleName() == "Hours"
        assert dialog._daily_goal_minutes._minutes_combo.accessibleName() == "Minutes"
        localization.set_language("zh-CN")
        assert dialog._daily_goal_minutes._hours_combo.accessibleName() == "小时"
        assert dialog._daily_goal_minutes._minutes_combo.accessibleName() == "分钟"
    finally:
        dialog.close()
        localization.set_language(previous_language)


def test_companion_boolean_settings_use_inline_rounded_checkboxes(
    qt_application,
) -> None:
    localization = get_localization()
    theme_manager = get_theme_manager()
    previous_language = localization.language
    previous_theme = theme_manager.theme_name
    localization.set_language("zh-CN")
    dialog = SettingsDialog()
    dialog.resize(620, 440)
    dialog._nav_buttons[1].click()
    dialog.show()
    qt_application.processEvents()

    controls = (
        (dialog._always_on_top, dialog._always_on_top_row, "始终置顶"),
        (dialog._start_with_windows, dialog._start_with_windows_row, "开机启动"),
        (dialog._notifications_enabled, dialog._notifications_enabled_row, "通知"),
    )
    try:
        for checkbox, row, expected_text in controls:
            assert isinstance(checkbox, RoundedCheckBox)
            assert checkbox.text() == expected_text
            assert checkbox.indicator_rect().size().toSize().width() == 20
            description = row.findChild(QLabel, "supportingText")
            assert description is not None
            assert description.contentsMargins().left() == 30
            assert checkbox.geometry().bottom() < description.geometry().top()

        spy = QSignalSpy(dialog.application_preferences_changed)
        dialog._always_on_top.setFocus()
        QTest.keyClick(dialog._always_on_top, Qt.Key.Key_Space)
        assert dialog._always_on_top.isChecked()
        assert spy.count() == 1

        dialog.set_application_preferences(False, False, False, False)
        assert not dialog._start_with_windows_row.isEnabled()
        assert not dialog._start_with_windows.isEnabled()
        assert not dialog._start_with_windows_row.findChild(
            QLabel, "supportingText"
        ).isEnabled()

        for theme_name in COLOR_THEMES:
            theme_manager.set_theme(theme_name)
            qt_application.processEvents()
            dialog._notifications_enabled.setChecked(False)
            unchecked = dialog._notifications_enabled.grab().toImage()
            dialog._notifications_enabled.setChecked(True)
            checked = dialog._notifications_enabled.grab().toImage()
            assert unchecked != checked

        localization.set_language("en-US")
        qt_application.processEvents()
        assert dialog._always_on_top.text() == "Always on top"
        assert dialog._start_with_windows.text() == "Start with Windows"
        assert dialog._notifications_enabled.text() == "Notifications"
    finally:
        dialog.close()
        localization.set_language(previous_language)
        theme_manager.set_theme(previous_theme)


def test_settings_sidebar_switches_scrollable_stacked_pages(qt_application) -> None:
    dialog = SettingsDialog()
    dialog.resize(620, 440)
    dialog.show()
    qt_application.processEvents()

    assert isinstance(dialog._tabs, QStackedWidget)
    assert len(dialog._nav_buttons) == dialog._tabs.count() == 5
    for index, button in enumerate(dialog._nav_buttons):
        button.click()
        qt_application.processEvents()
        assert dialog._tabs.currentIndex() == index
        assert button.isChecked()
        assert dialog._page_title.text() == dialog._tabs.tabText(index)
        assert dialog._tabs.widget(index).findChild(QScrollArea) is not None
        assert dialog._tabs.widget(index).graphicsEffect() is None

    dialog.close()


def test_default_focus_mode_and_target_apply_immediately_and_after_restart(
    qt_application, tmp_path: Path
) -> None:
    project_root = Path(__file__).resolve().parents[1]
    paths = ApplicationPaths(project_root, project_root / "assets", tmp_path / "profile")
    runtime = build_runtime(paths)

    runtime.settings_dialog.focus_timer_preferences_changed.emit("countdown", 90)

    saved = SettingsRepository(paths.settings_path).load()
    assert saved.default_focus_mode == "countdown"
    assert saved.default_focus_target_seconds == 90 * 60
    assert runtime.quick_panel._countdown_radio.isChecked()
    assert runtime.quick_panel._target_duration_picker.value() == 90
    assert runtime.quick_panel._target_duration_picker._hours_combo.currentData() == 1
    assert runtime.quick_panel._target_duration_picker._minutes_combo.currentData() == 30
    runtime.settings_dialog.close()
    runtime.focus_item_dialog.close()
    runtime.dashboard_window.close()
    runtime.quick_panel.close()
    runtime.pet_window.close()

    restarted = build_runtime(paths)
    assert restarted.quick_panel._countdown_radio.isChecked()
    assert restarted.quick_panel._target_duration_picker.value() == 90
    assert restarted.quick_panel._target_duration_picker._hours_combo.currentData() == 1
    assert restarted.quick_panel._target_duration_picker._minutes_combo.currentData() == 30
    restarted.settings_dialog.close()
    restarted.focus_item_dialog.close()
    restarted.dashboard_window.close()
    restarted.quick_panel.close()
    restarted.pet_window.close()
