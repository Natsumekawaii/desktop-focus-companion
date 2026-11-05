"""Localized message-box helpers with app-language button labels."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QMessageBox, QWidget

from app.core.icon_system import IconName, IconSystem
from app.core.theme import get_theme_manager
from app.i18n import tr


class _ConfirmationBox(QMessageBox):
    """Native dialog behavior with a small, live-theme line icon."""

    def __init__(self, parent: QWidget | None, *, destructive: bool) -> None:
        super().__init__(parent)
        self.setOption(QMessageBox.Option.DontUseNativeDialog, True)
        self._icon_name = IconName.DELETE if destructive else IconName.CONFIRM
        get_theme_manager().theme_changed.connect(self._update_icon)
        self._update_icon()

    def _update_icon(self, _theme: str | None = None) -> None:
        self.setIconPixmap(
            IconSystem.icon(self._icon_name, 28).pixmap(
                QSize(28, 28), self.devicePixelRatioF()
            )
        )


def ask_confirmation(
    parent: QWidget | None,
    title: str,
    message: str,
    *,
    accept_key: str = "common.yes",
    destructive: bool = False,
    plain_text: bool = False,
) -> bool:
    box = _ConfirmationBox(parent, destructive=destructive)
    box.setWindowTitle(title)
    if plain_text:
        box.setTextFormat(Qt.TextFormat.PlainText)
    box.setText(message)
    role = (
        QMessageBox.ButtonRole.DestructiveRole
        if destructive
        else QMessageBox.ButtonRole.AcceptRole
    )
    accept = box.addButton(tr(accept_key), role)
    if destructive:
        accept.setObjectName("danger")
        accept.style().unpolish(accept)
        accept.style().polish(accept)
    box.addButton(tr("common.cancel"), QMessageBox.ButtonRole.RejectRole)
    try:
        box.exec()
        return box.clickedButton() is accept
    finally:
        box.deleteLater()
