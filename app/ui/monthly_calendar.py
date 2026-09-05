"""Theme-aware calendar view for one month of daily Focus totals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import ceil, hypot

from PySide6.QtCore import QDate, QEvent, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from app.core.theme import ThemeTokens, get_theme_manager
from app.i18n import format_date, get_localization, tr
from app.statistics import DailyTotal
from app.ui.info_bubble import hide_tooltip, show_tooltip

CALENDAR_COLUMNS = 7
CELL_GAP = 4.0
ROW_GAP = 6.0
OUTER_MARGIN = 8.0
WEEKDAY_HEADER_HEIGHT = 24.0
CELL_WIDTH_SCALE = 0.75
MIN_CELL_WIDTH = 50.0
MAX_CELL_WIDTH = 80.0
MIN_CELL_HEIGHT = 50.0
MAX_CELL_HEIGHT = 72.0
CELL_ASPECT_RATIO = 0.90
DATE_FONT_SIZE = 12


@dataclass(frozen=True, slots=True)
class MonthlyCalendarCell:
    """Painted geometry retained for hover behavior and deterministic tests."""

    value: DailyTotal
    row: int
    column: int
    rect: QRectF


class MonthlyCalendarWidget(QWidget):
    """Show daily Focus duration as a Monday-first month grid, never as bars."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._values: tuple[DailyTotal, ...] = ()
        self._cells: tuple[MonthlyCalendarCell, ...] = ()
        self._hovered_day: date | None = None
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(self.heightForWidth(640))
        get_localization().language_changed.connect(self._retranslate_ui)
        get_theme_manager().theme_changed.connect(self.update)
        self._retranslate_ui()

    @property
    def values(self) -> tuple[DailyTotal, ...]:
        return self._values

    @property
    def cells(self) -> tuple[MonthlyCalendarCell, ...]:
        return self._cells

    def set_values(self, values: tuple[DailyTotal, ...]) -> None:
        self._values = tuple(sorted(values, key=lambda value: value.day))
        self._hovered_day = None
        hide_tooltip(self, immediate=True)
        self.setMinimumHeight(self.heightForWidth(640))
        self.updateGeometry()
        self._update_accessible_metadata()
        self.update()

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        _, cell_height = _calendar_cell_dimensions(width)
        rows = self._row_count()
        return ceil(
            OUTER_MARGIN * 2
            + WEEKDAY_HEADER_HEIGHT
            + CELL_GAP
            + rows * cell_height
            + max(0, rows - 1) * ROW_GAP
        )

    def sizeHint(self) -> QSize:
        width = 720
        return QSize(width, self.heightForWidth(width))

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tokens = get_theme_manager().tokens
        painter.fillRect(self.rect(), QColor(tokens.surface))
        if not self._values:
            self._cells = ()
            painter.setPen(QColor(tokens.muted))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, tr("chart.no_data"))
            return

        content = QRectF(self.rect()).adjusted(
            OUTER_MARGIN,
            OUTER_MARGIN,
            -OUTER_MARGIN,
            -OUTER_MARGIN,
        )
        column_slot_width = max(
            1.0,
            (content.width() - CELL_GAP * (CALENDAR_COLUMNS - 1))
            / CALENDAR_COLUMNS,
        )
        cell_width = _calendar_cell_width(column_slot_width)
        target_cell_height = max(
            MIN_CELL_HEIGHT,
            min(MAX_CELL_HEIGHT, cell_width * CELL_ASPECT_RATIO),
        )
        rows = self._row_count()
        grid_top = content.top() + WEEKDAY_HEADER_HEIGHT + CELL_GAP
        available_grid_height = max(1.0, content.bottom() - grid_top)
        cell_height = max(
            1.0,
            min(
                target_cell_height,
                (available_grid_height - ROW_GAP * max(0, rows - 1)) / rows,
            ),
        )

        self._paint_weekday_header(
            painter,
            content,
            column_slot_width,
            tokens.muted,
        )
        self._cells = self._calendar_cells(
            content.left(),
            grid_top,
            column_slot_width,
            cell_width,
            cell_height,
        )
        for cell in self._cells:
            active = cell.value.duration_seconds > 0
            hovered = cell.value.day == self._hovered_day
            today = cell.value.day == QDate.currentDate().toPython()
            fill, text_color = _calendar_cell_colors(
                cell.value.duration_seconds,
                tokens,
            )
            gradient_stops = (
                _calendar_activity_gradient_stops(tokens, hovered=hovered)
                if active
                else None
            )
            if hovered:
                border = QColor(tokens.border_strong)
                border_width = 1.1
            else:
                border = QColor(tokens.separator)
                border_width = 0.8
            painter.setPen(QPen(border, border_width, Qt.PenStyle.SolidLine))
            if gradient_stops is None:
                painter.setBrush(fill)
            else:
                gradient = QRadialGradient(
                    cell.rect.center(),
                    hypot(cell.rect.width(), cell.rect.height()) / 2,
                )
                gradient.setColorAt(0.0, gradient_stops[0])
                gradient.setColorAt(0.58, gradient_stops[1])
                gradient.setColorAt(1.0, gradient_stops[2])
                painter.setBrush(QBrush(gradient))
            painter.drawRoundedRect(cell.rect, 6, 6)

            date_rect, duration_rect = _cell_text_rects(cell.rect)
            date_font = QFont(self.font())
            date_font.setPointSize(DATE_FONT_SIZE)
            date_font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(date_font)
            painter.setPen(text_color)
            painter.drawText(
                date_rect,
                Qt.AlignmentFlag.AlignCenter,
                str(cell.value.day.day),
            )

            if today:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(text_color if active else QColor(tokens.primary))
                painter.drawEllipse(
                    QPointF(cell.rect.right() - 9, cell.rect.top() + 9),
                    2.5,
                    2.5,
                )

            if active:
                duration_font = QFont(self.font())
                duration_font.setPointSize(
                    _duration_font_size(cell.rect.height(), cell.rect.width())
                )
                duration_font.setWeight(QFont.Weight.DemiBold)
                painter.setFont(duration_font)
                # Drawing the today marker temporarily disables the pen.  Set
                # it again so an active selected/today cell never loses its
                # duration label.
                painter.setPen(text_color)
                duration = _format_calendar_duration(cell.value.duration_seconds)
                painter.drawText(
                    duration_rect,
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                    duration,
                )

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        cell = next(
            (candidate for candidate in self._cells if candidate.rect.contains(event.position())),
            None,
        )
        hovered_day = cell.value.day if cell is not None else None
        if hovered_day != self._hovered_day:
            self._hovered_day = hovered_day
            self.update()
        if cell is None:
            hide_tooltip(self)
        else:
            show_tooltip(
                self,
                tr(
                    "calendar.day_tooltip",
                    date=format_date(cell.value.day),
                    duration=_format_calendar_duration(cell.value.duration_seconds),
                ),
                event.globalPosition().toPoint(),
            )
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._hovered_day = None
        hide_tooltip(self)
        self.update()
        super().leaveEvent(event)

    def _row_count(self) -> int:
        if not self._values:
            return 5
        first_day = self._values[0].day
        last_day = self._values[-1].day
        occupied_cells = first_day.weekday() + (last_day - first_day).days + 1
        return max(1, ceil(occupied_cells / CALENDAR_COLUMNS))

    def _calendar_cells(
        self,
        left: float,
        top: float,
        column_slot_width: float,
        cell_width: float,
        cell_height: float,
    ) -> tuple[MonthlyCalendarCell, ...]:
        if not self._values:
            return ()
        first_day = self._values[0].day
        cells: list[MonthlyCalendarCell] = []
        for value in self._values:
            cell_index = first_day.weekday() + (value.day - first_day).days
            row, column = divmod(cell_index, CALENDAR_COLUMNS)
            cells.append(
                MonthlyCalendarCell(
                    value=value,
                    row=row,
                    column=column,
                    rect=QRectF(
                        _calendar_column_center(left, column_slot_width, column)
                        - cell_width / 2,
                        top + row * (cell_height + ROW_GAP),
                        cell_width,
                        cell_height,
                    ),
                )
            )
        return tuple(cells)

    def _paint_weekday_header(
        self,
        painter: QPainter,
        content: QRectF,
        column_slot_width: float,
        color: str,
    ) -> None:
        header_font = QFont(self.font())
        header_font.setPointSize(8)
        header_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(header_font)
        painter.setPen(QColor(color))
        locale = get_localization().locale
        for column, day_number in enumerate(range(1, 8)):
            rect = QRectF(
                content.left() + column * (column_slot_width + CELL_GAP),
                content.top(),
                column_slot_width,
                WEEKDAY_HEADER_HEIGHT,
            )
            painter.drawText(
                rect,
                Qt.AlignmentFlag.AlignCenter,
                locale.dayName(day_number, locale.FormatType.ShortFormat),
            )

    def _retranslate_ui(self, _language: str | None = None) -> None:
        self.setAccessibleName(tr("dashboard.daily_study_time"))
        self._update_accessible_metadata()
        self.update()

    def _update_accessible_metadata(self) -> None:
        active_values = [value for value in self._values if value.duration_seconds > 0]
        if not active_values:
            self.setAccessibleDescription(tr("chart.no_data"))
            return
        details = [
            tr(
                "calendar.day_tooltip",
                date=format_date(value.day),
                duration=_format_calendar_duration(value.duration_seconds),
            )
            for value in active_values
        ]
        self.setAccessibleDescription("; ".join(details))


def _duration_font_size(
    cell_height: float,
    cell_width: float | None = None,
) -> int:
    if cell_width is not None and cell_width < 56:
        return 8
    if cell_height >= 72:
        return 12
    if cell_height >= 60:
        return 11
    return 9


def _calendar_cell_dimensions(widget_width: float) -> tuple[float, float]:
    content_width = max(1.0, widget_width - OUTER_MARGIN * 2)
    column_slot_width = max(
        1.0,
        (content_width - CELL_GAP * (CALENDAR_COLUMNS - 1)) / CALENDAR_COLUMNS,
    )
    cell_width = _calendar_cell_width(column_slot_width)
    cell_height = max(
        MIN_CELL_HEIGHT,
        min(MAX_CELL_HEIGHT, cell_width * CELL_ASPECT_RATIO),
    )
    return cell_width, cell_height


def _calendar_cell_width(column_slot_width: float) -> float:
    preferred_width = max(MIN_CELL_WIDTH, column_slot_width * CELL_WIDTH_SCALE)
    return max(1.0, min(column_slot_width, MAX_CELL_WIDTH, preferred_width))


def _calendar_column_center(
    left: float,
    column_slot_width: float,
    column: int,
) -> float:
    return (
        left
        + column * (column_slot_width + CELL_GAP)
        + column_slot_width / 2
    )


def _cell_text_rects(cell_rect: QRectF) -> tuple[QRectF, QRectF]:
    """Return a stable centered two-line stack for date and duration."""
    content = cell_rect.adjusted(2, 7, -2, -7)
    line_height = min(24.0, content.height() / 2)
    stack_height = line_height * 2
    stack_top = content.center().y() - stack_height / 2
    date_rect = QRectF(content.left(), stack_top, content.width(), line_height)
    duration_rect = QRectF(
        content.left(),
        stack_top + line_height,
        content.width(),
        line_height,
    )
    return date_rect, duration_rect


def _duration_text_rect(cell_rect: QRectF) -> QRectF:
    """Compatibility helper returning the second line of the text stack."""
    return _cell_text_rects(cell_rect)[1]


def _format_calendar_duration(seconds: float) -> str:
    total_minutes = max(0, round(seconds / 60))
    hours, minutes = divmod(total_minutes, 60)
    if hours and minutes:
        return f"{hours}h {minutes}min"
    if hours:
        return f"{hours}h"
    return f"{minutes}min"


def _calendar_cell_colors(
    duration_seconds: float,
    tokens: ThemeTokens,
) -> tuple[QColor, QColor]:
    """Return one themed representative fill and a legible text color."""
    active = duration_seconds > 0
    if not active:
        return QColor(tokens.heatmap_levels[0]), QColor(tokens.muted)
    gradient_stops = _calendar_activity_gradient_stops(tokens)
    hover_stops = _calendar_activity_gradient_stops(tokens, hovered=True)
    candidates = (
        QColor(tokens.text),
        QColor(tokens.primary_text),
        QColor("#111111"),
        QColor("#ffffff"),
    )
    text = max(
        candidates,
        key=lambda candidate: min(
            _contrast_ratio(stop, candidate)
            for stop in (*gradient_stops, *hover_stops)
        ),
    )
    return gradient_stops[1], text


def _calendar_activity_gradient_stops(
    tokens: ThemeTokens,
    *,
    hovered: bool = False,
) -> tuple[QColor, QColor, QColor]:
    """Build one pale, centered, duration-independent activity gradient."""
    canvas = QColor(tokens.canvas)
    if canvas.lightnessF() < 0.35:
        primary = QColor(tokens.primary)
        surface_weight = 0.42 if primary.lightnessF() > 0.75 else 0.55
        base = _mix_colors(primary, QColor(tokens.surface_alt), surface_weight)
    else:
        base = _mix_colors(QColor(tokens.primary), QColor("#ffffff"), 0.55)
    center = _mix_colors(base, QColor("#ffffff"), 0.12)
    middle = _mix_colors(base, QColor("#ffffff"), 0.05)
    edge = base.darker(104)
    stops = (center, middle, edge)
    if hovered:
        return (
            stops[0].lighter(103),
            stops[1].lighter(103),
            stops[2].lighter(103),
        )
    return stops


def _mix_colors(first: QColor, second: QColor, second_weight: float) -> QColor:
    """Blend two opaque colors in sRGB space."""
    weight = max(0.0, min(1.0, second_weight))
    return QColor(
        round(first.red() * (1.0 - weight) + second.red() * weight),
        round(first.green() * (1.0 - weight) + second.green() * weight),
        round(first.blue() * (1.0 - weight) + second.blue() * weight),
    )


def _contrast_ratio(first: QColor, second: QColor) -> float:
    """Calculate the WCAG contrast ratio for two opaque colors."""
    lighter, darker = sorted(
        (_relative_luminance(first), _relative_luminance(second)),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


def _relative_luminance(color: QColor) -> float:
    channels = (color.redF(), color.greenF(), color.blueF())
    linear = tuple(
        channel / 12.92
        if channel <= 0.04045
        else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    )
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
