"""Smoke tests for the complete application object graph."""

from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QIcon
from PySide6.QtTest import QTest

from app import __version__
from app.application import APPLICATION_NAME, build_runtime
from app.core.paths import ApplicationPaths
from app.core.theme import THEME_TOKENS
from app.data.settings_repository import AppSettings, SettingsRepository
from app.i18n import tr
from app.ui.dashboard import DashboardPage
from app.ui.rounded_menu import RoundedMenu


def _create_default_pet(path: Path) -> None:
    from PySide6.QtGui import QColor, QImage

    path.parent.mkdir(parents=True, exist_ok=True)
    image = QImage(80, 100, QImage.Format.Format_ARGB32)
    image.fill(QColor(170, 120, 220, 255))
    assert image.save(str(path), "PNG")


def _create_default_icon(path: Path) -> None:
    from PySide6.QtGui import QColor, QImage

    path.parent.mkdir(parents=True, exist_ok=True)
    image = QImage(64, 64, QImage.Format.Format_ARGB32)
    image.fill(QColor(120, 70, 180, 255))
    assert image.save(str(path), "ICO")


def test_application_runtime_starts_and_persists_changes(qt_application, tmp_path: Path) -> None:
    paths = ApplicationPaths(
        project_root=tmp_path,
        assets_dir=tmp_path / "assets",
        data_dir=tmp_path / "data",
    )
    _create_default_pet(paths.default_pet_path)
    _create_default_icon(paths.application_icon_path)
    runtime = build_runtime(paths)

    runtime.pet_controller.start()
    assert runtime.tray_controller.tray_icon.contextMenu() is runtime.tray_controller.menu
    assert isinstance(runtime.tray_controller.menu, RoundedMenu)
    runtime.pet_window.context_menu_requested.emit(QPoint(30, 30))
    qt_application.processEvents()
    assert runtime.tray_controller.menu.isVisible()
    runtime.tray_controller.menu.hide()
    assert runtime.dashboard_window._tabs.count() >= 5
    runtime.settings_dialog.color_theme_changed.emit("pink")
    assert runtime.pet_controller.settings.color_theme == "pink"
    assert THEME_TOKENS["pink"].canvas in qt_application.styleSheet()
    runtime.settings_dialog.size_changed.emit(125)
    runtime.pet_window.position_changed.emit(35, 45)
    custom_pet_path = tmp_path / "selected-pet.webp"
    _create_custom_pet(custom_pet_path)
    runtime.settings_dialog.import_requested.emit(custom_pet_path)
    runtime.pet_controller.flush_settings()

    assert qt_application.applicationName() == APPLICATION_NAME
    assert APPLICATION_NAME == "Desktop Focus Companion"
    assert qt_application.applicationVersion() == __version__
    assert __version__ == "1.0.0"
    assert runtime.pet_window.windowTitle() == APPLICATION_NAME
    assert runtime.pet_window.size().width() == 240
    assert runtime.pet_window._image_label.size().height() == 120
    assert runtime.pet_window.size().height() == 120
    assert paths.settings_path.exists()
    settings_text = paths.settings_path.read_text(encoding="utf-8")
    assert '"pet_size_percent": 125' in settings_text
    assert '"pet_x": 35' in settings_text
    assert '"pet_y": 45' in settings_text
    assert '"custom_pet_path": "pets/custom/' in settings_text
    assert '"color_theme": "pink"' in settings_text

    runtime.settings_dialog.close()
    runtime.pet_window.close()

    restarted_runtime = build_runtime(paths)
    restarted_runtime.pet_controller.start()
    assert restarted_runtime.pet_window.pos() == QPoint(35, 45)
    assert restarted_runtime.pet_window.size().width() == 240
    assert restarted_runtime.pet_window._image_label.size().height() == 120
    assert restarted_runtime.pet_window.size().height() == 120
    assert restarted_runtime.pet_controller.settings.color_theme == "pink"
    assert THEME_TOKENS["pink"].canvas in qt_application.styleSheet()
    restarted_runtime.dashboard_controller.show()
    assert restarted_runtime.dashboard_window.isVisible()
    restarted_runtime.dashboard_window.close()
    restarted_runtime.settings_dialog.close()
    restarted_runtime.pet_window.close()


def test_reset_to_default_pet_is_immediate_and_preserves_size(
    qt_application, tmp_path: Path
) -> None:
    paths = ApplicationPaths(
        project_root=tmp_path,
        assets_dir=tmp_path / "assets",
        data_dir=tmp_path / "data",
    )
    _create_default_pet(paths.default_pet_path)
    _create_default_icon(paths.application_icon_path)
    runtime = build_runtime(paths)
    runtime.pet_controller.start()
    custom_pet_path = tmp_path / "selected-pet.webp"
    _create_custom_pet(custom_pet_path)
    runtime.settings_dialog.import_requested.emit(custom_pet_path)
    runtime.settings_dialog.size_changed.emit(135)

    runtime.settings_dialog.use_default_requested.emit()

    assert runtime.pet_controller.settings.custom_pet_path is None
    assert runtime.pet_controller.settings.pet_size_percent == 135
    assert runtime.pet_window._source_pixmap.size().width() == 80
    assert runtime.pet_window._source_pixmap.size().height() == 100
    persisted = SettingsRepository(paths.settings_path).load()
    assert persisted.custom_pet_path is None
    assert persisted.pet_size_percent == 135

    runtime.settings_dialog.close()
    runtime.pet_window.close()

    restarted_runtime = build_runtime(paths)
    restarted_runtime.pet_controller.start()
    assert restarted_runtime.pet_controller.settings.custom_pet_path is None
    assert restarted_runtime.pet_controller.settings.pet_size_percent == 135
    assert restarted_runtime.pet_window._source_pixmap.size().width() == 80
    assert restarted_runtime.pet_window._source_pixmap.size().height() == 100
    restarted_runtime.settings_dialog.close()
    restarted_runtime.pet_window.close()


def test_pet_click_toggles_focus_panel_and_shared_menu_is_minimal(
    qt_application, tmp_path: Path
) -> None:
    paths = ApplicationPaths(
        project_root=tmp_path,
        assets_dir=tmp_path / "assets",
        data_dir=tmp_path / "data",
    )
    _create_default_pet(paths.default_pet_path)
    _create_default_icon(paths.application_icon_path)
    runtime = build_runtime(paths)
    runtime.pet_controller.start()
    tray = runtime.tray_controller

    assert tray.tray_icon.contextMenu() is tray.menu
    assert isinstance(tray.menu, RoundedMenu)
    tray._refresh_actions()
    menu_entries = [
        None if action.isSeparator() else action.text()
        for action in tray.menu.actions()
    ]
    assert menu_entries == [
        tr("tray.focus_center"),
        tr("tray.settings"),
        None,
        tr("tray.hide_pet"),
        tr("tray.exit"),
    ]
    assert not hasattr(tray, "_brand_action")
    assert not hasattr(tray, "_start_focus_action")
    assert not hasattr(tray, "_recent_menu")
    assert not hasattr(tray, "_dashboard_action")
    assert not hasattr(tray, "_history_action")
    assert all(
        not action.icon().isNull()
        for action in (
            tray._focus_center_action,
            tray._settings_action,
            tray._show_pet_action,
            tray._exit_action,
        )
    )

    assert not runtime.quick_panel.isVisible()
    QTest.mouseClick(
        runtime.pet_window,
        Qt.MouseButton.LeftButton,
        pos=runtime.pet_window.rect().center(),
    )
    qt_application.processEvents()
    assert runtime.quick_panel.isVisible()
    assert runtime.quick_panel._close_button.isVisibleTo(runtime.quick_panel)
    assert runtime.quick_panel._close_button.text() == "×"
    assert runtime.quick_panel._close_button.objectName() == "iconButton"
    assert runtime.quick_panel._close_button.accessibleName() == tr(
        "quick.close_tooltip"
    )

    QTest.mouseClick(
        runtime.pet_window,
        Qt.MouseButton.LeftButton,
        pos=runtime.pet_window.rect().center(),
    )
    qt_application.processEvents()
    assert not runtime.quick_panel.isVisible()

    QTest.mouseClick(
        runtime.pet_window,
        Qt.MouseButton.LeftButton,
        pos=runtime.pet_window.rect().center(),
    )
    qt_application.processEvents()
    assert runtime.quick_panel.isVisible()

    runtime.quick_panel._close_button.click()
    qt_application.processEvents()
    assert not runtime.quick_panel.isVisible()

    runtime.dashboard_window.show_history()
    assert runtime.dashboard_window.current_page() is DashboardPage.HISTORY
    runtime.dashboard_window.hide()
    tray._focus_center_action.trigger()
    qt_application.processEvents()
    assert runtime.dashboard_window.isVisible()
    assert runtime.dashboard_window.current_page() is DashboardPage.OVERVIEW

    runtime.quick_panel.hide()
    runtime.dashboard_window.close()
    runtime.settings_dialog.close()
    runtime.pet_window.close()


def test_custom_application_icon_updates_immediately_persists_and_resets_safely(
    qt_application, tmp_path: Path
) -> None:
    paths = ApplicationPaths(
        project_root=tmp_path,
        assets_dir=tmp_path / "assets",
        data_dir=tmp_path / "data",
    )
    _create_default_pet(paths.default_pet_path)
    _create_default_icon(paths.application_icon_path)
    runtime = build_runtime(paths)
    runtime.pet_controller.start()
    custom_pet = tmp_path / "custom-pet.webp"
    _create_custom_pet(custom_pet)
    runtime.settings_dialog.import_requested.emit(custom_pet)
    custom_icon = tmp_path / "custom-icon.png"
    _create_colored_icon(custom_icon)

    runtime.settings_dialog.app_icon_import_requested.emit(custom_icon)

    saved_path = runtime.pet_controller.settings.custom_app_icon_path
    assert saved_path is not None
    assert saved_path.startswith("icons/custom/")
    assert (paths.data_dir / saved_path).is_file()
    assert _icon_center_color(qt_application.windowIcon()) == "#1eaa5f"
    assert _icon_center_color(runtime.tray_controller.tray_icon.icon()) == "#1eaa5f"
    for widget in qt_application.topLevelWidgets():
        assert _icon_center_color(widget.windowIcon()) == "#1eaa5f"

    runtime.settings_dialog.size_changed.emit(135)
    current_pet = runtime.pet_controller.settings.custom_pet_path
    runtime.settings_dialog.use_default_app_icon_requested.emit()
    assert runtime.pet_controller.settings.custom_app_icon_path is None
    assert runtime.pet_controller.settings.custom_pet_path == current_pet
    assert runtime.pet_controller.settings.pet_size_percent == 135
    assert _icon_center_color(runtime.tray_controller.tray_icon.icon()) == "#7846b4"

    runtime.settings_dialog.app_icon_import_requested.emit(custom_icon)
    runtime.pet_controller.flush_settings()
    runtime.settings_dialog.close()
    runtime.pet_window.close()

    restarted = build_runtime(paths)
    restarted.pet_controller.start()
    assert restarted.pet_controller.settings.custom_app_icon_path is not None
    assert _icon_center_color(qt_application.windowIcon()) == "#1eaa5f"
    restarted.settings_dialog.close()
    restarted.pet_window.close()


def test_missing_saved_application_icon_uses_bundled_default(
    qt_application, tmp_path: Path
) -> None:
    paths = ApplicationPaths(
        project_root=tmp_path,
        assets_dir=tmp_path / "assets",
        data_dir=tmp_path / "data",
    )
    _create_default_pet(paths.default_pet_path)
    _create_default_icon(paths.application_icon_path)
    SettingsRepository(paths.settings_path).save(
        AppSettings(custom_app_icon_path="icons/custom/missing.png")
    )

    runtime = build_runtime(paths)
    runtime.pet_controller.start()

    assert runtime.pet_controller.settings.custom_app_icon_path == "icons/custom/missing.png"
    assert _icon_center_color(qt_application.windowIcon()) == "#7846b4"
    assert _icon_center_color(runtime.tray_controller.tray_icon.icon()) == "#7846b4"
    assert runtime.settings_dialog._current_app_icon_default
    assert runtime.settings_dialog._current_app_icon_note
    runtime.settings_dialog.close()
    runtime.pet_window.close()


def _create_custom_pet(path: Path) -> None:
    from PySide6.QtGui import QColor, QImage

    image = QImage(200, 100, QImage.Format.Format_RGB32)
    image.fill(QColor(85, 120, 210))
    assert image.save(str(path), "WEBP")


def _create_colored_icon(path: Path) -> None:
    from PySide6.QtGui import QColor, QImage

    image = QImage(96, 96, QImage.Format.Format_ARGB32)
    image.fill(QColor(30, 170, 95, 255))
    assert image.save(str(path), "PNG")


def _icon_center_color(icon: QIcon) -> str:
    image = icon.pixmap(32, 32).toImage()
    return image.pixelColor(image.width() // 2, image.height() // 2).name()


def test_application_brand_icon_has_all_required_sizes(qt_application) -> None:
    icon_path = ApplicationPaths.discover().application_icon_path
    icon = QIcon(str(icon_path))

    assert icon_path.is_file()
    assert not icon.isNull()
    available = {(size.width(), size.height()) for size in icon.availableSizes()}
    assert {(size, size) for size in (16, 24, 32, 48, 64, 128, 256)} <= available
