"""Theme-aware Focus Activity matrices over a Monday-aligned annual range."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from math import ceil
from typing import TypeAlias, TypeVar, cast

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QLocale,
    QObject,
    QPoint,
    QRectF,
    Qt,
    QVariantAnimation,
)
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QCursor,
    QFocusEvent,
    QHideEvent,
    QKeyEvent,
    QMouseEvent,
    QMoveEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QResizeEvent,
    QShowEvent,
)
from PySide6.QtWidgets import QAbstractScrollArea, QScrollBar, QWidget

from app.core.theme import get_theme_manager
from app.i18n import format_date, get_localization, tr
from app.statistics import HeatmapData, HeatmapDay
from app.timer.formatting import format_compact_duration
from app.ui.info_bubble import AnimatedInfoBubble


class FocusActivityMode(Enum):
    """Stable display modes for the Focus Activity card."""

    DAILY = "daily"
    WEEKLY = "weekly"
    CUMULATIVE = "cumulative"


class _ModeTransitionPhase(Enum):
    IDLE = "idle"
    FADING = "fading"
    REVEALING = "revealing"


@dataclass(frozen=True, slots=True)
class WeeklyActivity:
    start_day: date
    end_day: date
    duration_seconds: float


@dataclass(frozen=True, slots=True)
class CumulativeActivity:
    start_day: date
    end_day: date
    duration_seconds: float


@dataclass(frozen=True, slots=True)
class _GridGeometry:
    left: float
    top: float
    cell: float
    gap: float
    columns: int

    @property
    def stride(self) -> float:
        return self.cell + self.gap

    @property
    def grid_height(self) -> float:
        return self.cell * 7 + self.gap * 6

    def cell_rect(self, column: int, row: int) -> QRectF:
        return QRectF(
            self.left + column * self.stride,
            self.top + row * self.stride,
            self.cell,
            self.cell,
        )

    def column_rect(self, column: int) -> QRectF:
        return QRectF(
            self.left + column * self.stride - 1,
            self.top - 1,
            self.cell + 2,
            self.grid_height + 2,
        )


HoverKey: TypeAlias = tuple[FocusActivityMode, int]


class _ActivityCallout(AnimatedInfoBubble):
    """A mouse-transparent information bubble anchored to one matrix target."""

    _gap = 5

    def __init__(self, owner: QWidget) -> None:
        super().__init__(
            owner,
            minimum_surface_width=112,
            maximum_surface_width=280,
        )
        self._owner = owner

    def show_for(self, text: str, target: QRectF) -> None:
        self.set_text(text)

        container = self.parentWidget() or self._owner
        target_top_left_global = self._owner.mapToGlobal(target.topLeft().toPoint())
        target_top_left = container.mapFromGlobal(target_top_left_global)
        anchor_x = target_top_left.x() + round(target.width() / 2)
        anchor_y = target_top_left.y()
        desired_x = anchor_x - self.width() // 2
        desired_y = anchor_y - self.height() - self._gap
        available = container.rect()
        desired_x = max(
            available.left(),
            min(desired_x, available.right() - self.width() + 1),
        )
        desired_y = max(available.top(), desired_y)
        self.move(desired_x, desired_y)
        self.show_animated()


class HeatmapWidget(QWidget):
    """Paint three views using one stable seven-by-week square matrix."""

    def __init__(self) -> None:
        super().__init__()
        self._data: HeatmapData | None = None
        self._mode = FocusActivityMode.DAILY
        self._rendered_mode = self._mode
        self._mode_transition_phase = _ModeTransitionPhase.IDLE
        self._mode_transition_progress = 1.0
        self._fade_reveal_progress = 1.0
        self._mode_exit_duration_ms = 120
        self._mode_reveal_duration_ms = 400
        self._mode_transition_animation = QVariantAnimation(self)
        self._mode_transition_animation.valueChanged.connect(
            self._update_mode_transition
        )
        self._mode_transition_animation.finished.connect(
            self._finish_mode_transition_phase
        )
        self._hit_regions: list[tuple[QRectF, HeatmapDay]] = []
        self._weekly_regions: list[tuple[QRectF, WeeklyActivity]] = []
        self._cumulative_regions: list[tuple[QRectF, CumulativeActivity]] = []
        self._weekly_values: tuple[WeeklyActivity, ...] = ()
        self._cumulative_values: tuple[CumulativeActivity, ...] = ()
        self._weekly_fill_heights: tuple[int, ...] = ()
        self._cumulative_fill_heights: tuple[int, ...] = ()
        self._cell_rects: tuple[QRectF, ...] = ()
        self._month_label_positions: tuple[tuple[date, float, float], ...] = ()
        self._rendered_month_labels: tuple[tuple[date, str, QRectF], ...] = ()
        self._keyboard_target: HoverKey | None = None
        self._hover_target: HoverKey | None = None
        self._hover_strengths: dict[HoverKey, float] = {}
        self._hover_animations: dict[HoverKey, QVariantAnimation] = {}
        self._callout = _ActivityCallout(self)
        self._filtered_window: QWidget | None = None
        self._scroll_bars: list[QScrollBar] = []
        self.setMouseTracking(True)
        self.setMinimumHeight(130)
        self.setMinimumWidth(280)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        get_localization().language_changed.connect(self._retranslate_ui)
        get_theme_manager().theme_changed.connect(self._theme_changed)
        self._sync_interaction_mode()
        self._retranslate_ui()

    @property
    def mode(self) -> FocusActivityMode:
        return self._mode

    def set_mode(self, mode: FocusActivityMode) -> None:
        if mode is self._mode:
            return
        self._clear_hover()
        self._mode = mode
        self._sync_interaction_mode()
        self._update_accessible_description()
        if self._data is None or not self._data.days or not self.isVisible():
            self._complete_mode_transition()
            return
        if self._mode_transition_phase is _ModeTransitionPhase.FADING:
            # The old matrix is already leaving.  Only replace the pending
            # destination so rapid clicks never queue extra animations.
            return
        if self._mode_transition_phase is _ModeTransitionPhase.REVEALING:
            self._fade_reveal_progress = self._mode_transition_progress
        else:
            self._fade_reveal_progress = 1.0
        self._start_mode_transition_phase(
            _ModeTransitionPhase.FADING,
            self._mode_exit_duration_ms,
        )

    def set_data(self, data: HeatmapData) -> None:
        self._complete_mode_transition()
        self._clear_hover()
        self._data = data
        self._weekly_values = _aggregate_weeks(data.days)
        self._cumulative_values = _accumulate_weeks(self._weekly_values)
        self._weekly_fill_heights = _relative_fill_heights(
            tuple(value.duration_seconds for value in self._weekly_values)
        )
        self._cumulative_fill_heights = _cumulative_fill_heights(
            tuple(value.duration_seconds for value in self._cumulative_values)
        )
        self._update_accessible_description()
        self.update()

    def _start_mode_transition_phase(
        self,
        phase: _ModeTransitionPhase,
        duration_ms: int,
    ) -> None:
        self._mode_transition_animation.stop()
        self._mode_transition_phase = phase
        self._mode_transition_progress = 0.0
        self._mode_transition_animation.setStartValue(0.0)
        self._mode_transition_animation.setEndValue(1.0)
        self._mode_transition_animation.setDuration(max(1, duration_ms))
        self._mode_transition_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._mode_transition_animation.start()
        self.update()

    def _update_mode_transition(self, value: object) -> None:
        self._mode_transition_progress = cast(float, value)
        self.update()

    def _finish_mode_transition_phase(self) -> None:
        if self._mode_transition_phase is _ModeTransitionPhase.FADING:
            self._rendered_mode = self._mode
            self._fade_reveal_progress = 1.0
            self._start_mode_transition_phase(
                _ModeTransitionPhase.REVEALING,
                self._mode_reveal_duration_ms,
            )
            return
        if self._mode_transition_phase is _ModeTransitionPhase.REVEALING:
            self._mode_transition_phase = _ModeTransitionPhase.IDLE
            self._mode_transition_progress = 1.0
            self._rendered_mode = self._mode
            self.update()
            self.repaint()
            self._restore_hover_under_cursor()

    def _complete_mode_transition(self) -> None:
        self._mode_transition_animation.stop()
        self._mode_transition_phase = _ModeTransitionPhase.IDLE
        self._mode_transition_progress = 1.0
        self._fade_reveal_progress = 1.0
        self._rendered_mode = self._mode
        self.update()

    def _matrix_transition_values(self) -> tuple[float, float]:
        if self._mode_transition_phase is _ModeTransitionPhase.FADING:
            return 1.0 - self._mode_transition_progress, self._fade_reveal_progress
        if self._mode_transition_phase is _ModeTransitionPhase.REVEALING:
            return 1.0, self._mode_transition_progress
        return 1.0, 1.0

    def _is_mode_transition_active(self) -> bool:
        return self._mode_transition_phase is not _ModeTransitionPhase.IDLE

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(get_theme_manager().tokens.surface))
        self._hit_regions.clear()
        self._weekly_regions.clear()
        self._cumulative_regions.clear()
        self._cell_rects = ()
        self._month_label_positions = ()
        self._rendered_month_labels = ()
        if self._data is None or not self._data.days:
            self._paint_empty(painter)
            return

        geometry = self._grid_geometry()
        self._cell_rects = tuple(
            geometry.cell_rect(column, row)
            for column in range(geometry.columns)
            for row in range(7)
        )
        month_candidates = self._month_positions(geometry)
        self._rendered_month_labels = self._layout_month_labels(
            painter,
            geometry,
            month_candidates,
        )
        self._month_label_positions = tuple(
            (day, rect.x(), rect.width())
            for day, _label, rect in self._rendered_month_labels
        )
        mode = self._rendered_mode
        matrix_opacity, reveal_progress = self._matrix_transition_values()
        if mode is FocusActivityMode.DAILY:
            self._paint_daily(
                painter,
                geometry,
                matrix_opacity,
                reveal_progress,
            )
        elif mode is FocusActivityMode.WEEKLY:
            self._paint_weekly(
                painter,
                geometry,
                matrix_opacity,
                reveal_progress,
            )
        else:
            self._paint_cumulative(
                painter,
                geometry,
                matrix_opacity,
                reveal_progress,
            )
        self._paint_month_labels(painter, geometry)

    def _grid_geometry(self) -> _GridGeometry:
        assert self._data is not None
        leading = self._data.start_day.weekday()
        columns = max(1, (leading + len(self._data.days) + 6) // 7)
        left_margin = 8.0
        right_margin = 8.0
        available_width = max(1.0, self.width() - left_margin - right_margin)
        gap = 2.2 if self.width() >= 640 else 1.2
        cell = min(
            12.5,
            max(2.5, (available_width - gap * (columns - 1)) / columns),
        )
        grid_width = columns * cell + max(0, columns - 1) * gap
        left = left_margin + max(0.0, (available_width - grid_width) / 2)
        return _GridGeometry(left, 4.0, cell, gap, columns)

    def _paint_daily(
        self,
        painter: QPainter,
        geometry: _GridGeometry,
        matrix_opacity: float,
        reveal_progress: float,
    ) -> None:
        assert self._data is not None
        leading = self._data.start_day.weekday()
        for index, value in enumerate(self._data.days):
            logical = leading + index
            column, row = divmod(logical, 7)
            rect = geometry.cell_rect(column, row)
            self._paint_cell(
                painter,
                rect,
                _daily_intensity(value.duration_seconds),
                self._hover_strength((FocusActivityMode.DAILY, index)),
                matrix_opacity
                * _diagonal_reveal_opacity(
                    column,
                    row,
                    geometry.columns,
                    reveal_progress,
                ),
            )
            self._hit_regions.append((rect.adjusted(-1, -1, 1, 1), value))

    def _paint_weekly(
        self,
        painter: QPainter,
        geometry: _GridGeometry,
        matrix_opacity: float,
        reveal_progress: float,
    ) -> None:
        for column in range(geometry.columns):
            value = self._weekly_values[column]
            filled = self._weekly_fill_heights[column]
            hover = self._hover_strength((FocusActivityMode.WEEKLY, column))
            for row in range(7):
                self._paint_cell(
                    painter,
                    geometry.cell_rect(column, row),
                    5 if row >= 7 - filled else 0,
                    hover,
                    matrix_opacity
                    * _diagonal_reveal_opacity(
                        column,
                        row,
                        geometry.columns,
                        reveal_progress,
                    ),
                )
            self._weekly_regions.append((geometry.column_rect(column), value))

    def _paint_cumulative(
        self,
        painter: QPainter,
        geometry: _GridGeometry,
        matrix_opacity: float,
        reveal_progress: float,
    ) -> None:
        for column in range(geometry.columns):
            value = self._cumulative_values[column]
            filled = self._cumulative_fill_heights[column]
            hover = self._hover_strength((FocusActivityMode.CUMULATIVE, column))
            for row in range(7):
                self._paint_cell(
                    painter,
                    geometry.cell_rect(column, row),
                    5 if row >= 7 - filled else 0,
                    hover,
                    matrix_opacity
                    * _diagonal_reveal_opacity(
                        column,
                        row,
                        geometry.columns,
                        reveal_progress,
                    ),
                )
            self._cumulative_regions.append((geometry.column_rect(column), value))

    def _paint_cell(
        self,
        painter: QPainter,
        rect: QRectF,
        level: int,
        hover_strength: float,
        matrix_opacity: float = 1.0,
    ) -> None:
        tokens = get_theme_manager().tokens
        active = level > 0
        fill = QColor(tokens.heatmap_levels[level])
        border = QColor(tokens.border)
        if hover_strength > 0:
            fill_target = QColor(tokens.primary_hover if active else tokens.surface_hover)
            fill = _blend_rgb(fill, fill_target, 0.24 * hover_strength)
            border = _blend_rgb(
                border,
                QColor(tokens.border_strong),
                0.65 * hover_strength,
            )
        surface = QColor(tokens.surface)
        fill = _blend_rgb(surface, fill, matrix_opacity)
        border = _blend_rgb(surface, border, matrix_opacity)
        painter.setPen(QPen(border, 0.75))
        painter.setBrush(fill)
        radius = min(2.5, max(1.0, rect.width() * 0.22))
        painter.drawRoundedRect(rect, radius, radius)

    def _month_positions(self, geometry: _GridGeometry) -> tuple[tuple[date, float, float], ...]:
        assert self._data is not None
        leading = self._data.start_day.weekday()
        positions: list[tuple[date, float, float]] = []
        last_month: tuple[int, int] | None = None
        for index, value in enumerate(self._data.days):
            month_key = (value.day.year, value.day.month)
            if month_key == last_month:
                continue
            if value.day.day <= 7 or last_month is None:
                column = (leading + index) // 7
                positions.append(
                    (
                        value.day,
                        geometry.left + column * geometry.stride,
                        geometry.cell + geometry.gap,
                    )
                )
                last_month = month_key
        return tuple(positions)

    def _paint_month_labels(self, painter: QPainter, geometry: _GridGeometry) -> None:
        del geometry
        painter.setPen(QColor(get_theme_manager().tokens.muted))
        for _day, label, rect in self._rendered_month_labels:
            painter.drawText(
                rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                label,
            )

    def _layout_month_labels(
        self,
        painter: QPainter,
        geometry: _GridGeometry,
        month_positions: tuple[tuple[date, float, float], ...],
    ) -> tuple[tuple[date, str, QRectF], ...]:
        """Lay out localized month labels without allowing adjacent overlap."""
        if not month_positions:
            return ()

        metrics = painter.fontMetrics()
        grid_right = (
            geometry.left
            + max(0, geometry.columns - 1) * geometry.stride
            + geometry.cell
        )
        y = geometry.top + geometry.grid_height + 4
        height = max(18.0, float(metrics.height()))
        candidates: list[tuple[date, str, QRectF]] = []
        for day, anchor_x, _column_width in month_positions:
            label = get_localization().locale.standaloneMonthName(
                day.month,
                QLocale.FormatType.ShortFormat,
            )
            width = float(metrics.horizontalAdvance(label))
            if width <= 0 or width > grid_right - geometry.left:
                continue
            x = min(max(anchor_x, geometry.left), grid_right - width)
            candidates.append((day, label, QRectF(x, y, width, height)))

        minimum_gap = 8.0
        if len(candidates) >= 2:
            leading = candidates[0]
            first_complete = candidates[1]
            if (
                leading[0].day != 1
                and leading[2].right() + minimum_gap
                > first_complete[2].left()
            ):
                candidates.pop(0)
        if len(candidates) <= 1:
            return tuple(candidates)

        # Keep the first complete month and the current month stable.  Months
        # between them are admitted from left to right only when their actual
        # localized text width leaves enough room on both sides.
        final_candidate = candidates[-1]
        accepted = [candidates[0]]
        for candidate in candidates[1:-1]:
            previous_rect = accepted[-1][2]
            rect = candidate[2]
            if previous_rect.right() + minimum_gap > rect.left():
                continue
            if rect.right() + minimum_gap > final_candidate[2].left():
                continue
            accepted.append(candidate)

        while (
            len(accepted) > 1
            and accepted[-1][2].right() + minimum_gap
            > final_candidate[2].left()
        ):
            accepted.pop()
        if accepted[-1][2].right() + minimum_gap <= final_candidate[2].left():
            accepted.append(final_candidate)
        return tuple(accepted)

    def _paint_empty(self, painter: QPainter) -> None:
        painter.setPen(QColor(get_theme_manager().tokens.muted))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, tr("chart.no_data"))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self._keyboard_target = None
        if self._is_mode_transition_active():
            self._callout.hide_immediately()
            super().mouseMoveEvent(event)
            return
        self._update_hover_for_point(event.position().toPoint())
        super().mouseMoveEvent(event)

    def _update_hover_for_point(self, point: QPoint) -> None:
        hover_target: HoverKey | None = None
        if self._mode is FocusActivityMode.DAILY:
            region_index, daily_value = _indexed_region_value(self._hit_regions, point)
            if daily_value is not None:
                hover_target = (FocusActivityMode.DAILY, region_index)
        elif self._mode is FocusActivityMode.WEEKLY:
            region_index, weekly_value = _indexed_region_value(
                self._weekly_regions, point
            )
            if weekly_value is not None:
                hover_target = (FocusActivityMode.WEEKLY, region_index)
        else:
            region_index, cumulative_value = _indexed_region_value(
                self._cumulative_regions, point
            )
            if cumulative_value is not None:
                hover_target = (FocusActivityMode.CUMULATIVE, region_index)
        self._set_hover_target(hover_target)
        detail = self._detail_for_key(hover_target) if hover_target else None
        if detail is None:
            self._callout.hide_animated()
        else:
            target_rect = self._region_rect_for_key(hover_target)
            if target_rect is not None:
                self._callout.show_for(detail, target_rect)

    def _restore_hover_under_cursor(self) -> None:
        if not self.isVisible() or self._is_mode_transition_active():
            return
        position = self.mapFromGlobal(QCursor.pos())
        if self.rect().contains(position):
            self._update_hover_for_point(position)

    def leaveEvent(self, event: QEvent) -> None:
        self._keyboard_target = None
        self._set_hover_target(None)
        self._callout.hide_animated()
        super().leaveEvent(event)

    def hideEvent(self, event: QHideEvent) -> None:
        self._complete_mode_transition()
        self._clear_hover()
        super().hideEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._filtered_window is not None:
            self._filtered_window.removeEventFilter(self)
            self._filtered_window = None
        self._disconnect_scroll_bars()
        self._complete_mode_transition()
        self._clear_hover()
        self._callout.close()
        super().closeEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self._is_mode_transition_active():
            event.accept()
            return
        if self._data is None or not self._data.days:
            super().keyPressEvent(event)
            return
        key = Qt.Key(event.key())
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            event.accept()
            return
        if self._mode is FocusActivityMode.DAILY:
            count = len(self._data.days)
            current_index = (
                self._keyboard_target[1]
                if self._keyboard_target is not None
                and self._keyboard_target[0] is FocusActivityMode.DAILY
                else count - 1
            )
            offsets = {
                Qt.Key.Key_Left: -1,
                Qt.Key.Key_Right: 1,
                Qt.Key.Key_Up: -7,
                Qt.Key.Key_Down: 7,
            }
        else:
            count = len(self._weekly_values)
            current_index = (
                self._keyboard_target[1]
                if self._keyboard_target is not None
                and self._keyboard_target[0] is self._mode
                else count - 1
            )
            offsets = {
                Qt.Key.Key_Left: -1,
                Qt.Key.Key_Right: 1,
            }
        if key in offsets:
            target_index = max(0, min(count - 1, current_index + offsets[key]))
        elif key == Qt.Key.Key_Home:
            target_index = 0
        elif key == Qt.Key.Key_End:
            target_index = count - 1
        else:
            super().keyPressEvent(event)
            return
        target_key = (self._mode, target_index)
        self._keyboard_target = target_key
        self._set_hover_target(target_key)
        if self._region_rect_for_key(target_key) is None:
            self.repaint()
        detail = self._detail_for_key(target_key)
        target_rect = self._region_rect_for_key(target_key)
        if detail is not None and target_rect is not None:
            self._callout.show_for(detail, target_rect)
        event.accept()

    def focusOutEvent(self, event: QFocusEvent) -> None:
        self._keyboard_target = None
        self._set_hover_target(None)
        self._callout.hide_animated()
        super().focusOutEvent(event)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        current_window = self.window()
        if current_window is not self._filtered_window:
            if self._filtered_window is not None:
                self._filtered_window.removeEventFilter(self)
            self._filtered_window = current_window
            current_window.installEventFilter(self)
        if self._callout.parentWidget() is not current_window:
            self._callout.setParent(current_window)
        self._connect_scroll_bars()

    def moveEvent(self, event: QMoveEvent) -> None:
        self._callout.hide_immediately()
        super().moveEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        self._callout.hide_immediately()
        super().resizeEvent(event)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._filtered_window and event.type() in {
            QEvent.Type.Move,
            QEvent.Type.Resize,
            QEvent.Type.WindowStateChange,
            QEvent.Type.Hide,
        }:
            self._callout.hide_immediately()
        return super().eventFilter(watched, event)

    def _set_hover_target(self, target: HoverKey | None) -> None:
        if target == self._hover_target:
            return
        previous = self._hover_target
        self._hover_target = target
        if previous is not None:
            self._animate_hover(previous, 0.0, 150)
        if target is not None:
            self._animate_hover(target, 1.0, 120)

    def _animate_hover(self, key: HoverKey, target: float, duration: int) -> None:
        current = self._hover_strengths.get(key, 0.0)
        old_animation = self._hover_animations.pop(key, None)
        if old_animation is not None:
            old_animation.stop()
            old_animation.deleteLater()
        if abs(current - target) < 0.001:
            if target <= 0:
                self._hover_strengths.pop(key, None)
            self.update()
            return
        animation = QVariantAnimation(self)
        animation.setStartValue(current)
        animation.setEndValue(target)
        animation.setDuration(duration)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        def update_strength(value: object) -> None:
            self._hover_strengths[key] = cast(float, value)
            self.update()

        def finish() -> None:
            if target <= 0:
                self._hover_strengths.pop(key, None)
            else:
                self._hover_strengths[key] = target
            self._hover_animations.pop(key, None)
            animation.deleteLater()
            self.update()

        animation.valueChanged.connect(update_strength)
        animation.finished.connect(finish)
        self._hover_animations[key] = animation
        animation.start()

    def _hover_strength(self, key: HoverKey) -> float:
        return max(0.0, min(1.0, self._hover_strengths.get(key, 0.0)))

    def _clear_hover(self) -> None:
        self._keyboard_target = None
        self._callout.hide_immediately()
        self._hover_target = None
        for animation in tuple(self._hover_animations.values()):
            animation.stop()
            animation.deleteLater()
        self._hover_animations.clear()
        self._hover_strengths.clear()
        self.update()

    def _theme_changed(self, _theme: str | None = None) -> None:
        self._callout.update()
        self._refresh_callout()
        self.update()

    def _connect_scroll_bars(self) -> None:
        if self._scroll_bars:
            return
        ancestor = self.parentWidget()
        while ancestor is not None:
            if isinstance(ancestor, QAbstractScrollArea):
                for scroll_bar in (
                    ancestor.horizontalScrollBar(),
                    ancestor.verticalScrollBar(),
                ):
                    scroll_bar.valueChanged.connect(self._hide_callout_for_scroll)
                    self._scroll_bars.append(scroll_bar)
            ancestor = ancestor.parentWidget()

    def _disconnect_scroll_bars(self) -> None:
        for scroll_bar in self._scroll_bars:
            try:
                scroll_bar.valueChanged.disconnect(self._hide_callout_for_scroll)
            except (RuntimeError, TypeError):
                pass
        self._scroll_bars.clear()

    def _hide_callout_for_scroll(self, _value: int) -> None:
        self._callout.hide_immediately()

    def _refresh_callout(self) -> None:
        if not self._callout.isVisible() or self._hover_target is None:
            return
        detail = self._detail_for_key(self._hover_target)
        target_rect = self._region_rect_for_key(self._hover_target)
        if detail is not None and target_rect is not None:
            self._callout.show_for(detail, target_rect)

    def _region_rect_for_key(self, key: HoverKey | None) -> QRectF | None:
        if key is None:
            return None
        mode, index = key
        regions: Sequence[tuple[QRectF, object]]
        if mode is FocusActivityMode.DAILY:
            regions = self._hit_regions
        elif mode is FocusActivityMode.WEEKLY:
            regions = self._weekly_regions
        else:
            regions = self._cumulative_regions
        if not 0 <= index < len(regions):
            return None
        return regions[index][0]

    def _detail_for_key(self, key: HoverKey) -> str | None:
        mode, index = key
        if mode is FocusActivityMode.DAILY and 0 <= index < len(self._hit_regions):
            return self._daily_tooltip(self._hit_regions[index][1])
        if mode is FocusActivityMode.WEEKLY and 0 <= index < len(self._weekly_regions):
            weekly_value = self._weekly_regions[index][1]
            return tr(
                "heatmap.weekly_tooltip",
                start=format_date(weekly_value.start_day),
                end=format_date(weekly_value.end_day),
                duration=format_compact_duration(weekly_value.duration_seconds),
            )
        if mode is FocusActivityMode.CUMULATIVE and 0 <= index < len(self._cumulative_regions):
            cumulative_value = self._cumulative_regions[index][1]
            return tr(
                "heatmap.cumulative_tooltip",
                date=format_date(cumulative_value.end_day),
                duration=format_compact_duration(cumulative_value.duration_seconds),
            )
        return None

    def _daily_tooltip(self, value: HeatmapDay) -> str:
        if value.session_count:
            key = "heatmap.tooltip_sessions.one" if value.session_count == 1 else "heatmap.tooltip_sessions.other"
            return tr(
                key,
                date=format_date(value.day),
                duration=format_compact_duration(value.duration_seconds),
                count=value.session_count,
            )
        return tr("heatmap.tooltip_empty", date=format_date(value.day))

    def _sync_interaction_mode(self) -> None:
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def _retranslate_ui(self, _language: str | None = None) -> None:
        self.setAccessibleName(tr("dashboard.heatmap_title"))
        self._update_accessible_description()
        self._refresh_callout()
        self.update()

    def _update_accessible_description(self) -> None:
        if self._data is None or not self._data.days:
            self.setAccessibleDescription(tr("chart.no_data"))
            return
        total = sum(value.duration_seconds for value in self._data.days)
        if self._mode is FocusActivityMode.DAILY:
            self.setAccessibleDescription(
                tr(
                    "heatmap.accessible_summary",
                    days=sum(value.duration_seconds > 0 for value in self._data.days),
                    duration=format_compact_duration(total),
                )
            )
        elif self._mode is FocusActivityMode.WEEKLY:
            self.setAccessibleDescription(
                tr(
                    "heatmap.accessible_weekly",
                    weeks=sum(value.duration_seconds > 0 for value in self._weekly_values),
                    duration=format_compact_duration(total),
                )
            )
        else:
            self.setAccessibleDescription(
                tr("heatmap.accessible_cumulative", duration=format_compact_duration(total))
            )


def _aggregate_weeks(days: tuple[HeatmapDay, ...]) -> tuple[WeeklyActivity, ...]:
    if not days:
        return ()
    grouped: list[list[HeatmapDay]] = []
    current_week: date | None = None
    for value in days:
        week_start = value.day - timedelta(days=value.day.weekday())
        if week_start != current_week:
            grouped.append([])
            current_week = week_start
        grouped[-1].append(value)
    return tuple(
        WeeklyActivity(
            start_day=values[0].day,
            end_day=values[-1].day,
            duration_seconds=sum(value.duration_seconds for value in values),
        )
        for values in grouped
    )


def _accumulate_weeks(
    weeks: tuple[WeeklyActivity, ...],
) -> tuple[CumulativeActivity, ...]:
    running = 0.0
    values: list[CumulativeActivity] = []
    for week in weeks:
        running += week.duration_seconds
        values.append(CumulativeActivity(week.start_day, week.end_day, running))
    return tuple(values)


def _relative_fill_heights(values: tuple[float, ...]) -> tuple[int, ...]:
    maximum = max(values, default=0.0)
    if maximum <= 0:
        return (0,) * len(values)
    return tuple(
        0 if value <= 0 else min(7, max(1, ceil(value / maximum * 7)))
        for value in values
    )


def _cumulative_fill_heights(values: tuple[float, ...]) -> tuple[int, ...]:
    final = values[-1] if values else 0.0
    if final <= 0:
        return (0,) * len(values)
    return tuple(
        0 if value <= 0 else min(7, max(1, ceil(value / final * 7)))
        for value in values
    )


_RegionValue = TypeVar("_RegionValue")


def _region_value(
    regions: Sequence[tuple[QRectF, _RegionValue]], point: QPoint
) -> _RegionValue | None:
    return _indexed_region_value(regions, point)[1]


def _indexed_region_value(
    regions: Sequence[tuple[QRectF, _RegionValue]], point: QPoint
) -> tuple[int, _RegionValue | None]:
    for index, (rect, value) in enumerate(regions):
        if rect.contains(point):
            return index, value
    return -1, None


def _blend_rgb(start: QColor, end: QColor, progress: float) -> QColor:
    progress = max(0.0, min(1.0, progress))
    return QColor(
        round(start.red() + (end.red() - start.red()) * progress),
        round(start.green() + (end.green() - start.green()) * progress),
        round(start.blue() + (end.blue() - start.blue()) * progress),
        255,
    )


def _diagonal_reveal_opacity(
    column: int,
    row: int,
    columns: int,
    progress: float,
    *,
    softness: float = 0.08,
) -> float:
    """Reveal a stable matrix through a soft top-left to bottom-right wave."""

    progress = max(0.0, min(1.0, progress))
    if progress <= 0:
        return 0.0
    if progress >= 1:
        return 1.0
    diagonal_extent = max(1, columns - 1 + 6)
    cell_position = (max(0, column) + max(0, row)) / diagonal_extent
    band = max(0.001, softness)
    reveal_head = progress * (1.0 + band)
    strength = max(0.0, min(1.0, (reveal_head - cell_position) / band))
    return strength * strength * (3.0 - 2.0 * strength)


def _daily_intensity(duration_seconds: float) -> int:
    minutes = duration_seconds / 60
    if minutes <= 0:
        return 0
    if minutes <= 30:
        return 1
    if minutes <= 60:
        return 2
    if minutes <= 120:
        return 3
    if minutes <= 240:
        return 4
    return 5


def _relative_intensity(duration_seconds: float, maximum_seconds: float) -> int:
    if duration_seconds <= 0 or maximum_seconds <= 0:
        return 0
    return min(5, max(1, ceil(duration_seconds / maximum_seconds * 5)))


# Kept for compatibility with existing focused tests and integrations.
def _intensity(duration_seconds: float) -> int:
    return _daily_intensity(duration_seconds)
