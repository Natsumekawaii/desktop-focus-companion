"""One theme-aware line icon language for Desktop Focus Companion surfaces."""

from __future__ import annotations

from enum import Enum
from math import cos, pi, sin

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)

from app.core.theme import get_theme_manager


class IconName(Enum):
    APPEARANCE = "appearance"
    COMPANION = "companion"
    TIMER = "timer"
    DATA = "data"
    ABOUT = "about"
    START = "start"
    RECENT = "recent"
    OVERVIEW = "overview"
    DASHBOARD = "dashboard"
    TIMELINE = "timeline"
    ANALYTICS = "analytics"
    MONTHLY = "monthly"
    FOCUS_ITEMS = "focus_items"
    HISTORY = "history"
    SETTINGS = "settings"
    SHOW_COMPANION = "show_companion"
    EXIT = "exit"


class IconSystem:
    """Render consistent rounded line icons from the active design tokens."""

    @staticmethod
    def icon(name: IconName, size: int = 20) -> QIcon:
        tokens = get_theme_manager().tokens
        icon = QIcon()
        normal = _render(name, size, QColor(tokens.primary))
        disabled = _render(name, size, QColor(tokens.disabled))
        icon.addPixmap(normal, QIcon.Mode.Normal, QIcon.State.Off)
        icon.addPixmap(normal, QIcon.Mode.Active, QIcon.State.Off)
        icon.addPixmap(normal, QIcon.Mode.Selected, QIcon.State.Off)
        icon.addPixmap(disabled, QIcon.Mode.Disabled, QIcon.State.Off)
        return icon


def _render(name: IconName, size: int, color: QColor) -> QPixmap:
    scale = 2
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.setDevicePixelRatio(scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(color, 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    bounds = QRectF(3, 3, size - 6, size - 6)
    center = QPointF(size / 2, size / 2)

    if name is IconName.APPEARANCE:
        painter.drawEllipse(QRectF(center.x() - 3, center.y() - 3, 6, 6))
        for index in range(8):
            angle = index * pi / 4
            painter.drawLine(
                QLineF(
                    center + QPointF(cos(angle) * 5.3, sin(angle) * 5.3),
                    center + QPointF(cos(angle) * 7.5, sin(angle) * 7.5),
                )
            )
    elif name is IconName.COMPANION:
        painter.drawEllipse(QRectF(4, 6, size - 8, size - 9))
        painter.drawLine(QLineF(5, 7, 7, 3.8))
        painter.drawLine(QLineF(7, 3.8, 9, 6))
        painter.drawLine(QLineF(size - 5, 7, size - 7, 3.8))
        painter.drawLine(QLineF(size - 7, 3.8, size - 9, 6))
        painter.drawPoint(QPointF(8, 11))
        painter.drawPoint(QPointF(size - 8, 11))
        painter.drawArc(QRectF(8, 10, size - 16, 6), 200 * 16, 140 * 16)
    elif name in {IconName.TIMER, IconName.RECENT}:
        painter.drawEllipse(bounds)
        painter.drawLine(QLineF(center, QPointF(center.x(), 6.2)))
        painter.drawLine(QLineF(center, QPointF(size - 6.2, center.y() + 2)))
        if name is IconName.RECENT:
            painter.drawArc(bounds.adjusted(-1, -1, 1, 1), 110 * 16, 105 * 16)
    elif name is IconName.DATA:
        painter.drawEllipse(QRectF(4, 3.5, size - 8, 5))
        painter.drawArc(QRectF(4, 8, size - 8, 5), 180 * 16, 180 * 16)
        painter.drawArc(QRectF(4, 12.5, size - 8, 5), 180 * 16, 180 * 16)
        painter.drawLine(QLineF(4, 6, 4, 15))
        painter.drawLine(QLineF(size - 4, 6, size - 4, 15))
    elif name is IconName.ABOUT:
        painter.drawEllipse(bounds)
        painter.drawPoint(QPointF(center.x(), 7))
        painter.drawLine(QLineF(center.x(), 10, center.x(), 15))
    elif name is IconName.START:
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(QPolygonF((QPointF(6, 4), QPointF(size - 4, size / 2), QPointF(6, size - 4))))
    elif name in {IconName.DASHBOARD, IconName.OVERVIEW}:
        for x, y in ((3, 3), (11, 3), (3, 11), (11, 11)):
            painter.drawRoundedRect(QRectF(x, y, 6, 6), 1.5, 1.5)
    elif name is IconName.TIMELINE:
        painter.drawLine(QLineF(6, 4, 6, size - 4))
        for y in (5, 10, 15):
            painter.setBrush(color)
            painter.drawEllipse(QPointF(6, y), 1.4, 1.4)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(QLineF(10, y, size - 3, y))
    elif name is IconName.ANALYTICS:
        painter.drawArc(bounds, 90 * 16, 270 * 16)
        path = QPainterPath(center)
        path.lineTo(center.x(), bounds.top())
        path.arcTo(bounds, 90, -90)
        path.closeSubpath()
        painter.drawPath(path)
    elif name is IconName.MONTHLY:
        painter.drawRoundedRect(QRectF(3.5, 5, size - 7, size - 8), 2, 2)
        painter.drawLine(QLineF(4, 9, size - 4, 9))
        painter.drawLine(QLineF(7, 3, 7, 7))
        painter.drawLine(QLineF(size - 7, 3, size - 7, 7))
    elif name is IconName.FOCUS_ITEMS:
        for y in (5, 10, 15):
            painter.setBrush(color)
            painter.drawEllipse(QPointF(5, y), 1.3, 1.3)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(QLineF(9, y, size - 3, y))
    elif name is IconName.HISTORY:
        painter.drawEllipse(QRectF(3, 3, 10, 10))
        painter.drawLine(QLineF(8, 5, 8, 8))
        painter.drawLine(QLineF(8, 8, 10.5, 9.5))
        painter.drawLine(QLineF(5, 16, size - 3, 16))
        painter.drawLine(QLineF(12, 7, size - 3, 7))
        painter.drawLine(QLineF(13, 11.5, size - 3, 11.5))
    elif name is IconName.SETTINGS:
        painter.drawEllipse(QRectF(center.x() - 3.2, center.y() - 3.2, 6.4, 6.4))
        painter.drawEllipse(QRectF(center.x() - 1, center.y() - 1, 2, 2))
        for index in range(8):
            angle = index * pi / 4
            painter.drawLine(
                QLineF(
                    center + QPointF(cos(angle) * 4.4, sin(angle) * 4.4),
                    center + QPointF(cos(angle) * 7.2, sin(angle) * 7.2),
                )
            )
    elif name is IconName.SHOW_COMPANION:
        path = QPainterPath(QPointF(2.5, center.y()))
        path.cubicTo(6, 4, size - 6, 4, size - 2.5, center.y())
        path.cubicTo(size - 6, size - 4, 6, size - 4, 2.5, center.y())
        painter.drawPath(path)
        painter.drawEllipse(QPointF(center.x(), center.y()), 2.3, 2.3)
    elif name is IconName.EXIT:
        painter.drawRoundedRect(QRectF(3, 3, 9, size - 6), 1, 1)
        painter.drawLine(QLineF(9, center.y(), size - 3, center.y()))
        painter.drawLine(QLineF(size - 3, center.y(), size - 6, center.y() - 3))
        painter.drawLine(QLineF(size - 3, center.y(), size - 6, center.y() + 3))
    painter.end()
    return pixmap
