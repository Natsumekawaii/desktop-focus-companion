"""Tests for multi-monitor-safe pet positioning."""

from PySide6.QtCore import QPoint, QRect, QSize

from app.pet.geometry import safe_window_position


def test_valid_position_is_clamped_fully_inside_its_screen() -> None:
    screens = [QRect(0, 0, 1920, 1080), QRect(1920, 0, 1280, 1024)]

    position = safe_window_position(QPoint(3150, 980), QSize(200, 160), screens)

    assert position == QPoint(3000, 864)


def test_offscreen_position_recovers_to_primary_screen() -> None:
    screens = [QRect(0, 0, 1920, 1080)]

    position = safe_window_position(QPoint(9000, 9000), QSize(200, 160), screens)

    assert position == QPoint(1696, 896)


def test_position_supports_negative_monitor_coordinates() -> None:
    screens = [QRect(0, 0, 1920, 1080), QRect(-1280, 0, 1280, 1024)]

    position = safe_window_position(QPoint(-1200, 100), QSize(200, 160), screens)

    assert position == QPoint(-1200, 100)

