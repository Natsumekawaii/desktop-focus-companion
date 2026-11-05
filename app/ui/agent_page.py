"""Theme-aware, network-safe chat presentation for the focus assistant."""

from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.agent.store import MODELS
from app.core.theme import DESIGN, get_theme_manager
from app.i18n import get_localization, tr
from app.ui.agent_conversations import ConversationList
from app.ui.agent_markdown import SafeMarkdown
from app.ui.agent_preview import ChangePreview, plain_label
from app.ui.rounded_selector import RoundedComboBox, SelectorDensity


class ToolCard(QFrame):
    confirm_requested = Signal(str)
    reject_requested = Signal(str)

    def __init__(self, card: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("agentToolCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        title = tr("agent.tool." + card.get("name", "apply_record_changes"))
        result = card.get("result", {})
        stale = result.get("code") == "stale_confirmation"
        status = tr("agent.state." + ("expired" if stale else card.get("status", "running")))
        self.header = plain_label(f"{title} · {status}")
        self.header.setWordWrap(False)
        self.header.setObjectName("agentToolHeader")
        layout.addWidget(self.header)
        if result.get("code"):
            explanation = tr("agent.validation." + result["code"])
            if explanation == "agent.validation." + result["code"]:
                explanation = tr("agent.tool_failed")
            self.header.setToolTip(explanation)
            self.header.setAccessibleDescription(explanation)
        elif card.get("status") == "failed":
            explanation = tr("agent.tool_failed")
            self.header.setToolTip(explanation)
            self.header.setAccessibleDescription(explanation)
        # Stored results remain intact for evidence/history and model continuation.
        # Only active confirmations expose record values in the user interface.
        if card.get("status") != "awaiting_confirmation" or stale:
            return
        preview = result.get("preview", result)
        layout.addWidget(plain_label(tr("agent.change_count", count=len(preview.get("changes", [])))))
        hint = plain_label(tr("agent.confirm_hint"))
        layout.addWidget(hint)
        for change in preview.get("changes", []):
            layout.addWidget(ChangePreview(change))
        actions = QHBoxLayout()
        confirm = QPushButton(tr("agent.confirm"))
        reject = QPushButton(tr("agent.reject"))
        confirm.clicked.connect(lambda: self.confirm_requested.emit(card["id"]))
        reject.clicked.connect(lambda: self.reject_requested.emit(card["id"]))
        actions.addWidget(confirm)
        actions.addWidget(reject)
        layout.addLayout(actions)


class TurnView(QWidget):
    content: str

    def __init__(self, page: AgentPage) -> None:
        super().__init__()
        self.page = page
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 12)
        self.user = QLabel()
        self.user.setTextFormat(Qt.TextFormat.PlainText)
        self.user.setWordWrap(True)
        self.user.setObjectName("agentUserMessage")
        self.user.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.user)
        self.cards_host = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_host)
        self.cards_layout.setContentsMargins(0, 6, 0, 6)
        layout.addWidget(self.cards_host)
        self.answer = SafeMarkdown()
        layout.addWidget(self.answer)
        # Only actionable failures need visible feedback; routine status, usage
        # and context bookkeeping stay in the stored turn, not under the reply.
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setObjectName("secondary")
        self.status.setWordWrap(True)
        self.status.hide()
        layout.addWidget(self.status)
        footer = QHBoxLayout()
        footer.addStretch()
        self.copy = QPushButton(tr("agent.copy"))
        self.copy.clicked.connect(
            lambda: QApplication.clipboard().setText(self.content)
        )
        footer.addWidget(self.copy)
        layout.addLayout(footer)
        self.content = ""
        self.signature = ""

    def update_turn(self, turn: dict[str, Any]) -> None:
        self.user.setText(turn.get("user", ""))
        content = turn.get("answer", "")
        if content != self.content:
            self.content = content
            self.answer.show_markdown(content)
        self.answer.setVisible(bool(content))
        error = tr("agent.error." + turn["error"]) if turn.get("error") else ""
        self.status.setText(error)
        self.status.setVisible(bool(error))
        self.copy.setText(tr("agent.copy"))
        signature = (
            json.dumps(turn.get("cards", []), ensure_ascii=False)
            + get_localization().language
            + get_theme_manager().theme_name
        )
        if self.signature != signature:
            while self.cards_layout.count():
                item = self.cards_layout.takeAt(0)
                if item and (widget := item.widget()):
                    widget.deleteLater()
            for data in turn.get("cards", []):
                card = ToolCard(data)
                card.confirm_requested.connect(self.page.confirm_requested)
                card.reject_requested.connect(self.page.reject_requested)
                self.cards_layout.addWidget(card)
            self.signature = signature


class AgentPage(QWidget):
    send_requested = Signal(str)
    stop_requested = Signal()
    new_requested = Signal()
    delete_requested = Signal()
    delete_conversation_requested = Signal(str)
    rename_conversation_requested = Signal(str)
    conversation_requested = Signal(str)
    configure_requested = Signal()
    preferences_changed = Signal(str, bool)
    confirm_requested = Signal(str)
    reject_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._layout_width_override: int | None = None
        self._busy = False
        self._stopping = False
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        header = QHBoxLayout()
        self.title = QLabel()
        self.title.setObjectName("pageTitle")
        self.history_toggle = QPushButton()
        self.history_toggle.setCheckable(True)
        self.configure = QPushButton()
        self.configure.clicked.connect(self.configure_requested)
        header.addWidget(self.title, 1)
        header.addWidget(self.history_toggle)
        header.addWidget(self.configure)
        root.addLayout(header)
        self.model = RoundedComboBox(density=SelectorDensity.COMPACT)
        self.model.setObjectName("agentComposerModel")
        for model in MODELS:
            self.model.addItem(model, model)
        self.thinking = QPushButton()
        self.thinking.setCheckable(True)
        self.model.currentIndexChanged.connect(self._preferences)
        self.thinking.toggled.connect(self._preferences)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        self.notice.setObjectName("secondary")
        root.addWidget(self.notice)
        body = QHBoxLayout()
        self.history = QWidget()
        self.history.setFixedWidth(180)
        history_layout = QVBoxLayout(self.history)
        history_layout.setContentsMargins(0, 0, 8, 0)
        self.new_button = QPushButton()
        self.new_button.clicked.connect(self.new_requested)
        self.conversations = ConversationList()
        self.conversations.rename_requested.connect(self.rename_conversation_requested)
        self.conversations.delete_requested.connect(self.delete_conversation_requested)
        self.conversations.setObjectName("agentConversations")
        self.conversations.setSpacing(3)
        self.conversations.currentItemChanged.connect(self._select)
        history_layout.addWidget(self.new_button)
        history_layout.addWidget(self.conversations, 1)
        body.addWidget(self.history)
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.chat_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.messages = QWidget()
        self.message_layout = QVBoxLayout(self.messages)
        self.message_layout.setContentsMargins(4, 0, 8, 4)
        self.empty_hint = QLabel()
        self.empty_hint.setWordWrap(True)
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint.setObjectName("agentEmptyHint")
        self.message_layout.addWidget(self.empty_hint)
        self.message_layout.addStretch()
        self.chat_scroll.setWidget(self.messages)
        body.addWidget(self.chat_scroll, 1)
        root.addLayout(body, 1)
        self.input = QTextEdit()
        self.input.setAcceptRichText(False)
        self.input.setFixedHeight(84)
        self.input.textChanged.connect(self._update_send_button)
        root.addWidget(self.input)
        actions = QHBoxLayout()
        self.send = QPushButton()
        self.send.setObjectName("agentComposerSend")
        self.send.clicked.connect(self._send)
        # Keep the whole row stable across language, selection and request states.
        for control in (self.model, self.thinking, self.send):
            control.setProperty("agentComposerControl", True)
            control.setFixedSize(160, 40)
        actions.addStretch()
        actions.setSpacing(8)
        actions.addWidget(self.model, 0, Qt.AlignmentFlag.AlignVCenter)
        actions.addWidget(self.thinking, 0, Qt.AlignmentFlag.AlignVCenter)
        actions.addWidget(self.send, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(actions)
        self.history_toggle.toggled.connect(
            lambda visible: self.history.setVisible(visible or self.width() >= 780)
        )
        self._views: dict[str, TurnView] = {}
        self._conversation = ""
        self._last_turns: list[dict[str, Any]] = []
        self._enabled = False
        get_theme_manager().theme_changed.connect(self._theme)
        get_localization().language_changed.connect(self.retranslate)
        self.retranslate()
        self._theme()

    def _preferences(self, *_: Any) -> None:
        self.preferences_changed.emit(
            str(self.model.currentData()), self.thinking.isChecked()
        )

    def set_preferences(self, model: str, thinking: bool, enabled: bool) -> None:
        self.model.blockSignals(True)
        self.thinking.blockSignals(True)
        self.model.setCurrentIndex(max(0, self.model.findData(model)))
        self.thinking.setChecked(thinking)
        self.model.blockSignals(False)
        self.thinking.blockSignals(False)
        self._enabled = enabled
        self.notice.setText(tr("agent.disclosure" if enabled else "agent.setup_hint"))

    def _send(self) -> None:
        if self._stopping:
            return
        if self._busy:
            self._stopping = True
            self._update_send_button()
            self.stop_requested.emit()
            return
        text = self.input.toPlainText().strip()
        if text:
            self.send_requested.emit(text)

    def _update_send_button(self) -> None:
        key = "agent.stopping" if self._stopping else "agent.stop" if self._busy else "agent.send"
        self.send.setText(tr(key))
        self.send.setToolTip(tr(key))
        self.send.setAccessibleName(tr(key))
        self.send.setEnabled(not self._stopping and (self._busy or bool(self.input.toPlainText().strip())))

    def _select(
        self, item: QListWidgetItem | None, _old: QListWidgetItem | None
    ) -> None:
        if item:
            self.conversation_requested.emit(str(item.data(Qt.ItemDataRole.UserRole)))

    def show_conversations(
        self, conversations: list[dict[str, Any]], selected: str
    ) -> None:
        scroll = self.conversations.verticalScrollBar().value()
        self.conversations.blockSignals(True)
        self.conversations.clear()
        for conversation in conversations:
            item = QListWidgetItem(conversation["title"])
            item.setData(Qt.ItemDataRole.UserRole, conversation["id"])
            item.setToolTip(conversation["title"])
            item.setSizeHint(QSize(150, 38))
            self.conversations.addItem(item)
            if conversation["id"] == selected:
                self.conversations.setCurrentItem(item)
        self.conversations.blockSignals(False)
        self.conversations.verticalScrollBar().setValue(scroll)

    def show_turns(
        self, conversation: str, turns: list[dict[str, Any]], busy: bool,
        *, stopping: bool = False,
    ) -> None:
        bar = self.chat_scroll.verticalScrollBar()
        follow = bar.maximum() - bar.value() < 40
        if conversation != self._conversation:
            for view in self._views.values():
                self.message_layout.removeWidget(view)
                view.deleteLater()
            self._views.clear()
            self._conversation = conversation
            follow = True
        self._last_turns = turns
        self.empty_hint.setVisible(not turns)
        for turn in turns:
            if turn["id"] not in self._views:
                view = TurnView(self)
                self._views[turn["id"]] = view
                self.message_layout.insertWidget(self.message_layout.count() - 1, view)
            self._views[turn["id"]].update_turn(turn)
        self._busy, self._stopping = busy, stopping and busy
        self._update_send_button()
        self.model.setEnabled(not busy)
        self.thinking.setEnabled(not busy)
        if follow:
            QTimer.singleShot(0, self, lambda: bar.setValue(bar.maximum()))

    def retranslate(self, *_: Any) -> None:
        for widget, key in (
            (self.title, "agent.title"),
            (self.history_toggle, "agent.conversations"),
            (self.configure, "agent.configure"),
            (self.thinking, "agent.thinking"),
            (self.new_button, "agent.new"),
        ):
            widget.setText(tr(key))
        self.thinking.setToolTip(tr("agent.thinking"))
        self.thinking.setAccessibleName(tr("agent.thinking"))
        self._update_send_button()
        self.input.setPlaceholderText(tr("agent.placeholder"))
        self.empty_hint.setText(tr("agent.empty_hint"))
        self.notice.setText(
            tr("agent.disclosure" if self._enabled else "agent.setup_hint")
        )
        for turn in self._last_turns:
            self._views[turn["id"]].update_turn(turn)

    def _theme(self, *_: Any) -> None:
        t = get_theme_manager().tokens
        self.setStyleSheet(f"""
            QComboBox[agentComposerControl="true"], QPushButton[agentComposerControl="true"] {{
                background: {t.surface}; color: {t.text};
                border: 1px solid {t.border}; border-radius: 10px;
                min-height: 38px; max-height: 38px; padding: 0;
                font-size: {DESIGN.font_body}px; font-weight: 500;
            }}
            QComboBox#agentComposerModel {{ padding: 0 0 0 10px; }}
            QComboBox[agentComposerControl="true"]:hover, QPushButton[agentComposerControl="true"]:hover {{
                background: {t.surface_hover}; border-color: {t.border_strong};
            }}
            QPushButton[agentComposerControl="true"]:checked {{
                background: {t.primary_soft}; color: {t.primary}; border-color: {t.border_strong};
            }}
            QPushButton[agentComposerControl="true"]:pressed {{ background: {t.primary_soft}; }}
            QPushButton#agentComposerSend {{
                background: {t.primary}; color: {t.primary_text}; border-color: {t.primary};
            }}
            QPushButton#agentComposerSend:hover {{ background: {t.primary_hover}; }}
            QPushButton#agentComposerSend:pressed {{ background: {t.primary_pressed}; }}
            QComboBox[agentComposerControl="true"]:focus, QPushButton[agentComposerControl="true"]:focus {{
                border-color: {t.focus_ring};
            }}
            QPushButton#agentComposerSend:focus {{ border-color: {t.focus_ring}; }}
            QComboBox[agentComposerControl="true"]:disabled,
            QPushButton[agentComposerControl="true"]:disabled, QPushButton#agentComposerSend:disabled {{
                background: {t.surface_alt}; color: {t.disabled}; border-color: {t.separator};
            }}
            QFrame#agentToolCard {{ background: {t.surface_alt}; border: 1px solid {t.border}; border-radius: 10px; }}
            QLabel#agentUserMessage {{ background: {t.primary_soft}; color: {t.text}; border-radius: 10px; padding: 12px; }}
            QTextBrowser {{ background: transparent; color: {t.text}; border: none; }}
            QListWidget#agentConversations {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 10px; padding: 4px; outline: 0; }}
            QListWidget#agentConversations::item {{ padding: 6px; border-radius: 8px; color: {t.text}; }}
            QListWidget#agentConversations::item:selected {{ background: {t.primary_soft}; color: {t.text}; }}
            QListWidget#agentConversations::item:hover {{ background: {t.surface_hover}; }}
            QLabel#agentEmptyHint {{ color: {t.muted}; background: {t.surface}; border: 1px solid {t.border}; border-radius: 14px; padding: 32px 20px; margin-top: 24px; }}
        """)
        for turn in self._last_turns:
            self._views[turn["id"]].update_turn(turn)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_history_visibility()

    def set_layout_width_override(self, width: int | None) -> None:
        """Hold responsive mode at the sidebar destination during live resizing."""
        self._layout_width_override = width
        self._update_history_visibility()

    def _update_history_visibility(self) -> None:
        width = self.width() if self._layout_width_override is None else self._layout_width_override
        self.history.setVisible(width >= 780 or self.history_toggle.isChecked())
        self.history_toggle.setVisible(width < 780)


class AgentConfigDialog(QDialog):
    test_requested = Signal(str)
    save_requested = Signal(str, bool)
    remove_requested = Signal()

    def __init__(self, has_key: bool, enabled: bool, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("agent.configure"))
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        disclosure = QLabel(tr("agent.privacy"))
        disclosure.setWordWrap(True)
        layout.addWidget(disclosure)
        form = QFormLayout()
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText(
            tr("agent.key_saved" if has_key else "agent.key_placeholder")
        )
        form.addRow("DeepSeek API Key", self.key)
        layout.addLayout(form)
        self.consent = QCheckBox(tr("agent.consent"))
        self.consent.setChecked(enabled)
        layout.addWidget(self.consent)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.test = QPushButton(tr("agent.test_connection"))
        self.save = QPushButton(tr("agent.save"))
        remove = QPushButton(tr("agent.remove_key"))
        close = QPushButton(tr("common.close"))
        self.test.clicked.connect(
            lambda: self.test_requested.emit(self.key.text().strip())
        )
        self.save.clicked.connect(
            lambda: self.save_requested.emit(
                self.key.text().strip(), self.consent.isChecked()
            )
        )
        remove.clicked.connect(self.remove_requested)
        close.clicked.connect(self.reject)
        for button in (self.test, self.save, remove, close):
            row.addWidget(button)
        layout.addLayout(row)
