"""Reusable rounded combo box with a painted chevron and shaped popup."""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QEvent, QModelIndex, QObject, QPointF, QRect, QSize, Qt
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QComboBox,
    QFrame,
    QListView,
    QVBoxLayout,
    QWidget,
)

from app.core.theme import get_theme_manager
from app.ui.anchored_popup import (
    AnimatedAnchoredPopup,
    PopupState,
    scroll_bar_from_wheel,
)


class SelectorDensity(str, Enum):
    """Supported selector heights in the shared design system."""

    COMPACT = "compact"
    LARGE = "large"


def draw_selector_chevron(widget: QWidget, painter: QPainter) -> None:
    """Paint the same antialiased V-shaped affordance on every selector."""

    arrow_rect = QRect(widget.width() - 38, 0, 38, widget.height())
    tokens = get_theme_manager().tokens
    if not widget.isEnabled():
        color = QColor(tokens.disabled)
    elif widget.hasFocus():
        color = QColor(tokens.primary)
    elif widget.underMouse():
        color = QColor(tokens.text_subtle)
    else:
        color = QColor(tokens.muted)
    center = arrow_rect.center()
    expanded = bool(widget.property("popupExpanded"))
    vertical_direction = -1 if expanded else 1
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(
        QPen(
            color,
            2.0,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
    )
    painter.drawLine(
        center.x() - 5,
        center.y() - 2 * vertical_direction,
        center.x(),
        center.y() + 3 * vertical_direction,
    )
    painter.drawLine(
        center.x(),
        center.y() + 3 * vertical_direction,
        center.x() + 5,
        center.y() - 2 * vertical_direction,
    )


def forward_wheel_event(event: QWheelEvent, target: QWidget) -> None:
    """Forward a wheel gesture without letting a selector commit a value."""

    forwarded = QWheelEvent(
        QPointF(target.rect().center()),
        event.globalPosition(),
        event.pixelDelta(),
        event.angleDelta(),
        event.buttons(),
        event.modifiers(),
        event.phase(),
        event.inverted(),
        event.source(),
        event.pointingDevice(),
    )
    QApplication.sendEvent(target, forwarded)
    event.accept()


def forward_closed_selector_wheel(
    owner: QWidget,
    event: QWheelEvent,
) -> None:
    """Keep closed selectors inert while preserving surrounding page scroll."""

    ancestor = owner.parentWidget()
    while ancestor is not None and not isinstance(ancestor, QAbstractScrollArea):
        ancestor = ancestor.parentWidget()
    if not isinstance(ancestor, QAbstractScrollArea):
        event.ignore()
        return
    forward_wheel_event(event, ancestor.viewport())


class _RoundedSelectorPopup(AnimatedAnchoredPopup):
    """Transparent popup host that avoids Qt's opaque combo container."""

    def __init__(self, owner: RoundedComboBox, view: QListView) -> None:
        super().__init__(owner)
        self._combo_owner = owner
        self.setObjectName(owner._popup_container_name)

        self.surface = QFrame(self)
        self.surface.setObjectName(owner._popup_surface_name)
        surface_layout = QVBoxLayout(self.surface)
        surface_layout.setContentsMargins(0, 0, 0, 0)
        view.setParent(self.surface)
        surface_layout.addWidget(view)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.surface)

    def _ideal_size(self) -> QSize:
        count = self._combo_owner.count()
        visible_rows = min(
            max(1, count), max(1, self._combo_owner.maxVisibleItems())
        )
        height = self._combo_owner._popup_height_for_visible_rows(visible_rows)
        return QSize(max(120, self._combo_owner.width()), height)

    def _focus_popup(self) -> None:
        self._combo_owner.view().setFocus(Qt.FocusReason.PopupFocusReason)

    def _handle_wheel(self, watched: QObject, event: QWheelEvent) -> bool:
        del watched
        scroll_bar_from_wheel(self._combo_owner.view().verticalScrollBar(), event)
        return True


class RoundedComboBox(QComboBox):
    """A text selector with a reliable chevron and genuine rounded popup."""

    _popup_surface_name = "roundedSelectorPopupSurface"
    _popup_container_name = "roundedSelectorPopup"
    _popup_view_name = "roundedSelectorPopupView"

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        density: SelectorDensity = SelectorDensity.LARGE,
    ) -> None:
        super().__init__(parent)
        self.setProperty("roundedSelector", True)
        self.setProperty("selectorDensity", density.value)
        self._density = density
        popup_view = self.view()
        if not isinstance(popup_view, QListView):
            popup_view = QListView()
            self.setView(popup_view)
        self._popup_view = popup_view
        self._popup_view.installEventFilter(self)
        self._popup_view.setFrameShape(QFrame.Shape.NoFrame)
        self._popup_view.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self._popup_view.setObjectName(self._popup_view_name)
        self._popup_view.viewport().setAutoFillBackground(False)
        self._popup_view.viewport().setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground, True
        )
        self._popup_container = _RoundedSelectorPopup(self, self._popup_view)
        self._popup_surface = self._popup_container.surface
        self._popup_view.clicked.connect(self._activate_index)

    def showPopup(self) -> None:
        if self._popup_container.popup_state in {
            PopupState.OPENING,
            PopupState.OPEN,
        }:
            return
        current = self.currentIndex()
        if current >= 0:
            index = self.model().index(current, self.modelColumn(), self.rootModelIndex())
            self._popup_view.setCurrentIndex(index)
            self._popup_view.scrollTo(index)
        self._popup_container.show_for_owner()

    def hidePopup(self) -> None:
        # Qt can invoke this virtual method while QComboBox is still being
        # constructed or torn down, before the custom popup exists.
        popup = getattr(self, "_popup_container", None)
        if popup is not None:
            popup.hide_animated()

    def _popup_height_for_visible_rows(self, visible_rows: int) -> int:
        row_height = self.view().sizeHintForRow(0)
        return visible_rows * max(40, row_height) + 12

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self._popup_container.toggle()
            event.accept()
            return
        super().mousePressEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Browse an open popup, but never wheel-change a closed selector."""

        if self._popup_container.is_expanded():
            self._popup_container.handle_wheel_event(self, event)
            return
        forward_closed_selector_wheel(self, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in {
            Qt.Key.Key_Space,
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
        } or (
            event.key() == Qt.Key.Key_Down
            and bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
        ):
            self._popup_container.toggle()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._popup_container.hide_immediately()
        super().closeEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        draw_selector_chevron(self, painter)
        painter.end()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._popup_view and event.type() == QEvent.Type.KeyPress:
            if isinstance(event, QKeyEvent) and event.key() == Qt.Key.Key_Space:
                index = self._popup_view.currentIndex()
                if index.isValid() and bool(
                    self.model().flags(index) & Qt.ItemFlag.ItemIsEnabled
                ):
                    self._activate_index(index)
                return True
            if isinstance(event, QKeyEvent) and event.key() == Qt.Key.Key_Escape:
                self.hidePopup()
                return True
        return super().eventFilter(watched, event)

    def _activate_index(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        flags = self.model().flags(index)
        if not bool(flags & Qt.ItemFlag.ItemIsEnabled):
            return
        self.setCurrentIndex(index.row())
        self.hidePopup()
        self.activated.emit(index.row())


__all__ = [
    "RoundedComboBox",
    "SelectorDensity",
    "draw_selector_chevron",
    "forward_closed_selector_wheel",
    "forward_wheel_event",
]
