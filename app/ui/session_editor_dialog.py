"""Dialog for manual focus records and history edits."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, time, timedelta, tzinfo
from typing import cast

from PySide6.QtCore import QDate, QTime
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QWidget,
)

from app.data.models import FocusItem, FocusSession
from app.i18n import get_localization, tr
from app.ui.components import DurationPicker, ThemedDateEdit
from app.ui.rounded_selector import RoundedComboBox, SelectorDensity
from app.ui.time_picker import RoundedTimePicker


class SessionEditorDialog(QDialog):
    """Collect a local date, Focus Item, and start/end time."""

    def __init__(self, local_timezone: tzinfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._local_timezone = local_timezone
        self._focus_items: list[FocusItem] = []
        self._focus_item_combo = RoundedComboBox(
            density=SelectorDensity.COMPACT
        )
        self._entry_method = RoundedComboBox(density=SelectorDensity.COMPACT)
        self._entry_method.addItem("", "range")
        self._entry_method.addItem("", "duration")
        self._entry_method.currentIndexChanged.connect(self._update_entry_method)
        self._date_edit = ThemedDateEdit(QDate.currentDate())
        current_time = QTime.currentTime()
        current_minute = QTime(current_time.hour(), current_time.minute())
        self._start_edit = RoundedTimePicker(current_minute.addSecs(-3600))
        self._start_edit.setDisplayFormat("HH:mm")
        self._end_edit = RoundedTimePicker(current_minute)
        self._end_edit.setDisplayFormat("HH:mm")
        self._duration_picker = DurationPicker(
            1,
            999 * 60 + 59,
            minute_step=1,
            hour_values=tuple(range(1000)),
            minute_values=tuple(range(60)),
            density=SelectorDensity.COMPACT,
        )
        self._duration_picker.setValue(30)
        self._duration_widget = self._duration_picker
        self._note_edit = QPlainTextEdit()
        self._note_edit.setMaximumHeight(90)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self._validate_and_accept)
        self._buttons.rejected.connect(self.reject)

        form = QFormLayout(self)
        self._date_label = QLabel()
        self._focus_item_label = QLabel()
        self._entry_method_label = QLabel()
        self._start_label = QLabel()
        self._end_label = QLabel()
        self._duration_label = QLabel()
        self._note_label = QLabel()
        form.addRow(self._date_label, self._date_edit)
        form.addRow(self._focus_item_label, self._focus_item_combo)
        form.addRow(self._entry_method_label, self._entry_method)
        form.addRow(self._start_label, self._start_edit)
        form.addRow(self._end_label, self._end_edit)
        form.addRow(self._duration_label, self._duration_widget)
        form.addRow(self._note_label, self._note_edit)
        form.addRow(self._buttons)
        get_localization().language_changed.connect(self.retranslate_ui)
        self.retranslate_ui()
        self._update_entry_method()

    def retranslate_ui(self, _language: str | None = None) -> None:
        selected_id = self._focus_item_combo.currentData()
        self.setWindowTitle(tr("session_editor.title"))
        self._date_label.setText(tr("session_editor.date"))
        self._focus_item_label.setText(tr("session_editor.subject"))
        self._entry_method_label.setText(tr("focus_entry.method"))
        self._start_label.setText(tr("session_editor.start"))
        self._end_label.setText(tr("session_editor.end"))
        self._duration_label.setText(tr("focus_entry.duration"))
        self._note_label.setText(tr("focus_entry.note"))
        self._entry_method.setItemText(0, tr("focus_entry.start_end"))
        self._entry_method.setItemText(1, tr("focus_entry.direct_duration"))
        self._note_edit.setPlaceholderText(tr("focus.note_placeholder"))
        self._date_edit.setDisplayFormat(tr("date.input_format"))
        self._date_edit.setAccessibleName(tr("session_editor.date"))
        self._focus_item_combo.setAccessibleName(tr("session_editor.subject"))
        self._entry_method.setAccessibleName(tr("focus_entry.method"))
        self._start_edit.setAccessibleName(tr("session_editor.start"))
        self._end_edit.setAccessibleName(tr("session_editor.end"))
        save = self._buttons.button(QDialogButtonBox.StandardButton.Save)
        cancel = self._buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if save is not None:
            save.setText(tr("common.save"))
        if cancel is not None:
            cancel.setText(tr("common.cancel"))
        if self._focus_items:
            self.set_focus_items(
                self._focus_items,
                int(selected_id) if selected_id is not None else None,
            )

    def set_focus_items(
        self,
        focus_items: Sequence[FocusItem],
        selected_id: int | None = None,
    ) -> None:
        self._focus_items = list(focus_items)
        self._focus_item_combo.clear()
        for item in focus_items:
            label = (
                tr("session_editor.archived", name=item.name)
                if item.is_archived
                else item.name
            )
            self._focus_item_combo.addItem(label, item.id)
        if selected_id is not None:
            index = self._focus_item_combo.findData(selected_id)
            if index >= 0:
                self._focus_item_combo.setCurrentIndex(index)

    def set_session(self, session: FocusSession) -> None:
        local_start = session.start_time.astimezone(self._local_timezone)
        local_end = session.end_time.astimezone(self._local_timezone)
        self._date_edit.setDate(QDate(local_start.year, local_start.month, local_start.day))
        self._start_edit.setTime(QTime(local_start.hour, local_start.minute))
        self._end_edit.setTime(QTime(local_end.hour, local_end.minute))
        index = self._focus_item_combo.findData(session.focus_item_id)
        if index >= 0:
            self._focus_item_combo.setCurrentIndex(index)
        self._note_edit.setPlainText(getattr(session, "note", ""))

    def values(self) -> tuple[int, datetime, datetime, float]:
        item_id, start, end, duration, _note = self.focus_values()
        return item_id, start, end, duration

    def focus_values(self) -> tuple[int, datetime, datetime, float, str]:
        """Return validated local input; range end-at/before-start means next day."""

        focus_item_id = int(self._focus_item_combo.currentData())
        selected_date = cast(date, self._date_edit.date().toPython())
        start_time = cast(time, self._start_edit.time().toPython()).replace(
            second=0, microsecond=0
        )
        end_time = cast(time, self._end_edit.time().toPython()).replace(
            second=0, microsecond=0
        )
        start = datetime.combine(selected_date, start_time, tzinfo=self._local_timezone)
        if self._entry_method.currentData() == "duration":
            duration = float(self._duration_picker.value() * 60)
            if duration < 60:
                raise ValueError(tr("error.session_duration_minimum"))
            end = start + timedelta(seconds=duration)
        else:
            end = datetime.combine(selected_date, end_time, tzinfo=self._local_timezone)
            if end <= start:
                end += timedelta(days=1)
            duration = (end - start).total_seconds()
        note = self._note_edit.toPlainText().strip()
        if len(note) > 2000:
            raise ValueError(tr("error.focus_note_long"))
        return focus_item_id, start, end, duration, note

    def _validate_and_accept(self) -> None:
        if self._focus_item_combo.currentData() is None:
            QMessageBox.warning(self, tr("app.name"), tr("session_editor.no_subject"))
            return
        try:
            self.focus_values()
        except ValueError as error:
            QMessageBox.warning(self, tr("app.name"), str(error))
            return
        self.accept()

    def _update_entry_method(self) -> None:
        direct_duration = self._entry_method.currentData() == "duration"
        self._end_label.setVisible(not direct_duration)
        self._end_edit.setVisible(not direct_duration)
        self._duration_label.setVisible(direct_duration)
        self._duration_widget.setVisible(direct_duration)
