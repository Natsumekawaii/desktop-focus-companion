"""Theme-aware confirmation icons without changing consent semantics."""

import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox

from app.core.icon_system import IconName, IconSystem
from app.core.theme import COLOR_THEMES, get_theme_manager
from app.i18n import get_localization, tr
from app.ui.message_boxes import _ConfirmationBox, ask_confirmation


@pytest.mark.parametrize("theme", COLOR_THEMES)
@pytest.mark.parametrize("destructive", [False, True])
def test_confirmation_uses_small_theme_icon(qt_application, theme, destructive):
    get_theme_manager().set_theme(theme)
    box = _ConfirmationBox(None, destructive=destructive)
    assert box.testOption(QMessageBox.Option.DontUseNativeDialog)
    assert box.icon() == QMessageBox.Icon.NoIcon
    assert box.iconPixmap().deviceIndependentSize().toSize() == QSize(28, 28)
    name = IconName.DELETE if destructive else IconName.CONFIRM
    expected = IconSystem.icon(name, 28).pixmap(QSize(28, 28), box.devicePixelRatioF())
    assert box.iconPixmap().toImage() == expected.toImage()


def test_confirmation_icon_updates_with_open_dialog_theme(qt_application):
    box = _ConfirmationBox(None, destructive=True)
    box.setText("A synthetic confirmation")
    box.show()
    for theme in COLOR_THEMES:
        get_theme_manager().set_theme(theme)
        expected = IconSystem.icon(IconName.DELETE, 28).pixmap(QSize(28, 28), box.devicePixelRatioF())
        assert box.iconPixmap().toImage() == expected.toImage()
    box.close()


@pytest.mark.parametrize("language", ["zh-CN", "en-US"])
@pytest.mark.parametrize("action", ["accept", "cancel", "escape", "close", "keyboard_accept"])
def test_delete_confirmation_labels_plain_text_and_result(qt_application, monkeypatch, language, action):
    get_localization().set_language(language)
    message = tr("agent.delete_chat_named", title="<b>A chat</b>")

    def execute(box):
        assert box.windowTitle() == tr("agent.delete_chat")
        assert box.text() == message and box.textFormat() == Qt.TextFormat.PlainText
        accept = next(b for b in box.buttons() if box.buttonRole(b) == QMessageBox.ButtonRole.DestructiveRole)
        cancel = next(b for b in box.buttons() if box.buttonRole(b) == QMessageBox.ButtonRole.RejectRole)
        assert accept.text() == tr("common.delete_action")
        assert cancel.text() == tr("common.cancel")
        assert box.buttonRole(accept) == QMessageBox.ButtonRole.DestructiveRole
        assert box.buttonRole(cancel) == QMessageBox.ButtonRole.RejectRole
        assert accept.objectName() == "danger"
        box.show()
        qt_application.processEvents()
        if action == "accept":
            accept.click()
        elif action == "cancel":
            cancel.click()
        elif action == "escape":
            QTest.keyClick(box, Qt.Key.Key_Escape)
        elif action == "close":
            box.close()
        else:
            accept.setFocus()
            QTest.keyClick(accept, Qt.Key.Key_Space)
        return 0

    monkeypatch.setattr(QMessageBox, "exec", execute)
    result = ask_confirmation(
        None, tr("agent.delete_chat"), message, accept_key="common.delete_action",
        destructive=True, plain_text=True,
    )
    assert result is (action in {"accept", "keyboard_accept"})


@pytest.mark.parametrize("destructive,key", [(False, "common.yes"), (True, "common.discard")])
def test_other_confirmation_labels_and_roles_remain_compatible(qt_application, monkeypatch, destructive, key):
    def execute(box):
        expected = QMessageBox.ButtonRole.DestructiveRole if destructive else QMessageBox.ButtonRole.AcceptRole
        accept = next(b for b in box.buttons() if box.buttonRole(b) == expected)
        assert accept.text() == tr(key)
        assert box.buttonRole(accept) == expected
        accept.click()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", execute)
    assert ask_confirmation(None, "Example", "Synthetic confirmation", accept_key=key, destructive=destructive)
