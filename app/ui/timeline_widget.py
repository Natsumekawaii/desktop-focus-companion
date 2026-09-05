"""Read-only day-calendar visualization for Focus Sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, tzinfo
from math import ceil, floor

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QSizePolicy, QWidget

from app.core.theme import get_theme_manager
from app.data.models import FocusSession
from app.i18n import format_date, get_localization, tr
from app.timer.formatting import format_compact_duration
from app.ui.info_bubble import hide_tooltip, show_tooltip

RULER_WIDTH = 58.0
HOUR_HEIGHT = 52.0
TOP_MARGIN = 18.0
BOTTOM_MARGIN = 16.0
LANE_GAP = 6.0
TIMELINE_MAX_WIDTH = 720.0
TIMELINE_SIDE_MARGIN = 12.0
BLOCK_COLOR_STRENGTH = 0.68
BLOCK_HOVER_STRENGTH = 0.80
BLOCK_MUTED_STRENGTH = 0.48


@dataclass(slots=True)
class TimelineBlock:
    """A session clipped and positioned within the selected local day."""

    session: FocusSession
    start: datetime
    end: datetime
    lane: int = 0
    lane_count: int = 1
    rect: QRectF = field(default_factory=QRectF)
    hit_rect: QRectF = field(default_factory=QRectF)

    @property
    def duration_seconds(self) -> float:
        return max(60.0, floor((self.end - self.start).total_seconds() / 60) * 60.0)


class DailyTimelineWidget(QWidget):
    """Calendar-style time track with overlap lanes and real-time placement."""

    def __init__(self, local_timezone: tzinfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._local_timezone = local_timezone
        self._selected_day = datetime.now(tz=local_timezone).date()
        self._sessions: tuple[FocusSession, ...] = ()
        self._colors: dict[int, str] = {}
        self._blocks: list[TimelineBlock] = []
        self._visible_start_minutes = 8 * 60
        self._visible_end_minutes = 18 * 60
        self._hovered_index: int | None = None
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName(tr("timeline.title"))
        get_localization().language_changed.connect(self._retranslate_ui)
        get_theme_manager().theme_changed.connect(self.update)

    @property
    def blocks(self) -> tuple[TimelineBlock, ...]:
        return tuple(self._blocks)

    @property
    def visible_minute_range(self) -> tuple[int, int]:
        return self._visible_start_minutes, self._visible_end_minutes

    def set_values(
        self,
        selected_day: date,
        sessions: list[FocusSession] | tuple[FocusSession, ...],
        colors: dict[int, str],
    ) -> None:
        self._selected_day = selected_day
        self._sessions = tuple(sessions)
        self._colors = dict(colors)
        self._blocks = self._build_blocks()
        self._assign_overlap_lanes()
        self._update_visible_range()
        height = self._content_height()
        self.setMinimumHeight(height)
        self.setMaximumHeight(height)
        self._hovered_index = None
        hide_tooltip(self, immediate=True)
        self._update_accessible_description()
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(round(TIMELINE_MAX_WIDTH), self._content_height())

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tokens = get_theme_manager().tokens
        painter.fillRect(self.rect(), QColor(tokens.surface))
        if not self._blocks:
            painter.setPen(QColor(tokens.muted))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                tr("timeline.empty"),
            )
            return

        timeline_rect = self._timeline_rect()
        track_left = timeline_rect.left() + RULER_WIDTH
        track_right = max(track_left + 1.0, timeline_rect.right())
        ruler_font = QFont(self.font())
        ruler_font.setPointSize(8)
        painter.setFont(ruler_font)
        first_hour = ceil(self._visible_start_minutes / 60)
        last_hour = floor(self._visible_end_minutes / 60)
        for hour in range(first_hour, last_hour + 1):
            y = self._minute_to_y(hour * 60)
            painter.setPen(QColor(tokens.chart_grid))
            painter.drawLine(QPointF(track_left, y), QPointF(track_right, y))
            painter.setPen(QColor(tokens.muted))
            painter.drawText(
                QRectF(
                    timeline_rect.left(),
                    y - 10,
                    RULER_WIDTH - 10,
                    20,
                ),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{hour:02d}:00",
            )

        self._layout_block_rects(track_left, track_right)
        for index, block in enumerate(self._blocks):
            base = self._block_background(index)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(base)
            radius = min(8.0, block.rect.height() / 2.0)
            painter.drawRoundedRect(block.rect, radius, radius)
            self._paint_block_text(painter, block, base)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        index = self._block_at(event.position())
        if index != self._hovered_index:
            self._hovered_index = index
            self.update()
        if index is None:
            hide_tooltip(self)
        else:
            block = self._blocks[index]
            details = tr(
                "timeline.tooltip",
                item=block.session.focus_item_name,
                start=block.start.strftime("%H:%M"),
                end=block.end.strftime("%H:%M"),
                duration=format_compact_duration(block.duration_seconds),
            )
            if block.session.note:
                details += f"\n\n{block.session.note}"
            show_tooltip(self, details, event.globalPosition().toPoint())
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._hovered_index = None
        hide_tooltip(self)
        self.update()
        super().leaveEvent(event)

    def _build_blocks(self) -> list[TimelineBlock]:
        day_start = datetime.combine(
            self._selected_day, time.min, tzinfo=self._local_timezone
        )
        day_end = datetime.combine(
            self._selected_day + timedelta(days=1),
            time.min,
            tzinfo=self._local_timezone,
        )
        blocks: list[TimelineBlock] = []
        for session in self._sessions:
            if session.duration_seconds < 60:
                continue
            local_start = session.start_time.astimezone(self._local_timezone)
            local_end = session.end_time.astimezone(self._local_timezone)
            clipped_start = max(local_start, day_start)
            clipped_end = min(local_end, day_end)
            if clipped_end <= clipped_start:
                continue
            blocks.append(TimelineBlock(session, clipped_start, clipped_end))
        return sorted(blocks, key=lambda block: (block.start, block.end, block.session.id))

    def _assign_overlap_lanes(self) -> None:
        group_start = 0
        while group_start < len(self._blocks):
            group_end = group_start + 1
            overlap_end = self._blocks[group_start].end
            while (
                group_end < len(self._blocks)
                and self._blocks[group_end].start < overlap_end
            ):
                overlap_end = max(overlap_end, self._blocks[group_end].end)
                group_end += 1
            lane_ends: list[datetime] = []
            for block in self._blocks[group_start:group_end]:
                lane = next(
                    (
                        index
                        for index, lane_end in enumerate(lane_ends)
                        if lane_end <= block.start
                    ),
                    len(lane_ends),
                )
                if lane == len(lane_ends):
                    lane_ends.append(block.end)
                else:
                    lane_ends[lane] = block.end
                block.lane = lane
            lane_count = max(1, len(lane_ends))
            for block in self._blocks[group_start:group_end]:
                block.lane_count = lane_count
            group_start = group_end

    def _update_visible_range(self) -> None:
        if not self._blocks:
            self._visible_start_minutes = 8 * 60
            self._visible_end_minutes = 18 * 60
            return
        earliest = min(
            self._minute_of_selected_day(block.start) for block in self._blocks
        )
        latest = max(
            self._minute_of_selected_day(block.end) for block in self._blocks
        )
        start = max(0, floor(earliest / 60) * 60)
        end = min(24 * 60, ceil(latest / 60) * 60)
        if end - start < 120:
            missing = 120 - (end - start)
            start = max(0, start - missing // 2)
            end = min(24 * 60, start + 120)
            start = max(0, end - 120)
        self._visible_start_minutes = start
        self._visible_end_minutes = end

    def _content_height(self) -> int:
        minutes = self._visible_end_minutes - self._visible_start_minutes
        return max(170, ceil(TOP_MARGIN + minutes / 60 * HOUR_HEIGHT + BOTTOM_MARGIN))

    def _minute_to_y(self, minute: int) -> float:
        return TOP_MARGIN + (
            minute - self._visible_start_minutes
        ) / 60.0 * HOUR_HEIGHT

    def _timeline_rect(self) -> QRectF:
        """Return the centered bounds shared by ruler, grid, blocks, and hit tests."""

        available_width = max(
            1.0,
            float(self.width()) - TIMELINE_SIDE_MARGIN * 2,
        )
        width = min(TIMELINE_MAX_WIDTH, available_width)
        left = max(TIMELINE_SIDE_MARGIN, (float(self.width()) - width) / 2.0)
        return QRectF(left, 0.0, width, float(self.height()))

    def _minute_of_selected_day(self, value: datetime) -> int:
        if value.date() > self._selected_day:
            return 24 * 60
        return value.hour * 60 + value.minute

    def _layout_block_rects(self, track_left: float, track_right: float) -> None:
        """Lay out truthful fixed-scale blocks without visual collisions."""

        available_width = max(1.0, track_right - track_left - 10.0)
        raw_bounds: list[tuple[float, float]] = []
        desired_heights: list[float] = []
        lower_bounds = [self._minute_to_y(self._visible_start_minutes)] * len(
            self._blocks
        )
        upper_bounds = [self._minute_to_y(self._visible_end_minutes)] * len(
            self._blocks
        )

        for block in self._blocks:
            lane_width = (
                available_width - LANE_GAP * max(0, block.lane_count - 1)
            ) / block.lane_count
            x = track_left + 8.0 + block.lane * (lane_width + LANE_GAP)
            start_y = self._minute_to_y(self._minute_of_selected_day(block.start))
            end_y = self._minute_to_y(self._minute_of_selected_day(block.end))
            raw_height = max(0.0, end_y - start_y)
            desired_height = max(0.5, raw_height - 4.0)
            if raw_height < 10.0:
                desired_height = 6.0
            block.rect = QRectF(x, start_y, lane_width, desired_height)
            raw_bounds.append((start_y, end_y))
            desired_heights.append(desired_height)

        for earlier_index, earlier in enumerate(self._blocks):
            earlier_rect = earlier.rect
            earlier_end_y = raw_bounds[earlier_index][1]
            for later_index in range(earlier_index + 1, len(self._blocks)):
                later = self._blocks[later_index]
                if earlier.end > later.start:
                    continue
                later_rect = later.rect
                horizontal_overlap = min(
                    earlier_rect.right(), later_rect.right()
                ) - max(earlier_rect.left(), later_rect.left())
                if horizontal_overlap <= 0.5:
                    continue
                later_start_y = raw_bounds[later_index][0]
                actual_gap = max(0.0, later_start_y - earlier_end_y)
                visual_gap = min(2.0, actual_gap)
                boundary = (earlier_end_y + later_start_y) / 2.0
                upper_bounds[earlier_index] = min(
                    upper_bounds[earlier_index],
                    boundary - visual_gap / 2.0,
                )
                lower_bounds[later_index] = max(
                    lower_bounds[later_index],
                    boundary + visual_gap / 2.0,
                )

        for index, block in enumerate(self._blocks):
            raw_start, raw_end = raw_bounds[index]
            center_y = (raw_start + raw_end) / 2.0
            lower = lower_bounds[index]
            upper = max(lower, upper_bounds[index])
            available_height = max(0.5, upper - lower)
            height = min(desired_heights[index], available_height)
            top = max(lower, min(center_y - height / 2.0, upper - height))
            block.rect.moveTop(top)
            block.rect.setHeight(height)
            hit_height = max(18.0, height)
            hit_top = max(
                0.0,
                min(
                    block.rect.center().y() - hit_height / 2.0,
                    float(self.height()) - hit_height,
                ),
            )
            block.hit_rect = QRectF(
                block.rect.left(),
                hit_top,
                block.rect.width(),
                hit_height,
            )

    def _block_at(self, position: QPointF) -> int | None:
        candidates = [
            (index, block)
            for index, block in enumerate(self._blocks)
            if block.hit_rect.contains(position)
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda candidate: (
                0 if candidate[1].rect.contains(position) else 1,
                abs(candidate[1].rect.center().y() - position.y()),
                candidate[0],
            ),
        )[0]

    @staticmethod
    def _block_title_rect(block: TimelineBlock) -> QRectF | None:
        if block.rect.height() < 20 or block.rect.width() < 36:
            return None
        return block.rect.adjusted(10, 2, -9, -2)

    def _block_background(self, index: int) -> QColor:
        tokens = get_theme_manager().tokens
        block = self._blocks[index]
        project_color = QColor(
            self._colors.get(block.session.focus_item_id, tokens.primary)
        )
        if self._hovered_index == index:
            color_strength = BLOCK_HOVER_STRENGTH
        elif self._hovered_index is not None:
            color_strength = BLOCK_MUTED_STRENGTH
        else:
            color_strength = BLOCK_COLOR_STRENGTH
        return _blend_opaque(
            QColor(tokens.surface),
            project_color,
            color_strength,
        )

    def _paint_block_text(
        self, painter: QPainter, block: TimelineBlock, background: QColor
    ) -> None:
        title_rect = self._block_title_rect(block)
        if title_rect is None:
            return
        tokens = get_theme_manager().tokens
        text_candidates = (QColor(tokens.text), QColor(tokens.primary_text))
        text_color = max(
            text_candidates,
            key=lambda candidate: _contrast_ratio(candidate, background),
        )
        painter.setPen(text_color)
        title_font = QFont(self.font())
        title_font.setPointSize(9)
        title_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(title_font)
        title = painter.fontMetrics().elidedText(
            block.session.focus_item_name,
            Qt.TextElideMode.ElideRight,
            max(1, round(title_rect.width())),
        )
        painter.drawText(
            title_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            title,
        )

    def _retranslate_ui(self, _language: str | None = None) -> None:
        self.setAccessibleName(tr("timeline.title"))
        self._update_accessible_description()
        self.update()

    def _update_accessible_description(self) -> None:
        if not self._blocks:
            self.setAccessibleDescription(tr("timeline.empty"))
            return
        details = [
            tr(
                "timeline.tooltip",
                item=block.session.focus_item_name,
                start=block.start.strftime("%H:%M"),
                end=block.end.strftime("%H:%M"),
                duration=format_compact_duration(block.duration_seconds),
            ).replace("\n", " ")
            for block in self._blocks
        ]
        self.setAccessibleDescription(
            f"{format_date(self._selected_day)}. " + "; ".join(details)
        )


def _blend_opaque(background: QColor, foreground: QColor, amount: float) -> QColor:
    """Mix two colors without alpha so large timeline blocks paint consistently."""

    progress = max(0.0, min(1.0, amount))
    return QColor(
        round(background.red() + (foreground.red() - background.red()) * progress),
        round(
            background.green()
            + (foreground.green() - background.green()) * progress
        ),
        round(background.blue() + (foreground.blue() - background.blue()) * progress),
    )


def _relative_luminance(color: QColor) -> float:
    def linear(channel: int) -> float:
        value = channel / 255.0
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * linear(color.red())
        + 0.7152 * linear(color.green())
        + 0.0722 * linear(color.blue())
    )


def _contrast_ratio(first: QColor, second: QColor) -> float:
    lighter, darker = sorted(
        (_relative_luminance(first), _relative_luminance(second)),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


__all__ = ["DailyTimelineWidget", "TimelineBlock"]
