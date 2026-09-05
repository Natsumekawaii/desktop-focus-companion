"""Transparent window for a static, draggable desktop pet image."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QContextMenuEvent, QGuiApplication, QMouseEvent, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from app.i18n import get_localization, tr
from app.pet.geometry import safe_window_position

BASE_PET_LONG_EDGE = 192


class PetWindow(QWidget):
    """Display one static image and support only resize, drag, and window placement."""

    position_changed = Signal(int, int)
    drag_moved = Signal(int, int)
    context_menu_requested = Signal(QPoint)
    focus_panel_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._source_pixmap = QPixmap()
        self._drag_offset: QPoint | None = None
        self._drag_origin: QPoint | None = None
        self._press_global_position: QPoint | None = None
        self._is_dragging = False
        self._size_percent = 100

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setProperty("themeTransitionExcluded", True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        self._image_label = QLabel(self)
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._image_label.setStyleSheet("background: transparent;")
        get_localization().language_changed.connect(self._retranslate_ui)
        self._retranslate_ui()

    def _retranslate_ui(self, _language: str | None = None) -> None:
        self.setWindowTitle(tr("app.name"))
        self.setAccessibleName(tr("companion.accessible_name"))

    def set_pet_asset(self, path: Path, size_percent: int) -> None:
        """Load and display a validated static image."""
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            raise ValueError(tr("error.pet_render", name=path.name))
        self.set_pet_image(pixmap, size_percent)

    def set_pet_image(self, pixmap: QPixmap, size_percent: int) -> None:
        """Render a source image at a quality-scaled, aspect-safe size."""
        if pixmap.isNull():
            raise ValueError(tr("error.pet_render", name=tr("common.no_value")))
        self._source_pixmap = pixmap
        self.set_pet_size(size_percent)

    def set_pet_size(self, size_percent: int) -> None:
        """Re-render the static source image for a display percentage."""
        self._size_percent = size_percent
        if self._source_pixmap.isNull():
            return

        target_long_edge = max(1, round(BASE_PET_LONG_EDGE * size_percent / 100))
        if self._source_pixmap.width() >= self._source_pixmap.height():
            scaled = self._source_pixmap.scaledToWidth(
                target_long_edge, Qt.TransformationMode.SmoothTransformation
            )
        else:
            scaled = self._source_pixmap.scaledToHeight(
                target_long_edge, Qt.TransformationMode.SmoothTransformation
            )
        self._image_label.setPixmap(scaled)
        self._image_label.setFixedSize(scaled.size())
        self.setFixedSize(scaled.size())
        self._image_label.move(0, 0)

    def move_to_safe_position(self, x: int | None, y: int | None) -> QPoint:
        """Restore a saved position while guaranteeing screen visibility."""
        requested_position = QPoint(x, y) if x is not None and y is not None else None
        screen_geometries = [screen.availableGeometry() for screen in QGuiApplication.screens()]
        position = safe_window_position(requested_position, self.size(), screen_geometries)
        self.move(position)
        return position

    def set_always_on_top(self, enabled: bool) -> None:
        """Update the top-most flag while preserving visibility and position."""
        was_visible = self.isVisible()
        flags = self.windowFlags()
        if enabled:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        if was_visible:
            self.show()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """Ask the integration layer to show the shared application menu."""
        self.context_menu_requested.emit(event.globalPos())
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._drag_origin = self.pos()
            self._press_global_position = event.globalPosition().toPoint()
            self._is_dragging = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            current_global = event.globalPosition().toPoint()
            if not self._is_dragging:
                if self._press_global_position is None:
                    return
                distance = (current_global - self._press_global_position).manhattanLength()
                if distance < QApplication.startDragDistance():
                    event.accept()
                    return
                self._is_dragging = True
            self.move(current_global - self._drag_offset)
            self.drag_moved.emit(self.x(), self.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_offset is not None:
            was_dragging = self._is_dragging
            moved = was_dragging and self._drag_origin is not None and self.pos() != self._drag_origin
            self._drag_offset = None
            self._drag_origin = None
            self._press_global_position = None
            self._is_dragging = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            if moved:
                self.position_changed.emit(self.x(), self.y())
            if not was_dragging:
                self.focus_panel_requested.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def commit_position(self) -> None:
        """Persist a linked drag that was initiated by the Focus Panel."""

        self.position_changed.emit(self.x(), self.y())
