"""Asynchronous official DeepSeek transport; no logging of headers or payloads."""

from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import QByteArray, QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from app.agent.protocol import CompletionStream, SSEParser, json_object
from app.agent.store import MODELS

API_BASE = "https://api.deepseek.com"


class DeepSeekClient(QObject):
    text_delta = Signal(str)
    thinking = Signal()
    completed = Signal(object, object)
    failed = Signal(str)
    models_ready = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.manager = QNetworkAccessManager(self)
        self.reply: QNetworkReply | None = None
        self.parser = SSEParser()
        self.stream = CompletionStream()
        self._models = False
        self._body = b""
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self._fail("timeout"))

    def models(self, key: str) -> None:
        self._start(key, None)

    def complete(
        self,
        key: str,
        model: str,
        thinking: bool,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> None:
        if model not in MODELS:
            self.failed.emit("model_unavailable")
            return
        self._start(
            key,
            {
                "model": model,
                "messages": messages,
                "tools": tools,
                "stream": True,
                "stream_options": {"include_usage": True},
                "thinking": {"type": "enabled" if thinking else "disabled"},
                "max_tokens": 16384 if thinking else 4096,
            },
            deep=thinking,
        )

    def _start(
        self, key: str, body: dict[str, Any] | None, *, deep: bool = False
    ) -> None:
        self.cancel()
        if not key or len(key) > 2000 or any(c.isspace() for c in key):
            raise ValueError("Invalid API Key format.")
        self._models = body is None
        self._body = b""
        self.parser, self.stream = SSEParser(), CompletionStream()
        request = QNetworkRequest(
            QUrl(API_BASE + ("/models" if body is None else "/chat/completions"))
        )
        request.setRawHeader(
            QByteArray(b"Authorization"), QByteArray(("Bearer " + key).encode())
        )
        request.setHeader(
            QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json"
        )
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.ManualRedirectPolicy,
        )
        request.setTransferTimeout(90_000)
        reply = (
            self.manager.get(request)
            if body is None
            else self.manager.post(
                request,
                QByteArray(
                    json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
                ),
            )
        )
        self.reply = reply
        reply.readyRead.connect(lambda: self._read(reply))
        reply.finished.connect(lambda: self._finished(reply))
        self._timer.start(600_000 if deep else 180_000)

    def _read(self, reply: QNetworkReply) -> None:
        if reply is not self.reply:
            return
        data = bytes(reply.readAll().data())
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if status and int(status) != 200:
            return  # Never expose provider error bodies (they may echo secrets).
        try:
            if self._models:
                self._body += data
                if len(self._body) > 1_000_000:
                    raise ValueError("Models payload too large.")
            else:
                for event in self.parser.feed(data):
                    delta, thinking = self.stream.accept(event)
                    if delta:
                        self.text_delta.emit(delta)
                    if thinking:
                        self.thinking.emit()
        except (ValueError, TypeError, KeyError, IndexError, UnicodeError):
            self._fail("invalid_response")

    def _finished(self, reply: QNetworkReply) -> None:
        if reply is not self.reply:
            reply.deleteLater()
            return
        self._read(reply)
        if self.reply is not reply:
            return
        self.reply = None
        self._timer.stop()
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        error = reply.error()
        reply.deleteLater()
        if status != 200:
            self.failed.emit(
                {401: "auth", 402: "balance", 429: "rate_limit"}.get(status, "network")
            )
            return
        if error != QNetworkReply.NetworkError.NoError:
            self.failed.emit("network")
            return
        try:
            if self._models:
                value = json_object(self._body.decode())
                models = [
                    m["id"]
                    for m in value["data"]
                    if isinstance(m, dict) and m.get("id") in MODELS
                ]
                self.models_ready.emit(models)
            else:
                self.completed.emit(self.stream.message(), self.stream.usage)
        except (ValueError, TypeError, KeyError, UnicodeError):
            self.failed.emit("invalid_response")

    def _fail(self, code: str) -> None:
        self.cancel()
        self.failed.emit(code)

    def cancel(self) -> None:
        self._timer.stop()
        reply, self.reply = self.reply, None
        if reply is not None:
            reply.abort()
            reply.deleteLater()
