"""Shared anchored information bubble for point-based trend charts."""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QEvent, QObject, QPointF, QRect
from PySide6.QtWidgets import QAbstractScrollArea, QScrollBar, QWidget

from app.ui.info_bubble import AnimatedInfoBubble


class TrendCalloutPlacement(Enum):
    """Vertical placement selected for the most recent anchor."""

    ABOVE = "above"
    BELOW = "below"


class AnchoredTrendCallout(AnimatedInfoBubble):
    """Mouse-transparent callout fixed to a chart point instead of the cursor."""

    _anchor_gap = 6

    def __init__(self, owner: QWidget) -> None:
        super().__init__(
            owner,
            minimum_surface_width=112,
            maximum_surface_width=300,
        )
        self._owner = owner
        self._anchor = QPointF()
        self._placement = TrendCalloutPlacement.ABOVE
        self._filtered_window: QWidget | None = None
        self._scroll_bars: list[QScrollBar] = []

    @property
    def anchor(self) -> QPointF:
        return QPointF(self._anchor)

    @property
    def placement(self) -> TrendCalloutPlacement:
        return self._placement

    def show_for(self, text: str, anchor: QPointF) -> None:
        """Show the bubble at one stable point in the owner's coordinate system."""
        self._sync_host()
        self.set_text(text)
        self._anchor = QPointF(anchor)

        container = self.parentWidget() or self._owner
        owner_top_left = container.mapFromGlobal(self._owner.mapToGlobal(self._owner.rect().topLeft()))
        available = QRect(owner_top_left, self._owner.size())
        anchor_position = container.mapFromGlobal(
            self._owner.mapToGlobal(anchor.toPoint())
        )

        desired_x = anchor_position.x() - self.width() // 2
        maximum_x = available.right() - self.width() + 1
        desired_x = max(available.left(), min(desired_x, maximum_x))

        above_y = anchor_position.y() - self.height() - self._anchor_gap
        if above_y >= available.top():
            desired_y = above_y
            self._placement = TrendCalloutPlacement.ABOVE
        else:
            desired_y = anchor_position.y() + self._anchor_gap
            maximum_y = available.bottom() - self.height() + 1
            desired_y = min(desired_y, maximum_y)
            desired_y = max(available.top(), desired_y)
            self._placement = TrendCalloutPlacement.BELOW

        self.move(desired_x, desired_y)
        self.show_animated()

    def owner_shown(self) -> None:
        self._sync_host()

    def dispose(self) -> None:
        if self._filtered_window is not None:
            self._filtered_window.removeEventFilter(self)
            self._filtered_window = None
        self._disconnect_scroll_bars()
        self.close()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is getattr(self, "_filtered_window", None) and event.type() in {
            QEvent.Type.Move,
            QEvent.Type.Resize,
            QEvent.Type.WindowStateChange,
            QEvent.Type.Hide,
        }:
            self.hide_immediately()
        return super().eventFilter(watched, event)

    def _sync_host(self) -> None:
        current_window = self._owner.window()
        if current_window is not self._filtered_window:
            if self._filtered_window is not None:
                self._filtered_window.removeEventFilter(self)
            self._filtered_window = current_window
            current_window.installEventFilter(self)
        if self.parentWidget() is not current_window:
            self.setParent(current_window)
        self._connect_scroll_bars()

    def _connect_scroll_bars(self) -> None:
        if self._scroll_bars:
            return
        ancestor = self._owner.parentWidget()
        while ancestor is not None:
            if isinstance(ancestor, QAbstractScrollArea):
                for scroll_bar in (
                    ancestor.horizontalScrollBar(),
                    ancestor.verticalScrollBar(),
                ):
                    scroll_bar.valueChanged.connect(self._hide_for_scroll)
                    self._scroll_bars.append(scroll_bar)
            ancestor = ancestor.parentWidget()

    def _disconnect_scroll_bars(self) -> None:
        for scroll_bar in self._scroll_bars:
            try:
                scroll_bar.valueChanged.disconnect(self._hide_for_scroll)
            except (RuntimeError, TypeError):
                pass
        self._scroll_bars.clear()

    def _hide_for_scroll(self, _value: int) -> None:
        self.hide_immediately()
