"""Whole-window theme snapshot transitions."""
from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QEvent,
    QObject,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QPainter, QPaintEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QFileDialog,
    QMenu,
    QMessageBox,
    QWidget,
)


def _snapshot_is_opaque(snapshot: QPixmap) -> bool:
    """Use representative pixels to select the safe backing-store paint mode."""

    if snapshot.isNull():
        return False
    image = snapshot.toImage()
    if image.isNull() or image.width() <= 0 or image.height() <= 0:
        return False
    right = image.width() - 1
    bottom = image.height() - 1
    points = (
        (0, 0),
        (right, 0),
        (0, bottom),
        (right, bottom),
        (right // 2, bottom // 2),
    )
    return all(image.pixelColor(x, y).alpha() == 255 for x, y in points)


class _ThemeSnapshotOverlay(QWidget):
    """Mouse-transparent dual snapshot that never exposes an unpainted window."""

    finished = Signal(object)

    def __init__(self, parent: QWidget, snapshot: QPixmap, duration_ms: int) -> None:
        super().__init__(parent)
        self._source_snapshot = snapshot
        self._target_snapshot: QPixmap | None = None
        self._opacity = 1.0
        self._finished = False
        self._duration_ms = duration_ms
        self.setObjectName("themeTransitionOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(
            Qt.WidgetAttribute.WA_OpaquePaintEvent,
            _snapshot_is_opaque(snapshot),
        )
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet("background: transparent; border: 0;")
        self.setGeometry(parent.rect())
        parent.installEventFilter(self)

        self._animation = QPropertyAnimation(self, b"overlayOpacity", self)
        self._animation.setDuration(duration_ms)
        self._animation.setStartValue(1.0)
        self._animation.setEndValue(0.0)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.finished.connect(self.finish)
        self._deadline_timer = QTimer(self)
        self._deadline_timer.setSingleShot(True)
        self._deadline_timer.timeout.connect(self.finish)

    def start(self) -> None:
        if self._target_snapshot is None:
            self.finish()
            return
        self.show()
        self.raise_()
        self.repaint()
        self._animation.start()
        self._deadline_timer.start(self._duration_ms + 20)

    def capture_target(self) -> bool:
        """Capture the fully themed parent while remaining hidden from the grab."""

        parent = self.parentWidget()
        if parent is None or not parent.isVisible():
            return False
        self.hide()
        target = parent.grab()
        self.show()
        self.raise_()
        if target.isNull():
            return False
        self._target_snapshot = target
        self.setAttribute(
            Qt.WidgetAttribute.WA_OpaquePaintEvent,
            _snapshot_is_opaque(self._source_snapshot)
            and _snapshot_is_opaque(target),
        )
        self.repaint()
        return True

    def current_frame(self) -> QPixmap:
        """Return the exact composited frame used as a rapid-switch source."""

        ratio = max(1.0, self.devicePixelRatioF())
        frame = QPixmap(
            max(1, round(self.width() * ratio)),
            max(1, round(self.height() * ratio)),
        )
        frame.setDevicePixelRatio(ratio)
        frame.fill(Qt.GlobalColor.transparent)
        painter = QPainter(frame)
        self._paint_snapshots(painter, self.rect())
        painter.end()
        return frame

    def finish(self) -> None:
        if self._finished:
            return
        self._finished = True
        self._animation.stop()
        self._deadline_timer.stop()
        parent = self.parentWidget()
        if parent is not None:
            parent.removeEventFilter(self)
        self.hide()
        self.finished.emit(self)
        self.deleteLater()

    def opacity(self) -> float:
        return self._opacity

    def set_opacity(self, value: float) -> None:
        self._opacity = max(0.0, min(1.0, float(value)))
        self.update()

    overlayOpacity = Property(float, opacity, set_opacity)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.parentWidget():
            if event.type() == QEvent.Type.Resize:
                parent = self.parentWidget()
                if parent is not None:
                    self.setGeometry(parent.rect())
                return False
            if event.type() in {
                QEvent.Type.Hide,
                QEvent.Type.Close,
            }:
                self.finish()
        return False

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        if not self.testAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent):
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceOver
            )
        self._paint_snapshots(painter, self.rect())
        painter.end()

    def _paint_snapshots(self, painter: QPainter, target_rect: QRect) -> None:
        if self._target_snapshot is not None:
            painter.setOpacity(1.0)
            painter.drawPixmap(target_rect, self._target_snapshot)
        painter.setOpacity(self._opacity)
        painter.drawPixmap(target_rect, self._source_snapshot)
        painter.setOpacity(1.0)


class _ThemeTransitionCoordinator(QObject):
    """Capture and fade all eligible visible application surfaces together."""

    duration_ms = 220

    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        self._overlays: list[_ThemeSnapshotOverlay] = []

    @property
    def active_overlays(self) -> tuple[_ThemeSnapshotOverlay, ...]:
        return tuple(self._overlays)

    def prepare(self, application: QApplication) -> bool:
        self._dismiss_transient_windows(application)
        candidates = [
            widget
            for widget in application.topLevelWidgets()
            if self._is_eligible(widget)
        ]
        existing_by_parent = {
            overlay.parentWidget(): overlay for overlay in self._overlays
        }
        snapshots = [
            (
                widget,
                existing_by_parent[widget].current_frame()
                if widget in existing_by_parent
                else widget.grab(),
            )
            for widget in candidates
        ]
        self.finish_all()
        for widget, snapshot in snapshots:
            if snapshot.isNull() or not widget.isVisible():
                continue
            overlay = _ThemeSnapshotOverlay(widget, snapshot, self.duration_ms)
            overlay.finished.connect(self._overlay_finished)
            overlay.show()
            overlay.raise_()
            overlay.repaint()
            self._overlays.append(overlay)
        return bool(self._overlays)

    def start(self) -> None:
        for overlay in tuple(self._overlays):
            if overlay.capture_target():
                overlay.start()
            else:
                parent = overlay.parentWidget()
                overlay.finish()
                # A failed target grab must degrade to a fully painted instant
                # switch.  Repaint synchronously before yielding to Windows so
                # the backing store can never expose an intermediate black frame.
                if parent is not None and parent.isVisible():
                    parent.repaint()

    def finish_all(self) -> None:
        for overlay in tuple(self._overlays):
            overlay.finish()
        self._overlays.clear()

    def _overlay_finished(self, value: object) -> None:
        if isinstance(value, _ThemeSnapshotOverlay) and value in self._overlays:
            self._overlays.remove(value)

    @staticmethod
    def _is_eligible(widget: QWidget) -> bool:
        if not widget.isVisible() or bool(widget.property("themeTransitionExcluded")):
            return False
        if isinstance(widget, (QColorDialog, QFileDialog, QMenu, QMessageBox)):
            return False
        return widget.windowType() not in {
            Qt.WindowType.Popup,
            Qt.WindowType.ToolTip,
        }

    @staticmethod
    def _dismiss_transient_windows(application: QApplication) -> None:
        for widget in application.topLevelWidgets():
            if not widget.isVisible() or not bool(
                widget.property("themeTransitionTransient")
            ):
                continue
            hide_immediately = getattr(widget, "hide_immediately", None)
            if callable(hide_immediately):
                hide_immediately()
            else:
                widget.hide()
