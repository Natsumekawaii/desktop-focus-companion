"""Shared animated, rounded information bubbles for every hover surface."""

from __future__ import annotations

from typing import cast

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QRect,
    QRectF,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QHelpEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QAbstractItemView, QApplication, QWidget

from app.core.theme import get_theme_manager


class AnimatedInfoBubble(QWidget):
    """An opaque RGB bubble whose complete painted surface animates briefly."""

    hidden = Signal()

    shadow_margin = 8
    surface_radius = 10.0
    horizontal_padding = 12
    vertical_padding = 8
    show_duration_ms = 100
    hide_duration_ms = 70

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        tooltip_window: bool = False,
        minimum_surface_width: int = 64,
        maximum_surface_width: int = 320,
    ) -> None:
        flags = Qt.WindowType.Widget
        if tooltip_window:
            flags = (
                Qt.WindowType.ToolTip
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.NoDropShadowWindowHint
            )
        super().__init__(parent, flags)
        self._text = ""
        self._minimum_surface_width = minimum_surface_width
        self._maximum_surface_width = maximum_surface_width
        self._visual_opacity = 0.0
        self._vertical_offset = 0.0
        self._target_visible = False
        self._animation = QVariantAnimation(self)
        self._animation.valueChanged.connect(self._update_animation)
        self._animation.finished.connect(self._finish_animation)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setProperty("themeTransitionExcluded", True)
        self.setProperty("themeTransitionTransient", not tooltip_window)
        get_theme_manager().theme_changed.connect(self.update)

    @property
    def text(self) -> str:
        return self._text

    @property
    def animation_progress(self) -> float:
        return self._visual_opacity

    @property
    def vertical_offset(self) -> float:
        return self._vertical_offset

    @property
    def surface_rect(self) -> QRectF:
        return QRectF(self.rect()).adjusted(
            self.shadow_margin,
            self.shadow_margin,
            -self.shadow_margin,
            -self.shadow_margin,
        )

    def set_text(self, text: str) -> None:
        self._text = text
        self._resize_for_text()
        self.update()

    def show_animated(self) -> None:
        if not self._text:
            self.hide_immediately()
            return
        already_appearing = (
            self._target_visible
            and self._animation.state() is QAbstractAnimation.State.Running
        )
        self._target_visible = True
        if not self.isVisible():
            self._visual_opacity = 0.0
            self._vertical_offset = 2.0
            self.show()
        self.raise_()
        if already_appearing:
            self.update()
            return
        if self._visual_opacity >= 0.999:
            self._visual_opacity = 1.0
            self._vertical_offset = 0.0
            self.update()
            return
        self._start_animation(
            self._visual_opacity,
            1.0,
            max(1, round(self.show_duration_ms * (1.0 - self._visual_opacity))),
            QEasingCurve.Type.OutCubic,
        )

    def hide_animated(self) -> None:
        if not self.isVisible():
            return
        if (
            not self._target_visible
            and self._animation.state() is QAbstractAnimation.State.Running
        ):
            return
        self._target_visible = False
        self._vertical_offset = 0.0
        if self._visual_opacity <= 0.001:
            self.hide_immediately()
            return
        self._start_animation(
            self._visual_opacity,
            0.0,
            max(1, round(self.hide_duration_ms * self._visual_opacity)),
            QEasingCurve.Type.InCubic,
        )

    def hide_immediately(self) -> None:
        had_state = self.isVisible() or self._visual_opacity > 0.0
        self._animation.stop()
        self._target_visible = False
        self._visual_opacity = 0.0
        self._vertical_offset = 0.0
        self.hide()
        if had_state:
            self.hidden.emit()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        if self._visual_opacity <= 0.001:
            return
        tokens = get_theme_manager().tokens
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self._visual_opacity)
        painter.translate(0.0, self._vertical_offset)
        surface = self.surface_rect

        shadow = QColor(tokens.shadow)
        for spread in range(6, 0, -1):
            shadow.setAlpha(2 + (6 - spread))
            shadow_rect = surface.translated(0, 2).adjusted(
                -spread,
                -spread,
                spread,
                spread,
            )
            shadow_path = QPainterPath()
            shadow_path.addRoundedRect(
                shadow_rect,
                self.surface_radius + spread,
                self.surface_radius + spread,
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(shadow)
            painter.drawPath(shadow_path)

        painter.setPen(QPen(QColor(tokens.border_strong), 1))
        painter.setBrush(QColor(tokens.surface_elevated))
        painter.drawRoundedRect(surface, self.surface_radius, self.surface_radius)
        text_rect = surface.adjusted(
            self.horizontal_padding,
            self.vertical_padding,
            -self.horizontal_padding,
            -self.vertical_padding,
        )
        painter.setPen(QColor(tokens.text))
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter
            | Qt.TextFlag.TextWordWrap,
            self._text,
        )

    def _resize_for_text(self) -> None:
        metrics = self.fontMetrics()
        lines = self._text.splitlines() or [""]
        natural_width = max(metrics.horizontalAdvance(line) for line in lines)
        maximum_content_width = max(
            40,
            self._maximum_surface_width - 2 * self.horizontal_padding,
        )
        content_width = max(40, min(maximum_content_width, natural_width))
        bounds = metrics.boundingRect(
            QRect(0, 0, content_width, 2000),
            Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap,
            self._text,
        )
        surface_width = max(
            self._minimum_surface_width,
            min(
                self._maximum_surface_width,
                max(content_width, bounds.width()) + 2 * self.horizontal_padding,
            ),
        )
        surface_height = max(metrics.lineSpacing(), bounds.height()) + 2 * self.vertical_padding
        self.resize(
            surface_width + 2 * self.shadow_margin,
            surface_height + 2 * self.shadow_margin,
        )

    def _start_animation(
        self,
        start: float,
        end: float,
        duration_ms: int,
        easing: QEasingCurve.Type,
    ) -> None:
        self._animation.stop()
        self._animation.setStartValue(start)
        self._animation.setEndValue(end)
        self._animation.setDuration(duration_ms)
        self._animation.setEasingCurve(easing)
        self._animation.start()
        self.update()

    def _update_animation(self, value: object) -> None:
        self._visual_opacity = max(0.0, min(1.0, cast(float, value)))
        self._vertical_offset = (
            2.0 * (1.0 - self._visual_opacity) if self._target_visible else 0.0
        )
        self.update()

    def _finish_animation(self) -> None:
        if self._target_visible:
            self._visual_opacity = 1.0
            self._vertical_offset = 0.0
            self.update()
            return
        self.hide_immediately()


class AnimatedToolTipManager(QObject):
    """Application event filter replacing native tooltips with one shared bubble."""

    def __init__(self, application: QApplication) -> None:
        super().__init__(application)
        self._application = application
        self._bubble = AnimatedInfoBubble(tooltip_window=True)
        self._owner: QWidget | None = None
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide_animated)
        self._bubble.hidden.connect(self._bubble_hidden)
        application.installEventFilter(self)

    @property
    def bubble(self) -> AnimatedInfoBubble:
        return self._bubble

    @property
    def owner(self) -> QWidget | None:
        return self._owner

    def show_for(
        self,
        owner: QWidget,
        text: str,
        global_position: QPoint,
        *,
        duration_ms: int | None = None,
    ) -> None:
        if not text or not owner.isVisible():
            self.hide_immediately(owner=owner)
            return
        self._owner = owner
        self._bubble.set_text(text)
        self._position_bubble(global_position)
        self._bubble.show_animated()
        self._hide_timer.start(
            duration_ms
            if duration_ms is not None and duration_ms > 0
            else max(4000, min(12000, 2400 + len(text) * 90))
        )

    def hide_animated(self, *, owner: QWidget | None = None) -> None:
        if owner is not None and owner is not self._owner:
            return
        self._hide_timer.stop()
        self._bubble.hide_animated()

    def hide_immediately(self, *, owner: QWidget | None = None) -> None:
        if owner is not None and owner is not self._owner:
            return
        self._hide_timer.stop()
        self._bubble.hide_immediately()
        self._owner = None

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ToolTip and isinstance(watched, QWidget):
            help_event = cast(QHelpEvent, event)
            owner, text = self._tooltip_target(watched, help_event)
            if text:
                duration = owner.toolTipDuration()
                self.show_for(
                    owner,
                    text,
                    help_event.globalPos(),
                    duration_ms=duration if duration > 0 else None,
                )
                event.accept()
                return True
        if watched is self._owner:
            if event.type() == QEvent.Type.Leave:
                self.hide_animated(owner=self._owner)
            elif event.type() in {
                QEvent.Type.Hide,
                QEvent.Type.Close,
                QEvent.Type.Destroy,
                QEvent.Type.MouseButtonPress,
                QEvent.Type.Wheel,
            }:
                self.hide_immediately(owner=self._owner)
        active_owner = self._owner
        if (
            active_owner is not None
            and isinstance(watched, QWidget)
            and watched.window() is active_owner.window()
            and event.type() in {QEvent.Type.MouseButtonPress, QEvent.Type.Wheel}
        ):
            self.hide_immediately(owner=active_owner)
            return super().eventFilter(watched, event)
        if active_owner is not None and watched is active_owner.window() and event.type() in {
            QEvent.Type.Move,
            QEvent.Type.Resize,
            QEvent.Type.WindowStateChange,
            QEvent.Type.Hide,
            QEvent.Type.Close,
        }:
            self.hide_immediately(owner=active_owner)
        return super().eventFilter(watched, event)

    @staticmethod
    def _tooltip_target(
        watched: QWidget,
        event: QHelpEvent,
    ) -> tuple[QWidget, str]:
        text = watched.toolTip()
        if text:
            return watched, text
        ancestor = watched.parentWidget()
        while ancestor is not None and not isinstance(ancestor, QAbstractItemView):
            ancestor = ancestor.parentWidget()
        if not isinstance(ancestor, QAbstractItemView):
            return watched, ""
        viewport = ancestor.viewport()
        viewport_position = viewport.mapFromGlobal(event.globalPos())
        index = ancestor.indexAt(viewport_position)
        if not index.isValid():
            return viewport, ""
        value = index.data(Qt.ItemDataRole.ToolTipRole)
        return viewport, value if isinstance(value, str) else ""

    def _position_bubble(self, global_position: QPoint) -> None:
        screen = QGuiApplication.screenAt(global_position)
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else QRect()
        desired_x = global_position.x() + 12
        desired_y = global_position.y() + 18
        if not available.isNull():
            if desired_y + self._bubble.height() > available.bottom() + 1:
                desired_y = global_position.y() - self._bubble.height() - 10
            desired_x = max(
                available.left(),
                min(desired_x, available.right() - self._bubble.width() + 1),
            )
            desired_y = max(
                available.top(),
                min(desired_y, available.bottom() - self._bubble.height() + 1),
            )
        self._bubble.move(desired_x, desired_y)

    def _bubble_hidden(self) -> None:
        self._owner = None

    def dispose(self) -> None:
        self._application.removeEventFilter(self)
        self._bubble.close()


_tooltip_manager: AnimatedToolTipManager | None = None


def install_animated_tooltips(application: QApplication) -> AnimatedToolTipManager:
    global _tooltip_manager
    if _tooltip_manager is not None and _tooltip_manager.parent() is application:
        return _tooltip_manager
    if _tooltip_manager is not None:
        _tooltip_manager.dispose()
    _tooltip_manager = AnimatedToolTipManager(application)
    return _tooltip_manager


def get_animated_tooltip_manager() -> AnimatedToolTipManager | None:
    application = QApplication.instance()
    if not isinstance(application, QApplication):
        return None
    return install_animated_tooltips(application)


def show_tooltip(owner: QWidget, text: str, global_position: QPoint) -> None:
    manager = get_animated_tooltip_manager()
    if manager is not None:
        manager.show_for(owner, text, global_position)


def hide_tooltip(owner: QWidget | None = None, *, immediate: bool = False) -> None:
    manager = get_animated_tooltip_manager()
    if manager is None:
        return
    if immediate:
        manager.hide_immediately(owner=owner)
    else:
        manager.hide_animated(owner=owner)


__all__ = [
    "AnimatedInfoBubble",
    "AnimatedToolTipManager",
    "get_animated_tooltip_manager",
    "hide_tooltip",
    "install_animated_tooltips",
    "show_tooltip",
]
