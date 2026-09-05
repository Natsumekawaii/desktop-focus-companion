"""Theme-aware charts for the Focus Analytics dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from itertools import pairwise
from math import atan2, degrees, hypot
from typing import cast

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPointF,
    QRectF,
    Qt,
    QVariantAnimation,
)
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QCursor,
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
from app.i18n import get_localization, tr
from app.statistics import FocusItemTotal, TrendPoint
from app.timer.formatting import format_compact_duration
from app.ui.info_bubble import hide_tooltip, show_tooltip
from app.ui.trend_callout import AnchoredTrendCallout


class FocusTrendWidget(QWidget):
    """Compact line-and-area trend that remains readable in narrow windows."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._values: tuple[TrendPoint, ...] = ()
        self._chart_points: tuple[QPointF, ...] = ()
        self._hovered_index: int | None = None
        self._callout = AnchoredTrendCallout(self)
        self.setMinimumHeight(150)
        self.setMouseTracking(True)
        self.setAccessibleName(tr("analytics.title"))
        get_localization().language_changed.connect(self._retranslate_ui)
        get_theme_manager().theme_changed.connect(self._theme_changed)

    @property
    def values(self) -> tuple[TrendPoint, ...]:
        return self._values

    @property
    def chart_points(self) -> tuple[QPointF, ...]:
        return self._chart_points

    def set_values(self, values: tuple[TrendPoint, ...]) -> None:
        self._values = tuple(values)
        self._hovered_index = None
        self._callout.hide_immediately()
        self._update_accessible_description()
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tokens = get_theme_manager().tokens
        if not self._values or not any(point.duration_seconds > 0 for point in self._values):
            self._chart_points = ()
            painter.setPen(QColor(tokens.muted))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, tr("chart.no_data"))
            return

        chart = QRectF(self.rect()).adjusted(12, 12, -12, -26)
        maximum = max(point.duration_seconds for point in self._values) or 1.0
        self._chart_points = _trend_points(
            chart,
            tuple(point.duration_seconds for point in self._values),
            maximum,
        )

        guide_color = QColor(tokens.chart_grid)
        painter.setPen(QPen(guide_color, 1, Qt.PenStyle.DashLine))
        for fraction in (0.0, 0.5, 1.0):
            y = chart.bottom() - chart.height() * fraction
            painter.drawLine(QPointF(chart.left(), y), QPointF(chart.right(), y))

        area_path = _trend_area_path(self._chart_points, chart.bottom())
        gradient = QLinearGradient(0, chart.top(), 0, chart.bottom())
        start_color = QColor(tokens.primary)
        start_color.setAlpha(72)
        end_color = QColor(tokens.primary)
        end_color.setAlpha(5)
        gradient.setColorAt(0.0, start_color)
        gradient.setColorAt(1.0, end_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawPath(area_path)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(
            QPen(
                QColor(tokens.primary),
                2.2,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        painter.drawPath(_trend_line_path(self._chart_points))

        for index, chart_point in enumerate(self._chart_points):
            hovered = index == self._hovered_index
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(tokens.surface))
            radius = 4.6 if hovered else 3.5
            painter.drawEllipse(chart_point, radius, radius)
            painter.setBrush(QColor(tokens.primary))
            radius = 2.8 if hovered else 2.0
            painter.drawEllipse(chart_point, radius, radius)

        if self._hovered_index is not None:
            hovered_point = self._chart_points[self._hovered_index]
            hover_color = QColor(tokens.primary)
            hover_color.setAlpha(75)
            painter.setPen(QPen(hover_color, 1, Qt.PenStyle.DashLine))
            painter.drawLine(hovered_point, QPointF(hovered_point.x(), chart.bottom()))

        label_font = QFont(self.font())
        label_font.setPointSize(8)
        painter.setFont(label_font)
        painter.setPen(QColor(tokens.muted))
        label_step = max(1, (len(self._values) + 4) // 5)
        label_indices = list(range(0, len(self._values), label_step))
        last_index = len(self._values) - 1
        if label_indices[-1] != last_index:
            if last_index - label_indices[-1] < max(2, label_step // 2):
                label_indices[-1] = last_index
            else:
                label_indices.append(last_index)
        for index, point in enumerate(self._values):
            if index not in label_indices:
                continue
            label = point.label[5:] if len(point.label) >= 7 else point.label
            painter.drawText(
                QRectF(
                    self._chart_points[index].x() - 38,
                    chart.bottom() + 5,
                    76,
                    18,
                ),
                Qt.AlignmentFlag.AlignCenter,
                label,
            )

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        index = _trend_nearest_index(event.position(), self._chart_points, self.width())
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
        self.setAccessibleName(tr("analytics.title"))
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
        point = self._values[index]
        detail = f"{point.label} · {format_compact_duration(point.duration_seconds)}"
        self._callout.show_for(detail, self._chart_points[index])

    def _refresh_callout(self) -> None:
        if self._callout.isVisible() and self._hovered_index is not None:
            self._show_callout(self._hovered_index)

    def _update_accessible_description(self) -> None:
        if not self._values or not any(point.duration_seconds > 0 for point in self._values):
            self.setAccessibleDescription(tr("chart.no_data"))
            return
        self.setAccessibleDescription(
            "; ".join(
                f"{point.label}: {format_compact_duration(point.duration_seconds)}"
                for point in self._values
            )
        )


def _trend_points(
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


def _trend_line_path(points: tuple[QPointF, ...]) -> QPainterPath:
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


def _trend_area_path(points: tuple[QPointF, ...], baseline: float) -> QPainterPath:
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


def _trend_nearest_index(
    position: QPointF,
    points: tuple[QPointF, ...],
    widget_width: int,
) -> int | None:
    if not points:
        return None
    nearest = min(range(len(points)), key=lambda index: abs(points[index].x() - position.x()))
    threshold = max(14.0, widget_width / max(1, len(points)) * 0.48)
    return nearest if abs(points[nearest].x() - position.x()) <= threshold else None


@dataclass(frozen=True, slots=True)
class DistributionSegment:
    focus_item_id: int
    name: str
    duration_seconds: float
    percentage: float
    color: str
    start_degrees: float
    span_degrees: float


class DistributionTransitionPhase(Enum):
    """Internal two-stage period transition for the distribution chart."""

    IDLE = "idle"
    EXIT = "exit"
    REVEAL = "reveal"


def _blend_opaque(first: QColor, second: QColor, amount: float) -> QColor:
    progress = max(0.0, min(1.0, amount))
    return QColor(
        round(first.red() + (second.red() - first.red()) * progress),
        round(first.green() + (second.green() - first.green()) * progress),
        round(first.blue() + (second.blue() - first.blue()) * progress),
    )


class FocusDistributionChart(QWidget):
    """Interactive donut and legend for stable Focus Item time allocation."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._segments: tuple[DistributionSegment, ...] = ()
        self._raw_values: tuple[FocusItemTotal, ...] = ()
        self._colors: dict[int, str] = {}
        self._hovered_index: int | None = None
        self._display_segments: tuple[DistributionSegment, ...] = ()
        self._transition_phase = DistributionTransitionPhase.IDLE
        self._content_opacity = 1.0
        self._reveal_progress = 1.0
        self._transition_animation = QVariantAnimation(self)
        self._transition_animation.valueChanged.connect(
            self._update_transition_value
        )
        self._transition_animation.finished.connect(
            self._finish_transition_phase
        )
        self.setMouseTracking(True)
        self.setMinimumSize(280, 300)
        self.setAccessibleName(tr("analytics.distribution.title"))
        get_localization().language_changed.connect(self._retranslate_ui)
        get_theme_manager().theme_changed.connect(self.update)

    @property
    def segments(self) -> tuple[DistributionSegment, ...]:
        return self._segments

    @property
    def donut_rect(self) -> QRectF:
        """Return the shared paint and hit-test geometry for the outer ring."""
        return self._donut_rect()

    @property
    def inner_donut_rect(self) -> QRectF:
        donut = self._donut_rect()
        inset = donut.width() * 0.23
        return donut.adjusted(inset, inset, -inset, -inset)

    @property
    def transition_phase(self) -> DistributionTransitionPhase:
        return self._transition_phase

    @property
    def reveal_progress(self) -> float:
        return self._reveal_progress

    def set_values(
        self,
        values: tuple[FocusItemTotal, ...] | list[FocusItemTotal],
        colors: dict[int, str],
        *,
        animate: bool = False,
    ) -> None:
        self._raw_values = tuple(values)
        self._colors = dict(colors)
        usable = [value for value in self._raw_values if value.duration_seconds >= 60]
        if len(usable) > 7:
            visible = usable[:6]
            visible.append(
                FocusItemTotal(
                    focus_item_id=-1,
                    focus_item_name=tr("common.other"),
                    duration_seconds=sum(
                        value.duration_seconds for value in usable[6:]
                    ),
                )
            )
            usable = visible
        total = sum(value.duration_seconds for value in usable)
        start = 90.0
        segments: list[DistributionSegment] = []
        for value in usable:
            percentage = value.duration_seconds / total if total else 0.0
            span = percentage * 360.0
            segments.append(
                DistributionSegment(
                    focus_item_id=value.focus_item_id,
                    name=value.focus_item_name,
                    duration_seconds=value.duration_seconds,
                    percentage=percentage,
                    color=colors.get(value.focus_item_id, _fallback_color(value.focus_item_id)),
                    start_degrees=start,
                    span_degrees=span,
                )
            )
            start += span
        self._segments = tuple(segments)
        self._hovered_index = None
        hide_tooltip(self, immediate=True)
        self._sync_minimum_height()
        self._update_accessible_description()
        if animate and self.isVisible() and (self._display_segments or self._segments):
            self._queue_animated_transition()
        else:
            self._complete_transition()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tokens = get_theme_manager().tokens
        segments = self._display_segments
        if not segments:
            painter.setPen(QColor(tokens.muted))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, tr("analytics.distribution.empty"))
            return

        compact = self.width() < 560
        donut = self._donut_rect()
        painter.save()
        painter.setOpacity(self._content_opacity)
        if self._reveal_progress <= 0.001:
            painter.setClipRect(QRectF())
        elif self._reveal_progress < 0.999:
            reveal = QPainterPath()
            reveal.moveTo(donut.center())
            reveal.arcTo(donut, 90.0, -359.999 * self._reveal_progress)
            reveal.closeSubpath()
            painter.setClipPath(reveal, Qt.ClipOperation.IntersectClip)
        for index, segment in enumerate(segments):
            color = QColor(segment.color)
            if self._hovered_index is not None and index != self._hovered_index:
                color.setAlpha(105)
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            if len(segments) == 1:
                painter.drawEllipse(donut)
            else:
                painter.drawPie(
                    donut,
                    round(segment.start_degrees * 16),
                    round(segment.span_degrees * 16),
                )
        painter.restore()

        painter.save()
        painter.setOpacity(self._content_opacity)
        inner = self.inner_donut_rect
        painter.setBrush(QColor(tokens.surface))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(inner)
        total = sum(segment.duration_seconds for segment in segments)
        painter.setPen(QColor(tokens.text))
        total_font = QFont(self.font())
        total_font.setPointSize(15)
        total_font.setWeight(QFont.Weight.Bold)
        painter.setFont(total_font)
        total_text = format_compact_duration(total)
        while (
            painter.fontMetrics().horizontalAdvance(total_text) > inner.width() - 10
            and total_font.pointSize() > 9
        ):
            total_font.setPointSize(total_font.pointSize() - 1)
            painter.setFont(total_font)
        painter.drawText(
            inner.adjusted(4, 30, -4, -30),
            Qt.AlignmentFlag.AlignCenter,
            total_text,
        )

        if compact:
            legend_left = 18.0
            legend_width = max(120.0, self.width() - 36.0)
            row_height = min(
                38.0,
                max(30.0, (self.height() - donut.bottom() - 20) / len(segments)),
            )
            top = donut.bottom() + 12.0
        else:
            legend_left = donut.right() + 30
            legend_width = max(160.0, self.width() - legend_left - 20)
            row_height = min(43.0, max(30.0, (self.height() - 28) / len(segments)))
            top = max(14.0, (self.height() - row_height * len(segments)) / 2)
        label_font = QFont(self.font())
        label_font.setPointSize(10)
        label_font.setWeight(QFont.Weight.Medium)
        detail_font = QFont(label_font)
        detail_font.setWeight(QFont.Weight.Normal)
        detail_color = _blend_opaque(
            QColor(tokens.muted),
            QColor(tokens.text),
            0.5,
        )
        for index, segment in enumerate(segments):
            y = top + index * row_height
            painter.setFont(label_font)
            painter.setPen(QColor(segment.color))
            name_width = legend_width * (0.55 if compact else 0.48)
            name_rect = QRectF(legend_left, y, name_width, row_height)
            elided_name = painter.fontMetrics().elidedText(
                segment.name,
                Qt.TextElideMode.ElideRight,
                max(1, round(name_rect.width())),
            )
            painter.drawText(
                name_rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                elided_name,
            )
            painter.setFont(detail_font)
            painter.setPen(detail_color)
            detail = f"{format_compact_duration(segment.duration_seconds)}  ·  {segment.percentage:.0%}"
            painter.drawText(
                QRectF(
                    legend_left + legend_width * (0.58 if compact else 0.5),
                    y,
                    legend_width * (0.42 if compact else 0.5),
                    row_height,
                ),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                detail,
            )
        painter.restore()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._transition_phase is not DistributionTransitionPhase.IDLE:
            self._hovered_index = None
            hide_tooltip(self, immediate=True)
            self.update()
            super().mouseMoveEvent(event)
            return
        index = self._segment_at(event.position())
        if index != self._hovered_index:
            self._hovered_index = index
            self.update()
        if index is not None:
            self._show_segment_tooltip(index, event.globalPosition().toPoint())
        else:
            hide_tooltip(self)

    def leaveEvent(self, event: QEvent) -> None:
        del event
        self._hovered_index = None
        hide_tooltip(self)
        self.update()

    def hideEvent(self, event: QHideEvent) -> None:
        hide_tooltip(self, immediate=True)
        self._complete_transition()
        super().hideEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        self._sync_minimum_height()
        super().resizeEvent(event)

    def _donut_rect(self) -> QRectF:
        compact = self.width() < 560
        maximum_side = 178.0 if compact else 202.0
        side = min(maximum_side, max(0.0, float(self.width()) - 48.0))
        if compact:
            return QRectF((self.width() - side) / 2, 18.0, side, side)
        return QRectF(24.0, (self.height() - side) / 2, side, side)

    def _sync_minimum_height(self) -> None:
        if self.width() >= 560:
            required = 300
        else:
            segment_count = max(len(self._segments), len(self._display_segments))
            required = max(
                300,
                round(18 + self._donut_rect().height() + 12 + segment_count * 30 + 12),
            )
        if self.minimumHeight() != required:
            self.setMinimumHeight(required)

    def _queue_animated_transition(self) -> None:
        self._hovered_index = None
        hide_tooltip(self, immediate=True)
        if self._transition_phase is DistributionTransitionPhase.EXIT:
            self.update()
            return
        if not self._display_segments:
            self._display_segments = self._segments
            self._start_reveal()
            return
        self._start_exit()

    def _start_exit(self) -> None:
        start_opacity = max(0.0, min(1.0, self._content_opacity))
        if start_opacity <= 0.001:
            self._display_segments = self._segments
            self._start_reveal()
            return
        self._transition_phase = DistributionTransitionPhase.EXIT
        self._start_transition_animation(
            start_opacity,
            0.0,
            max(1, round(100 * start_opacity)),
        )

    def _start_reveal(self) -> None:
        if not self._display_segments:
            self._complete_transition()
            return
        self._transition_phase = DistributionTransitionPhase.REVEAL
        self._content_opacity = 0.0
        self._reveal_progress = 0.0
        self._start_transition_animation(0.0, 1.0, 320)

    def _start_transition_animation(
        self,
        start: float,
        end: float,
        duration_ms: int,
    ) -> None:
        self._transition_animation.stop()
        self._transition_animation.setStartValue(start)
        self._transition_animation.setEndValue(end)
        self._transition_animation.setDuration(duration_ms)
        self._transition_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._transition_animation.start()
        self.update()

    def _update_transition_value(self, value: object) -> None:
        progress = cast(float, value)
        if self._transition_phase is DistributionTransitionPhase.EXIT:
            self._content_opacity = progress
        elif self._transition_phase is DistributionTransitionPhase.REVEAL:
            self._content_opacity = progress
            self._reveal_progress = progress
        self.update()

    def _finish_transition_phase(self) -> None:
        if self._transition_phase is DistributionTransitionPhase.EXIT:
            self._display_segments = self._segments
            self._sync_minimum_height()
            self._start_reveal()
            return
        if self._transition_phase is DistributionTransitionPhase.REVEAL:
            self._complete_transition(restore_hover=True)

    def _complete_transition(self, *, restore_hover: bool = False) -> None:
        self._transition_animation.stop()
        self._display_segments = self._segments
        self._transition_phase = DistributionTransitionPhase.IDLE
        self._content_opacity = 1.0
        self._reveal_progress = 1.0
        self._sync_minimum_height()
        self.update()
        if restore_hover:
            self._restore_hover_under_cursor()

    def _restore_hover_under_cursor(self) -> None:
        if not self.isVisible():
            return
        global_position = QCursor.pos()
        position = self.mapFromGlobal(global_position)
        if not self.rect().contains(position):
            return
        index = self._segment_at(QPointF(position))
        self._hovered_index = index
        if index is None:
            hide_tooltip(self)
        else:
            self._show_segment_tooltip(index, global_position)
        self.update()

    def _show_segment_tooltip(self, index: int, global_position: QPoint) -> None:
        if not 0 <= index < len(self._display_segments):
            return
        segment = self._display_segments[index]
        show_tooltip(
            self,
            tr(
                "analytics.distribution.tooltip",
                item=segment.name,
                duration=format_compact_duration(segment.duration_seconds),
                percent=f"{segment.percentage:.1%}",
            ),
            global_position,
        )

    def _segment_at(self, position: QPointF) -> int | None:
        donut = self._donut_rect()
        side = donut.width()
        center = donut.center()
        distance = hypot(position.x() - center.x(), position.y() - center.y())
        if distance < side * 0.27 or distance > side / 2:
            return None
        angle = (degrees(atan2(center.y() - position.y(), position.x() - center.x())) + 360.0) % 360.0
        for index, segment in enumerate(self._display_segments):
            relative = (angle - segment.start_degrees) % 360.0
            if relative <= segment.span_degrees:
                return index
        return None

    def _retranslate_ui(self, _language: str | None = None) -> None:
        self.setAccessibleName(tr("analytics.distribution.title"))
        self.set_values(self._raw_values, self._colors)

    def _update_accessible_description(self) -> None:
        if not self._segments:
            self.setAccessibleDescription(tr("analytics.distribution.empty"))
            return
        self.setAccessibleDescription(
            "; ".join(
                tr(
                    "analytics.distribution.tooltip",
                    item=segment.name,
                    duration=format_compact_duration(segment.duration_seconds),
                    percent=f"{segment.percentage:.1%}",
                )
                for segment in self._segments
            )
        )


def _fallback_color(focus_item_id: int) -> str:
    palette = ("#7C5CFC", "#3B82F6", "#10B981", "#F59E0B", "#EC4899", "#6366F1", "#14B8A6")
    return palette[abs(focus_item_id) % len(palette)]
