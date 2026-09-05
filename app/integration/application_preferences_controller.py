"""Coordinate persisted preferences with reversible OS integration."""

from PySide6.QtCore import QObject

from app.integration.startup_manager import StartupManagerError, WindowsStartupManager
from app.pet.pet_controller import PetController
from app.ui.settings_dialog import SettingsDialog


class ApplicationPreferencesController(QObject):
    """Apply application preferences transactionally where practical."""

    def __init__(
        self,
        settings_dialog: SettingsDialog,
        pet_controller: PetController,
        startup_manager: WindowsStartupManager,
    ) -> None:
        super().__init__()
        self._dialog = settings_dialog
        self._pet_controller = pet_controller
        self._startup = startup_manager
        settings_dialog.application_preferences_changed.connect(self.apply)
        self._sync_dialog()

    def apply(
        self,
        always_on_top: bool,
        start_with_windows: bool,
        notifications_enabled: bool,
    ) -> None:
        try:
            previous_startup = self._startup.is_enabled() if self._startup.supported else False
            self._startup.set_enabled(start_with_windows)
        except StartupManagerError as error:
            self._dialog.show_error(str(error))
            self._sync_dialog()
            return
        if not self._pet_controller.update_application_preferences(
            always_on_top,
            start_with_windows,
            notifications_enabled,
        ):
            try:
                self._startup.set_enabled(previous_startup)
            except StartupManagerError:
                pass
        self._sync_dialog()

    def _sync_dialog(self) -> None:
        settings = self._pet_controller.settings
        try:
            startup_enabled = self._startup.is_enabled()
        except StartupManagerError:
            startup_enabled = False
        if settings.start_with_windows != startup_enabled:
            self._pet_controller.update_application_preferences(
                settings.always_on_top,
                startup_enabled,
                settings.notifications_enabled,
            )
            settings = self._pet_controller.settings
        self._dialog.set_application_preferences(
            settings.always_on_top,
            startup_enabled,
            settings.notifications_enabled,
            self._startup.supported,
        )
