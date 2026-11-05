"""One cancellable agent turn, with client-owned authorization and confirmations."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from PySide6.QtCore import QEvent, QObject, QThread, QTimer, Signal
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from app.agent.client import DeepSeekClient
from app.agent.credentials import CredentialStore
from app.agent.prompts import system_prompt, tool_definitions
from app.agent.protocol import json_object
from app.agent.requests import WriteRequestContext, is_supplement
from app.agent.store import AgentStore, redact, request_history
from app.agent.tools import WRITE_TOOL, FocusTools
from app.agent.validation import ToolValidationError, operation_signature
from app.core.timezones import system_timezone
from app.data.database import Database
from app.data.focus_record_changes import RecordChangePlan, apply_changes
from app.i18n import get_localization, tr
from app.ui.agent_conversations import RenameConversationDialog
from app.ui.agent_page import AgentConfigDialog, AgentPage
from app.ui.message_boxes import ask_confirmation


class ToolJob(QThread):
    def __init__(self, action: Callable[[], Any], parent: QObject) -> None:
        super().__init__(parent)
        self.action = action
        self.result: Any = None
        self.error = ""

    def run(self) -> None:
        try:
            self.result = self.action()
        except ToolValidationError as error:
            self.result = {"validation_error": error.payload()}
            self.error = str(error)
        except (
            ValueError,
            TypeError,
            KeyError,
            RuntimeError,
            OSError,
            sqlite3.Error,
        ) as error:
            self.error = redact(str(error))[:500]
        except Exception:  # noqa: BLE001 — thread boundary: never log user data or escape into Qt.
            self.error = "Unexpected tool failure; no success assumed."


class AgentController(QObject):
    records_changed = Signal()

    def __init__(
        self,
        page: AgentPage,
        data_dir: Path,
        database: Database,
        active_timer: Callable[[], dict[str, Any]],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.page, self.database = page, database
        self.active_timer = active_timer
        self.store = AgentStore(data_dir)
        self.credentials = CredentialStore(data_dir)
        self.client = DeepSeekClient(self)
        self.config_client = DeepSeekClient(self)
        self.client.text_delta.connect(self._delta)
        self.client.thinking.connect(self._thinking)
        self.client.completed.connect(self._response)
        self.client.failed.connect(self._network_failed)
        self.config_client.models_ready.connect(self._models_ready)
        self.config_client.failed.connect(self._config_error)
        self.dialog: AgentConfigDialog | None = None
        self._config_key = ""
        self._config_save = False
        self._answer_text = ""
        self.preferences: dict[str, Any] = {
            "enabled": False,
            "model": "deepseek-flash",
            "thinking": False,
            "models": [],
        }
        self.conversation = ""
        self.turns: list[dict[str, Any]] = []
        self.turn: dict[str, Any] | None = None
        self.tools: FocusTools | None = None
        self.worker: ToolJob | None = None
        self._worker_conversation: str | None = None
        self._deleting_conversation: str | None = None
        self._cancel = threading.Event()
        self._request_count = 0
        self._messages: list[dict[str, Any]] = []
        self._calls: list[dict[str, Any]] = []
        self._pending: (
            tuple[RecordChangePlan, dict[str, Any], dict[str, Any]] | None
        ) = None
        self._write_allowed = False
        self._evidence: list[str] = []
        self._action_context: WriteRequestContext | None = None
        self._repair_signature: str | None = None
        self._last_validation: dict[str, Any] | None = None
        self._zone = ""
        self._now = datetime.now(timezone.utc)
        self._active: dict[str, Any] = {}
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(60)
        self._render_timer.timeout.connect(self._render)
        self._save_timer = QTimer(self)
        self._save_timer.setInterval(1500)
        self._save_timer.timeout.connect(self._save)
        page.send_requested.connect(self.send)
        page.stop_requested.connect(self.stop)
        page.new_requested.connect(self.new_conversation)
        page.delete_requested.connect(self.delete_conversation)
        page.delete_conversation_requested.connect(self.delete_conversation_by_id)
        page.rename_conversation_requested.connect(self.rename_conversation)
        page.conversation_requested.connect(self.select_conversation)
        page.configure_requested.connect(self.configure)
        page.preferences_changed.connect(self.set_preferences)
        page.confirm_requested.connect(self.confirm)
        page.reject_requested.connect(lambda _: self.stop())
        page.window().installEventFilter(self)
        application = QApplication.instance()
        if application is not None:
            application.aboutToQuit.connect(self.shutdown)
        try:
            self.preferences = self.store.preferences()
            conversations = self.store.conversations()
            if conversations:
                self.select_conversation(conversations[0]["id"])
            else:
                self.new_conversation()
        except (OSError, sqlite3.Error, ValueError, TypeError):
            page.notice.setText(tr("agent.error.storage"))
        self.page.set_preferences(
            self.preferences["model"],
            self.preferences["thinking"],
            self.preferences["enabled"],
        )

    @property
    def busy(self) -> bool:
        return self._deleting_conversation is not None or self.worker is not None or (
            self.turn is not None
            and self.turn.get("status")
            in {"streaming", "thinking", "running", "awaiting_confirmation"}
        )

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Close:
            self.stop()
        return super().eventFilter(watched, event)

    def _render(self) -> None:
        self.page.show_turns(
            self.conversation, self.turns, self.busy,
            stopping=self.busy and (self._cancel.is_set() or self._deleting_conversation is not None),
        )

    def _save(self) -> None:
        if self.turn is None:
            return
        try:
            self.store.save_turn(self.turn["conversation"], self.turn)
        except (OSError, sqlite3.Error, ValueError):
            self.page.notice.setText(tr("agent.error.storage"))
            self.client.cancel()
            self._cancel.set()
            self._save_timer.stop()
            self.turn["status"] = "failed"
            self.turn["error"] = "storage"

    def new_conversation(self) -> None:
        if self._deleting_conversation is not None:
            return
        self.stop()
        try:
            self.select_conversation(self.store.new_conversation(tr("agent.new_chat")))
        except (OSError, sqlite3.Error):
            self.page.notice.setText(tr("agent.error.storage"))

    def select_conversation(self, identity: str) -> None:
        if self._deleting_conversation is not None:
            return
        if identity == self.conversation:
            return
        self.stop()
        try:
            conversations = self.store.conversations()
            if identity not in {c["id"] for c in conversations}:
                return
            turns = self.store.turns(identity)
            for turn in turns:
                if turn.get("status") in {
                    "streaming",
                    "thinking",
                    "running",
                    "awaiting_confirmation",
                    "cancelled",
                }:
                    turn["status"] = "cancelled"
                    for card in turn.get("cards", []):
                        if card["status"] in {"running", "awaiting_confirmation"}:
                            card["status"] = "cancelled"
                        operation_id = card.get("result", {}).get("operation_id")
                        if (
                            operation_id
                            and card.get("name") == WRITE_TOOL
                            and card["status"] != "completed"
                        ):
                            with self.database.connect() as connection:
                                receipt = connection.execute(
                                    "SELECT value FROM settings WHERE key = ?",
                                    (f"agent.operation.{operation_id}",),
                                ).fetchone()
                            if receipt:
                                card.update(
                                    status="completed",
                                    result={
                                        **json.loads(receipt[0])["result"],
                                        "preview": card["result"],
                                    },
                                )
                    self.store.save_turn(identity, turn)
            self.conversation, self.turns = identity, turns
            self.turn = None
            self.page.show_conversations(conversations, identity)
            self._render()
        except (OSError, sqlite3.Error, ValueError, RuntimeError):
            self.page.notice.setText(tr("agent.error.storage"))

    def delete_conversation(self) -> None:
        """Compatibility entry point for deleting the active conversation."""
        self.delete_conversation_by_id(self.conversation)

    def _conversation_entry(self, identity: str) -> dict[str, Any] | None:
        try:
            entry = next((c for c in self.store.conversations() if c["id"] == identity), None)
            if entry is None:
                self.page.notice.setText(tr("agent.chat_missing"))
            return entry
        except (OSError, sqlite3.Error):
            self.page.notice.setText(tr("agent.error.storage"))
            return None

    def rename_conversation(self, identity: str) -> None:
        if self._deleting_conversation is not None:
            return
        entry = self._conversation_entry(identity)
        if entry is None:
            return
        dialog = RenameConversationDialog(entry["title"], self.page)
        try:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            self.store.rename_conversation(identity, dialog.title, manual=True)
            self.page.show_conversations(self.store.conversations(), self.conversation)
        except ValueError:
            self.page.notice.setText(tr("agent.chat_missing"))
        except (OSError, sqlite3.Error):
            self.page.notice.setText(tr("agent.error.storage"))
        finally:
            dialog.deleteLater()

    def delete_conversation_by_id(self, identity: str) -> None:
        if not identity or self._deleting_conversation is not None:
            return
        entry = self._conversation_entry(identity)
        if entry is None or not ask_confirmation(
            self.page,
            tr("agent.delete_chat"),
            tr("agent.delete_chat_named", title=entry["title"]),
            accept_key="common.delete_action",
            destructive=True,
            plain_text=True,
        ):
            return
        self._deleting_conversation = identity
        if identity == self.conversation:
            self.stop()
        if self.worker is not None and self._worker_conversation == identity:
            self._render()
            return
        self._finish_conversation_deletion()

    def _finish_conversation_deletion(self) -> None:
        identity = self._deleting_conversation
        if identity is None:
            return
        try:
            conversations = self.store.delete_conversation(identity, fallback_title=tr("agent.new_chat"))
            self._deleting_conversation = None
            if identity == self.conversation:
                self.conversation, self.turns, self.turn = "", [], None
                self.page.show_conversations(conversations, "")
                self._render()
                self.select_conversation(conversations[0]["id"])
            else:
                self.page.show_conversations(conversations, self.conversation)
        except (OSError, sqlite3.Error):
            self.page.notice.setText(tr("agent.error.storage"))
        finally:
            self._deleting_conversation = None
            self._render()

    def set_preferences(self, model: str, thinking: bool) -> None:
        self.preferences.update(model=model, thinking=thinking)
        try:
            self.store.save_preferences({"model": model, "thinking": thinking})
        except (OSError, sqlite3.Error):
            self.page.notice.setText(tr("agent.error.storage"))

    def send(self, text: str) -> None:
        if self.busy:
            return
        if not self.preferences["enabled"]:
            self.configure()
            return
        if redact(text) != text:
            self.page.notice.setText(tr("agent.error.key_in_chat"))
            return
        try:
            key = self.credentials.read()
            if key and key in text:
                self.page.notice.setText(tr("agent.error.key_in_chat"))
                return
            if not key or self.preferences["model"] not in self.preferences["models"]:
                self.configure()
                return
            zone = system_timezone()
            self._zone, self._now = str(zone), datetime.now(zone)
            self._active = self.active_timer()
        except (OSError, RuntimeError):
            self.page.notice.setText(tr("agent.error.configuration"))
            return
        if len(text) > 12000:
            self.page.notice.setText(tr("agent.error.too_long"))
            return
        if not self.conversation:
            self.new_conversation()
        if not self.turns:
            try:
                self.store.rename_conversation(self.conversation, text)
                self.page.show_conversations(
                    self.store.conversations(), self.conversation
                )
            except (OSError, sqlite3.Error):
                self.page.notice.setText(tr("agent.error.storage"))
                return
        new_request = WriteRequestContext.create(text)
        if new_request is not None:
            self._action_context = new_request
        elif self._action_context is not None:
            from app.data.focus_item_repository import FocusItemRepository

            names = [i.name for i in FocusItemRepository(self.database).list_active()]
            if (
                self._action_context.state == "awaiting_details"
                and len(self._action_context.sources) < 8
                and is_supplement(text, names)
            ):
                self._action_context.add_source(text)
            else:
                self._action_context = None
        self._write_allowed = self._action_context is not None
        self._evidence = (
            list(self._action_context.sources.values())
            if self._action_context
            else [text]
        )
        self._repair_signature = None
        self._last_validation = None
        history, trimmed = request_history(self.turns)
        self._messages = [
            {
                "role": "system",
                "content": system_prompt(
                    self._now,
                    self._zone,
                    get_localization().language,
                    self._write_allowed,
                    self._action_context,
                ),
            },
            *history,
        ]
        self.turn = {
            "id": str(uuid4()),
            "created": AgentStore.now(),
            "conversation": self.conversation,
            "user": text,
            "answer": "",
            "cards": [],
            "messages": [{"role": "user", "content": text}],
            "status": "streaming",
            "context_trimmed": trimmed,
            "user_evidence": self._evidence,
            "clarification_open": False,
            "usage": {},
            "request_context": self._action_context.payload()
            if self._action_context
            else None,
        }
        self.turns.append(self.turn)
        self._answer_text = ""
        self.tools = None
        self._pending = None
        self._calls = []
        self._cancel = threading.Event()
        self._request_count = 0
        self.page.input.clear()
        self._save()
        self._save_timer.start()
        self._request()

    def _request(self) -> None:
        if self.turn is None or self._cancel.is_set():
            return
        if self._request_count >= 8:
            self._network_failed("limit")
            return
        try:
            key = self.credentials.read()
            messages = [*self._messages, *self.turn["messages"]]
            if len(json.dumps(messages, ensure_ascii=False).encode()) > 1_000_000:
                self._network_failed("too_long")
                return
            self._request_count += 1
            self.turn["status"] = "streaming"
            self.client.complete(
                key,
                self.preferences["model"],
                self.preferences["thinking"],
                messages,
                tool_definitions(
                    self._write_allowed
                    and not (self.tools and self.tools.plan_prepared),
                    self._action_context,
                ),
            )
        except (OSError, ValueError):
            self._network_failed("configuration")
        self._render()

    def _delta(self, text: str) -> None:
        if self.turn is not None and not self._cancel.is_set():
            self._answer_text += text
            self.turn["answer"] = redact(self._answer_text)
            self.turn["status"] = "streaming"
            if not self._render_timer.isActive():
                self._render_timer.start()

    def _thinking(self) -> None:
        if self.turn is not None and not self._cancel.is_set():
            self.turn["status"] = "thinking"
            if not self._render_timer.isActive():
                self._render_timer.start()

    def _response(self, message: dict[str, Any], usage: dict[str, Any]) -> None:
        if self.turn is None or self._cancel.is_set():
            return
        self.turn["messages"].append(message)
        for name, value in usage.items():
            if isinstance(value, (int, float)):
                self.turn["usage"][name] = self.turn["usage"].get(name, 0) + value
        calls = message.get("tool_calls", [])
        if sum(c["function"]["name"] == WRITE_TOOL for c in calls) > 1:
            self._network_failed("multiple_plans")
            return
        self._calls = list(calls)
        if not calls:
            if self._last_validation is not None and not (
                self.tools and self.tools.plan_prepared
            ):
                self._finish_validation(self._last_validation)
                return
            self.turn["status"] = "completed"
            committed = any(
                c.get("result", {}).get("status") == "committed"
                for c in self.turn["cards"]
            )
            self.turn["clarification_open"] = (
                self._write_allowed
                and not committed
                and self._action_context is not None
            )
            if self._action_context is not None:
                self._action_context.state = "awaiting_details"
                self.turn["request_context"] = self._action_context.payload()
            self._save_timer.stop()
            self._save()
            self._render()
        else:
            if self.turn["answer"]:
                self._answer_text += "\n\n"
                self.turn["answer"] = redact(self._answer_text)
            self._next_tool()

    def _job(
        self, action: Callable[[], Any], callback: Callable[[Any, str], None]
    ) -> None:
        if self.worker is not None:
            raise RuntimeError("Only one tool job may run.")
        worker = ToolJob(action, self)
        self.worker = worker
        self._worker_conversation = self.turn["conversation"] if self.turn else self.conversation

        def finished() -> None:
            self.worker = None
            self._worker_conversation = None
            worker.deleteLater()
            callback(worker.result, worker.error)
            self._finish_conversation_deletion()
            self._render()

        worker.finished.connect(finished)
        worker.start()

    def _next_tool(self) -> None:
        if self.turn is None or self._cancel.is_set():
            return
        if not self._calls:
            self._save()
            self._request()
            return
        call = self._calls.pop(0)
        card = {
            "id": call["id"],
            "name": call["function"]["name"],
            "status": "running",
            "result": {},
        }
        turn = self.turn
        turn["cards"].append(card)
        turn["status"] = "running"
        cancellation = self._cancel

        def execute() -> Any:
            if cancellation.is_set():
                raise ValueError("Cancelled.")
            if self.tools is None:
                self.tools = FocusTools(
                    self.database, self._zone, self._now, self._active
                )
            arguments = json_object(call["function"]["arguments"])
            if card["name"] == WRITE_TOOL:
                if (
                    self._repair_signature is not None
                    and operation_signature(arguments) != self._repair_signature
                ):
                    raise ToolValidationError("repair_changed", kind="authorization")
                return self.tools.prepare(
                    arguments,
                    self._evidence,
                    self._write_allowed,
                    context=self._action_context,
                )
            return self.tools.execute(card["name"], arguments)

        def ready(result: Any, error: str) -> None:
            if cancellation.is_set() or self.turn is not turn:
                return
            if error:
                if card["name"] == WRITE_TOOL:
                    failure = (
                        result.get("validation_error")
                        if isinstance(result, dict)
                        else None
                    )
                    failure = failure or ToolValidationError("invalid_plan").payload()
                    self._last_validation = failure
                    signature = None
                    try:
                        signature = operation_signature(
                            json_object(call["function"]["arguments"])
                        )
                    except (ValueError, TypeError):
                        pass
                    if (
                        failure["category"] == "format"
                        and self._repair_signature is None
                        and signature is not None
                        and not (self.tools and self.tools.plan_prepared)
                    ):
                        self._repair_signature = signature
                        self._tool_result(
                            call,
                            card,
                            {
                                **failure,
                                "retry_format": True,
                                "instruction": "Repair FORMAT once. Keep operation kinds, record IDs, field values and count identical. Evidence must be arrays of exact {message_id, quote} user substrings; delete has no fields/evidence. No writing occurred.",
                            },
                            failed=True,
                        )
                    else:
                        self._tool_result(
                            call,
                            card,
                            {**failure, "retry_format": False},
                            failed=True,
                            continue_turn=False,
                        )
                        self._finish_validation(failure)
                    return
                self._tool_result(
                    call,
                    card,
                    {"status": "needs_clarification", "message": error},
                    failed=True,
                )
            elif card["name"] == WRITE_TOOL:
                plan, preview = result
                self._last_validation = None
                if self._action_context is not None:
                    self._action_context.state = (
                        "awaiting_confirmation"
                        if plan.requires_confirmation
                        else "preparing"
                    )
                card["result"] = json.loads(
                    redact(json.dumps(preview, ensure_ascii=False))
                )
                if plan.requires_confirmation:
                    card["status"] = "awaiting_confirmation"
                    turn["status"] = "awaiting_confirmation"
                    self._pending = plan, call, card
                    self._save()
                else:
                    self._commit(plan, call, card, confirmed=False)
            else:
                self._tool_result(call, card, result)

        self._job(execute, ready)
        self._render()

    def _tool_result(
        self,
        call: dict[str, Any],
        card: dict[str, Any],
        result: dict[str, Any],
        *,
        failed: bool = False,
        continue_turn: bool = True,
    ) -> None:
        if self.turn is None:
            return
        result = json.loads(
            redact(json.dumps(result, ensure_ascii=False, allow_nan=False))
        )
        card.update(status="failed" if failed else "completed", result=result)
        self.turn["messages"].append(
            {
                "role": "tool",
                "tool_call_id": call["id"],
                "content": redact(
                    json.dumps(result, ensure_ascii=False, allow_nan=False)
                ),
            }
        )
        self._save()
        if continue_turn:
            self._next_tool()

    def _finish_validation(self, result: dict[str, Any]) -> None:
        """Terminal guard outcomes are local facts, not a model's diagnosis."""
        assert self.turn is not None
        for skipped in self._calls:
            self.turn["messages"].append(
                {
                    "role": "tool",
                    "tool_call_id": skipped["id"],
                    "content": '{"status":"cancelled"}',
                }
            )
        self._calls = []
        code = result.get("code", "invalid_plan")
        self._answer_text = tr("agent.validation." + code)
        self.turn["answer"] = self._answer_text
        self.turn["status"] = "completed"
        self.turn["validation_error"] = result
        self.turn["messages"].append(
            {"role": "assistant", "content": self._answer_text, "reasoning_content": ""}
        )
        if result.get("category") == "authorization":
            self._action_context = None
        if self._action_context is not None:
            self._action_context.state = "awaiting_details"
            self._action_context.missing_fields = (
                [result["field"]] if result.get("field") else []
            )
        self.turn["clarification_open"] = self._action_context is not None
        self.turn["request_context"] = (
            self._action_context.payload() if self._action_context else None
        )
        self._save_timer.stop()
        self._save()
        self._render()

    def confirm(self, card_id: str) -> None:
        if self._pending is None or self.worker is not None or self._cancel.is_set():
            return
        plan, call, card = self._pending
        if card_id != card["id"]:
            return
        self._pending = None
        self._commit(plan, call, card, confirmed=True)

    def _commit(
        self,
        plan: RecordChangePlan,
        call: dict[str, Any],
        card: dict[str, Any],
        *,
        confirmed: bool,
    ) -> None:
        assert self.turn is not None
        turn, cancellation = self.turn, self._cancel
        card["status"] = "running"
        turn["status"] = "running"
        self._save()  # Persist the operation ID before starting the transaction.

        def ready(result: Any, error: str) -> None:
            preview = card["result"]
            self._action_context = None
            self._write_allowed = False
            if not error:
                card.update(
                    status="completed", result={**result, "preview": card["result"]}
                )
                self.records_changed.emit()
            else:
                card.update(
                    status="cancelled" if cancellation.is_set() else "failed",
                    result={
                        "status": "not_committed",
                        "message": error,
                        "code": "stale_confirmation"
                        if "changed" in error or "overlap" in error
                        else "invalid_plan",
                        "category": "authorization",
                        "preview": preview,
                    },
                )
            # A committed transaction stays visible even if Stop/switch raced its completion.
            try:
                self.store.save_turn(turn["conversation"], turn)
            except (OSError, sqlite3.Error):
                self.page.notice.setText(tr("agent.error.storage"))
            if self.turn is turn and not cancellation.is_set():
                self._tool_result(
                    call,
                    card,
                    card["result"],
                    failed=bool(error),
                    continue_turn=not error,
                )
                if error:
                    self._finish_validation(card["result"])
            elif self.conversation == turn["conversation"]:
                self.turns = [turn if t["id"] == turn["id"] else t for t in self.turns]

        self._job(
            lambda: apply_changes(
                self.database, plan, confirmed=confirmed, cancelled=cancellation.is_set
            ),
            ready,
        )

    def _network_failed(self, code: str) -> None:
        self.client.cancel()
        self._cancel.set()
        self._calls = []
        self._pending = None
        self._action_context = None
        if self.turn is not None:
            self.turn.update(status="failed", error=code)
            self._save_timer.stop()
            self._save()
            self._render()

    def stop(self) -> None:
        self.client.cancel()
        self._cancel.set()
        self._save_timer.stop()
        self._pending = None
        self._calls = []
        self._action_context = None
        if self.turn is not None and self.turn.get("status") in {
            "streaming",
            "thinking",
            "running",
            "awaiting_confirmation",
        }:
            self.turn["status"] = "cancelled"
            self.turn["clarification_open"] = False
            for card in self.turn["cards"]:
                if card["status"] in {"running", "awaiting_confirmation"}:
                    card["status"] = "cancelled"
            self._save()
        self._render()

    def shutdown(self) -> None:
        self.stop()
        self.config_client.cancel()
        if self.worker is not None:
            self.worker.wait()  # Only app exit: allow an owned transaction to finish/roll back.

    def configure(self) -> None:
        if self._deleting_conversation is not None:
            return
        self.stop()
        try:
            has_key = bool(self.credentials.read())
        except OSError:
            has_key = False
        if self.dialog is not None:
            self.dialog.close()
            self.dialog.deleteLater()
        dialog = AgentConfigDialog(has_key, self.preferences["enabled"], self.page)
        self.dialog = dialog
        dialog.test_requested.connect(lambda key: self._test_config(key, False))
        dialog.save_requested.connect(self._save_config)
        dialog.remove_requested.connect(self._remove_key)
        dialog.finished.connect(self._close_config)
        dialog.show()

    def _close_config(self, _result: int) -> None:
        self.config_client.cancel()
        self._config_key = ""
        if self.dialog:
            self.dialog.key.clear()

    def _test_config(self, key: str, save: bool) -> None:
        assert self.dialog is not None
        try:
            self._config_key = key or self.credentials.read()
            if not self._config_key:
                raise ValueError("Missing key.")
            self._config_save = save
            self.dialog.status.setText(tr("agent.testing"))
            self.dialog.test.setEnabled(False)
            self.dialog.save.setEnabled(False)
            self.config_client.models(self._config_key)
        except (OSError, ValueError):
            self._config_error("configuration")

    def _save_config(self, key: str, enabled: bool) -> None:
        if not enabled:
            self.preferences["enabled"] = False
            try:
                self.store.save_preferences({"enabled": False})
            except (OSError, sqlite3.Error):
                self._config_error("storage")
                return
            self.page.set_preferences(
                self.preferences["model"], self.preferences["thinking"], False
            )
            if self.dialog:
                self.dialog.accept()
            return
        self._test_config(key, True)

    def _models_ready(self, models: list[str]) -> None:
        if self.dialog is None:
            return
        self.dialog.test.setEnabled(True)
        self.dialog.save.setEnabled(True)
        if self.preferences["model"] not in models:
            self._config_error("model_unavailable")
            return
        self.dialog.status.setText(tr("agent.connected", models=", ".join(models)))
        if self._config_save:
            try:
                persisted = self.credentials.save(self._config_key)
                self.preferences.update(enabled=True, models=models)
                self.store.save_preferences({"enabled": persisted, "models": models})
                self.page.set_preferences(
                    self.preferences["model"], self.preferences["thinking"], True
                )
                self.dialog.key.clear()
                if not persisted:
                    QMessageBox.warning(
                        self.dialog, tr("agent.configure"), tr("agent.session_key_only")
                    )
                self.dialog.accept()
            except (OSError, ValueError, sqlite3.Error):
                self._config_error("storage")
        self._config_key = ""

    def _config_error(self, code: str) -> None:
        self._config_key = ""
        if self.dialog is not None:
            self.dialog.status.setText(tr("agent.error." + code))
            self.dialog.test.setEnabled(True)
            self.dialog.save.setEnabled(True)

    def _remove_key(self) -> None:
        try:
            self.config_client.cancel()
            self.credentials.delete()
            self.preferences.update(enabled=False, models=[])
            self.store.save_preferences({"enabled": False, "models": []})
            self.page.set_preferences(
                self.preferences["model"], self.preferences["thinking"], False
            )
            if self.dialog:
                self.dialog.key.clear()
                self.dialog.status.setText(tr("agent.key_removed"))
        except (OSError, sqlite3.Error):
            self._config_error("storage")
