"""Merged composer controls and identity-safe, local-only chat management."""

import sqlite3
import threading
from datetime import timezone

import pytest
from PySide6.QtCore import QCoreApplication, QPoint, QSize, Qt
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QPushButton,
    QStyle,
    QStyleOptionComboBox,
)
from test_agent import controller as controller_fixture
from test_agent import focus as focus_fixture

from app.agent.store import AgentStore
from app.core.theme import COLOR_THEMES, get_theme_manager
from app.i18n import get_localization, tr
from app.ui.agent_conversations import RenameConversationDialog
from app.ui.agent_page import AgentPage
from app.ui.dashboard import DashboardPage, DashboardWindow

controller = controller_fixture
focus = focus_fixture


@pytest.mark.parametrize(
    "status", ["streaming", "thinking", "running", "awaiting_confirmation"]
)
def test_one_button_stops_busy_turn_without_sending_draft(qt_application, status):
    page = AgentPage()
    page.show()
    send, stop = QSignalSpy(page.send_requested), QSignalSpy(page.stop_requested)
    assert not page.send.isEnabled()
    page.input.setPlainText("   \n ")
    assert not page.send.isEnabled()
    page.input.setPlainText("draft")
    width = page.send.width()
    page.send.click()
    assert send.count() == 1 and stop.count() == 0
    page.show_turns("id", [{"id": "turn", "status": status}], True)
    assert page.send.text() == tr("agent.stop") and page.send.width() == width
    assert not page.model.isEnabled() and not page.thinking.isEnabled()
    assert page.input.isEnabled()
    page.send.click()
    page.send.click()
    assert stop.count() == 1 and send.count() == 1
    assert not page.send.isEnabled() and page.send.text() == tr("agent.stopping")
    assert page.input.toPlainText() == "draft"
    page.show_turns("id", [{"id": "turn", "status": "cancelled"}], True, stopping=True)
    assert not page.send.isEnabled()
    page.show_turns("id", [{"id": "turn", "status": "cancelled"}], False)
    assert page.send.text() == tr("agent.send") and page.send.width() == width
    assert (
        page.send.isEnabled() and page.model.isEnabled() and page.thinking.isEnabled()
    )


@pytest.mark.parametrize("language", ["en-US", "zh-CN"])
@pytest.mark.parametrize("theme", COLOR_THEMES)
def test_bottom_composer_geometry_and_localized_states(qt_application, language, theme):
    get_localization().set_language(language)
    get_theme_manager().set_theme(theme)
    window = DashboardWindow(timezone.utc)
    window.set_sidebar_mode("expanded")
    window.set_current_page(DashboardPage.AI_ASSISTANT)
    window.show()
    page = window.agent_page
    for width in (600, 708, 864, 1120):
        window.resize(width + 160, 520)
        qt_application.processEvents()
        for busy, stopping in ((False, False), (True, False), (True, True)):
            page.show_turns("id", [], busy, stopping=stopping)
            qt_application.processEvents()
            assert page.width() == width
            assert page.input.height() == 84
            assert all(
                control.size() == QSize(160, 40)
                for control in (page.model, page.thinking, page.send)
            )
            assert page.model.y() == page.thinking.y() == page.send.y()
            assert page.thinking.x() - page.model.x() == 168
            assert page.send.x() - page.thinking.x() == 168
            option = QStyleOptionComboBox()
            page.model.initStyleOption(option)
            text_rect = page.model.style().subControlRect(
                QStyle.ComplexControl.CC_ComboBox,
                option,
                QStyle.SubControl.SC_ComboBoxEditField,
                page.model,
            )
            # Reserve the arrow once, not in both padding and drop-down width.
            assert text_rect.width() >= 108
            assert page.model.y() > page.input.geometry().bottom()
            assert page.model.geometry().right() < page.thinking.x()
            assert page.thinking.geometry().right() < page.send.x()
            assert page.send.geometry().right() <= width - 20
            assert page.rect().contains(page.send.geometry())
            assert not any(
                b.text() == tr("agent.delete_chat")
                for b in page.findChildren(QPushButton)
            )


def test_thinking_button_preserves_preferences_and_keyboard_toggle(qt_application):
    page = AgentPage()
    page.show()
    changed = QSignalSpy(page.preferences_changed)
    page.set_preferences("deepseek-v4-pro", True, True)
    assert page.thinking.isCheckable() and page.thinking.isChecked()
    assert changed.count() == 0
    page.thinking.click()
    assert changed.count() == 1 and changed.at(0) == ["deepseek-v4-pro", False]
    page.thinking.setFocus()
    QTest.keyClick(page.thinking, Qt.Key.Key_Space)
    assert changed.count() == 2 and changed.at(1) == ["deepseek-v4-pro", True]
    assert page.thinking.accessibleName() == tr("agent.thinking")
    page.show_turns("id", [], True)
    page.thinking.click()
    assert changed.count() == 2 and page.thinking.isChecked()
    page.show_turns("id", [], False)
    assert page.thinking.isEnabled() and page.thinking.isChecked()


def chats(page):
    page.show_conversations(
        [{"id": "a", "title": "Same"}, {"id": "b", "title": "Same"}], "a"
    )
    return page.conversations


def test_context_menu_does_not_select_and_remains_bound_to_clicked_id(qt_application):
    page = AgentPage()
    page.resize(1000, 640)
    page.show()
    listing = chats(page)
    qt_application.processEvents()
    selected = QSignalSpy(page.conversation_requested)
    renamed, deleted = (
        QSignalSpy(page.rename_conversation_requested),
        QSignalSpy(page.delete_conversation_requested),
    )
    point = listing.visualItemRect(listing.item(1)).center()
    QTest.mouseClick(listing.viewport(), Qt.MouseButton.RightButton, pos=point)
    assert selected.count() == 0 and listing.currentRow() == 0
    event = QContextMenuEvent(
        QContextMenuEvent.Reason.Mouse, point, listing.viewport().mapToGlobal(point)
    )
    QCoreApplication.sendEvent(listing.viewport(), event)
    menu = listing.context_menu
    assert [a.text() for a in menu.actions()] == [
        tr("agent.rename_chat"),
        tr("agent.delete_chat"),
    ]
    # Reordering/rebuilding rows while a menu is open must not retarget it.
    page.show_conversations(
        [{"id": "b", "title": "Same"}, {"id": "a", "title": "Same"}], "a"
    )
    menu.actions()[0].trigger()
    menu.actions()[1].trigger()
    assert renamed.at(0) == deleted.at(0) == ["b"]
    assert selected.count() == 0
    menu.hide()
    blank = QPoint(10, listing.viewport().height() - 5)
    QCoreApplication.sendEvent(
        listing.viewport(),
        QContextMenuEvent(
            QContextMenuEvent.Reason.Mouse, blank, listing.viewport().mapToGlobal(blank)
        ),
    )
    assert not menu.isVisible() and not menu.actions()
    listing.setFocus()
    QTest.keyClick(listing, Qt.Key.Key_F10, Qt.KeyboardModifier.ShiftModifier)
    assert menu.isVisible()
    menu.actions()[0].trigger()
    assert renamed.at(1) == ["a"]
    menu.hide()
    QTest.keyClick(listing, Qt.Key.Key_Menu)
    assert menu.isVisible()
    menu.hide()


def test_rename_dialog_validation(qt_application):
    page = AgentPage()
    dialog = RenameConversationDialog("Old", page)
    dialog.show()
    assert dialog.input.text() == "Old" and dialog.input.selectedText() == "Old"
    accept = dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
    dialog.input.setText("  ")
    assert not accept.isEnabled()
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    dialog.input.setText("长" * 70)
    assert len(dialog.input.text()) == 60
    dialog.input.setText("  New  ")
    assert dialog.title == "New" and accept.isEnabled()
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_manual_title_persists_without_changing_order_or_preferences(tmp_path):
    store = AgentStore(tmp_path)
    first, second = store.new_conversation("First"), store.new_conversation("Second")
    initial = store.conversations()
    preferences = store.preferences()
    store.rename_conversation(first, "  Second  ", manual=True)
    store = AgentStore(tmp_path)
    store.rename_conversation(first, "Do not replace this title")
    after = store.conversations()
    assert [(c["id"], c["updated"]) for c in after] == [
        (c["id"], c["updated"]) for c in initial
    ]
    assert all(c["title"] == "Second" for c in after)
    assert store.preferences() == preferences
    for invalid in ("", " ", "a" * 61):
        with pytest.raises(ValueError):
            store.rename_conversation(first, invalid, manual=True)
    store.delete_conversation(first)
    with store.connect() as connection:
        assert not connection.execute(
            "SELECT 1 FROM preferences WHERE key=?",
            (f"conversation.manual_title.{first}",),
        ).fetchone()
    assert store.conversations()[0]["id"] == second


def rename_as(monkeypatch, title, accepted=True):
    def show(dialog):
        dialog.input.setText(title)
        return QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected

    monkeypatch.setattr(RenameConversationDialog, "exec", show)


def test_manual_rename_of_empty_chat_survives_first_message(controller, monkeypatch):
    identity = controller.conversation
    rename_as(monkeypatch, "My title")
    controller.rename_conversation(identity)
    controller.send("Hello, first message")
    assert controller.store.conversations()[0]["title"] == "My title"


def test_rename_and_delete_other_chat_preserve_stream_and_draft(
    controller, monkeypatch
):
    import app.agent.controller as module

    other = controller.store.new_conversation("Other")
    current = controller.conversation
    controller.send("Hello")
    controller.client.cancelled = False
    controller.client.text_delta.emit("Partial")
    controller.page.input.setPlainText("next draft")
    turn = controller.turn
    rename_as(monkeypatch, "Renamed")
    controller.rename_conversation(other)
    assert controller.conversation == current and controller.turn is turn
    assert not controller.client.cancelled and controller.busy
    messages = []

    def confirm(*args, **kwargs):
        messages.append(args[2])
        assert kwargs["plain_text"] is True
        assert kwargs["accept_key"] == "common.delete_action"
        return True

    monkeypatch.setattr(module, "ask_confirmation", confirm)
    controller.delete_conversation_by_id(other)
    assert "Renamed" in messages[0]
    assert [c["id"] for c in controller.store.conversations()] == [current]
    assert (
        not controller.client.cancelled and controller.turn is turn and controller.busy
    )
    assert controller.page.input.toPlainText() == "next draft"
    assert len(controller.client.requests) == 1


def test_chat_operations_cancel_and_storage_failure_do_not_fake_success(
    controller, monkeypatch
):
    import app.agent.controller as module

    identity = controller.conversation
    before = controller.store.conversations()
    rename_as(monkeypatch, "Changed", accepted=False)
    controller.rename_conversation(identity)
    monkeypatch.setattr(module, "ask_confirmation", lambda *a, **k: False)
    controller.delete_conversation()
    assert controller.store.conversations() == before
    rename_as(monkeypatch, "Changed")

    def fail(*a, **k):
        raise sqlite3.OperationalError("simulated failure")

    monkeypatch.setattr(controller.store, "rename_conversation", fail)
    controller.rename_conversation(identity)
    assert controller.store.conversations() == before
    monkeypatch.setattr(module, "ask_confirmation", lambda *a, **k: True)
    monkeypatch.setattr(controller.store, "delete_conversation", fail)
    controller.delete_conversation()
    assert (
        controller.conversation == identity
        and controller.store.conversations() == before
    )
    assert controller.page.notice.text() == tr("agent.error.storage")
    assert controller._deleting_conversation is None


def test_delete_current_and_last_chats_preserves_focus_records(
    controller, focus, monkeypatch
):
    import app.agent.controller as module

    monkeypatch.setattr(module, "ask_confirmation", lambda *a, **k: True)
    before = focus[2].list_sessions()
    old = controller.conversation
    other = controller.store.new_conversation("Remaining")
    controller.delete_conversation()
    assert controller.conversation == other and controller.turn is None
    assert old not in [c["id"] for c in controller.store.conversations()]
    controller.delete_conversation()
    remaining = controller.store.conversations()
    assert len(remaining) == 1 and remaining[0]["id"] != other
    assert controller.conversation == remaining[0]["id"] and not controller.turns
    assert focus[2].list_sessions() == before


def test_delete_waits_for_owned_tool_callback_before_removing_chat(
    controller, qt_wait_until, monkeypatch
):
    import app.agent.controller as module

    monkeypatch.setattr(module, "ask_confirmation", lambda *a, **k: True)
    controller.send("Hello")
    identity, turn = controller.conversation, controller.turn
    gate = threading.Event()
    callback_ran = []

    def delayed():
        if not gate.wait(3):
            raise RuntimeError("Test gate timed out")
        return "committed"

    def ready(result, error):
        assert not error and result == "committed"
        controller.store.save_turn(identity, turn)
        callback_ran.append(True)

    controller._job(delayed, ready)
    try:
        controller.delete_conversation()
        assert identity in [c["id"] for c in controller.store.conversations()]
        assert controller.page.send.text() == tr("agent.stopping")
        assert not controller.page.send.isEnabled()
        controller.new_conversation()
        assert controller.conversation == identity
    finally:
        gate.set()
    qt_wait_until(lambda: controller.worker is None)
    assert callback_ran and not controller.busy
    assert identity not in [c["id"] for c in controller.store.conversations()]
    assert not controller.store.turns(identity)
    controller._render()
    controller._save()
    assert not controller.store.turns(identity)


def test_store_delete_and_fallback_roll_back_together(tmp_path):
    store = AgentStore(tmp_path)
    identity = store.new_conversation("Preserve")
    store.rename_conversation(identity, "Manual", manual=True)
    with store.connect() as connection:
        connection.execute(
            "CREATE TRIGGER reject_replacement BEFORE INSERT ON conversations BEGIN SELECT RAISE(ABORT, 'simulated'); END"
        )
    with pytest.raises(sqlite3.IntegrityError):
        store.delete_conversation(identity, fallback_title="New")
    assert store.conversations()[0]["id"] == identity
    store.rename_conversation(identity, "Must not overwrite")
    assert store.conversations()[0]["title"] == "Manual"


def test_store_manual_title_marker_and_name_roll_back_together(tmp_path):
    store = AgentStore(tmp_path)
    identity = store.new_conversation("Original")
    with store.connect() as connection:
        connection.execute(
            "CREATE TRIGGER reject_marker BEFORE INSERT ON preferences BEGIN SELECT RAISE(ABORT, 'simulated'); END"
        )
    with pytest.raises(sqlite3.IntegrityError):
        store.rename_conversation(identity, "Changed", manual=True)
    assert store.conversations()[0]["title"] == "Original"


def test_merged_stop_preserves_partial_answer_and_unsent_draft(controller):
    controller.page.input.setPlainText("Hello")
    controller.page.send.click()
    assert controller.busy and controller.page.send.text() == tr("agent.stop")
    controller.client.text_delta.emit("Partial response")
    controller.page.input.setPlainText("Next draft")
    controller.page.send.click()
    assert controller.client.cancelled and not controller.busy
    assert controller.page.send.text() == tr("agent.send")
    assert controller.turn["answer"] == "Partial response"
    assert controller.page.input.toPlainText() == "Next draft"
    assert len(controller.client.requests) == 1


def test_merged_stop_waits_for_local_job_then_restores_send(controller, qt_wait_until):
    controller.send("Hello")
    gate = threading.Event()

    def wait():
        assert gate.wait(3)

    controller._job(wait, lambda _result, _error: None)
    try:
        controller.page.input.setPlainText("draft")
        controller.page.send.click()
        assert controller.busy and controller.page.send.text() == tr("agent.stopping")
        assert (
            not controller.page.send.isEnabled()
            and not controller.page.model.isEnabled()
        )
        controller.page.send.click()
        assert len(controller.client.requests) == 1
    finally:
        gate.set()
    qt_wait_until(lambda: controller.worker is None)
    assert (
        controller.page.send.text() == tr("agent.send")
        and controller.page.send.isEnabled()
    )
    assert controller.page.input.toPlainText() == "draft"


def test_delete_old_chat_waits_for_its_worker_without_switching_current_chat(
    controller, qt_wait_until, monkeypatch
):
    import app.agent.controller as module

    monkeypatch.setattr(module, "ask_confirmation", lambda *a, **k: True)
    controller.send("Hello")
    old, turn = controller.conversation, controller.turn
    new = controller.store.new_conversation("New")
    gate = threading.Event()

    def wait():
        assert gate.wait(3)

    controller._job(wait, lambda _r, _e: controller.store.save_turn(old, turn))
    try:
        controller.select_conversation(new)
        controller.page.input.setPlainText("new chat draft")
        controller.delete_conversation_by_id(old)
        assert controller.conversation == new
        assert old in [c["id"] for c in controller.store.conversations()]
    finally:
        gate.set()
    qt_wait_until(lambda: controller.worker is None)
    assert controller.conversation == new and controller.turn is None
    assert controller.page.input.toPlainText() == "new chat draft"
    assert not controller.store.turns(old)
    assert old not in [c["id"] for c in controller.store.conversations()]


def test_rename_current_streaming_chat_keeps_request_and_order(controller, monkeypatch):
    controller.send("Hello")
    controller.client.cancelled = False
    turn = controller.turn
    before = controller.store.conversations()
    rename_as(monkeypatch, "Renamed live")
    controller.rename_conversation(controller.conversation)
    after = controller.store.conversations()
    assert before[0]["updated"] == after[0]["updated"]
    assert after[0]["title"] == "Renamed live"
    assert (
        controller.turn is turn and controller.busy and not controller.client.cancelled
    )
