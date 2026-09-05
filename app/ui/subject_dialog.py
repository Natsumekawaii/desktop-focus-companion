"""Compact Focus Item management with creation-only visual colors."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import cast

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QModelIndex,
    QPersistentModelIndex,
    QRectF,
    QSize,
    Qt,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QEnterEvent,
    QLinearGradient,
    QPainter,
    QPaintEvent,
    QPen,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from app.core.theme import get_theme_manager
from app.data.models import FocusItem
from app.i18n import format_datetime, get_localization, tr
from app.timer.formatting import format_compact_duration

FOCUS_COLORS = (
    "#8B97A8",
    "#FF4D5A",
    "#FF6B4A",
    "#FFAA1F",
    "#FFD21F",
    "#9AD82B",
    "#55C52B",
    "#35C8B0",
    "#55C4E6",
    "#4299E1",
    "#5B83D6",
    "#9575CD",
    "#F47FA7",
    "#F36F82",
)
FOCUS_COLOR_KEYS = (
    "focus_items.color.slate",
    "focus_items.color.red",
    "focus_items.color.coral",
    "focus_items.color.orange",
    "focus_items.color.yellow",
    "focus_items.color.lime",
    "focus_items.color.green",
    "focus_items.color.teal",
    "focus_items.color.cyan",
    "focus_items.color.blue",
    "focus_items.color.indigo",
    "focus_items.color.purple",
    "focus_items.color.pink",
    "focus_items.color.rose",
)
DEFAULT_FOCUS_SWATCH_COLOR = "#9575CD"


def _mix_color(first: QColor, second: QColor, progress: float) -> QColor:
    amount = max(0.0, min(1.0, progress))
    return QColor(
        round(first.red() + (second.red() - first.red()) * amount),
        round(first.green() + (second.green() - first.green()) * amount),
        round(first.blue() + (second.blue() - first.blue()) * amount),
    )


class ColorSwatchButton(QAbstractButton):
    """Theme-aware circular color choice with stable custom painting."""

    _button_size = 48
    _disc_inset = 5.0

    def __init__(self, color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = color
        self._hover_progress = 0.0
        self._hover_animation = QVariantAnimation(self)
        self._hover_animation.valueChanged.connect(self._set_hover_progress)
        self.setCheckable(True)
        self.setFixedSize(self._button_size, self._button_size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent; border: 0; padding: 0;")
        self.setProperty("swatchColor", color)
        self.pressed.connect(self.update)
        self.released.connect(self.update)
        self.toggled.connect(self._checked_changed)
        get_theme_manager().theme_changed.connect(self.update)

    @property
    def color(self) -> str:
        return self._color

    @property
    def hover_progress(self) -> float:
        return self._hover_progress

    @property
    def disc_rect(self) -> QRectF:
        return QRectF(self.rect()).adjusted(
            self._disc_inset,
            self._disc_inset,
            -self._disc_inset,
            -self._disc_inset,
        )

    def sizeHint(self) -> QSize:
        return QSize(self._button_size, self._button_size)

    def enterEvent(self, event: QEnterEvent) -> None:
        self._animate_hover(1.0, 120)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._animate_hover(0.0, 150)
        super().leaveEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tokens = get_theme_manager().tokens

        outer_ring = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        if self.isChecked():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(tokens.focus_ring), 2.0))
            painter.drawEllipse(outer_ring)
        elif self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(tokens.focus_ring), 1.5, Qt.PenStyle.DashLine))
            painter.drawEllipse(outer_ring)
        elif self._hover_progress > 0.0:
            hover_ring = _mix_color(
                QColor(tokens.border_strong),
                QColor(tokens.focus_ring),
                self._hover_progress,
            )
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(hover_ring, 1.4))
            painter.drawEllipse(outer_ring)

        base = QColor(self._color)
        if self.isDown():
            top = base.darker(104)
            bottom = base.darker(112)
        else:
            normal_top = base.lighter(109)
            normal_bottom = base.darker(105)
            hover_top = base.lighter(118)
            hover_bottom = base.lighter(103)
            top = _mix_color(normal_top, hover_top, self._hover_progress)
            bottom = _mix_color(normal_bottom, hover_bottom, self._hover_progress)
        gradient = QLinearGradient(
            self.disc_rect.center().x(),
            self.disc_rect.top(),
            self.disc_rect.center().x(),
            self.disc_rect.bottom(),
        )
        gradient.setColorAt(0.0, top)
        gradient.setColorAt(1.0, bottom)
        inner_border = _mix_color(
            base.darker(112),
            base.lighter(104),
            self._hover_progress,
        )
        painter.setPen(QPen(inner_border, 1.0))
        painter.setBrush(gradient)
        painter.drawEllipse(self.disc_rect)

    def _animate_hover(self, target: float, duration_ms: int) -> None:
        self._hover_animation.stop()
        self._hover_animation.setStartValue(self._hover_progress)
        self._hover_animation.setEndValue(target)
        self._hover_animation.setDuration(duration_ms)
        self._hover_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_animation.start()

    def _set_hover_progress(self, value: object) -> None:
        self._hover_progress = cast(float, value)
        self.update()

    def _checked_changed(self, _checked: bool) -> None:
        self.update()


class ColorSwatchPicker(QWidget):
    """Accessible 4/4/4/2 palette that never exposes raw color codes."""

    color_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, ColorSwatchButton] = {}
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(10)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        for index, (color, key) in enumerate(
            zip(FOCUS_COLORS, FOCUS_COLOR_KEYS, strict=True)
        ):
            button = ColorSwatchButton(color)
            button.clicked.connect(
                lambda checked=False, value=color: self._select_clicked(value, checked)
            )
            self._group.addButton(button)
            self._buttons[color] = button
            layout.addWidget(button, index // 4, index % 4)
            button.setAccessibleName(tr(key))
            button.setToolTip(tr(key))
        self.set_color(DEFAULT_FOCUS_SWATCH_COLOR)
        get_localization().language_changed.connect(self._retranslate_ui)

    @property
    def selected_color(self) -> str:
        checked = self._group.checkedButton()
        value = (
            checked.property("swatchColor")
            if checked is not None
            else DEFAULT_FOCUS_SWATCH_COLOR
        )
        return str(value)

    def set_color(self, color: str) -> None:
        target = color if color in self._buttons else DEFAULT_FOCUS_SWATCH_COLOR
        self._buttons[target].setChecked(True)

    def _select_clicked(self, color: str, checked: bool) -> None:
        if checked:
            self.color_selected.emit(color)

    def _retranslate_ui(self, _language: str | None = None) -> None:
        for color, key in zip(FOCUS_COLORS, FOCUS_COLOR_KEYS, strict=True):
            self._buttons[color].setAccessibleName(tr(key))
            self._buttons[color].setToolTip(tr(key))


class FocusItemCreateDialog(QDialog):
    """Collect a new Focus Item name and its permanent visual color."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setFixedWidth(320)
        self._name_input = QLineEdit()
        self._palette_caption = QLabel()
        self._palette_caption.setObjectName("cardCaption")
        self._color_picker = ColorSwatchPicker()
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(12)
        layout.addWidget(self._name_input)
        layout.addWidget(self._palette_caption)
        layout.addWidget(self._color_picker, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._buttons)
        self._name_input.textChanged.connect(self._sync_accept_button)
        get_localization().language_changed.connect(self.retranslate_ui)
        self.retranslate_ui()
        self._sync_accept_button()

    @property
    def focus_item_name(self) -> str:
        return self._name_input.text()

    @property
    def selected_color(self) -> str:
        return self._color_picker.selected_color

    def retranslate_ui(self, _language: str | None = None) -> None:
        self.setWindowTitle(tr("focus_items.add_title"))
        self._name_input.setPlaceholderText(tr("focus_items.name_placeholder"))
        self._palette_caption.setText(tr("focus_items.choose_color"))
        accept = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        cancel = self._buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if accept is not None:
            accept.setText(tr("common.add"))
        if cancel is not None:
            cancel.setText(tr("common.cancel"))

    def _sync_accept_button(self) -> None:
        accept = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        if accept is not None:
            accept.setEnabled(bool(self._name_input.text().strip()))


class FocusItemRenameDialog(QDialog):
    """Rename one item without exposing color controls."""

    def __init__(self, current_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setFixedWidth(320)
        self._name_input = QLineEdit(current_name)
        self._name_input.selectAll()
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(12)
        layout.addWidget(self._name_input)
        layout.addWidget(self._buttons)
        self._name_input.textChanged.connect(self._sync_accept_button)
        get_localization().language_changed.connect(self.retranslate_ui)
        self.retranslate_ui()
        self._sync_accept_button()

    @property
    def focus_item_name(self) -> str:
        return self._name_input.text()

    def retranslate_ui(self, _language: str | None = None) -> None:
        self.setWindowTitle(tr("focus_items.rename_title"))
        self._name_input.setPlaceholderText(tr("focus_items.name_placeholder"))
        accept = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        cancel = self._buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if accept is not None:
            accept.setText(tr("common.rename"))
        if cancel is not None:
            cancel.setText(tr("common.cancel"))

    def _sync_accept_button(self) -> None:
        accept = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        if accept is not None:
            accept.setEnabled(bool(self._name_input.text().strip()))


class _FocusItemListDelegate(QStyledItemDelegate):
    """Leave row painting entirely to the embedded rounded card."""

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        del painter, option, index


class _FocusItemCardHost(QWidget):
    """Center a bounded card inside a full-width, transparent list row."""

    _maximum_card_width = 350
    _minimum_side_margin = 12

    def __init__(self, card: QFrame) -> None:
        super().__init__()
        self.card = card
        self._minimum_card_height = card.minimumHeight()
        self.setObjectName("focusItemManagementRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addStretch()
        layout.addWidget(card)
        layout.addStretch()

    def set_available_width(self, width: int) -> None:
        available = max(1, width)
        card_width = min(
            self._maximum_card_width,
            max(1, available - self._minimum_side_margin * 2),
        )
        self.setFixedWidth(available)
        card_layout = cast(QLayout, self.card.layout())
        margins = card_layout.contentsMargins()
        content_width = max(1, card_width - margins.left() - margins.right())
        content_height = margins.top() + margins.bottom()
        visible_widgets: list[QWidget] = []
        for index in range(card_layout.count()):
            layout_item = card_layout.itemAt(index)
            if layout_item is None:
                continue
            widget = layout_item.widget()
            if widget is not None and widget.isVisibleTo(self.card):
                visible_widgets.append(widget)
        for widget in visible_widgets:
            single_line_label = (
                isinstance(widget, QLabel)
                and widget.wordWrap()
                and widget.fontMetrics().horizontalAdvance(widget.text())
                <= content_width
            )
            if single_line_label:
                preferred_height = widget.fontMetrics().height()
            elif widget.hasHeightForWidth():
                preferred_height = widget.heightForWidth(content_width)
            else:
                preferred_height = widget.sizeHint().height()
            content_height += max(widget.minimumHeight(), preferred_height)
        if visible_widgets:
            content_height += card_layout.spacing() * (len(visible_widgets) - 1)
        card_height = max(self._minimum_card_height, content_height)
        self.card.setFixedSize(card_width, card_height)
        self.setFixedHeight(card_height)
        self.updateGeometry()


class UniformWidthListWidget(QListWidget):
    """Keep transparent rows flush while centering bounded item cards."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setItemDelegate(_FocusItemListDelegate(self))
        self.setSpacing(4)

    def sync_item_widths(self) -> None:
        width = max(1, self.viewport().width())
        for row in range(self.count()):
            item = self.item(row)
            widget = self.itemWidget(item)
            if not isinstance(widget, _FocusItemCardHost):
                continue
            widget.set_available_width(width)
            item.setSizeHint(QSize(width, widget.sizeHint().height()))

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.sync_item_widths()


class FocusItemDialog(QDialog):
    """List Focus Items and expose only Add, Rename, and Delete."""

    create_focus_item_requested = Signal(str, str)
    rename_requested = Signal(int, str)
    delete_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(440, 400)
        self._focus_items: list[FocusItem] = []
        self._total_seconds_by_id: dict[int, float] = {}
        self._last_record_by_id: dict[int, datetime] = {}
        self._item_list = UniformWidthListWidget()
        self._item_list.setObjectName("focusItemManagementList")
        self._item_list.currentItemChanged.connect(self._on_current_item_changed)
        self._caption = QLabel()

        self._add_button = QPushButton()
        self._add_button.clicked.connect(self._request_create)
        self._rename_button = QPushButton()
        self._rename_button.clicked.connect(self._request_rename)
        self._delete_button = QPushButton()
        self._delete_button.setObjectName("danger")
        self._delete_button.clicked.connect(self._request_delete)

        action_buttons = QHBoxLayout()
        action_buttons.setSpacing(8)
        action_buttons.addWidget(self._add_button)
        action_buttons.addWidget(self._rename_button)
        action_buttons.addWidget(self._delete_button)

        self._close_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self._close_buttons.rejected.connect(self.close)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(8)
        layout.addWidget(self._caption)
        layout.addWidget(self._item_list, 1)
        layout.addLayout(action_buttons)
        layout.addWidget(self._close_buttons)
        get_localization().language_changed.connect(self.retranslate_ui)
        self.retranslate_ui()
        self._sync_lifecycle_buttons()

    def retranslate_ui(self, _language: str | None = None) -> None:
        self.setWindowTitle(tr("focus_items.title"))
        self._caption.setText(tr("focus_items.caption"))
        self._add_button.setText(tr("common.add"))
        self._rename_button.setText(tr("common.rename"))
        self._delete_button.setText(tr("common.delete"))
        close = self._close_buttons.button(QDialogButtonBox.StandardButton.Close)
        if close is not None:
            close.setText(tr("common.close"))
        self.set_focus_items(self._focus_items)

    def set_focus_items(self, items: Sequence[FocusItem]) -> None:
        selected_id = self.selected_focus_item_id()
        self._focus_items = list(items)
        self._item_list.clear()
        for focus_item in items:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, focus_item.id)
            item.setToolTip(focus_item.name)
            self._item_list.addItem(item)
            card = self._focus_item_card(focus_item)
            self._item_list.setItemWidget(item, _FocusItemCardHost(card))
            if focus_item.id == selected_id:
                self._item_list.setCurrentItem(item)
        if self._item_list.currentItem() is None and self._item_list.count():
            self._item_list.setCurrentRow(0)
        self._item_list.sync_item_widths()
        self._sync_item_card_selection()
        self._sync_lifecycle_buttons()

    def set_focus_item_metrics(
        self,
        total_seconds_by_id: dict[int, float],
        last_record_by_id: dict[int, datetime],
    ) -> None:
        self._total_seconds_by_id = dict(total_seconds_by_id)
        self._last_record_by_id = dict(last_record_by_id)
        self.set_focus_items(self._focus_items)

    def selected_focus_item_id(self) -> int | None:
        item = self._item_list.currentItem()
        return int(item.data(Qt.ItemDataRole.UserRole)) if item is not None else None

    def _selected_model(self) -> FocusItem | None:
        selected_id = self.selected_focus_item_id()
        return next(
            (item for item in self._focus_items if item.id == selected_id), None
        )

    def _focus_item_card(self, focus_item: FocusItem) -> QFrame:
        card = QFrame()
        card.setObjectName("focusItemManagementCard")
        card.setProperty("selected", False)
        card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        card.setMinimumHeight(48)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(1)
        title = QLabel(focus_item.name)
        title.setObjectName("focusItemManagementTitle")
        title.setStyleSheet(
            f"color: {focus_item.color}; background: transparent; "
            "font-size: 14px; font-weight: 600;"
        )
        title.setToolTip(focus_item.name)
        title.setWordWrap(True)
        total = format_compact_duration(
            self._total_seconds_by_id.get(focus_item.id, 0.0)
        )
        last_record = self._last_record_by_id.get(focus_item.id)
        recent = (
            tr("focus_items.last_record", value=format_datetime(last_record))
            if last_record is not None
            else tr("focus_items.no_records")
        )
        metadata = QLabel(
            tr("focus_items.card_metadata", total=total, recent=recent)
        )
        metadata.setObjectName("secondary")
        metadata.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(metadata)
        return card

    def _on_current_item_changed(
        self,
        _current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        self._sync_item_card_selection()
        self._sync_lifecycle_buttons()

    def _sync_item_card_selection(self) -> None:
        current = self._item_list.currentItem()
        for row in range(self._item_list.count()):
            item = self._item_list.item(row)
            host = self._item_list.itemWidget(item)
            if not isinstance(host, _FocusItemCardHost):
                continue
            card = host.card
            selected = item is current
            if card.property("selected") == selected:
                continue
            card.setProperty("selected", selected)
            card.style().unpolish(card)
            card.style().polish(card)
            card.update()

    def _request_create(self) -> None:
        dialog = FocusItemCreateDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.create_focus_item_requested.emit(
                dialog.focus_item_name, dialog.selected_color
            )

    def _request_rename(self) -> None:
        selected = self._selected_model()
        if selected is None:
            return
        dialog = FocusItemRenameDialog(selected.name, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.rename_requested.emit(selected.id, dialog.focus_item_name)

    def _request_delete(self) -> None:
        item_id = self.selected_focus_item_id()
        if item_id is not None:
            self.delete_requested.emit(item_id)

    def _sync_lifecycle_buttons(self) -> None:
        selected = self._selected_model()
        self._rename_button.setEnabled(selected is not None)
        self._delete_button.setEnabled(selected is not None)


__all__ = [
    "DEFAULT_FOCUS_SWATCH_COLOR",
    "FOCUS_COLORS",
    "ColorSwatchButton",
    "ColorSwatchPicker",
    "FocusItemCreateDialog",
    "FocusItemDialog",
    "FocusItemRenameDialog",
]
