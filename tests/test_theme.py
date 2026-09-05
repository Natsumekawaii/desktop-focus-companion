"""Tests for global runtime color themes and semantic visualization tokens."""

from datetime import timezone

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QPalette
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QPushButton, QStackedWidget, QVBoxLayout, QWidget

from app.core.theme import (
    COLOR_THEMES,
    DEFAULT_COLOR_THEME,
    THEME_TOKENS,
    _ThemeSnapshotOverlay,
    get_theme_manager,
    normalize_color_theme,
)
from app.i18n import get_localization
from app.pet.pet_window import PetWindow
from app.ui.anchored_popup import PopupState
from app.ui.components import ThemedDateEdit
from app.ui.dashboard import DashboardWindow
from app.ui.quick_panel import FocusPanel
from app.ui.rounded_selector import RoundedComboBox, SelectorDensity
from app.ui.settings_dialog import SettingsDialog


def test_all_presets_have_complete_distinct_semantic_tokens() -> None:
    assert COLOR_THEMES == (
        "default",
        "lavender",
        "pink",
        "blue",
        "dark",
        "charcoal",
    )
    assert DEFAULT_COLOR_THEME == "lavender"
    assert set(THEME_TOKENS) == set(COLOR_THEMES)
    assert len({tokens.canvas for tokens in THEME_TOKENS.values()}) == len(COLOR_THEMES)
    for tokens in THEME_TOKENS.values():
        assert len(tokens.heatmap_levels) == 6
        assert len(set(tokens.heatmap_levels)) == 6
        assert tokens.primary != tokens.surface
        assert tokens.text != tokens.canvas


def test_invalid_theme_falls_back_to_lavender() -> None:
    assert normalize_color_theme(None) == "lavender"
    assert normalize_color_theme("neon") == "lavender"
    assert normalize_color_theme("dark") == "dark"
    assert normalize_color_theme("charcoal") == "charcoal"


def test_charcoal_theme_is_neutral_dark_with_white_primary_text() -> None:
    tokens = THEME_TOKENS["charcoal"]

    assert tokens.canvas == "#101114"
    assert tokens.surface == "#181A1E"
    assert tokens.text == "#FFFFFF"
    assert tokens.muted == "#D2D5DA"
    assert tokens.text_subtle == "#9EA4AD"
    assert tokens.primary == "#D8DCE2"
    assert tokens.primary_text == "#111317"
    assert tokens.focus_ring == "#FFFFFF"
    assert tokens != THEME_TOKENS["dark"]


def test_switching_theme_updates_global_palette_and_stylesheet_immediately(
    qt_application,
) -> None:
    manager = get_theme_manager()

    for theme_name in COLOR_THEMES:
        manager.set_theme(theme_name)
        tokens = THEME_TOKENS[theme_name]
        assert manager.theme_name == theme_name
        assert (
            qt_application.palette().color(QPalette.ColorRole.Window).name()
            == tokens.canvas
        )
        assert tokens.canvas in qt_application.styleSheet()
        assert tokens.primary in qt_application.styleSheet()
        assert tokens.surface in qt_application.styleSheet()
        assert f"QProgressBar {{\n            background: {tokens.border};" in (
            qt_application.styleSheet()
        )

    manager.set_theme(DEFAULT_COLOR_THEME)


def test_theme_switch_crossfades_visible_surfaces_but_not_the_pet(
    qt_application,
) -> None:
    manager = get_theme_manager()
    manager._transition.finish_all()
    manager.set_theme("default")
    settings = SettingsDialog()
    panel = FocusPanel()
    pet = PetWindow()
    for widget in (settings, panel, pet):
        widget.show()
    qt_application.processEvents()

    try:
        changed = QSignalSpy(manager.theme_changed)
        manager.set_theme("dark")
        overlays = manager._transition.active_overlays
        parents = {overlay.parentWidget() for overlay in overlays}
        assert settings in parents
        assert panel in parents
        assert pet not in parents
        assert changed.count() == 1
        assert manager.theme_name == "dark"
        assert all(
            overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            for overlay in overlays
        )

        panel_overlay = next(
            overlay for overlay in overlays if overlay.parentWidget() is panel
        )
        panel_overlay.set_opacity(0.5)
        panel_image = panel_overlay.current_frame().toImage()
        assert panel_image.pixelColor(0, 0).alpha() == 0
        assert panel_image.pixelColor(panel_image.width() // 2, panel_image.height() // 2).alpha() > 0
        assert panel_overlay._animation.duration() == 220
        QTest.qWait(280)
        assert manager._transition.active_overlays == ()
    finally:
        manager._transition.finish_all()
        settings.close()
        panel.close()
        pet.close()
        manager.set_theme(DEFAULT_COLOR_THEME)


def test_theme_transition_composites_complete_source_and_target_frames(
    qt_application,
) -> None:
    manager = get_theme_manager()
    manager._transition.finish_all()
    manager.set_theme("default")
    settings = SettingsDialog()
    settings.show()
    qt_application.processEvents()

    try:
        for theme_name in ("lavender", "pink", "blue", "dark", "default"):
            manager.set_theme(theme_name)
            overlays = manager._transition.active_overlays
            assert len(overlays) == 1
            overlay = overlays[0]
            center = (overlay.width() // 2, overlay.height() // 2)
            for opacity in (1.0, 0.75, 0.5, 0.25, 0.0):
                overlay.set_opacity(opacity)
                frame = overlay.current_frame().toImage()
                color = frame.pixelColor(*center)
                assert color.alpha() == 255
                assert (color.red(), color.green(), color.blue()) != (0, 0, 0)
            manager._transition.finish_all()
    finally:
        manager._transition.finish_all()
        settings.close()
        manager.set_theme(DEFAULT_COLOR_THEME)


def test_theme_target_capture_failure_falls_back_to_stable_instant_switch(
    qt_application,
    monkeypatch,
) -> None:
    manager = get_theme_manager()
    manager._transition.finish_all()
    manager.set_theme("default")
    settings = SettingsDialog()
    settings.show()
    qt_application.processEvents()
    repaint_calls: list[bool] = []
    original_repaint = settings.repaint

    def tracked_repaint() -> None:
        repaint_calls.append(True)
        original_repaint()

    try:
        monkeypatch.setattr(settings, "repaint", tracked_repaint)
        monkeypatch.setattr(
            _ThemeSnapshotOverlay,
            "capture_target",
            lambda _overlay: False,
        )
        manager.set_theme("dark")
        qt_application.processEvents()
        assert manager.theme_name == "dark"
        assert manager._transition.active_overlays == ()
        assert repaint_calls
        center = settings.grab().toImage().pixelColor(
            settings.width() // 2,
            settings.height() // 2,
        )
        assert center.alpha() == 255
        assert (center.red(), center.green(), center.blue()) != (0, 0, 0)
    finally:
        manager._transition.finish_all()
        settings.close()
        manager.set_theme(DEFAULT_COLOR_THEME)


def test_rapid_theme_switch_replaces_transition_and_same_theme_is_a_noop(
    qt_application,
) -> None:
    manager = get_theme_manager()
    manager._transition.finish_all()
    manager.set_theme("default")
    settings = SettingsDialog()
    settings.show()
    qt_application.processEvents()

    try:
        changed = QSignalSpy(manager.theme_changed)
        manager.set_theme("lavender")
        first_overlays = manager._transition.active_overlays
        assert len(first_overlays) == 1
        first_overlays[0].set_opacity(0.5)

        manager.set_theme("dark")
        second_overlays = manager._transition.active_overlays
        assert len(second_overlays) == 1
        assert second_overlays[0] is not first_overlays[0]
        assert manager.theme_name == "dark"
        assert changed.count() == 2

        manager.set_theme("dark")
        assert manager._transition.active_overlays == second_overlays
        assert changed.count() == 2
        QTest.qWait(280)
        assert manager._transition.active_overlays == ()
    finally:
        manager._transition.finish_all()
        settings.close()
        manager.set_theme(DEFAULT_COLOR_THEME)


def test_theme_transition_closes_transients_and_does_not_block_input(
    qt_application,
) -> None:
    manager = get_theme_manager()
    manager._transition.finish_all()
    manager.set_theme("default")
    host = QWidget()
    layout = QVBoxLayout(host)
    selector = RoundedComboBox(density=SelectorDensity.COMPACT)
    selector.addItems(["First", "Second"])
    button = QPushButton("Action")
    layout.addWidget(selector)
    layout.addWidget(button)
    host.show()
    qt_application.processEvents()
    selector.showPopup()
    QTest.qWait(180)
    assert selector._popup_container.isVisible()

    try:
        clicked = QSignalSpy(button.clicked)
        manager.set_theme("dark")
        assert selector._popup_container.popup_state is PopupState.CLOSED
        assert not selector._popup_container.isVisible()
        assert len(manager._transition.active_overlays) == 1
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        assert clicked.count() == 1
        QTest.qWait(280)
        assert manager._transition.active_overlays == ()
    finally:
        manager._transition.finish_all()
        host.close()
        manager.set_theme(DEFAULT_COLOR_THEME)


def test_page_tabs_switch_natively_without_page_effects_or_stale_pages(
    qt_application,
) -> None:
    windows = (DashboardWindow(timezone.utc), SettingsDialog())

    for window in windows:
        tabs = window._tabs
        assert isinstance(tabs, QStackedWidget)
        window.show()
        qt_application.processEvents()
        for _round in range(3):
            for index in range(tabs.count()):
                tabs.setCurrentIndex(index)
                qt_application.processEvents()
                current_widget = tabs.currentWidget()
                assert current_widget is tabs.widget(index)
                assert current_widget is not None
                assert current_widget.graphicsEffect() is None
                assert not current_widget.isHidden()
                for other_index in range(tabs.count()):
                    if other_index == index:
                        continue
                    other_widget = tabs.widget(other_index)
                    assert other_widget is not None
                    assert other_widget.isHidden()
        window.close()


def test_focus_panel_close_button_remains_visible_across_themes_and_languages(
    qt_application,
) -> None:
    theme_manager = get_theme_manager()
    localization = get_localization()
    original_theme = theme_manager.theme_name
    original_language = localization.language
    panel = FocusPanel()
    panel.show()

    try:
        for language in ("en-US", "zh-CN"):
            localization.set_language(language)
            for theme_name in ("lavender", "dark"):
                theme_manager.set_theme(theme_name)
                qt_application.processEvents()
                assert panel._close_button.isVisibleTo(panel)
                assert panel._close_button.text() == "×"
                assert panel._close_button.size().width() >= 30
                assert panel._close_button.size().height() >= 30
                assert panel._close_button.toolTip()
                assert panel._close_button.accessibleName() == panel._close_button.toolTip()
    finally:
        panel.hide()
        localization.set_language(original_language)
        theme_manager.set_theme(original_theme)


def test_date_popup_uses_one_theme_color_for_every_weekday(qt_application) -> None:
    theme_manager = get_theme_manager()
    localization = get_localization()
    original_theme = theme_manager.theme_name
    original_language = localization.language
    editor = ThemedDateEdit(QDate(2026, 9, 11))

    try:
        for language in ("en-US", "zh-CN"):
            localization.set_language(language)
            for theme_name in COLOR_THEMES:
                theme_manager.set_theme(theme_name)
                expected = THEME_TOKENS[theme_name].text.casefold()
                calendar = editor.calendarWidget()
                weekday_colors = {
                    calendar.weekdayTextFormat(weekday)
                    .foreground()
                    .color()
                    .name()
                    .casefold()
                    for weekday in Qt.DayOfWeek
                }
                assert weekday_colors == {expected}
    finally:
        editor.close()
        localization.set_language(original_language)
        theme_manager.set_theme(original_theme)


def test_focus_panel_uses_a_transparent_window_and_rounded_inner_surface(
    qt_application,
) -> None:
    theme_manager = get_theme_manager()
    original_theme = theme_manager.theme_name
    panel = FocusPanel()
    panel.show()

    try:
        assert panel.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        assert panel.testAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        assert not panel.autoFillBackground()
        assert panel._surface.objectName() == "focusPanelSurface"
        for theme_name in ("lavender", "dark"):
            theme_manager.set_theme(theme_name)
            qt_application.processEvents()
            image = panel.grab().toImage()
            assert image.pixelColor(0, 0).alpha() == 0
            assert image.pixelColor(image.width() - 1, 0).alpha() == 0
            assert image.pixelColor(0, image.height() - 1).alpha() == 0
            assert image.pixelColor(image.width() - 1, image.height() - 1).alpha() == 0
            assert image.pixelColor(image.width() // 2, image.height() // 2).alpha() > 0
    finally:
        panel.close()
        theme_manager.set_theme(original_theme)
