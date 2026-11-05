"""Readable, responsive previews of the exact client-validated change plan."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from app.core.theme import get_theme_manager
from app.i18n import tr
from app.timer.formatting import format_duration

FIELDS = ("focus_item_name", "start_time", "end_time", "duration_seconds", "note")


def display_value(key: str, value: Any) -> str:
    if value is None or value == "":
        return tr("agent.preview.empty")
    if key == "duration_seconds":
        return f"{format_duration(float(value))} ({float(value):g} s)"
    if key in {"start_time", "end_time"}:
        try:
            return datetime.fromisoformat(str(value)).isoformat(sep=" ")
        except ValueError:
            pass
    return str(value)


def plain_label(text: str, parent: QWidget | None = None) -> QLabel:
    label = QLabel(text, parent)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setMinimumWidth(0)
    return label


class ChangePreview(QFrame):
    def __init__(self, change: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.kind = change.get("kind", "update")
        before, after = change.get("before") or {}, change.get("after") or {}
        identity = before or after
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 8, 0, 8)
        title = tr("agent.preview." + self.kind)
        if identity.get("id") is not None:
            title += f" · #{identity['id']}"
        title += " · " + str(identity.get("focus_item_name", ""))
        root.addWidget(plain_label(title))
        if self.kind == "update":
            context = f"{display_value('start_time', before.get('start_time'))} → {display_value('end_time', before.get('end_time'))}"
            context += " · " + display_value(
                "duration_seconds", before.get("duration_seconds")
            )
            root.addWidget(plain_label(context))
        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(8)
        root.addLayout(self.grid)
        self.rows: list[tuple[QLabel, QLabel, QLabel]] = []
        tokens = get_theme_manager().tokens
        for key in FIELDS:
            if self.kind == "update" and before.get(key) == after.get(key):
                continue
            label = plain_label(tr("agent.preview." + key), self)
            label.setObjectName("secondary")
            old = plain_label(display_value(key, before.get(key)), self)
            new = plain_label(display_value(key, after.get(key)), self)
            if self.kind == "update":
                old.setText(tr("agent.preview.before") + ": " + old.text())
                new.setText(tr("agent.preview.after") + ": " + new.text())
                new.setStyleSheet(
                    f"color: {tokens.text}; background: {tokens.primary_soft}; border-radius: 6px; padding: 5px;"
                )
            self.rows.append((label, old, new))
        self._narrow: bool | None = None
        self._layout_rows(True)
        if change.get("overlapping_record_ids"):
            warning = plain_label(
                tr(
                    "agent.preview.overlap",
                    ids=", ".join(f"#{i}" for i in change["overlapping_record_ids"]),
                )
            )
            warning.setObjectName("agentOverlapWarning")
            root.addWidget(warning)
            for record in change.get("overlapping_records", []):
                root.addWidget(
                    plain_label(
                        f"#{record['id']} · {record.get('focus_item_name', '')}\n"
                        f"{display_value('start_time', record.get('start_time'))} → "
                        f"{display_value('end_time', record.get('end_time'))}\n"
                        f"{display_value('duration_seconds', record.get('duration_seconds'))} · "
                        f"{display_value('note', record.get('note'))}"
                    )
                )

    def _layout_rows(self, narrow: bool) -> None:
        if narrow == self._narrow:
            return
        self._narrow = narrow
        while self.grid.count():
            self.grid.takeAt(0)
        for column in range(3):
            self.grid.setColumnStretch(column, 0)
        for index, (label, old, new) in enumerate(self.rows):
            old.setVisible(self.kind != "create")
            new.setVisible(self.kind != "delete")
            if self.kind == "update":
                old.setAccessibleName(tr("agent.preview.before"))
                new.setAccessibleName(tr("agent.preview.after"))
            if narrow:
                row = index * (3 if self.kind == "update" else 2)
                self.grid.addWidget(label, row, 0)
                if self.kind == "update":
                    self.grid.addWidget(old, row + 1, 0)
                    self.grid.addWidget(new, row + 2, 0)
                else:
                    self.grid.addWidget(
                        new if self.kind == "create" else old, row + 1, 0
                    )
                self.grid.setColumnStretch(0, 1)
            else:
                self.grid.addWidget(label, index, 0)
                self.grid.addWidget(old if self.kind != "create" else new, index, 1)
                if self.kind == "update":
                    self.grid.addWidget(new, index, 2)
                self.grid.setColumnStretch(1, 1)
                self.grid.setColumnStretch(2, 1 if self.kind == "update" else 0)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._layout_rows(self.width() < 520)
