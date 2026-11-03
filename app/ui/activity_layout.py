"""Pure Focus Activity layout, aggregation and hit-testing helpers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from math import ceil
from typing import TypeAlias, TypeVar

from PySide6.QtCore import QPoint, QRectF
from PySide6.QtGui import QColor

from app.statistics import HeatmapDay


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
        0 if value <= 0 else min(7, max(1, ceil(value / final * 7))) for value in values
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
