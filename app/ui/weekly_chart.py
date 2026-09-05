"""Theme-aware seven-day Focus rhythm chart."""

from __future__ import annotations

from itertools import pairwise

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QFont,
    QHideEvent,
    QLinearGradient,
    QMouseEvent,
    QMoveEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QResizeEvent,
    QShowEvent,
)
from PySide6.QtWidgets import QWidget

from app.core.theme import get_theme_manager
from app.i18n import format_date, format_weekday, get_localization, tr
from app.statistics import DailyTotal
from app.timer.formatting import format_compact_duration
from app.ui.trend_callout import AnchoredTrendCallout


class WeeklyChart(QWidget):
    """Render a quiet line-and-area rhythm without statistical bars."""

    def __init__(self) -> None:
        super().__init__()
        self._values: list[DailyTotal] = []
        self._chart_points: tuple[QPointF, ...] = ()
        self._hovered_index: int | None = None
        self._callout = AnchoredTrendCallout(self)
        self.setMinimumHeight(220)
        self.setMouseTracking(True)
        self.setAccessibleName(tr("dashboard.weekly_trend"))
        get_localization().language_changed.connect(self._retranslate_ui)
        get_theme_manager().theme_changed.connect(self._theme_changed)

    @property
    def values(self) -> tuple[DailyTotal, ...]:
        return tuple(self._values)

    @property
    def chart_points(self) -> tuple[QPointF, ...]:
        """Return the last painted points for hit testing and widget tests."""
        return self._chart_points

    def set_values(self, values: list[DailyTotal]) -> None:
        self._values = list(values)
        self._hovered_index = None
        self._callout.hide_immediately()
        self._update_accessible_description()
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tokens = get_theme_manager().tokens
        if not self._values:
            self._chart_points = ()
            painter.setPen(QColor(tokens.muted))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, tr("chart.no_data"))
            return

        chart = QRectF(self.rect()).adjusted(24, 18, -24, -38)
        maximum = max(value.duration_seconds for value in self._values) or 1.0
        self._chart_points = _plot_points(
            chart,
            tuple(value.duration_seconds for value in self._values),
            maximum,
        )

        grid_pen = QPen(QColor(tokens.chart_grid), 1)
        grid_pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(grid_pen)
        for fraction in (0.0, 0.5, 1.0):
            y = chart.bottom() - chart.height() * fraction
            painter.drawLine(QPointF(chart.left(), y), QPointF(chart.right(), y))

        if any(value.duration_seconds > 0 for value in self._values):
            line_path = _smooth_path(self._chart_points)
            area_path = _area_path(self._chart_points, chart.bottom())
            gradient = QLinearGradient(0, chart.top(), 0, chart.bottom())
            top_color = QColor(tokens.primary)
            top_color.setAlpha(88)
            bottom_color = QColor(tokens.primary)
            bottom_color.setAlpha(8)
            gradient.setColorAt(0.0, top_color)
            gradient.setColorAt(1.0, bottom_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(gradient)
            painter.drawPath(area_path)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(
                QPen(
                    QColor(tokens.primary),
                    2.4,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            painter.drawPath(line_path)

        label_font = QFont(self.font())
        label_font.setPointSize(9)
        painter.setFont(label_font)
        slot = chart.width() / max(1, len(self._values) - 1)
        for index, (value, point) in enumerate(
            zip(self._values, self._chart_points, strict=True)
        ):
            is_hovered = index == self._hovered_index
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(tokens.surface))
            radius = 5.0 if is_hovered else 3.8
            painter.drawEllipse(point, radius, radius)
            painter.setBrush(QColor(tokens.primary))
            radius = 3.0 if is_hovered else 2.3
            painter.drawEllipse(point, radius, radius)
            painter.setPen(QColor(tokens.text if is_hovered else tokens.muted))
            label_width = min(72.0, max(32.0, slot))
            painter.drawText(
                QRectF(point.x() - label_width / 2, chart.bottom() + 8, label_width, 22),
                Qt.AlignmentFlag.AlignCenter,
                format_weekday(value.day),
            )

        if self._hovered_index is not None:
            point = self._chart_points[self._hovered_index]
            guide = QColor(tokens.primary)
            guide.setAlpha(80)
            painter.setPen(QPen(guide, 1, Qt.PenStyle.DashLine))
            painter.drawLine(point, QPointF(point.x(), chart.bottom()))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        index = _nearest_index(event.position(), self._chart_points, self.width())
        target_changed = index != self._hovered_index
        if index != self._hovered_index:
            self._hovered_index = index
            self.update()
        if index is None:
            self._callout.hide_animated()
        elif target_changed or not self._callout.isVisible():
            self._show_callout(index)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._hovered_index = None
        self._callout.hide_animated()
        self.update()
        super().leaveEvent(event)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._callout.owner_shown()

    def hideEvent(self, event: QHideEvent) -> None:
        self._callout.hide_immediately()
        super().hideEvent(event)

    def moveEvent(self, event: QMoveEvent) -> None:
        self._callout.hide_immediately()
        super().moveEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        self._callout.hide_immediately()
        super().resizeEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._callout.dispose()
        super().closeEvent(event)

    def _retranslate_ui(self, _language: str | None = None) -> None:
        self.setAccessibleName(tr("dashboard.weekly_trend"))
        self._update_accessible_description()
        self._refresh_callout()
        self.update()

    def _theme_changed(self, _theme: str | None = None) -> None:
        self._callout.update()
        self._refresh_callout()
        self.update()

    def _show_callout(self, index: int) -> None:
        if not 0 <= index < len(self._values) or index >= len(self._chart_points):
            self._callout.hide_immediately()
            return
        value = self._values[index]
        detail = tr(
            "calendar.day_tooltip",
            date=format_date(value.day),
            duration=format_compact_duration(value.duration_seconds),
        )
        self._callout.show_for(detail, self._chart_points[index])

    def _refresh_callout(self) -> None:
        if self._callout.isVisible() and self._hovered_index is not None:
            self._show_callout(self._hovered_index)

    def _update_accessible_description(self) -> None:
        if not self._values:
            self.setAccessibleDescription(tr("chart.no_data"))
            return
        details = (
            tr(
                "calendar.day_tooltip",
                date=format_date(value.day),
                duration=format_compact_duration(value.duration_seconds),
            )
            for value in self._values
        )
        self.setAccessibleDescription("; ".join(details))


def _plot_points(
    chart: QRectF,
    values: tuple[float, ...],
    maximum: float,
) -> tuple[QPointF, ...]:
    if not values:
        return ()
    x_values: tuple[float, ...]
    if len(values) == 1:
        x_values = (chart.center().x(),)
    else:
        slot = chart.width() / (len(values) - 1)
        x_values = tuple(chart.left() + index * slot for index in range(len(values)))
    return tuple(
        QPointF(x, chart.bottom() - chart.height() * max(0.0, value) / maximum)
        for x, value in zip(x_values, values, strict=True)
    )


def _smooth_path(points: tuple[QPointF, ...]) -> QPainterPath:
    path = QPainterPath()
    if not points:
        return path
    path.moveTo(points[0])
    for first, second in pairwise(points):
        midpoint_x = (first.x() + second.x()) / 2
        path.cubicTo(
            QPointF(midpoint_x, first.y()),
            QPointF(midpoint_x, second.y()),
            second,
        )
    return path


def _area_path(points: tuple[QPointF, ...], baseline: float) -> QPainterPath:
    if not points:
        return QPainterPath()
    path = QPainterPath(QPointF(points[0].x(), baseline))
    path.lineTo(points[0])
    for first, second in pairwise(points):
        midpoint_x = (first.x() + second.x()) / 2
        path.cubicTo(
            QPointF(midpoint_x, first.y()),
            QPointF(midpoint_x, second.y()),
            second,
        )
    path.lineTo(points[-1].x(), baseline)
    path.closeSubpath()
    return path


def _nearest_index(
    position: QPointF,
    points: tuple[QPointF, ...],
    widget_width: int,
) -> int | None:
    if not points:
        return None
    nearest = min(range(len(points)), key=lambda index: abs(points[index].x() - position.x()))
    threshold = max(18.0, widget_width / max(1, len(points)) * 0.48)
    return nearest if abs(points[nearest].x() - position.x()) <= threshold else None
