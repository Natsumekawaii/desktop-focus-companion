"""Top-level application commands including safe shutdown."""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from app.i18n import tr
from app.pet.pet_controller import PetController
from app.pet.pet_window import PetWindow
from app.timer.focus_session_manager import FocusSessionManager
from app.timer.timer_state import TimerState
from app.ui.quick_panel_controller import FocusPanelController


class ApplicationController(QObject):
    """Coordinate commands that span pet, timer, and application lifecycle."""

    def __init__(
        self,
        pet_window: PetWindow,
        pet_controller: PetController,
        session_manager: FocusSessionManager,
        quick_panel_controller: FocusPanelController,
    ) -> None:
        super().__init__()
        self._pet_window = pet_window
        self._pet_controller = pet_controller
        self._session_manager = session_manager
        self._quick_panel_controller = quick_panel_controller
        if session_manager.has_recoverable_session:
            QTimer.singleShot(0, self.offer_active_session_recovery)

    def offer_active_session_recovery(self) -> None:
        """Ask before restoring crash-checkpointed work; never count downtime."""
        checkpoint = self._session_manager.recovery_checkpoint
        if checkpoint is None:
            return
        message_box = QMessageBox(self._pet_window)
        message_box.setWindowTitle(tr("recovery.title"))
        message_box.setText(
            tr("recovery.found", subject=checkpoint.focus_item_name)
        )
        message_box.setInformativeText(tr("recovery.prompt"))
        recover_button = message_box.addButton(tr("common.recover"), QMessageBox.ButtonRole.AcceptRole)
        discard_button = message_box.addButton(tr("common.discard"), QMessageBox.ButtonRole.DestructiveRole)
        message_box.addButton(tr("common.cancel"), QMessageBox.ButtonRole.RejectRole)
        message_box.exec()
        if message_box.clickedButton() is recover_button:
            self._quick_panel_controller.recover_session()
        elif message_box.clickedButton() is discard_button:
            self._quick_panel_controller.discard_recovery()

    def request_exit(self) -> None:
        """Finish and persist an active session before a confirmed exit."""
        if self._session_manager.current_state is not TimerState.IDLE:
            message_box = QMessageBox(self._pet_window)
            message_box.setWindowTitle(tr("app.name"))
            message_box.setText(tr("exit.running"))
            message_box.setInformativeText(tr("exit.finish_prompt"))
            finish_button = message_box.addButton(tr("exit.finish_and_exit"), QMessageBox.ButtonRole.AcceptRole)
            message_box.addButton(tr("common.cancel"), QMessageBox.ButtonRole.RejectRole)
            message_box.exec()
            if message_box.clickedButton() is not finish_button:
                return
            if (
                self._quick_panel_controller.finish_session() is None
                and self._session_manager.current_state is not TimerState.IDLE
            ):
                return
        elif self._session_manager.has_pending_session:
            if self._quick_panel_controller.retry_pending_save() is None:
                return

        self._pet_controller.flush_settings()
        QApplication.quit()
