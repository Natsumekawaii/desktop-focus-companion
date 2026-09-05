"""Daily Focus Replay presentation derived from existing Focus Sessions."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.core.theme import get_theme_manager
from app.i18n import format_date, get_localization, tr
from app.statistics import DailyReplaySummary
from app.timer.formatting import format_compact_duration
from app.ui.components import MetricStrip, apply_elevation
from app.ui.info_bubble import hide_tooltip, show_tooltip


class HourlyDistributionWidget(QWidget):
    """Equal-height 24-hour heat ribbon for daily replay."""

    def __init__(self) -> None:
        super().__init__()
        self._values: tuple[float, ...] = (0.0,) * 24
        self._cells: tuple[QRectF, ...] = ()
        self._hovered_hour: int | None = None
        self.setMinimumHeight(132)
        self.setMouseTracking(True)
        self.setAccessibleName(tr("replay.time_distribution"))
        get_localization().language_changed.connect(self._retranslate_ui)
        get_theme_manager().theme_changed.connect(self.update)

    @property
    def values(self) -> tuple[float, ...]:
        return self._values

    @property
    def cells(self) -> tuple[QRectF, ...]:
        return self._cells

    @property
    def intensity_levels(self) -> tuple[int, ...]:
        maximum = max(self._values, default=0.0)
        return tuple(_hour_intensity(value, maximum) for value in self._values)

    def set_values(self, values: tuple[float, ...]) -> None:
        if len(values) != 24:
            raise ValueError("Hourly distribution requires 24 values.")
        self._values = tuple(max(0.0, value) for value in values)
        self._hovered_hour = None
        hide_tooltip(self, immediate=True)
        self._update_accessible_description()
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tokens = get_theme_manager().tokens
        maximum = max(self._values, default=0.0)
        left, top, bottom = 10.0, 28.0, 34.0
        gap = 3.0
        width = max(3.0, (self.width() - left * 2 - gap * 23) / 24)
        ribbon_height = max(30.0, min(48.0, self.height() - top - bottom))
        ribbon_top = top + max(0.0, (self.height() - top - bottom - ribbon_height) / 2)
        self._cells = tuple(
            QRectF(left + hour * (width + gap), ribbon_top, width, ribbon_height)
            for hour in range(24)
        )
        for hour, (value, rect) in enumerate(zip(self._values, self._cells, strict=True)):
            level = _hour_intensity(value, maximum)
            painter.setBrush(QColor(tokens.heatmap_levels[level]))
            border = QColor(tokens.primary if hour == self._hovered_hour else tokens.separator)
            painter.setPen(QPen(border, 2.0 if hour == self._hovered_hour else 0.8))
            painter.drawRoundedRect(rect, 5, 5)

        painter.setPen(QColor(tokens.muted))
        if not any(self._values):
            painter.drawText(
                QRectF(left, 2, self.width() - left * 2, 20),
                Qt.AlignmentFlag.AlignCenter,
                tr("chart.no_data"),
            )
        painter.setPen(QColor(tokens.muted))
        for hour in (0, 6, 12, 18, 23):
            cell = self._cells[hour]
            label_width = 44.0
            label_left = max(0.0, min(self.width() - label_width, cell.center().x() - label_width / 2))
            painter.drawText(
                QRectF(label_left, self.height() - 25, label_width, 18),
                Qt.AlignmentFlag.AlignCenter,
                f"{hour:02d}:00",
            )

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        hour = next(
            (index for index, cell in enumerate(self._cells) if cell.contains(event.position())),
            None,
        )
        if hour != self._hovered_hour:
            self._hovered_hour = hour
            self.update()
        if hour is None:
            hide_tooltip(self)
        else:
            end_hour = (hour + 1) % 24
            show_tooltip(
                self,
                (
                    f"{hour:02d}:00–{end_hour:02d}:00 · "
                    f"{format_compact_duration(self._values[hour])}"
                ),
                event.globalPosition().toPoint(),
            )
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._hovered_hour = None
        hide_tooltip(self)
        self.update()
        super().leaveEvent(event)

    def _retranslate_ui(self, _language: str | None = None) -> None:
        self.setAccessibleName(tr("replay.time_distribution"))
        self._update_accessible_description()
        self.update()

    def _update_accessible_description(self) -> None:
        active = [
            f"{hour:02d}:00: {format_compact_duration(value)}"
            for hour, value in enumerate(self._values)
            if value > 0
        ]
        self.setAccessibleDescription("; ".join(active) if active else tr("chart.no_data"))


def _hour_intensity(value: float, maximum: float) -> int:
    if value <= 0 or maximum <= 0:
        return 0
    ratio = value / maximum
    if ratio <= 0.25:
        return 1
    if ratio <= 0.5:
        return 2
    if ratio <= 0.75:
        return 3
    return 4


class FocusReplayDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.resize(720, 590)
        self.setMinimumSize(620, 500)
        self._summary: DailyReplaySummary | None = None
        self._title = QLabel()
        self._title.setObjectName("pageTitle")
        self._subtitle = QLabel()
        self._subtitle.setObjectName("pageSubtitle")
        self._metric_strip = MetricStrip(max_columns=4)
        self._replay_metrics = []
        metric_values: list[QLabel] = []
        for key in ("replay.total", "replay.sessions", "replay.longest", "replay.top_item"):
            item = self._metric_strip.add_metric(tr(key), tr("common.no_value"))
            self._replay_metrics.append((item, key))
            metric_values.append(item.value_label)
        self._total, self._sessions, self._longest, self._top_item = metric_values
        completion_card = QFrame()
        completion_card.setObjectName("heroCard")
        completion_layout = QVBoxLayout(completion_card)
        self._completion_title = QLabel()
        self._completion_title.setObjectName("cardCaption")
        self._completion = QLabel()
        self._completion.setObjectName("sectionTitle")
        completion_layout.addWidget(self._completion_title)
        completion_layout.addWidget(self._completion)
        apply_elevation(completion_card, subtle=True)
        distribution_card = QFrame()
        distribution_card.setObjectName("sectionSurface")
        distribution_layout = QVBoxLayout(distribution_card)
        self._distribution_title = QLabel()
        self._distribution_title.setObjectName("sectionTitle")
        self._distribution = HourlyDistributionWidget()
        distribution_layout.addWidget(self._distribution_title)
        distribution_layout.addWidget(self._distribution)
        self._close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self._close.rejected.connect(self.close)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)
        layout.addWidget(self._title)
        layout.addWidget(self._subtitle)
        layout.addWidget(self._metric_strip)
        layout.addWidget(completion_card)
        layout.addWidget(distribution_card, 1)
        layout.addWidget(self._close)
        get_localization().language_changed.connect(self.retranslate_ui)
        self.retranslate_ui()

    def set_summary(self, summary: DailyReplaySummary) -> None:
        self._summary = summary
        self._subtitle.setText(format_date(summary.day))
        self._total.setText(format_compact_duration(summary.total_seconds))
        self._sessions.setText(str(summary.session_count))
        self._longest.setText(format_compact_duration(summary.longest_session_seconds))
        self._top_item.setText(
            summary.top_focus_item.focus_item_name
            if summary.top_focus_item is not None
            else tr("common.no_value")
        )
        self._completion.setText(
            tr("replay.completed", count=summary.session_count)
        )
        self._distribution.set_values(summary.hourly_seconds)

    def retranslate_ui(self, _language: str | None = None) -> None:
        self.setWindowTitle(tr("replay.window_title"))
        self._title.setText(tr("replay.title"))
        for item, key in self._replay_metrics:
            item.set_caption(tr(key))
        for caption in self.findChildren(QLabel):
            key = caption.property("translation_key")
            if isinstance(key, str) and key:
                caption.setText(tr(key))
        self._completion_title.setText(tr("replay.completion"))
        self._distribution_title.setText(tr("replay.time_distribution"))
        close = self._close.button(QDialogButtonBox.StandardButton.Close)
        if close is not None:
            close.setText(tr("common.close"))
        if self._summary is not None:
            self.set_summary(self._summary)
