"""Theme-aware, network-safe chat presentation for the focus assistant."""

from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QResizeEvent, QTextDocument
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.agent.store import MODELS
from app.core.theme import get_theme_manager
from app.i18n import get_localization, tr
from app.ui.rounded_selector import RoundedComboBox


class SafeMarkdown(QTextBrowser):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setOpenExternalLinks(False)
        self.setOpenLinks(False)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

    def loadResource(self, resource_type: int, name: QUrl | str) -> Any:
        return None  # Never load remote images, local files, stylesheets or URLs.

    def show_markdown(self, value: str) -> None:
        self.document().setMarkdown(value, QTextDocument.MarkdownFeature.MarkdownNoHTML)
        self._fit()

    def _fit(self) -> None:
        self.document().setTextWidth(max(150, self.viewport().width()))
        self.setFixedHeight(max(40, int(self.document().size().height()) + 14))

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fit()


class ToolCard(QFrame):
    confirm_requested = Signal(str)
    reject_requested = Signal(str)

    def __init__(self, card: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("agentToolCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        title = tr("agent.tool." + card.get("name", "apply_record_changes"))
        status = tr("agent.state." + card.get("status", "running"))
        button = QPushButton(f"{title} · {status}")
        button.setCheckable(True)
        layout.addWidget(button)
        result = card.get("result", {})
        scope = result.get("scope", {})
        summary_parts = []
        if scope:
            summary_parts.append(
                " · ".join(
                    str(scope[k])
                    for k in ("start_date", "end_date", "focus_item_id", "keyword")
                    if k in scope
                )
            )
        if "total_count" in result or "record_count" in result:
            summary_parts.append(
                tr(
                    "agent.record_count",
                    count=result.get("total_count", result.get("record_count")),
                )
            )
        if result.get("changes"):
            summary_parts.append(tr("agent.change_count", count=len(result["changes"])))
        if result.get("queried_at"):
            summary_parts.append(tr("agent.queried_at", time=result["queried_at"]))
        if summary_parts:
            summary = QLabel("\n".join(summary_parts))
            summary.setTextFormat(Qt.TextFormat.PlainText)
            summary.setWordWrap(True)
            summary.setObjectName("secondary")
            layout.addWidget(summary)
        details = QTextEdit()
        details.setReadOnly(True)
        details.setPlainText(
            json.dumps(card.get("result", {}), indent=2, ensure_ascii=False)
        )
        details.setFixedHeight(230)
        details.setVisible(False)
        button.toggled.connect(details.setVisible)
        layout.addWidget(details)
        if card.get("status") == "awaiting_confirmation":
            hint = QLabel(tr("agent.confirm_hint"))
            hint.setWordWrap(True)
            layout.addWidget(hint)
            details.setVisible(True)
            button.setChecked(True)
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
        footer = QHBoxLayout()
        self.status = QLabel()
        self.status.setObjectName("secondary")
        self.status.setWordWrap(True)
        self.copy = QPushButton(tr("agent.copy"))
        self.copy.clicked.connect(
            lambda: QApplication.clipboard().setText(self.content)
        )
        footer.addWidget(self.status, 1)
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
        status = tr("agent.state." + turn.get("status", "completed"))
        if turn.get("error"):
            status += " · " + tr("agent.error." + turn["error"])
        if turn.get("context_trimmed"):
            status += " · " + tr("agent.context_trimmed")
        if turn.get("usage", {}).get("total_tokens"):
            status += " · " + tr("agent.usage", count=turn["usage"]["total_tokens"])
        self.status.setText(status)
        self.copy.setText(tr("agent.copy"))
        signature = (
            json.dumps(turn.get("cards", []), ensure_ascii=False)
            + get_localization().language
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
    conversation_requested = Signal(str)
    configure_requested = Signal()
    preferences_changed = Signal(str, bool)
    confirm_requested = Signal(str)
    reject_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
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
        controls = QHBoxLayout()
        self.model = RoundedComboBox()
        for model in MODELS:
            self.model.addItem(model, model)
        self.thinking = QCheckBox()
        self.model.currentIndexChanged.connect(self._preferences)
        self.thinking.toggled.connect(self._preferences)
        controls.addWidget(self.model)
        controls.addWidget(self.thinking)
        controls.addStretch()
        root.addLayout(controls)
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
        self.delete_button = QPushButton()
        self.delete_button.clicked.connect(self.delete_requested)
        self.conversations = QListWidget()
        self.conversations.setObjectName("agentConversations")
        self.conversations.setSpacing(3)
        self.conversations.currentItemChanged.connect(self._select)
        history_layout.addWidget(self.new_button)
        history_layout.addWidget(self.conversations, 1)
        history_layout.addWidget(self.delete_button)
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
        root.addWidget(self.input)
        actions = QHBoxLayout()
        self.send = QPushButton()
        self.stop = QPushButton()
        self.send.clicked.connect(self._send)
        self.stop.clicked.connect(self.stop_requested)
        actions.addStretch()
        actions.addWidget(self.stop)
        actions.addWidget(self.send)
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
        text = self.input.toPlainText().strip()
        if text:
            self.send_requested.emit(text)

    def _select(
        self, item: QListWidgetItem | None, _old: QListWidgetItem | None
    ) -> None:
        if item:
            self.conversation_requested.emit(str(item.data(Qt.ItemDataRole.UserRole)))

    def show_conversations(
        self, conversations: list[dict[str, Any]], selected: str
    ) -> None:
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

    def show_turns(
        self, conversation: str, turns: list[dict[str, Any]], busy: bool
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
        self.send.setEnabled(not busy)
        self.stop.setEnabled(busy)
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
            (self.delete_button, "agent.delete_chat"),
            (self.send, "agent.send"),
            (self.stop, "agent.stop"),
        ):
            widget.setText(tr(key))
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
            QFrame#agentToolCard {{ background: {t.surface_alt}; border: 1px solid {t.border}; border-radius: 10px; }}
            QLabel#agentUserMessage {{ background: {t.primary_soft}; color: {t.text}; border-radius: 10px; padding: 12px; }}
            QTextBrowser {{ background: transparent; color: {t.text}; border: none; }}
            QListWidget#agentConversations {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 10px; padding: 4px; outline: 0; }}
            QListWidget#agentConversations::item {{ padding: 6px; border-radius: 8px; color: {t.text}; }}
            QListWidget#agentConversations::item:selected {{ background: {t.primary_soft}; color: {t.text}; }}
            QListWidget#agentConversations::item:hover {{ background: {t.surface_hover}; }}
            QLabel#agentEmptyHint {{ color: {t.muted}; background: {t.surface}; border: 1px solid {t.border}; border-radius: 14px; padding: 32px 20px; margin-top: 24px; }}
        """)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.history.setVisible(self.width() >= 780 or self.history_toggle.isChecked())
        self.history_toggle.setVisible(self.width() < 780)


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
