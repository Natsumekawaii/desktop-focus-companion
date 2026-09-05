"""Shared ordinary application menu for the desktop pet and system tray."""

from __future__ import annotations

from PySide6.QtCore import QObject, QPoint
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QSystemTrayIcon

from app.application_controller import ApplicationController
from app.core.icon_system import IconName, IconSystem
from app.core.theme import get_theme_manager
from app.data.models import FocusSession
from app.i18n import get_localization, tr
from app.pet.pet_controller import PetController
from app.pet.pet_window import PetWindow
from app.timer.formatting import format_compact_duration
from app.ui.dashboard_controller import DashboardController
from app.ui.quick_panel_controller import FocusPanelController
from app.ui.rounded_menu import RoundedMenu


class TrayController(QObject):
    """Keep application-level actions accessible from one shared menu."""

    def __init__(
        self,
        icon_path: str,
        pet_window: PetWindow,
        pet_controller: PetController,
        quick_panel_controller: FocusPanelController,
        dashboard_controller: DashboardController,
        application_controller: ApplicationController,
    ) -> None:
        super().__init__()
        self._pet_window = pet_window
        self._notifications_enabled = pet_controller.settings.notifications_enabled

        application_icon = QIcon(icon_path)
        self.tray_icon = QSystemTrayIcon(application_icon, self)
        self.tray_icon.setToolTip(tr("app.name"))
        self.menu = RoundedMenu()

        self._show_pet_action = QAction(self.menu)
        self._show_pet_action.triggered.connect(self._toggle_pet)

        self._focus_center_action = QAction(self.menu)
        self._focus_center_action.triggered.connect(dashboard_controller.show)
        self._settings_action = QAction(self.menu)
        self._settings_action.triggered.connect(pet_controller.show_settings)
        for action in (
            self._focus_center_action,
            self._settings_action,
        ):
            self.menu.addAction(action)
        self.menu.addSeparator()
        self.menu.addAction(self._show_pet_action)
        self._exit_action = QAction(self.menu)
        self._exit_action.triggered.connect(application_controller.request_exit)
        self.menu.addAction(self._exit_action)

        self._refresh_icons()

        self.menu.aboutToShow.connect(self._refresh_actions)
        self.tray_icon.setContextMenu(self.menu)
        self.tray_icon.activated.connect(self._on_activated)
        pet_window.context_menu_requested.connect(self._show_context_menu)
        pet_controller.application_preferences_updated.connect(self._preferences_updated)
        pet_controller.application_icon_updated.connect(self._apply_application_icon)
        quick_panel_controller.session_finished.connect(self.notify_session_finished)
        get_localization().language_changed.connect(self._retranslate_ui)
        get_theme_manager().theme_changed.connect(self._refresh_icons)
        self._retranslate_ui()
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon.show()

    @property
    def available(self) -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    def notify(self, title: str, message: str) -> None:
        if self.available and self._notifications_enabled:
            self.tray_icon.showMessage(
                title,
                message,
                QSystemTrayIcon.MessageIcon.Information,
                5000,
            )

    def notify_session_finished(self, session: FocusSession) -> None:
        self.notify(
            tr("tray.session_completed_title"),
            tr(
                "tray.session_completed",
                subject=session.focus_item_name,
                duration=format_compact_duration(session.duration_seconds),
            ),
        )

    def _toggle_pet(self) -> None:
        if self._pet_window.isVisible():
            self._pet_window.hide()
        else:
            self._pet_window.show()
            self._pet_window.raise_()
        self._refresh_actions()

    def _show_context_menu(self, position: QPoint) -> None:
        """Open the exact same menu used by the system tray."""
        self._refresh_actions()
        self.menu.popup(position)

    def _apply_application_icon(self, icon_path: str) -> None:
        icon = QIcon(icon_path)
        self.tray_icon.setIcon(icon)

    def _refresh_actions(self) -> None:
        self._show_pet_action.setText(
            tr("tray.hide_pet") if self._pet_window.isVisible() else tr("tray.show_pet")
        )

    def _refresh_icons(self) -> None:
        self._focus_center_action.setIcon(IconSystem.icon(IconName.DASHBOARD))
        self._settings_action.setIcon(IconSystem.icon(IconName.SETTINGS))
        self._show_pet_action.setIcon(IconSystem.icon(IconName.SHOW_COMPANION))
        self._exit_action.setIcon(IconSystem.icon(IconName.EXIT))

    def _retranslate_ui(self, _language: str | None = None) -> None:
        self.tray_icon.setToolTip(tr("app.name"))
        self._focus_center_action.setText(tr("tray.focus_center"))
        self._settings_action.setText(tr("tray.settings"))
        self._exit_action.setText(tr("tray.exit"))
        self._refresh_actions()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._toggle_pet()

    def _preferences_updated(
        self,
        always_on_top: bool,
        start_with_windows: bool,
        notifications_enabled: bool,
    ) -> None:
        del always_on_top, start_with_windows
        self._notifications_enabled = notifications_enabled
