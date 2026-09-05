"""Coordinate the static pet window, settings, assets, and persistence."""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.core.app_icon_manager import AppIconError, AppIconImportError, AppIconManager
from app.core.theme import get_theme_manager, normalize_color_theme
from app.data.settings_repository import (
    AppSettings,
    SettingsRepository,
    SettingsSaveError,
)
from app.focus_mode import FocusMode, validate_target_duration
from app.i18n.translator import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGE_CODES,
    get_localization,
)
from app.pet.pet_asset_manager import (
    PetAssetError,
    PetAssetImportError,
    PetAssetManager,
)
from app.pet.pet_window import PetWindow
from app.ui.settings_dialog import SettingsDialog

logger = logging.getLogger(__name__)


class PetController(QObject):
    """Apply static pet preferences while keeping filesystem work out of widgets."""

    application_preferences_updated = Signal(bool, bool, bool)
    color_theme_updated = Signal(str)
    application_icon_updated = Signal(str)
    focus_timer_preferences_updated = Signal(object, int)

    def __init__(
        self,
        window: PetWindow,
        settings_dialog: SettingsDialog,
        settings_repository: SettingsRepository,
        asset_manager: PetAssetManager,
        app_icon_manager: AppIconManager,
    ) -> None:
        super().__init__()
        self._window = window
        self._settings_dialog = settings_dialog
        self._settings_repository = settings_repository
        self._asset_manager = asset_manager
        self._app_icon_manager = app_icon_manager
        self._settings = settings_repository.load()
        self._settings_dirty = False

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(250)
        self._save_timer.timeout.connect(self._save_dirty_settings)

        window.position_changed.connect(self._on_position_changed)
        settings_dialog.import_requested.connect(self._on_import_requested)
        settings_dialog.use_default_requested.connect(self._use_default_pet)
        settings_dialog.app_icon_import_requested.connect(self._on_app_icon_import_requested)
        settings_dialog.use_default_app_icon_requested.connect(self._use_default_app_icon)
        settings_dialog.size_changed.connect(self._on_size_changed)
        settings_dialog.language_changed.connect(self.update_language)
        settings_dialog.color_theme_changed.connect(self.update_color_theme)
        settings_dialog.focus_timer_preferences_changed.connect(
            self.update_focus_timer_preferences
        )

    @property
    def settings(self) -> AppSettings:
        return self._settings

    def start(self) -> None:
        self._apply_current_asset()
        self._apply_current_application_icon()
        self._window.set_always_on_top(self._settings.always_on_top)
        self._move_window_safely()
        self._sync_settings_dialog()
        self._window.show()

    def flush_settings(self) -> None:
        self._save_timer.stop()
        self._save_dirty_settings(show_errors=False)

    def update_application_preferences(
        self,
        always_on_top: bool,
        start_with_windows: bool,
        notifications_enabled: bool,
    ) -> bool:
        updated = replace(
            self._settings,
            always_on_top=always_on_top,
            start_with_windows=start_with_windows,
            notifications_enabled=notifications_enabled,
        )
        if not self._persist_immediately(updated):
            return False
        self._window.set_always_on_top(always_on_top)
        self._sync_settings_dialog()
        self.application_preferences_updated.emit(
            always_on_top, start_with_windows, notifications_enabled
        )
        return True

    def update_language(self, language: str) -> bool:
        target = language if language in SUPPORTED_LANGUAGE_CODES else DEFAULT_LANGUAGE
        updated = replace(self._settings, language=target)
        if not self._persist_immediately(updated):
            self._settings_dialog.set_language(self._settings.language)
            return False
        get_localization().set_language(target)
        self._sync_settings_dialog()
        self._apply_current_asset()
        self._apply_current_application_icon()
        return True

    def update_color_theme(self, theme_name: str) -> bool:
        target = normalize_color_theme(theme_name)
        if target == self._settings.color_theme:
            self._settings_dialog.set_color_theme(target)
            return True
        if not self._persist_immediately(replace(self._settings, color_theme=target)):
            self._settings_dialog.set_color_theme(self._settings.color_theme)
            return False
        get_theme_manager().set_theme(target)
        self._settings_dialog.set_color_theme(target)
        self.color_theme_updated.emit(target)
        return True

    def update_focus_timer_preferences(self, mode: str, target_minutes: int) -> bool:
        try:
            focus_mode = FocusMode(mode)
            target_seconds = int(validate_target_duration(target_minutes * 60))
        except (ValueError, TypeError) as error:
            self._settings_dialog.show_error(str(error))
            self._sync_settings_dialog()
            return False
        updated = replace(
            self._settings,
            default_focus_mode=focus_mode.value,
            default_focus_target_seconds=target_seconds,
        )
        if not self._persist_immediately(updated):
            self._sync_settings_dialog()
            return False
        self._settings_dialog.set_focus_timer_preferences(
            focus_mode, target_seconds // 60
        )
        self.focus_timer_preferences_updated.emit(focus_mode, target_seconds)
        return True

    def show_settings(self) -> None:
        self._sync_settings_dialog()
        self._settings_dialog.open_and_raise()

    def _on_import_requested(self, source_path: Path) -> None:
        try:
            stored_path = self._asset_manager.import_image(source_path)
        except PetAssetImportError as error:
            logger.warning("Static pet image import rejected: %s", error)
            self._settings_dialog.show_error(str(error))
            return
        if not self._persist_immediately(replace(self._settings, custom_pet_path=stored_path)):
            return
        self._apply_current_asset()
        self._move_window_safely()
        self._sync_settings_dialog()

    def _use_default_pet(self) -> None:
        if not self._persist_immediately(replace(self._settings, custom_pet_path=None)):
            return
        self._apply_current_asset()
        self._move_window_safely()
        self._sync_settings_dialog()

    def _on_app_icon_import_requested(self, source_path: Path) -> None:
        try:
            stored_path = self._app_icon_manager.import_icon(source_path)
        except AppIconImportError as error:
            logger.warning("Application icon import rejected: %s", error)
            self._settings_dialog.show_error(str(error))
            return
        if not self._persist_immediately(
            replace(self._settings, custom_app_icon_path=stored_path)
        ):
            return
        self._apply_current_application_icon()
        self._sync_settings_dialog()

    def _use_default_app_icon(self) -> None:
        if not self._persist_immediately(
            replace(self._settings, custom_app_icon_path=None)
        ):
            return
        self._apply_current_application_icon()
        self._sync_settings_dialog()

    def _on_size_changed(self, size_percent: int) -> None:
        self._settings = replace(self._settings, pet_size_percent=size_percent)
        self._window.set_pet_size(size_percent)
        self._move_window_safely()
        self._settings_dirty = True
        self._save_timer.start()

    def _on_position_changed(self, x: int, y: int) -> None:
        self._settings = replace(self._settings, pet_x=x, pet_y=y)
        self._settings_dirty = True
        self._save_timer.stop()
        self._save_dirty_settings()

    def _apply_current_asset(self) -> None:
        try:
            asset = self._asset_manager.resolve(self._settings.custom_pet_path)
            self._window.set_pet_asset(asset.path, self._settings.pet_size_percent)
        except (PetAssetError, ValueError) as error:
            logger.error("Static pet fallback/render failed: %s", error)
            self._settings_dialog.show_error(str(error))
            return
        self._settings_dialog.set_current_pet(
            asset.path.name, asset.using_default, asset.fallback_reason
        )

    def _apply_current_application_icon(self) -> None:
        try:
            asset = self._app_icon_manager.resolve(self._settings.custom_app_icon_path)
        except AppIconError as error:
            logger.error("Application icon fallback failed: %s", error)
            self._settings_dialog.show_error(str(error))
            return
        icon = QIcon(str(asset.path))
        application = QApplication.instance()
        if isinstance(application, QApplication):
            application.setWindowIcon(icon)
            for widget in application.topLevelWidgets():
                widget.setWindowIcon(icon)
        self._settings_dialog.set_current_application_icon(
            asset.path,
            asset.path.name,
            asset.using_default,
            asset.fallback_reason,
        )
        self.application_icon_updated.emit(str(asset.path))

    def _move_window_safely(self) -> None:
        position = self._window.move_to_safe_position(self._settings.pet_x, self._settings.pet_y)
        if position.x() != self._settings.pet_x or position.y() != self._settings.pet_y:
            self._settings = replace(self._settings, pet_x=position.x(), pet_y=position.y())
            self._settings_dirty = True

    def _sync_settings_dialog(self) -> None:
        self._settings_dialog.set_language(self._settings.language)
        self._settings_dialog.set_color_theme(self._settings.color_theme)
        self._settings_dialog.set_size_percent(self._settings.pet_size_percent)
        self._settings_dialog.set_focus_timer_preferences(
            self._settings.default_focus_mode,
            self._settings.default_focus_target_seconds // 60,
        )
        self._settings_dialog.set_application_preferences(
            self._settings.always_on_top,
            self._settings.start_with_windows,
            self._settings.notifications_enabled,
        )

    def _persist_immediately(self, settings: AppSettings) -> bool:
        self._save_timer.stop()
        try:
            self._settings_repository.save(settings)
        except SettingsSaveError as error:
            self._settings_dialog.show_error(str(error))
            return False
        self._settings = settings
        self._settings_dirty = False
        return True

    def _save_dirty_settings(self, show_errors: bool = True) -> None:
        if not self._settings_dirty:
            return
        try:
            self._settings_repository.save(self._settings)
        except SettingsSaveError as error:
            if show_errors:
                self._settings_dialog.show_error(str(error))
            return
        self._settings_dirty = False
