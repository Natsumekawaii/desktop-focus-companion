"""Deterministic sidebar frames and compact, confirmation-safe tool cards."""

from copy import deepcopy
from datetime import timezone

import pytest
from PySide6.QtCore import QAbstractAnimation, QCoreApplication, QEvent
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QLabel, QPushButton, QTextEdit

from app.core.theme import COLOR_THEMES, get_theme_manager
from app.i18n import get_localization, tr
from app.ui.agent_page import AgentPage, ToolCard, TurnView
from app.ui.agent_preview import ChangePreview
from app.ui.dashboard import DashboardPage, DashboardWindow


def intermediate(window, time=65):
    animation = window._sidebar.animation
    animation.pause()
    animation.setCurrentTime(time)


def test_live_sidebar_frames_reverse_without_snapping_or_queueing(qt_application):
    window = DashboardWindow(timezone.utc)
    window.resize(1024, 640)
    window.show()
    qt_application.processEvents()
    sidebar = window._sidebar
    original_page = window.current_page()
    first_y = window._nav_buttons[DashboardPage.OVERVIEW].y()
    window._sidebar_toggle.click()
    assert sidebar.animation.duration() == 180
    assert sidebar.width() == 160
    intermediate(window, 50)
    qt_application.processEvents()
    assert 52 < sidebar.width() < 160
    assert 0 < sidebar.progress < 1
    assert (
        0
        < window._nav_focus_label.height()
        < window._nav_focus_label.fontMetrics().height() + 16
    )
    assert window._nav_buttons[DashboardPage.OVERVIEW].y() < first_y
    assert window._pages.x() == sidebar.width()
    assert all(b.reveal == sidebar.progress for b in window._nav_buttons.values())
    previous_width, previous_progress = sidebar.width(), sidebar.progress
    window._sidebar_toggle.click()
    assert sidebar.width() == previous_width and sidebar.progress == previous_progress
    assert sidebar.animation.duration() == round(180 * (1 - previous_progress))
    intermediate(window, sidebar.animation.duration() // 2)
    qt_application.processEvents()
    assert previous_width < sidebar.width() < 160
    previous_width = sidebar.width()
    window._sidebar_toggle.click()
    assert sidebar.width() == previous_width
    sidebar.animation.setCurrentTime(sidebar.animation.duration())
    qt_application.processEvents()
    assert sidebar.width() == 52 and window._pages.x() == 52
    assert sidebar.animation.state() == QAbstractAnimation.State.Stopped
    assert window.current_page() == original_page
    assert window._nav_focus_label.height() == 0
    assert window._nav_buttons[DashboardPage.OVERVIEW].height() == 42


@pytest.mark.parametrize("finish_event", ["hide", "theme", "language", "restore"])
def test_sidebar_safely_settles_on_visual_changes(qt_application, finish_event):
    window = DashboardWindow(timezone.utc)
    window.show()
    qt_application.processEvents()
    window._sidebar_toggle.click()
    intermediate(window)
    assert 52 < window._sidebar.width() < 160
    if finish_event == "hide":
        window.hide()
    elif finish_event == "theme":
        manager = get_theme_manager()
        manager.set_theme("charcoal" if manager.theme_name != "charcoal" else "blue")
        manager._transition.finish_all()
    elif finish_event == "language":
        locale = get_localization()
        locale.set_language("en-US" if locale.language != "en-US" else "zh-CN")
    else:
        window.set_sidebar_mode("collapsed")
    qt_application.processEvents()
    assert window._sidebar.width() == 52
    assert window._sidebar.animation.state() == QAbstractAnimation.State.Stopped
    window.show()
    assert window.sidebar_mode == "collapsed"


def test_auto_resize_does_not_restart_motion_and_manual_overrides_it(qt_application):
    window = DashboardWindow(timezone.utc)
    window.show()
    qt_application.processEvents()
    saved = QSignalSpy(window.sidebar_mode_changed)
    window.resize(800, 640)
    intermediate(window, 50)
    progress = window._sidebar.progress
    for width in (810, 820, 830):
        window.resize(width, 640)
        qt_application.processEvents()
        assert window._sidebar.progress == progress
        assert window._sidebar.animation.currentTime() == 50
    assert saved.count() == 0
    window._sidebar_toggle.click()
    window._sidebar.finish()
    window.resize(760, 520)
    qt_application.processEvents()
    assert window.sidebar_mode == "expanded" and window._sidebar.width() == 160
    assert saved.count() == 1


def test_sidebar_does_not_thrash_chat_history_breakpoint(qt_application):
    window = DashboardWindow(timezone.utc)
    window.set_sidebar_mode("expanded")
    window.resize(880, 640)
    window.set_current_page(DashboardPage.AI_ASSISTANT)
    window.show()
    qt_application.processEvents()
    page = window.agent_page
    assert not page.history.isVisible()
    page.input.setPlainText("unchanged draft")
    page.input.setFocus()
    window._toggle_sidebar()  # Preserve keyboard focus while checking geometry.
    for t in (20, 70, 110, 160):
        intermediate(window, t)
        qt_application.processEvents()
        assert page.history.isVisible()
        assert page.input.hasFocus()
        assert page.input.toPlainText() == "unchanged draft"
    window._sidebar.finish()
    qt_application.processEvents()
    assert page.history.isVisible()
    window._toggle_sidebar()
    for t in (20, 70, 110, 160):
        intermediate(window, t)
        qt_application.processEvents()
        assert not page.history.isVisible()


def test_sidebar_real_time_completion(qt_application, qt_wait_until):
    window = DashboardWindow(timezone.utc)
    window.show()
    qt_application.processEvents()
    window._sidebar_toggle.click()
    qt_wait_until(
        lambda: window._sidebar.animation.state() == QAbstractAnimation.State.Stopped
    )
    assert window._sidebar.width() == 52


def sample_card(status="completed"):
    before = {
        "id": 23,
        "focus_item_name": "Demo",
        "note": "old note",
        "start_time": "2026-11-04T08:00:03+08:00",
        "end_time": "2026-11-04T10:00:07+08:00",
        "duration_seconds": 3603,
    }
    return {
        "id": "one-plan",
        "name": "apply_record_changes",
        "status": status,
        "result": {
            "queried_at": "2026-11-04T12:34:56+08:00",
            "total_count": 1200,
            "scope": {"start_date": "2026-10-01", "keyword": "secret query"},
            "changes": [
                {
                    "kind": "update",
                    "before": before,
                    "after": {**before, "note": "new note"},
                    "overlapping_record_ids": [24],
                }
            ],
        },
    }


@pytest.mark.parametrize("status", ["running", "completed", "cancelled", "failed"])
@pytest.mark.parametrize("language", ["en-US", "zh-CN"])
def test_ordinary_tool_cards_are_one_line_without_losing_internal_evidence(
    status, language
):
    get_localization().set_language(language)
    for theme in COLOR_THEMES:
        get_theme_manager().set_theme(theme)
        source = sample_card(status)
        before = deepcopy(source)
        card = ToolCard(source)
        labels = card.findChildren(QLabel)
        assert labels == [card.header]
        assert card.header.text() == tr("agent.tool.apply_record_changes") + " · " + tr(
            "agent.state." + status
        )
        assert not card.header.wordWrap()
        assert not card.findChildren(QTextEdit)
        assert not card.findChildren(QPushButton)
        assert not card.findChildren(ChangePreview)
        assert source == before
        if status == "failed":
            assert card.header.toolTip() == tr("agent.tool_failed")


def test_confirmation_only_expands_until_finished_and_never_shows_json(qt_application):
    page = AgentPage()
    turn = TurnView(page)
    source = sample_card("awaiting_confirmation")
    data = {
        "user": "Change the note",
        "cards": [source],
        "status": "awaiting_confirmation",
    }
    turn.update_turn(data)
    card = turn.findChildren(ToolCard)[0]
    assert len(card.findChildren(ChangePreview)) == 1
    assert not card.findChildren(QTextEdit)
    labels = "\n".join(w.text() for w in card.findChildren(QLabel))
    assert "08:00:03" in labels and "10:00:07" in labels
    assert "old note" in labels and "new note" in labels and "#24" in labels
    assert "12:34:56" not in labels and "secret query" not in labels
    confirmed, rejected = (
        QSignalSpy(page.confirm_requested),
        QSignalSpy(page.reject_requested),
    )
    buttons = card.findChildren(QPushButton)
    assert len(buttons) == 2
    next(b for b in buttons if b.text() == tr("agent.confirm")).click()
    next(b for b in buttons if b.text() == tr("agent.reject")).click()
    assert confirmed.count() == rejected.count() == 1
    assert confirmed.at(0) == rejected.at(0) == ["one-plan"]
    source["status"] = "completed"
    turn.update_turn(data)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    card = turn.findChildren(ToolCard)[0]
    assert len(card.findChildren(QLabel)) == 1
    assert not card.findChildren(QPushButton)
    assert not card.findChildren(ChangePreview)


@pytest.mark.parametrize(
    "code", ["stale_confirmation", "duration_conflict", "private_internal_error"]
)
def test_failed_tool_cards_explain_failure_without_reexposing_parameters(code):
    source = sample_card("failed")
    source["result"]["code"] = code
    card = ToolCard(source)
    assert len(card.findChildren(QLabel)) == 1 and not card.findChildren(QPushButton)
    if code == "stale_confirmation":
        assert tr("agent.state.expired") in card.header.text()
    explanation = tr(
        "agent.tool_failed"
        if code == "private_internal_error"
        else "agent.validation." + code
    )
    assert card.header.toolTip() == card.header.accessibleDescription() == explanation
