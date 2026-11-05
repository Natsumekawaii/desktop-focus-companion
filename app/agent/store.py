"""Private profile-local conversation storage; never stores API credentials."""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

SECRET = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")
MODELS = ("deepseek-flash", "deepseek-v4-pro")


def redact(text: str) -> str:
    return SECRET.sub("[REDACTED API KEY]", text)


class AgentStore:
    def __init__(self, data_dir: Path) -> None:
        self.root = data_dir / "agent"
        self.path = self.root / "conversations.sqlite3"

    @contextmanager
    def connect(self):
        self.root.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY, title TEXT NOT NULL, updated TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS turns(id TEXT PRIMARY KEY, conversation TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    created TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS preferences(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def preferences(self) -> dict[str, Any]:
        with self.connect() as connection:
            rows = connection.execute("SELECT key, value FROM preferences").fetchall()
        result = {"enabled": False, "model": MODELS[0], "thinking": False, "models": []}
        for row in rows:
            if row["key"] in result:
                result[row["key"]] = json.loads(row["value"])
        self._validate_preferences(result)
        return result

    def save_preferences(self, values: dict[str, Any]) -> None:
        self._validate_preferences(values)
        with self.connect() as connection:
            for key, value in values.items():
                connection.execute(
                    "INSERT INTO preferences VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, json.dumps(value)),
                )

    @staticmethod
    def _validate_preferences(values: dict[str, Any]) -> None:
        allowed = {"enabled", "model", "thinking", "models"}
        if set(values) - allowed:
            raise ValueError("Only non-secret assistant preferences may be stored.")
        for key in ("enabled", "thinking"):
            if key in values and not isinstance(values[key], bool):
                raise TypeError("Consent and thinking preferences must be boolean.")
        if "model" in values and values["model"] not in MODELS:
            raise ValueError("Unsupported model; no automatic fallback.")
        if "models" in values and (
            not isinstance(values["models"], list)
            or any(m not in MODELS for m in values["models"])
        ):
            raise ValueError("Invalid verified model list.")

    def new_conversation(self, title: str) -> str:
        identity = str(uuid4())
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO conversations VALUES (?, ?, ?)",
                (identity, redact(title[:80]), self.now()),
            )
        return identity

    def conversations(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM conversations ORDER BY updated DESC, id"
                )
            ]

    def rename_conversation(self, identity: str, title: str, *, manual: bool = False) -> None:
        title = title.strip()
        if manual and (not title or len(title) > 60):
            raise ValueError("A conversation title must contain 1–60 characters.")
        marker = f"conversation.manual_title.{identity}"
        with self.connect() as connection:
            if not connection.execute("SELECT 1 FROM conversations WHERE id = ?", (identity,)).fetchone():
                raise ValueError("Conversation no longer exists.")
            if not manual and connection.execute("SELECT 1 FROM preferences WHERE key = ?", (marker,)).fetchone():
                return
            connection.execute(
                "UPDATE conversations SET title = ? WHERE id = ?",
                (redact(title)[:60], identity),
            )
            if manual:
                connection.execute("INSERT OR REPLACE INTO preferences VALUES (?, ?)", (marker, "true"))

    def delete_conversation(self, identity: str, *, fallback_title: str | None = None) -> list[dict[str, Any]]:
        """Remove a chat and its title marker atomically; optionally keep one chat."""
        with self.connect() as connection:
            connection.execute("DELETE FROM conversations WHERE id = ?", (identity,))
            connection.execute("DELETE FROM preferences WHERE key = ?", (f"conversation.manual_title.{identity}",))
            if fallback_title is not None and not connection.execute("SELECT 1 FROM conversations LIMIT 1").fetchone():
                connection.execute("INSERT INTO conversations VALUES (?, ?, ?)", (str(uuid4()), redact(fallback_title[:80]), self.now()))
            return [dict(row) for row in connection.execute("SELECT * FROM conversations ORDER BY updated DESC, id")]

    def turns(self, conversation: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM turns WHERE conversation = ? ORDER BY created, id",
                (conversation,),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def save_turn(self, conversation: str, turn: dict[str, Any]) -> None:
        payload = redact(json.dumps(turn, ensure_ascii=False, allow_nan=False))
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO turns VALUES (?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                (turn["id"], conversation, turn["created"], payload),
            )
            connection.execute(
                "UPDATE conversations SET updated = ? WHERE id = ?",
                (self.now(), conversation),
            )

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()


def request_history(
    turns: list[dict[str, Any]], *, max_bytes: int = 160_000
) -> tuple[list[dict[str, Any]], bool]:
    """Retain complete protocol turns, including reasoning/tool pairs."""
    retained: list[list[dict[str, Any]]] = []
    size = 0
    for turn in reversed(turns):
        if turn.get("status") != "completed":
            continue
        messages = turn.get("messages", [])
        cost = len(json.dumps(messages, ensure_ascii=False).encode())
        if size + cost > max_bytes:
            break
        retained.append(messages)
        size += cost
    return [message for group in reversed(retained) for message in group], len(
        retained
    ) < len(turns)
