"""Structured, non-secret validation results shared by tools and presentation."""

from __future__ import annotations

import json
from typing import Any


class ToolValidationError(ValueError):
    def __init__(
        self,
        code: str,
        *,
        field: str = "",
        kind: str = "clarification",
        detail: str = "",
    ) -> None:
        super().__init__(detail or code)
        self.code, self.field, self.kind = code, field, kind

    def payload(self) -> dict[str, Any]:
        return {
            "status": "needs_clarification",
            "code": self.code,
            "field": self.field,
            "category": self.kind,
        }


def from_validation_error(error: Exception) -> ToolValidationError:
    if isinstance(error, ToolValidationError):
        return error
    message = str(error)
    if "exceeds the interval" in message:
        return ToolValidationError("duration_conflict", field="duration_seconds")
    if "effective duration" in message or "Invalid actual duration" in message:
        return ToolValidationError("duration", field="duration_seconds")
    if any(word in message for word in ("date", "time", "UTC", "precision")):
        return ToolValidationError("time", field="start_time/end_time")
    if "focus item" in message or "project" in message:
        return ToolValidationError("project", field="focus_item_id")
    if "Read the current" in message:
        return ToolValidationError(
            "read_required", field="record_id", kind="authorization"
        )
    if "batch" in message or "1–50" in message:
        return ToolValidationError("batch", field="operations", kind="authorization")
    return ToolValidationError("invalid_plan")


def operation_signature(arguments: dict[str, Any]) -> str | None:
    """A format repair must keep every operation, target and proposed value."""
    operations = arguments.get("operations")
    if not isinstance(operations, list) or not operations:
        return None
    normalized = []
    for op in operations:
        if not isinstance(op, dict) or op.get("kind") not in {
            "create",
            "update",
            "delete",
        }:
            return None
        normalized.append(
            {
                "kind": op["kind"],
                "record_id": op.get("record_id"),
                "fields": op.get("fields", {}) if op["kind"] != "delete" else {},
            }
        )
    try:
        return json.dumps(
            normalized, sort_keys=True, ensure_ascii=False, allow_nan=False
        )
    except (ValueError, TypeError):
        return None
