"""Bounded SSE framing and Chat Completion stream assembly."""

from __future__ import annotations

import json
from typing import Any


def _invalid_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON numeric constant: {value}")


def json_object(text: str) -> dict[str, Any]:
    value = json.loads(text, parse_constant=_invalid_constant)
    if not isinstance(value, dict):
        raise TypeError("Expected a JSON object.")
    return value


class SSEParser:
    def __init__(self) -> None:
        self.buffer = b""
        self.lines: list[bytes] = []
        self.frame_size = 0

    def feed(self, data: bytes) -> list[str]:
        self.buffer += data
        if len(self.buffer) + self.frame_size > 2_000_000:
            raise ValueError("SSE frame is too large.")
        events = []
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            line = line.removesuffix(b"\r")
            if not line:
                if self.lines:
                    events.append(b"\n".join(self.lines).decode("utf-8"))
                self.lines = []
                self.frame_size = 0
            elif line.startswith(b"data:"):
                self.lines.append(line[5:].removeprefix(b" "))
                self.frame_size += len(line)
        return events


class CompletionStream:
    def __init__(self) -> None:
        self.content = ""
        self.reasoning = ""
        self.calls: dict[int, dict[str, Any]] = {}
        self.finish_reason: str | None = None
        self.done = False
        self.usage: dict[str, Any] = {}

    def accept(self, event: str) -> tuple[str, bool]:
        if not event.strip():
            return "", False
        if self.done:
            raise ValueError("Data after stream completion.")
        if event == "[DONE]":
            if self.finish_reason not in {"stop", "tool_calls"}:
                raise ValueError("Incomplete model response; no actions executed.")
            self.done = True
            return "", False
        packet = json_object(event)
        if "error" in packet:
            raise ValueError("Provider returned a stream error.")
        if isinstance(packet.get("usage"), dict):
            self.usage = packet["usage"]
        choices = packet.get("choices", [])
        if not isinstance(choices, list) or any(
            not isinstance(c, dict) for c in choices
        ):
            raise ValueError("Invalid choices.")
        if not choices:
            return "", False
        choice = choices[0]
        if choice.get("index", 0) != 0:
            raise ValueError("Unexpected completion choice.")
        delta = choice.get("delta", {})
        if not isinstance(delta, dict):
            raise TypeError("Invalid delta.")
        content = delta.get("content") or ""
        reasoning = delta.get("reasoning_content") or ""
        if not isinstance(content, str) or not isinstance(reasoning, str):
            raise TypeError("Invalid text delta.")
        self.content += content
        self.reasoning += reasoning
        parts = delta.get("tool_calls") or []
        if not isinstance(parts, list) or any(not isinstance(p, dict) for p in parts):
            raise ValueError("Invalid tool fragments.")
        for part in parts:
            index = part.get("index")
            if (
                isinstance(index, bool)
                or not isinstance(index, int)
                or not 0 <= index < 16
            ):
                raise ValueError("Invalid tool index.")
            call = self.calls.setdefault(
                index,
                {
                    "id": "",
                    "type": "function",
                    "function": {"name": "", "arguments": ""},
                },
            )
            if part.get("id"):
                if not isinstance(part["id"], str):
                    raise TypeError("Invalid tool identity.")
                if call["id"] and call["id"] != part["id"]:
                    raise ValueError("Tool ID changed mid-stream.")
                call["id"] = part["id"]
            function = part.get("function") or {}
            if not isinstance(function, dict) or any(
                not isinstance(function[k], str)
                for k in ("name", "arguments")
                if function.get(k) is not None
            ):
                raise ValueError("Invalid function fragment.")
            if function.get("name"):
                call["function"]["name"] += function["name"]
            call["function"]["arguments"] += function.get("arguments") or ""
        if choice.get("finish_reason"):
            self.finish_reason = choice["finish_reason"]
        if (
            len(self.content) + len(self.reasoning) + len(json.dumps(self.calls))
            > 1_000_000
        ):
            raise ValueError("Model response is too large.")
        return content, bool(reasoning)

    def message(self) -> dict[str, Any]:
        if not self.done:
            raise ValueError("Stream ended before DONE; no actions executed.")
        result: dict[str, Any] = {
            "role": "assistant",
            "content": self.content,
            "reasoning_content": self.reasoning,
        }
        if self.calls:
            if self.finish_reason != "tool_calls" or sorted(self.calls) != list(
                range(len(self.calls))
            ):
                raise ValueError("Incomplete tool-call sequence.")
            calls = [self.calls[index] for index in sorted(self.calls)]
            if any(not c["id"] or not c["function"]["name"] for c in calls) or len(
                {c["id"] for c in calls}
            ) != len(calls):
                raise ValueError("Missing or duplicate tool identity.")
            for call in calls:
                json_object(call["function"]["arguments"])
            result["tool_calls"] = calls
        elif self.finish_reason == "tool_calls":
            raise ValueError("Missing tool calls.")
        return result
