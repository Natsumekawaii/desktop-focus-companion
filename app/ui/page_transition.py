"""Short, interruptible transitions for stacked application pages."""

from __future__ import annotations

from typing import cast

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPointF,
    QRect,
    QRectF,
    Qt,
    QVariantAnimation,
)
from PySide6.QtGui import QHideEvent, QPainter, QPaintEvent, QPixmap, QResizeEvent
from PySide6.QtWidgets import QGraphicsEffect, QStackedWidget, QWidget

from app.core.theme import get_theme_manager
from app.i18n import get_localization


class _PageRevealEffect(QGraphicsEffect):
    """Paint one live widget with transition-only opacity and vertical offset."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._opacity = 1.0
        self._offset_y = 0.0

    @property
    def opacity(self) -> float:
        return self._opacity

    @property
    def offset_y(self) -> float:
        return self._offset_y

    def set_progress(self, progress: float, rise_distance: float) -> None:
        bounded = max(0.0, min(1.0, float(progress)))
        self._opacity = bounded
        self._offset_y = (1.0 - bounded) * rise_distance
        self.update()

    def draw(self, painter: QPainter) -> None:
        painter.save()
        painter.setOpacity(self._opacity)
        painter.translate(QPointF(0.0, self._offset_y))
        self.drawSource(painter)
        painter.restore()

    def boundingRectFor(self, source_rect: QRectF | QRect) -> QRectF:
        return QRectF(source_rect).adjusted(
            0.0, 0.0, 0.0, max(0.0, self._offset_y)
        )


class _OutgoingPageOverlay(QWidget):
    """Mouse-transparent snapshot of the page that is leaving."""

    def __init__(self, parent: QWidget, snapshot: QPixmap) -> None:
        super().__init__(parent)
        self._snapshot = snapshot
        self._opacity = 1.0
        self.setObjectName("pageTransitionOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet("background: transparent; border: 0;")

    @property
    def snapshot(self) -> QPixmap:
        return self._snapshot

    @property
    def opacity(self) -> float:
        return self._opacity

    def set_opacity(self, opacity: float) -> None:
        self._opacity = max(0.0, min(1.0, float(opacity)))
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setOpacity(self._opacity)
        painter.drawPixmap(self.rect(), self._snapshot)
        painter.end()


class AnimatedPageStack(QStackedWidget):
    """A compatible stacked widget with a short page-level visual transition."""

    transition_duration_ms = 160
    transition_rise_distance = 4.0

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._transition_target: QWidget = self
        self._transition_animation = QVariantAnimation(self)
        self._transition_animation.setStartValue(0.0)
        self._transition_animation.setEndValue(1.0)
        self._transition_animation.setDuration(self.transition_duration_ms)
        self._transition_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._transition_animation.valueChanged.connect(self._update_transition)
        self._transition_animation.finished.connect(self.finish_transition)
        self._transition_effect: _PageRevealEffect | None = None
        self._transition_overlay: _OutgoingPageOverlay | None = None
        self._transition_progress = 1.0
        self._transition_target.installEventFilter(self)
        get_theme_manager().theme_changed.connect(self._finish_for_visual_change)
        get_localization().language_changed.connect(self._finish_for_visual_change)

    @property
    def is_transition_active(self) -> bool:
        return self._transition_effect is not None

    @property
    def transition_progress(self) -> float:
        return self._transition_progress

    @property
    def transition_offset_y(self) -> float:
        effect = self._transition_effect
        return effect.offset_y if effect is not None else 0.0

    def set_transition_target(self, widget: QWidget) -> None:
        """Include a stable surrounding region, such as a page title, in transitions."""

        if widget is self._transition_target:
            return
        self.finish_transition()
        self._transition_target.removeEventFilter(self)
        self._transition_target = widget
        self._transition_target.installEventFilter(self)

    def setCurrentIndex(self, index: int) -> None:
        if index == self.currentIndex():
            return
        if not 0 <= index < self.count():
            QStackedWidget.setCurrentIndex(self, index)
            return
        source = self._capture_current_frame() if self._can_animate() else QPixmap()
        self.finish_transition()
        QStackedWidget.setCurrentIndex(self, index)
        if not source.isNull() and self._can_animate():
            self._start_transition(source)

    def setCurrentWidget(self, widget: QWidget) -> None:
        index = self.indexOf(widget)
        if index < 0:
            QStackedWidget.setCurrentWidget(self, widget)
            return
        self.setCurrentIndex(index)

    def finish_transition(self) -> None:
        """Finish immediately on resize, hide, theme, or language changes."""

        self._transition_animation.stop()
        target = self._transition_target
        effect = self._transition_effect
        if effect is not None and target.graphicsEffect() is effect:
            # Qt accepts a null effect to detach it; the PySide stub omits None.
            target.setGraphicsEffect(cast(QGraphicsEffect, None))
        self._transition_effect = None
        overlay = self._transition_overlay
        self._transition_overlay = None
        if overlay is not None:
            overlay.hide()
            overlay.deleteLater()
        self._transition_progress = 1.0
        target.update()

    def hideEvent(self, event: QHideEvent) -> None:
        self.finish_transition()
        super().hideEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        if self.is_transition_active:
            self.finish_transition()
        super().resizeEvent(event)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if (
            watched is self._transition_target
            and self.is_transition_active
            and event.type()
            in {
                QEvent.Type.Resize,
                QEvent.Type.Hide,
                QEvent.Type.Close,
            }
        ):
            self.finish_transition()
        return False

    def _can_animate(self) -> bool:
        target = self._transition_target
        parent = target.parentWidget()
        return (
            self.isVisible()
            and target.isVisible()
            and parent is not None
            and target.width() > 0
            and target.height() > 0
        )

    def _capture_current_frame(self) -> QPixmap:
        target = self._transition_target
        frame = target.grab()
        overlay = self._transition_overlay
        if frame.isNull() or overlay is None or overlay.opacity <= 0.0:
            return frame
        painter = QPainter(frame)
        painter.setOpacity(overlay.opacity)
        painter.drawPixmap(frame.rect(), overlay.snapshot)
        painter.end()
        return frame

    def _start_transition(self, source: QPixmap) -> None:
        target = self._transition_target
        parent = target.parentWidget()
        if parent is None:
            return
        effect = _PageRevealEffect(target)
        effect.set_progress(0.0, self.transition_rise_distance)
        target.setGraphicsEffect(effect)
        overlay = _OutgoingPageOverlay(parent, source)
        overlay.setGeometry(target.geometry())
        overlay.show()
        overlay.raise_()
        self._transition_effect = effect
        self._transition_overlay = overlay
        self._transition_progress = 0.0
        self._transition_animation.stop()
        self._transition_animation.setDuration(self.transition_duration_ms)
        self._transition_animation.start()

    def _update_transition(self, value: object) -> None:
        progress = max(0.0, min(1.0, cast(float, value)))
        self._transition_progress = progress
        effect = self._transition_effect
        if effect is not None:
            effect.set_progress(progress, self.transition_rise_distance)
        overlay = self._transition_overlay
        if overlay is not None:
            overlay.set_opacity(max(0.0, 1.0 - progress / 0.72))

    def _finish_for_visual_change(self, _value: object) -> None:
        self.finish_transition()


__all__ = ["AnimatedPageStack"]
