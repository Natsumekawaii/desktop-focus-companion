"""Reply footers omit routine metadata without hiding actionable failures."""

from copy import deepcopy

import pytest
from PySide6.QtWidgets import QLabel

from app.i18n import get_localization, tr
from app.ui.agent_page import AgentPage


@pytest.mark.parametrize("language", ["en-US", "zh-CN"])
@pytest.mark.parametrize(
    "state",
    ["completed", "streaming", "thinking", "running", "awaiting_confirmation", "cancelled"],
)
def test_reply_hides_routine_footer_and_keeps_copy(qt_application, language, state):
    get_localization().set_language(language)
    page = AgentPage()
    page.resize(900, 600)
    page.show()
    turn = {
        "id": "reply",
        "user": "Example question",
        "answer": "**Example answer**",
        "status": state,
        "context_trimmed": True,
        "usage": {"total_tokens": 3894},
    }
    original = deepcopy(turn)
    page.show_turns("chat", [turn], False)
    qt_application.processEvents()
    view = page._views["reply"]
    assert view.status.isHidden() and not view.status.text()
    assert [label.text() for label in view.findChildren(QLabel) if label.isVisible()] == [
        turn["user"]
    ]
    assert view.copy.isVisible() and view.copy.text() == tr("agent.copy")
    assert view.copy.geometry().right() == view.width() - 1
    previous_clipboard = qt_application.clipboard().text()
    try:
        view.copy.click()
        assert qt_application.clipboard().text() == turn["answer"]
    finally:
        qt_application.clipboard().setText(previous_clipboard)
    assert turn == original  # Presentation must not remove persisted metadata.


@pytest.mark.parametrize("language", ["en-US", "zh-CN"])
def test_reply_shows_only_actionable_error_and_clears_it(qt_application, language):
    get_localization().set_language(language)
    page = AgentPage()
    page.show()
    turn = {
        "id": "reply", "status": "failed", "error": "network",
        "context_trimmed": True, "usage": {"total_tokens": 3894},
    }
    page.show_turns("chat", [turn], False)
    view = page._views["reply"]
    assert not view.status.isHidden()
    assert view.status.text() == tr("agent.error.network")
    page.show_turns("chat", [{"id": "reply", "status": "completed"}], False)
    assert view.status.isHidden() and not view.status.text()
