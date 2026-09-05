"""Private widgets shared by the responsive Dashboard pages."""

from __future__ import annotations

from enum import IntEnum

from PySide6.QtCore import (
    QEvent,
    QModelIndex,
    QPersistentModelIndex,
    QRectF,
    Qt,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.theme import get_theme_manager
from app.ui.components import SegmentedControl
from app.ui.page_transition import AnimatedPageStack


class SessionTableRole(IntEnum):
    """Visual and interaction role for dashboard session tables."""

    READ_ONLY = 0
    ACTIONABLE = 1


class SessionTableWidget(QTableWidget):
    """Table with stable whole-row hover state for custom rounded painting."""

    def __init__(self, rows: int, columns: int) -> None:
        super().__init__(rows, columns)
        self._hovered_row = -1
        self.setMouseTracking(True)

    @property
    def hovered_row(self) -> int:
        return self._hovered_row

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        row = self.rowAt(event.position().toPoint().y())
        if row != self._hovered_row:
            self._hovered_row = row
            self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        if self._hovered_row != -1:
            self._hovered_row = -1
            self.viewport().update()
        super().leaveEvent(event)

    def refresh_theme(self, _theme_name: str) -> None:
        self.viewport().update()


class SessionTableDelegate(QStyledItemDelegate):
    """Paint one calm, rounded visual surface across every table row."""

    _horizontal_inset = 6
    _vertical_inset = 3
    _radius = 10

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        table = self.parent()
        if not isinstance(table, SessionTableWidget):
            super().paint(painter, option, index)
            return

        selected = table.selectionModel().isRowSelected(index.row(), QModelIndex())
        hovered = table.hovered_row == index.row()
        tokens = get_theme_manager().tokens
        row_rect = self._row_rect(table, option)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setClipRect(option.rect)
        path = QPainterPath()
        path.addRoundedRect(row_rect, self._radius, self._radius)
        if selected:
            painter.fillPath(path, QColor(tokens.primary_soft))
            painter.setPen(QColor(tokens.focus_ring))
            painter.drawPath(path)
        elif hovered:
            painter.fillPath(path, QColor(tokens.surface_hover))
        else:
            painter.setPen(QColor(tokens.separator))
            painter.drawLine(row_rect.bottomLeft(), row_rect.bottomRight())
        painter.restore()

        content_option = QStyleOptionViewItem(option)
        content_option.state &= ~(
            QStyle.StateFlag.State_Selected
            | QStyle.StateFlag.State_MouseOver
            | QStyle.StateFlag.State_HasFocus
        )
        content_option.backgroundBrush = QBrush(Qt.BrushStyle.NoBrush)
        super().paint(painter, content_option, index)

    def _row_rect(
        self,
        table: SessionTableWidget,
        option: QStyleOptionViewItem,
    ) -> QRectF:
        visible_columns = [
            column
            for column in range(table.columnCount())
            if not table.isColumnHidden(column)
        ]
        if not visible_columns:
            return QRectF(
                option.rect.adjusted(
                    self._horizontal_inset,
                    self._vertical_inset,
                    -self._horizontal_inset,
                    -self._vertical_inset,
                )
            )
        left = min(table.columnViewportPosition(column) for column in visible_columns)
        right = max(
            table.columnViewportPosition(column) + table.columnWidth(column)
            for column in visible_columns
        )
        return QRectF(
            left + self._horizontal_inset,
            option.rect.top() + self._vertical_inset,
            max(1, right - left - self._horizontal_inset * 2),
            max(1, option.rect.height() - self._vertical_inset * 2),
        )


class DashboardPageStack(AnimatedPageStack):
    """QStackedWidget with tab-like metadata kept for API compatibility."""

    def __init__(self) -> None:
        super().__init__()
        self._labels: list[str] = []
        self._icons: list[QIcon] = []

    def add_page(self, page: QWidget) -> int:
        index = self.addWidget(page)
        self._labels.append("")
        self._icons.append(QIcon())
        return index

    def setTabText(self, index: int, text: str) -> None:
        self._labels[index] = text

    def tabText(self, index: int) -> str:
        return self._labels[index]

    def setTabIcon(self, index: int, icon: QIcon) -> None:
        self._icons[index] = icon

    def tabIcon(self, index: int) -> QIcon:
        return self._icons[index]


class FocusActivityCard(QFrame):
    """Section surface whose title and mode control reflow on narrow widths."""

    def __init__(self, title: str, control: SegmentedControl) -> None:
        super().__init__()
        self.setObjectName("sectionSurface")
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(8)
        self._header = QWidget()
        self._header_layout = QGridLayout(self._header)
        self._header_layout.setContentsMargins(0, 0, 0, 0)
        self._header_layout.setHorizontalSpacing(12)
        self._header_layout.setVerticalSpacing(8)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("sectionTitle")
        self.title_label.setWordWrap(True)
        self.control = control
        self.control.setMinimumWidth(210)
        self.control.setMaximumWidth(270)
        self.control.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        root.addWidget(self._header)
        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(8)
        root.addLayout(self.content_layout)
        self._narrow = False
        self._arrange_header(False)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._arrange_header(event.size().width() < 560)

    def _arrange_header(self, narrow: bool) -> None:
        if narrow == self._narrow and self._header_layout.count() > 0:
            return
        self._narrow = narrow
        self._header_layout.removeWidget(self.title_label)
        self._header_layout.removeWidget(self.control)
        if narrow:
            self._header_layout.addWidget(self.title_label, 0, 0)
            self._header_layout.addWidget(
                self.control,
                1,
                0,
                Qt.AlignmentFlag.AlignRight,
            )
            self._header_layout.setColumnStretch(0, 1)
            self._header_layout.setColumnStretch(1, 0)
        else:
            self._header_layout.addWidget(self.title_label, 0, 0)
            self._header_layout.addWidget(self.control, 0, 1)
            self._header_layout.setColumnStretch(0, 1)
            self._header_layout.setColumnStretch(1, 0)


# Private compatibility aliases retained for existing imports and tests.
_SessionTableRole = SessionTableRole
_SessionTableWidget = SessionTableWidget
_SessionTableDelegate = SessionTableDelegate
_DashboardPageStack = DashboardPageStack
_FocusActivityCard = FocusActivityCard
