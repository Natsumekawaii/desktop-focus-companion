"""Screen-safe positioning helpers independent from the pet window."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QPoint, QRect, QSize


def safe_window_position(
    requested_position: QPoint | None,
    window_size: QSize,
    screen_geometries: Sequence[QRect],
    margin: int = 24,
) -> QPoint:
    """Clamp a window to a visible screen or choose a safe default position."""
    if not screen_geometries:
        return requested_position or QPoint(0, 0)

    if requested_position is not None:
        requested_rect = QRect(requested_position, window_size)
        best_screen = max(
            screen_geometries,
            key=lambda screen: _intersection_area(screen, requested_rect),
        )
        if _intersection_area(best_screen, requested_rect) > 0:
            return _clamp_inside(requested_position, window_size, best_screen)

    primary_screen = screen_geometries[0]
    return QPoint(
        max(primary_screen.left(), primary_screen.right() - window_size.width() - margin + 1),
        max(primary_screen.top(), primary_screen.bottom() - window_size.height() - margin + 1),
    )


def _clamp_inside(position: QPoint, size: QSize, screen: QRect) -> QPoint:
    maximum_x = max(screen.left(), screen.right() - size.width() + 1)
    maximum_y = max(screen.top(), screen.bottom() - size.height() + 1)
    return QPoint(
        max(screen.left(), min(position.x(), maximum_x)),
        max(screen.top(), min(position.y(), maximum_y)),
    )


def _intersection_area(first: QRect, second: QRect) -> int:
    intersection = first.intersected(second)
    return max(0, intersection.width()) * max(0, intersection.height())

