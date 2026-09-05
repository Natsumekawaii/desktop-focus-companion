"""Crash-safe checkpoint persistence for an unfinished focus session."""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.data.datetime_utils import from_storage_datetime, to_storage_datetime
from app.focus_mode import FocusMode, validate_target_duration

logger = logging.getLogger(__name__)
CHECKPOINT_VERSION = 4
SUPPORTED_CHECKPOINT_VERSIONS = frozenset({1, 2, 3, CHECKPOINT_VERSION})
RECOVERABLE_STATES = frozenset({"FOCUSING", "STUDYING", "PAUSED", "PENDING"})


class ActiveSessionStoreError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ActiveSessionCheckpoint:
    recovery_token: str
    focus_item_id: int
    focus_item_name: str
    start_time: datetime
    accumulated_seconds: float
    timer_state: str
    last_checkpoint: datetime
    end_time: datetime | None = None
    mode: str = FocusMode.STOPWATCH.value
    target_duration_seconds: float | None = None
    note: str = ""

    def __post_init__(self) -> None:
        to_storage_datetime(self.start_time)
        to_storage_datetime(self.last_checkpoint)
        if self.end_time is not None:
            to_storage_datetime(self.end_time)
        if self.focus_item_id <= 0 or not self.focus_item_name.strip():
            raise ValueError("Recovery checkpoint has an invalid Focus Item.")
        if not self.recovery_token.strip() or len(self.recovery_token) > 80:
            raise ValueError("Recovery checkpoint has an invalid token.")
        if self.accumulated_seconds < 0:
            raise ValueError("Recovery checkpoint has a negative duration.")
        if self.timer_state not in RECOVERABLE_STATES:
            raise ValueError("Recovery checkpoint has an unsupported timer state.")
        if self.timer_state == "PENDING" and self.end_time is None:
            raise ValueError("Pending recovery checkpoint is missing its end time.")
        try:
            mode = FocusMode(self.mode)
        except ValueError as error:
            raise ValueError("Recovery checkpoint has an invalid focus mode.") from error
        if mode is FocusMode.COUNTDOWN:
            target = validate_target_duration(self.target_duration_seconds)
            if self.accumulated_seconds > target:
                raise ValueError("Recovery checkpoint exceeds its countdown target.")
        elif self.target_duration_seconds is not None:
            raise ValueError("Stopwatch recovery checkpoint cannot have a target.")
        if len(self.note) > 2000:
            raise ValueError("Recovery checkpoint note is too long.")

class ActiveSessionStore:
    """Atomically save one minimal checkpoint outside SQLite transactions."""

    def __init__(self, checkpoint_path: Path) -> None:
        self.path = checkpoint_path

    def load(self) -> ActiveSessionCheckpoint | None:
        if not self.path.exists():
            return None
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if (
                not isinstance(raw, dict)
                or raw.get("version") not in SUPPORTED_CHECKPOINT_VERSIONS
            ):
                raise ValueError("Unsupported active-session checkpoint version.")
            version = int(raw["version"])
            legacy = version < CHECKPOINT_VERSION
            return ActiveSessionCheckpoint(
                recovery_token=str(raw["recovery_token"]),
                focus_item_id=int(
                    raw["subject_id"] if legacy else raw["focus_item_id"]
                ),
                focus_item_name=str(
                    raw["subject_name"] if legacy else raw["focus_item_name"]
                ),
                start_time=from_storage_datetime(str(raw["start_time"])),
                accumulated_seconds=float(raw["accumulated_seconds"]),
                timer_state=str(raw["timer_state"]),
                last_checkpoint=from_storage_datetime(str(raw["last_checkpoint"])),
                end_time=(
                    from_storage_datetime(str(raw["end_time"]))
                    if raw.get("end_time") is not None
                    else None
                ),
                mode=str(
                    raw.get("study_mode", FocusMode.STOPWATCH.value)
                    if legacy
                    else raw.get("mode", FocusMode.STOPWATCH.value)
                ),
                target_duration_seconds=(
                    float(raw["target_duration_seconds"])
                    if raw.get("target_duration_seconds") is not None
                    else None
                ),
                note=str(raw.get("note", "")),
            )
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            logger.error("Active-session checkpoint is invalid: %s", error)
            self._preserve_corrupt()
            return None

    def save(self, checkpoint: ActiveSessionCheckpoint) -> None:
        temporary = self.path.with_suffix(".json.tmp")
        payload = asdict(checkpoint)
        payload["version"] = CHECKPOINT_VERSION
        for key in ("start_time", "last_checkpoint", "end_time"):
            value = payload[key]
            payload[key] = to_storage_datetime(value) if value is not None else None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise ActiveSessionStoreError("Unable to save active-session recovery data.") from error

    def clear(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError as error:
            raise ActiveSessionStoreError("Unable to clear active-session recovery data.") from error

    def _preserve_corrupt(self) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        destination = self.path.with_name(f"active-session.corrupt-{timestamp}.json")
        try:
            shutil.move(self.path, destination)
        except OSError:
            logger.exception("Unable to preserve invalid active-session checkpoint")
