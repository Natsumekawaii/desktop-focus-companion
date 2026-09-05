"""Reusable content containers and responsive layouts."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.core.theme import DESIGN
from app.ui.component_controls import apply_elevation


class CardFrame(QFrame):
    """A consistently padded semantic card for application content."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        variant: str = "card",
        elevated: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setObjectName(variant)
        card_layout = QVBoxLayout(self)
        card_layout.setContentsMargins(
            DESIGN.space_lg,
            DESIGN.space_md,
            DESIGN.space_lg,
            DESIGN.space_lg,
        )
        card_layout.setSpacing(DESIGN.space_sm)
        self.content_layout = card_layout
        if elevated:
            apply_elevation(self, subtle=variant != "heroCard")


class PageHeader(QWidget):
    """Consistent title, supporting copy, and trailing actions for a page."""

    def __init__(
        self,
        title: str = "",
        subtitle: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(DESIGN.space_lg)

        copy_layout = QVBoxLayout()
        copy_layout.setContentsMargins(0, 0, 0, 0)
        copy_layout.setSpacing(DESIGN.space_xs)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("pageTitle")
        self.title_label.setWordWrap(True)
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("pageSubtitle")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setVisible(bool(subtitle))
        copy_layout.addWidget(self.title_label)
        copy_layout.addWidget(self.subtitle_label)
        root.addLayout(copy_layout, 1)

        self.actions_layout = QHBoxLayout()
        self.actions_layout.setContentsMargins(0, 0, 0, 0)
        self.actions_layout.setSpacing(DESIGN.space_sm)
        root.addLayout(self.actions_layout)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

    def set_subtitle(self, subtitle: str) -> None:
        self.subtitle_label.setText(subtitle)
        self.subtitle_label.setVisible(bool(subtitle))

    def add_action(self, widget: QWidget) -> None:
        self.actions_layout.addWidget(widget)


class SectionSurface(QFrame):
    """Flat section container with optional heading, description, and actions."""

    def __init__(
        self,
        title: str = "",
        description: str = "",
        parent: QWidget | None = None,
        *,
        elevated: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("sectionSurface")
        root = QVBoxLayout(self)
        root.setContentsMargins(
            DESIGN.space_lg,
            DESIGN.space_lg,
            DESIGN.space_lg,
            DESIGN.space_lg,
        )
        root.setSpacing(DESIGN.space_md)

        self.header = QWidget()
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(DESIGN.space_md)
        copy_layout = QVBoxLayout()
        copy_layout.setContentsMargins(0, 0, 0, 0)
        copy_layout.setSpacing(DESIGN.space_xs)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("sectionTitle")
        self.title_label.setWordWrap(True)
        self.description_label = QLabel(description)
        self.description_label.setObjectName("supportingText")
        self.description_label.setWordWrap(True)
        copy_layout.addWidget(self.title_label)
        copy_layout.addWidget(self.description_label)
        header_layout.addLayout(copy_layout, 1)
        self.actions_layout = QHBoxLayout()
        self.actions_layout.setContentsMargins(0, 0, 0, 0)
        self.actions_layout.setSpacing(DESIGN.space_sm)
        header_layout.addLayout(self.actions_layout)
        root.addWidget(self.header)

        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(DESIGN.space_md)
        root.addLayout(self.content_layout)
        self._sync_header_visibility()
        if elevated:
            apply_elevation(self, subtle=True)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)
        self._sync_header_visibility()

    def set_description(self, description: str) -> None:
        self.description_label.setText(description)
        self._sync_header_visibility()

    def add_action(self, widget: QWidget) -> None:
        self.actions_layout.addWidget(widget)
        self._sync_header_visibility()

    def add_widget(self, widget: QWidget, stretch: int = 0) -> None:
        self.content_layout.addWidget(widget, stretch)

    def _sync_header_visibility(self) -> None:
        self.title_label.setVisible(bool(self.title_label.text()))
        self.description_label.setVisible(bool(self.description_label.text()))
        self.header.setVisible(
            bool(self.title_label.text())
            or bool(self.description_label.text())
            or self.actions_layout.count() > 0
        )


class MetricItem(QFrame):
    """One compact labelled value used inside a :class:`MetricStrip`."""

    def __init__(
        self,
        caption: str,
        value: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("metricItem")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(DESIGN.space_md, DESIGN.space_sm, DESIGN.space_md, DESIGN.space_sm)
        layout.setSpacing(DESIGN.space_xs)
        self.caption_label = QLabel(caption)
        self.caption_label.setObjectName("cardCaption")
        self.caption_label.setWordWrap(True)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("metricValue")
        self.value_label.setWordWrap(True)
        layout.addWidget(self.caption_label)
        layout.addWidget(self.value_label)

    def set_caption(self, caption: str) -> None:
        self.caption_label.setText(caption)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


class ResponsiveGrid(QWidget):
    """A small grid that reflows widgets as its available width changes."""

    columns_changed = Signal(int)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        min_item_width: int = 220,
        min_columns: int = 1,
        max_columns: int = 4,
        spacing: int = DESIGN.space_md,
    ) -> None:
        super().__init__(parent)
        self._min_item_width = max(1, min_item_width)
        self._min_columns = max(1, min_columns)
        self._max_columns = max(self._min_columns, max_columns)
        self._spacing = max(0, spacing)
        self._widgets: list[QWidget] = []
        self._column_count = 0
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(self._spacing)
        self._grid.setVerticalSpacing(self._spacing)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    @property
    def column_count(self) -> int:
        return self._column_count

    @property
    def widgets(self) -> tuple[QWidget, ...]:
        return tuple(self._widgets)

    def add_widget(self, widget: QWidget) -> None:
        if widget in self._widgets:
            return
        self._widgets.append(widget)
        self._reflow(force=True)

    def addWidget(self, widget: QWidget) -> None:
        self.add_widget(widget)

    def remove_widget(self, widget: QWidget) -> None:
        if widget not in self._widgets:
            return
        self._widgets.remove(widget)
        self._grid.removeWidget(widget)
        widget.setParent(None)
        self._reflow(force=True)

    def clear(self, *, delete_widgets: bool = False) -> None:
        widgets = tuple(self._widgets)
        self._widgets.clear()
        while self._grid.count():
            self._grid.takeAt(0)
        for widget in widgets:
            widget.setParent(None)
            if delete_widgets:
                widget.deleteLater()
        self._reflow(force=True)

    def set_minimum_item_width(self, width: int) -> None:
        self._min_item_width = max(1, width)
        self._reflow(force=True)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._reflow(event.size().width())

    def _columns_for_width(self, width: int) -> int:
        available = max(0, width)
        calculated = max(
            1,
            (available + self._spacing) // (self._min_item_width + self._spacing),
        )
        return min(self._max_columns, max(self._min_columns, calculated))

    def _reflow(self, width: int | None = None, *, force: bool = False) -> None:
        columns = self._columns_for_width(self.width() if width is None else width)
        if not force and columns == self._column_count:
            return
        while self._grid.count():
            self._grid.takeAt(0)
        for column in range(self._max_columns):
            self._grid.setColumnStretch(column, 1 if column < columns else 0)
        for index, widget in enumerate(self._widgets):
            self._grid.addWidget(widget, index // columns, index % columns)
        changed = columns != self._column_count
        self._column_count = columns
        if changed:
            self.columns_changed.emit(columns)


class MetricStrip(QFrame):
    """Responsive row of compact metrics with deliberately low visual weight."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        max_columns: int = 4,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("metricStrip")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(DESIGN.space_sm, DESIGN.space_xs, DESIGN.space_sm, DESIGN.space_xs)
        self.grid = ResponsiveGrid(
            min_item_width=140,
            max_columns=max_columns,
            spacing=DESIGN.space_xs,
        )
        layout.addWidget(self.grid)
        self.items: list[MetricItem] = []

    def add_metric(self, caption: str, value: str) -> MetricItem:
        item = MetricItem(caption, value)
        self.items.append(item)
        self.grid.add_widget(item)
        return item

    def clear(self) -> None:
        self.items.clear()
        self.grid.clear(delete_widgets=True)


class EmptyState(QFrame):
    """Localizable empty-state presentation with an optional action."""

    def __init__(
        self,
        title: str = "",
        message: str = "",
        parent: QWidget | None = None,
        *,
        icon_text: str = "○",
    ) -> None:
        super().__init__(parent)
        self.setObjectName("emptyState")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            DESIGN.space_xl,
            DESIGN.space_xl,
            DESIGN.space_xl,
            DESIGN.space_xl,
        )
        layout.setSpacing(DESIGN.space_sm)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label = QLabel(icon_text)
        self.icon_label.setObjectName("emptyStateIcon")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("emptyStateTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setWordWrap(True)
        self.message_label = QLabel(message)
        self.message_label.setObjectName("emptyStateMessage")
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message_label.setWordWrap(True)
        self.action_container = QWidget()
        self.action_layout = QHBoxLayout(self.action_container)
        self.action_layout.setContentsMargins(0, DESIGN.space_xs, 0, 0)
        self.action_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.message_label)
        layout.addWidget(self.action_container)
        self.action_container.hide()
        self._sync_visibility()

    def set_content(self, title: str, message: str = "", icon_text: str | None = None) -> None:
        self.title_label.setText(title)
        self.message_label.setText(message)
        if icon_text is not None:
            self.icon_label.setText(icon_text)
        self._sync_visibility()

    def set_action(self, button: QPushButton | None) -> None:
        while self.action_layout.count():
            item = self.action_layout.takeAt(0)
            child = item.widget() if item is not None else None
            if child is not None:
                child.setParent(None)
        if button is not None:
            self.action_layout.addWidget(button)
            self.action_container.show()
        else:
            self.action_container.hide()

    def _sync_visibility(self) -> None:
        self.icon_label.setVisible(bool(self.icon_label.text()))
        self.title_label.setVisible(bool(self.title_label.text()))
        self.message_label.setVisible(bool(self.message_label.text()))
