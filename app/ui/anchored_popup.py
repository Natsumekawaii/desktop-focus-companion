"""Shared animated popup behavior for selector-style controls."""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
)
from PySide6.QtGui import (
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QWheelEvent,
    QWindow,
)
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QFrame,
    QScrollBar,
    QWidget,
)


def scroll_bar_from_wheel(scroll_bar: QScrollBar, event: QWheelEvent) -> None:
    """Scroll directly without changing an item view's current selection."""

    pixel_delta = event.pixelDelta().y()
    if pixel_delta:
        distance = -pixel_delta
    else:
        angle_delta = event.angleDelta().y()
        if not angle_delta:
            event.accept()
            return
        step = max(12, scroll_bar.singleStep())
        distance = round(-(angle_delta / 120.0) * step * 3)
    scroll_bar.setValue(scroll_bar.value() + distance)
    event.accept()


class PopupState(str, Enum):
    """Lifecycle states used to make rapid popup toggles deterministic."""

    CLOSED = "closed"
    OPENING = "opening"
    OPEN = "open"
    CLOSING = "closing"


class AnimatedAnchoredPopup(QFrame):
    """A downward-only popup with reversible height animation.

    The window deliberately uses ``Qt.Tool`` instead of ``Qt.Popup``.  Native
    popup mouse grabbing can consume the first click on its owner, which leaves
    custom selector controls needing a second click to close.  Outside-click
    dismissal is handled explicitly here so the owner remains a true one-click
    toggle.
    """

    _gap = 4
    _open_duration_ms = 160
    _close_duration_ms = 120

    def __init__(self, owner: QWidget) -> None:
        super().__init__(
            owner,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self._anchor_widget: QWidget | None = owner
        self._state = PopupState.CLOSED
        self._target_geometry = QRect()
        self._filter_installed = False
        self._anchor_scroll_bars: list[QScrollBar] = []
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setProperty("themeTransitionExcluded", True)
        self.setProperty("themeTransitionTransient", True)

        self._animation = QPropertyAnimation(self, b"geometry", self)
        self._animation.finished.connect(self._animation_finished)

    @property
    def popup_state(self) -> PopupState:
        return self._state

    def is_expanded(self) -> bool:
        return self._state in {PopupState.OPENING, PopupState.OPEN}

    def toggle(self) -> None:
        if self._state in {PopupState.OPENING, PopupState.OPEN}:
            self.hide_animated()
        else:
            self.show_for_owner()

    def show_for_owner(self) -> None:
        self._prepare_to_show()
        target = self._calculate_target_geometry(self._ideal_size())
        if target.height() <= 0:
            return

        self._animation.stop()
        if self.isVisible():
            current_height = max(1, self.height())
            start = QRect(target.x(), target.y(), target.width(), current_height)
        else:
            start = QRect(target.x(), target.y(), target.width(), 1)
            self.setGeometry(start)
            self.show()
        self._target_geometry = target
        self._install_application_filter()
        self._set_state(PopupState.OPENING)
        self.raise_()
        self._focus_popup()
        self._animate(start, target, self._open_duration_ms, QEasingCurve.Type.OutCubic)

    def hide_animated(self) -> None:
        if self._state is PopupState.CLOSED:
            return
        self._animation.stop()
        current = self.geometry()
        collapsed = QRect(current.x(), current.y(), current.width(), 1)
        self._set_state(PopupState.CLOSING)
        self._animate(
            current,
            collapsed,
            self._close_duration_ms,
            QEasingCurve.Type.InCubic,
        )

    def hide_immediately(self) -> None:
        self._animation.stop()
        self.hide()
        self._set_state(PopupState.CLOSED)
        self._remove_application_filter()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        event_type = event.type()
        if event_type == QEvent.Type.ApplicationDeactivate:
            self.hide_immediately()
            return False
        if event_type == QEvent.Type.Wheel and isinstance(event, QWheelEvent):
            if isinstance(watched, QWindow):
                return self._handle_window_wheel(watched, event)
            if self._contains_object(watched) or self._contains_anchor_object(watched):
                return self.handle_wheel_event(watched, event)
            # The popup is a separate top-level window.  Scrolling an owning
            # page moves the field without emitting Move on the field itself,
            # so close synchronously before the page can leave it behind.
            self.hide_immediately()
            return False
        if watched is self._anchor_widget and event_type == QEvent.Type.Destroy:
            self._animation.stop()
            self._remove_application_filter()
            self._anchor_widget = None
            self._state = PopupState.CLOSED
            return False
        if watched is self._anchor_widget and event_type in {
            QEvent.Type.Hide,
            QEvent.Type.Close,
        }:
            self.hide_immediately()
            return False
        if (
            event_type == QEvent.Type.KeyPress
            and isinstance(event, QKeyEvent)
            and event.key() == Qt.Key.Key_Escape
        ):
            self.hide_animated()
            return True
        if event_type == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent):
            global_position = event.globalPosition().toPoint()
            if self.geometry().contains(global_position):
                return False
            owner = self._anchor_widget
            if owner is None:
                return False
            owner_rect = QRect(owner.mapToGlobal(QPoint(0, 0)), owner.size())
            if owner_rect.contains(global_position):
                return False
            self.hide_animated()
        if watched is self._anchor_widget and event_type in {
            QEvent.Type.Move,
            QEvent.Type.Resize,
        }:
            self._reanchor()
            return False
        if self._is_anchor_ancestor(watched) and event_type in {
            QEvent.Type.Move,
            QEvent.Type.Resize,
            QEvent.Type.WindowStateChange,
        }:
            # Moving or resizing an owning window changes the anchor's global
            # position without necessarily delivering a Move event to the
            # child field.  A detached tool window would otherwise remain at
            # the old screen coordinates for the duration of the drag.  Close
            # synchronously so no stale frame is ever painted.
            self.hide_immediately()
        return False

    def handle_wheel_event(self, watched: QObject, event: QWheelEvent) -> bool:
        """Route wheel input received by the anchor or any popup descendant."""

        return self._handle_wheel(watched, event)

    def _handle_window_wheel(self, watched: QWindow, event: QWheelEvent) -> bool:
        """Classify the native top-level event before Qt dispatches to widgets."""

        popup_window = self.windowHandle()
        if popup_window is not None and watched == popup_window:
            return self.handle_wheel_event(self, event)

        anchor = self._anchor_widget
        if anchor is not None:
            anchor_window = anchor.window().windowHandle()
            anchor_rect = QRect(anchor.mapToGlobal(QPoint(0, 0)), anchor.size())
            if watched == anchor_window and anchor_rect.contains(
                event.globalPosition().toPoint()
            ):
                return self.handle_wheel_event(anchor, event)

        # A wheel gesture elsewhere in the owning window must keep its native
        # page-scroll behavior, but the detached popup has to disappear first.
        self.hide_immediately()
        return False

    def _contains_object(self, watched: QObject) -> bool:
        current: QObject | None = watched
        while current is not None:
            if current is self:
                return True
            current = current.parent()
        return False

    def _contains_anchor_object(self, watched: QObject) -> bool:
        anchor = self._anchor_widget
        current: QObject | None = watched
        while current is not None:
            if current is anchor:
                return True
            current = current.parent()
        return False

    def _is_anchor_ancestor(self, watched: QObject) -> bool:
        """Return whether *watched* owns the anchor without matching it."""

        anchor = self._anchor_widget
        current = anchor.parentWidget() if anchor is not None else None
        while current is not None:
            if current is watched:
                return True
            current = current.parentWidget()
        return False

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.end()

    def _ideal_size(self) -> QSize:
        return self.sizeHint()

    def _prepare_to_show(self) -> None:
        """Allow subclasses to synchronize their content before measurement."""

    def _focus_popup(self) -> None:
        self.setFocus(Qt.FocusReason.PopupFocusReason)

    def _handle_wheel(self, watched: QObject, event: QWheelEvent) -> bool:
        del watched, event
        return False

    def _calculate_target_geometry(self, ideal_size: QSize) -> QRect:
        owner = self._anchor_widget
        if owner is None:
            return QRect()
        below = owner.mapToGlobal(QPoint(0, owner.height() + self._gap))
        owner_center = owner.mapToGlobal(owner.rect().center())
        screen = QApplication.screenAt(owner_center) or QApplication.primaryScreen()
        available = screen.availableGeometry()

        width = min(max(1, ideal_size.width()), available.width())
        x = max(available.left(), min(below.x(), available.right() - width + 1))
        available_below = max(1, available.bottom() - below.y() + 1)
        height = min(max(1, ideal_size.height()), available_below)
        return QRect(x, below.y(), width, height)

    def _reanchor(self) -> None:
        if self._state is PopupState.CLOSED:
            return
        target = self._calculate_target_geometry(self._ideal_size())
        self._target_geometry = target
        current_height = min(max(1, self.height()), target.height())
        self.setGeometry(target.x(), target.y(), target.width(), current_height)

    def _animate(
        self,
        start: QRect,
        end: QRect,
        duration: int,
        easing: QEasingCurve.Type,
    ) -> None:
        if start == end:
            self.setGeometry(end)
            self._animation_finished()
            return
        self._animation.setDuration(duration)
        self._animation.setEasingCurve(easing)
        self._animation.setStartValue(start)
        self._animation.setEndValue(end)
        self._animation.start()

    def _animation_finished(self) -> None:
        if self._state is PopupState.OPENING:
            self.setGeometry(self._target_geometry)
            self._set_state(PopupState.OPEN)
            return
        if self._state is PopupState.CLOSING:
            self.hide()
            self._set_state(PopupState.CLOSED)
            self._remove_application_filter()

    def _set_state(self, state: PopupState) -> None:
        self._state = state
        owner = self._anchor_widget
        if owner is not None:
            owner.setProperty("popupExpanded", state is not PopupState.CLOSED)
            owner.update()

    def _install_application_filter(self) -> None:
        if self._filter_installed:
            return
        application = QApplication.instance()
        if application is not None:
            application.installEventFilter(self)
            self._filter_installed = True
        self._connect_anchor_scroll_bars()

    def _remove_application_filter(self) -> None:
        self._disconnect_anchor_scroll_bars()
        if not self._filter_installed:
            return
        application = QApplication.instance()
        if application is not None:
            application.removeEventFilter(self)
        self._filter_installed = False

    def _connect_anchor_scroll_bars(self) -> None:
        self._disconnect_anchor_scroll_bars()
        current = self._anchor_widget.parentWidget() if self._anchor_widget else None
        while current is not None:
            if isinstance(current, QAbstractScrollArea):
                for scroll_bar in (
                    current.horizontalScrollBar(),
                    current.verticalScrollBar(),
                ):
                    if scroll_bar in self._anchor_scroll_bars:
                        continue
                    scroll_bar.valueChanged.connect(self._anchor_page_scrolled)
                    self._anchor_scroll_bars.append(scroll_bar)
            current = current.parentWidget()

    def _disconnect_anchor_scroll_bars(self) -> None:
        for scroll_bar in self._anchor_scroll_bars:
            try:
                scroll_bar.valueChanged.disconnect(self._anchor_page_scrolled)
            except (RuntimeError, TypeError):
                pass
        self._anchor_scroll_bars.clear()

    def _anchor_page_scrolled(self, _value: int) -> None:
        self.hide_immediately()

__all__ = ["AnimatedAnchoredPopup", "PopupState", "scroll_bar_from_wheel"]
