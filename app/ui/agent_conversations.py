"""Identity-bound chat context menus and a small localized rename dialog."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QContextMenuEvent, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.i18n import get_localization, tr
from app.ui.rounded_menu import RoundedMenu


class ConversationList(QListWidget):
    rename_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.context_menu = RoundedMenu(self)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            event.accept()  # A right click must not activate/cancel another chat.
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        keyboard = event.reason() == QContextMenuEvent.Reason.Keyboard
        item = self.currentItem() if keyboard else self.itemAt(event.pos())
        position = (
            self.viewport().mapToGlobal(self.visualItemRect(item).center())
            if keyboard and item
            else event.globalPos()
        )
        self._open_menu(item, position)
        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Menu or (
            event.key() == Qt.Key.Key_F10
            and event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            item = self.currentItem()
            if item:
                self._open_menu(
                    item,
                    self.viewport().mapToGlobal(self.visualItemRect(item).center()),
                )
            event.accept()
            return
        super().keyPressEvent(event)

    def _open_menu(self, item: QListWidgetItem | None, position: QPoint) -> None:
        self.context_menu.hide()
        self.context_menu.clear()
        if item is None:
            return
        identity = str(item.data(Qt.ItemDataRole.UserRole))
        rename = self.context_menu.addAction(tr("agent.rename_chat"))
        delete = self.context_menu.addAction(tr("agent.delete_chat"))
        rename.triggered.connect(lambda: self.rename_requested.emit(identity))
        delete.triggered.connect(lambda: self.delete_requested.emit(identity))
        self.context_menu.popup(position)


class RenameConversationDialog(QDialog):
    def __init__(self, title: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setFixedWidth(360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 16)
        self.caption = QLabel()
        self.input = QLineEdit(title)
        self.input.setMaxLength(60)
        self.input.selectAll()
        self.caption.setBuddy(self.input)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.input.textChanged.connect(self._validate)
        layout.addWidget(self.caption)
        layout.addWidget(self.input)
        layout.addWidget(self.buttons)
        get_localization().language_changed.connect(self.retranslate)
        self.retranslate()
        self._validate()

    @property
    def title(self) -> str:
        return self.input.text().strip()

    def accept(self) -> None:
        if self.title and len(self.title) <= 60:
            super().accept()

    def _validate(self) -> None:
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
            bool(self.title)
        )

    def retranslate(self, *_: object) -> None:
        self.setWindowTitle(tr("agent.rename_chat"))
        self.caption.setText(tr("agent.chat_name"))
        self.input.setAccessibleName(tr("agent.chat_name"))
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            tr("common.save")
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            tr("common.cancel")
        )
