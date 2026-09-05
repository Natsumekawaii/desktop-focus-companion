"""Focus Item specialization of the shared rounded selector."""

from __future__ import annotations

from PySide6.QtCore import (
    QModelIndex,
    QPersistentModelIndex,
    QPointF,
    QRectF,
    QSize,
    Qt,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QStyle,
    QStyledItemDelegate,
    QStyleOptionComboBox,
    QStyleOptionViewItem,
    QStylePainter,
    QWidget,
)

from app.core.theme import get_theme_manager
from app.ui.rounded_selector import RoundedComboBox, draw_selector_chevron

_FOCUS_ITEM_KIND_ROLE = int(Qt.ItemDataRole.UserRole) + 1
_FOCUS_ITEM_COLOR_ROLE = int(Qt.ItemDataRole.UserRole) + 2
_FOCUS_ITEM_KIND_ITEM = "item"
_FOCUS_ITEM_KIND_EMPTY = "empty"
_FOCUS_ITEM_KIND_SEPARATOR = "separator"
_FOCUS_ITEM_KIND_MANAGE = "manage"

_PROJECT_ROW_HEIGHT = 36
_PROJECT_SEPARATOR_HORIZONTAL_INSET = 6
_SEPARATOR_ROW_HEIGHT = 9
_MANAGE_ROW_HEIGHT = 40
_POPUP_VERTICAL_INSET = 12


class _FocusItemRowDelegate(QStyledItemDelegate):
    """Paint Focus Item rows without native rectangular selection layers."""

    def __init__(self, selector: FocusItemSelector) -> None:
        super().__init__(selector)
        self._selector = selector

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QSize:
        kind = index.data(_FOCUS_ITEM_KIND_ROLE)
        if kind == _FOCUS_ITEM_KIND_SEPARATOR:
            height = _SEPARATOR_ROW_HEIGHT
        elif kind == _FOCUS_ITEM_KIND_MANAGE:
            height = _MANAGE_ROW_HEIGHT
        else:
            height = _PROJECT_ROW_HEIGHT
        return QSize(max(1, option.rect.width()), height)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        styled = QStyleOptionViewItem(option)
        self.initStyleOption(styled, index)
        kind = index.data(_FOCUS_ITEM_KIND_ROLE)
        tokens = get_theme_manager().tokens

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if kind == _FOCUS_ITEM_KIND_SEPARATOR:
            painter.setPen(QPen(QColor(tokens.separator), 1.0))
            y = styled.rect.center().y()
            painter.drawLine(styled.rect.left() + 10, y, styled.rect.right() - 10, y)
            painter.restore()
            return

        row_rect = QRectF(styled.rect).adjusted(4, 2, -4, -2)
        enabled = bool(index.flags() & Qt.ItemFlag.ItemIsEnabled)
        committed = (
            enabled
            and kind == _FOCUS_ITEM_KIND_ITEM
            and self._selector.currentIndex() == index.row()
        )
        candidate = bool(styled.state & QStyle.StateFlag.State_Selected)
        hovered = bool(styled.state & QStyle.StateFlag.State_MouseOver)

        painter.setPen(Qt.PenStyle.NoPen)
        if committed or (
            kind == _FOCUS_ITEM_KIND_MANAGE and (hovered or candidate)
        ):
            painter.setBrush(QColor(tokens.primary_soft))
            painter.drawRoundedRect(row_rect, 9, 9)
        elif hovered or candidate:
            painter.setBrush(QColor(tokens.surface_hover))
            painter.drawRoundedRect(row_rect, 9, 9)

        if candidate and not committed:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(tokens.focus_ring), 1.0))
            painter.drawRoundedRect(row_rect.adjusted(0.5, 0.5, -0.5, -0.5), 8.5, 8.5)

        font = QFont(styled.font)
        if kind in {_FOCUS_ITEM_KIND_ITEM, _FOCUS_ITEM_KIND_MANAGE}:
            font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        if not enabled or kind == _FOCUS_ITEM_KIND_EMPTY:
            text_color = QColor(tokens.disabled)
        elif kind == _FOCUS_ITEM_KIND_MANAGE:
            text_color = QColor(tokens.primary)
        else:
            saved_color = QColor(str(index.data(_FOCUS_ITEM_COLOR_ROLE) or ""))
            text_color = saved_color if saved_color.isValid() else QColor(tokens.text)
        painter.setPen(text_color)

        text_right = 34 if committed else 10
        text_rect = row_rect.adjusted(10, 0, -text_right, 0)
        text = painter.fontMetrics().elidedText(
            styled.text,
            Qt.TextElideMode.ElideRight,
            max(0, round(text_rect.width())),
        )
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            text,
        )

        if committed:
            self._paint_checkmark(painter, row_rect, QColor(tokens.primary))
        if kind == _FOCUS_ITEM_KIND_ITEM:
            previous_index = index.sibling(index.row() - 1, index.column())
            if (
                previous_index.isValid()
                and previous_index.data(_FOCUS_ITEM_KIND_ROLE)
                == _FOCUS_ITEM_KIND_ITEM
            ):
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
                painter.setPen(QPen(QColor(tokens.border), 1.0))
                separator_y = styled.rect.top()
                painter.drawLine(
                    styled.rect.left() + _PROJECT_SEPARATOR_HORIZONTAL_INSET,
                    separator_y,
                    styled.rect.right() - _PROJECT_SEPARATOR_HORIZONTAL_INSET,
                    separator_y,
                )
        painter.restore()

    @staticmethod
    def _paint_checkmark(
        painter: QPainter,
        row_rect: QRectF,
        color: QColor,
    ) -> None:
        center = QPointF(row_rect.right() - 16, row_rect.center().y())
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(
            QPen(
                color,
                1.9,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        painter.drawLine(
            QPointF(center.x() - 4.0, center.y()),
            QPointF(center.x() - 1.2, center.y() + 3.0),
        )
        painter.drawLine(
            QPointF(center.x() - 1.2, center.y() + 3.0),
            QPointF(center.x() + 4.5, center.y() - 3.5),
        )


class FocusItemSelector(RoundedComboBox):
    """A text-only selector whose popup has genuine transparent rounded corners."""

    _popup_surface_name = "focusItemSelectorPopupSurface"
    _popup_container_name = "focusItemSelectorPopup"
    _popup_view_name = "focusItemSelectorPopupView"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._focus_item_delegate = _FocusItemRowDelegate(self)
        self.view().setItemDelegate(self._focus_item_delegate)
        self.view().setMouseTracking(True)

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        option.currentText = ""

        painter = QStylePainter(self)
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option)

        tokens = get_theme_manager().tokens
        kind = self.currentData(_FOCUS_ITEM_KIND_ROLE)
        saved_color = QColor(str(self.currentData(_FOCUS_ITEM_COLOR_ROLE) or ""))
        if not self.isEnabled() or kind == _FOCUS_ITEM_KIND_EMPTY:
            text_color = QColor(tokens.disabled)
        elif kind == _FOCUS_ITEM_KIND_ITEM and saved_color.isValid():
            text_color = saved_color
        else:
            text_color = QColor(tokens.text)

        text_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox,
            option,
            QStyle.SubControl.SC_ComboBoxEditField,
            self,
        )
        text_rect.setRight(min(text_rect.right(), self.width() - 42))
        text = painter.fontMetrics().elidedText(
            self.currentText(),
            Qt.TextElideMode.ElideRight,
            max(0, text_rect.width()),
        )
        painter.setPen(text_color)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            text,
        )
        draw_selector_chevron(self, painter)
        painter.end()

    def _popup_height_for_visible_rows(self, visible_rows: int) -> int:
        row_heights = (
            max(1, self.view().sizeHintForRow(row))
            for row in range(min(visible_rows, self.count()))
        )
        return sum(row_heights) + _POPUP_VERTICAL_INSET


__all__ = ["FocusItemSelector"]
