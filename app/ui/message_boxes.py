"""Localized message-box helpers with app-language button labels."""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget

from app.i18n import tr


def ask_confirmation(
    parent: QWidget | None,
    title: str,
    message: str,
    *,
    accept_key: str = "common.yes",
    destructive: bool = False,
) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setIcon(QMessageBox.Icon.Question)
    box.setText(message)
    role = (
        QMessageBox.ButtonRole.DestructiveRole
        if destructive
        else QMessageBox.ButtonRole.AcceptRole
    )
    accept = box.addButton(tr(accept_key), role)
    box.addButton(tr("common.cancel"), QMessageBox.ButtonRole.RejectRole)
    box.exec()
    return box.clickedButton() is accept
