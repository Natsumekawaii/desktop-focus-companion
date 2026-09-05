"""Connect derived progression to settings and Qt views."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox

from app.gamification.gamification_service import GamificationService
from app.i18n import get_localization, tr
from app.ui.dashboard import DashboardWindow
from app.ui.quick_panel import FocusPanel
from app.ui.settings_dialog import SettingsDialog


class GamificationController(QObject):
    """Refresh focus goals and consistency while preserving legacy storage."""

    notification_requested = Signal(str, str)

    def __init__(
        self,
        service: GamificationService,
        quick_panel: FocusPanel,
        dashboard: DashboardWindow,
        settings_dialog: SettingsDialog,
    ) -> None:
        super().__init__()
        self._service = service
        self._quick_panel = quick_panel
        self._dashboard = dashboard
        self._settings_dialog = settings_dialog
        settings_dialog.focus_goal_preferences_changed.connect(
            self.set_preferences_minutes
        )
        get_localization().language_changed.connect(self._refresh_localized)
        self.refresh()

    def refresh(self) -> None:
        snapshot = self._service.snapshot()
        self._quick_panel.set_gamification(snapshot)
        self._dashboard.set_gamification(snapshot)
        self._settings_dialog.set_focus_goal_preferences(
            snapshot.daily_goal_seconds // 60,
            snapshot.weekly_goal_seconds // 60,
            snapshot.streak_minimum_seconds // 60,
        )
        if snapshot.goal_completed and self._service.mark_goal_celebrated_today():
            self.notification_requested.emit(
                tr("notification.goal_title"), tr("notification.goal_body")
            )

    def set_preferences_minutes(
        self,
        daily_goal_minutes: int,
        weekly_goal_minutes: int,
        streak_minutes: int,
    ) -> None:
        try:
            self._service.set_preferences(
                daily_goal_minutes * 60,
                streak_minutes * 60,
                weekly_goal_minutes * 60,
            )
        except ValueError as error:
            QMessageBox.warning(self._settings_dialog, tr("app.name"), str(error))
            return
        self.refresh()

    def _refresh_localized(self, _language: str) -> None:
        snapshot = self._service.snapshot()
        self._quick_panel.set_gamification(snapshot)
        self._dashboard.set_gamification(snapshot)
