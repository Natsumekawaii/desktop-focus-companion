"""A lightweight, genuinely rounded menu for desktop companion actions."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import (
    QAction,
    QColor,
    QHideEvent,
    QIcon,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QResizeEvent,
    QShowEvent,
)
from PySide6.QtWidgets import QMenu, QWidget

from app.core.theme import DESIGN, get_theme_manager


class RoundedMenu(QMenu):
    """Render a QMenu on a transparent canvas with real rounded corners.

    ``QMenu`` normally paints an opaque rectangular native surface before its
    stylesheet can apply a border radius.  This subclass keeps QMenu's action,
    keyboard, action, and tray compatibility, while drawing its background and
    centered action content itself.
    """

    _object_name = "roundedContextMenu"
    _minimum_width = 150
    _width_reserve = 60
    _surface_radius = DESIGN.radius_lg
    _item_radius = 10
    _shadow_margin = 10
    _shadow_offset_y = 2
    _icon_size = 16
    _icon_text_gap = 8

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(self._object_name)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setProperty("themeTransitionExcluded", True)
        self.setProperty("themeTransitionTransient", True)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self._pressed_action: QAction | None = None
        self.setMinimumWidth(self._minimum_width)
        get_theme_manager().theme_changed.connect(self._refresh_appearance)
        self._refresh_appearance()

    def sizeHint(self) -> QSize:
        """Return a compact width based on the longest visible action label."""
        base = super().sizeHint()
        metrics = self.fontMetrics()
        longest_text = max(
            (
                metrics.horizontalAdvance(self._display_text(action.text()))
                for action in self.actions()
                if action.isVisible() and not action.isSeparator()
            ),
            default=0,
        )
        width = max(self._minimum_width, longest_text + self._width_reserve)
        return QSize(width, base.height())

    def paintEvent(self, event: QPaintEvent) -> None:
        """Draw the floating surface and one centered icon/text content column."""
        del event
        tokens = get_theme_manager().tokens
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        surface_rect = self._surface_rect()
        shadow_color = QColor(tokens.shadow)
        for spread in range(self._shadow_margin, 0, -1):
            shadow_rect = surface_rect.translated(0, self._shadow_offset_y).adjusted(
                -spread, -spread, spread, spread
            )
            shadow_path = self._rounded_path(
                shadow_rect, self._surface_radius + spread
            )
            shadow_color.setAlpha(
                1 + (self._shadow_margin - spread) // 2
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(shadow_color)
            painter.drawPath(shadow_path)

        surface_path = self._rounded_path(surface_rect, self._surface_radius)
        painter.setPen(QPen(QColor(tokens.border), 1))
        painter.setBrush(QColor(tokens.surface_elevated))
        painter.drawPath(surface_path)
        self._paint_actions(painter)
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() is Qt.MouseButton.LeftButton:
            self._pressed_action = self.actionAt(event.position().toPoint())
            self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        self._pressed_action = None
        self.update()

    def hideEvent(self, event: QHideEvent) -> None:
        self._pressed_action = None
        super().hideEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.clearMask()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.clearMask()

    def _refresh_appearance(self, _theme_name: str | None = None) -> None:
        """Keep the floating surface and action states aligned with the theme."""
        tokens = get_theme_manager().tokens
        self.setStyleSheet(
            f"""
            QMenu#{self._object_name} {{
                background: transparent;
                border: 0;
                padding: 13px 11px 17px 11px;
            }}
            QMenu#{self._object_name}::item {{
                background: transparent;
                color: {tokens.text};
                border: 0;
                border-radius: {self._item_radius}px;
                min-height: 40px;
                padding: 0 8px 0 10px;
            }}
            QMenu#{self._object_name}::item:selected {{
                background: {tokens.primary_soft};
                color: {tokens.text};
            }}
            QMenu#{self._object_name}::item:pressed {{
                background: {tokens.primary_pressed};
                color: {tokens.primary_text};
            }}
            QMenu#{self._object_name}::item:disabled {{
                color: {tokens.disabled};
            }}
            QMenu#{self._object_name}::separator {{
                height: 1px;
                background: {tokens.separator};
                margin: 6px 10px;
            }}
            """
        )
        self.clearMask()
        self.update()

    def _surface_rect(self) -> QRectF:
        return QRectF(self.rect()).adjusted(10.5, 8.5, -10.5, -12.5)

    def _paint_actions(self, painter: QPainter) -> None:
        tokens = get_theme_manager().tokens
        painter.setFont(self.font())
        for action in self.actions():
            geometry = QRectF(self.actionGeometry(action))
            if geometry.isEmpty() or not action.isVisible():
                continue
            if action.isSeparator():
                y = geometry.center().y()
                separator_rect = self._surface_rect().adjusted(10, 0, -10, 0)
                painter.setPen(QPen(QColor(tokens.separator), 1))
                painter.drawLine(
                    int(separator_rect.left()),
                    int(y),
                    int(separator_rect.right()),
                    int(y),
                )
                continue

            item_rect = self._item_rect(action)
            active = action is self.activeAction()
            pressed = action is self._pressed_action and active
            if active:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(
                    QColor(tokens.primary_pressed if pressed else tokens.primary_soft)
                )
                painter.drawRoundedRect(
                    item_rect,
                    self._item_radius,
                    self._item_radius,
                )

            if not action.isEnabled():
                text_color = QColor(tokens.disabled)
                icon_mode = QIcon.Mode.Disabled
            elif pressed:
                text_color = QColor(tokens.primary_text)
                icon_mode = QIcon.Mode.Selected
            else:
                text_color = QColor(tokens.text)
                icon_mode = QIcon.Mode.Normal

            icon_rect, text_rect = self._action_content_layout(action)
            if icon_rect is not None and not action.icon().isNull():
                icon_state = QIcon.State.On if action.isChecked() else QIcon.State.Off
                pixmap = action.icon().pixmap(
                    QSize(self._icon_size, self._icon_size),
                    icon_mode,
                    icon_state,
                )
                painter.drawPixmap(icon_rect.toRect(), pixmap)
            painter.setPen(text_color)
            painter.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self._display_text(action.text()),
            )

    def _item_rect(self, action: QAction) -> QRectF:
        geometry = QRectF(self.actionGeometry(action))
        surface = self._surface_rect()
        left = surface.left() + 2
        right = surface.right() - 2
        return QRectF(left, geometry.top(), max(0.0, right - left), geometry.height())

    def _action_content_layout(
        self,
        action: QAction,
    ) -> tuple[QRectF | None, QRectF]:
        """Return one shared centered icon column and left-aligned text column."""
        metrics = self.fontMetrics()
        longest_text = self._longest_visible_text_width()
        has_icons = any(
            candidate.isVisible()
            and not candidate.isSeparator()
            and not candidate.icon().isNull()
            for candidate in self.actions()
        )
        icon_space = self._icon_size + self._icon_text_gap if has_icons else 0
        block_width = icon_space + longest_text
        item_rect = self._item_rect(action)
        left = self._surface_rect().center().x() - block_width / 2
        icon_rect = (
            QRectF(
                left,
                item_rect.center().y() - self._icon_size / 2,
                self._icon_size,
                self._icon_size,
            )
            if has_icons
            else None
        )
        text_rect = QRectF(
            left + icon_space,
            item_rect.top(),
            max(float(metrics.horizontalAdvance(self._display_text(action.text()))), 1.0),
            item_rect.height(),
        )
        return icon_rect, text_rect

    def _longest_visible_text_width(self) -> float:
        metrics = self.fontMetrics()
        return float(
            max(
                (
                    metrics.horizontalAdvance(self._display_text(action.text()))
                    for action in self.actions()
                    if action.isVisible() and not action.isSeparator()
                ),
                default=0,
            )
        )

    @staticmethod
    def _display_text(text: str) -> str:
        """Measure menu labels without Qt mnemonic marker characters."""
        escaped_ampersand = "\0"
        return (
            text.replace("&&", escaped_ampersand)
            .replace("&", "")
            .replace(escaped_ampersand, "&")
        )

    @staticmethod
    def _rounded_path(rect: QRectF, radius: float) -> QPainterPath:
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        return path
