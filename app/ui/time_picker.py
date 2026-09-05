"""Rounded, minute-precise time selector with a two-column popup."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRect, QSize, Qt, QTime, Signal
from PySide6.QtGui import (
    QCloseEvent,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.i18n import get_localization, tr
from app.ui.anchored_popup import (
    AnimatedAnchoredPopup,
    PopupState,
    scroll_bar_from_wheel,
)
from app.ui.rounded_selector import (
    SelectorDensity,
    draw_selector_chevron,
    forward_closed_selector_wheel,
)


class _TimePickerPopup(AnimatedAnchoredPopup):
    """Popup surface containing scrollable hour and minute columns."""

    def __init__(self, owner: RoundedTimePicker) -> None:
        super().__init__(owner)
        self._time_owner = owner
        self._updating = False
        self.setObjectName("roundedTimePickerPopup")

        self.surface = QFrame(self)
        self.surface.setObjectName("roundedTimePickerPopupSurface")
        surface_layout = QHBoxLayout(self.surface)
        surface_layout.setContentsMargins(10, 10, 10, 10)
        surface_layout.setSpacing(8)

        self._hour_label = QLabel()
        self._hour_label.setObjectName("selectorPopupHeader")
        self._minute_label = QLabel()
        self._minute_label.setObjectName("selectorPopupHeader")
        self._hour_list = self._new_list(tuple(range(24)))
        self._minute_list = self._new_list(tuple(range(60)))
        hour_column = self._column(self._hour_label, self._hour_list)
        minute_column = self._column(self._minute_label, self._minute_list)
        surface_layout.addWidget(hour_column, 1)
        surface_layout.addWidget(minute_column, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.surface)
        self._hour_list.currentRowChanged.connect(self._selection_changed)
        self._minute_list.currentRowChanged.connect(self._selection_changed)
        self._hour_list.itemClicked.connect(self._hour_clicked)
        self._minute_list.itemClicked.connect(self._minute_clicked)
        self._hour_list.itemActivated.connect(self._hour_activated)
        self._minute_list.itemActivated.connect(self._minute_activated)
        get_localization().language_changed.connect(self.retranslate_ui)
        self.retranslate_ui()

    @staticmethod
    def _new_list(values: tuple[int, ...]) -> QListWidget:
        widget = QListWidget()
        widget.setObjectName("roundedTimePickerList")
        widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        widget.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        for value in values:
            item = QListWidgetItem(f"{value:02d}")
            item.setData(Qt.ItemDataRole.UserRole, value)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            widget.addItem(item)
        return widget

    @staticmethod
    def _column(label: QLabel, values: QListWidget) -> QWidget:
        column = QWidget()
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(label)
        layout.addWidget(values, 1)
        return column

    def retranslate_ui(self, _language: str | None = None) -> None:
        self._hour_label.setText(tr("settings.duration_hours"))
        self._minute_label.setText(tr("settings.duration_minutes"))
        self._hour_list.setAccessibleName(tr("settings.duration_hours"))
        self._minute_list.setAccessibleName(tr("settings.duration_minutes"))

    def _prepare_to_show(self) -> None:
        value = self._time_owner.time()
        self._updating = True
        try:
            self._hour_list.setCurrentRow(value.hour())
            self._minute_list.setCurrentRow(value.minute())
        finally:
            self._updating = False
        self._hour_list.scrollToItem(
            self._hour_list.currentItem(),
            QAbstractItemView.ScrollHint.PositionAtCenter,
        )
        self._minute_list.scrollToItem(
            self._minute_list.currentItem(),
            QAbstractItemView.ScrollHint.PositionAtCenter,
        )

    def _ideal_size(self) -> QSize:
        return QSize(240, 300)

    def _focus_popup(self) -> None:
        self._hour_list.setFocus(Qt.FocusReason.PopupFocusReason)

    def wheel_target(self) -> QWidget:
        if self._minute_list.hasFocus():
            return self._minute_list.viewport()
        return self._hour_list.viewport()

    @staticmethod
    def _is_inside(watched: QObject, widget: QWidget) -> bool:
        current: QObject | None = watched
        while current is not None:
            if current is widget:
                return True
            current = current.parent()
        return False

    def _wheel_list(self, watched: QObject, event: QWheelEvent) -> QListWidget:
        if self._is_inside(watched, self._hour_list):
            return self._hour_list
        if self._is_inside(watched, self._minute_list):
            return self._minute_list
        if self._is_inside(watched, self._time_owner):
            return self._minute_list if self._minute_list.hasFocus() else self._hour_list
        global_position = event.globalPosition().toPoint()
        minute_rect = self._minute_list.rect()
        minute_top_left = self._minute_list.mapToGlobal(minute_rect.topLeft())
        if QRect(minute_top_left, minute_rect.size()).contains(global_position):
            return self._minute_list
        return self._hour_list

    def _handle_wheel(self, watched: QObject, event: QWheelEvent) -> bool:
        target = self._wheel_list(watched, event)
        scroll_bar_from_wheel(target.verticalScrollBar(), event)
        return True

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide_animated()
            return
        if event.key() in {Qt.Key.Key_Tab, Qt.Key.Key_Backtab}:
            target = (
                self._minute_list
                if self._hour_list.hasFocus()
                else self._hour_list
            )
            target.setFocus(Qt.FocusReason.TabFocusReason)
            return
        super().keyPressEvent(event)

    def _selection_changed(self, _row: int) -> None:
        if self._updating:
            return
        hour_item = self._hour_list.currentItem()
        minute_item = self._minute_list.currentItem()
        if hour_item is None or minute_item is None:
            return
        self._time_owner._set_time(
            QTime(
                int(hour_item.data(Qt.ItemDataRole.UserRole)),
                int(minute_item.data(Qt.ItemDataRole.UserRole)),
            ),
            emit=True,
        )

    def _hour_clicked(self, _item: QListWidgetItem) -> None:
        self._minute_list.setFocus(Qt.FocusReason.MouseFocusReason)

    def _minute_clicked(self, _item: QListWidgetItem) -> None:
        self.hide_animated()

    def _hour_activated(self, _item: QListWidgetItem) -> None:
        self._minute_list.setFocus(Qt.FocusReason.TabFocusReason)

    def _minute_activated(self, _item: QListWidgetItem) -> None:
        self.hide_animated()


class RoundedTimePicker(QPushButton):
    """A field-like button exposing the subset of QTimeEdit used by the app."""

    timeChanged = Signal(QTime)

    def __init__(
        self,
        value: QTime | None = None,
        parent: QWidget | None = None,
        *,
        density: SelectorDensity = SelectorDensity.COMPACT,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("roundedTimePicker")
        self.setProperty("roundedSelector", True)
        self.setProperty("selectorDensity", density.value)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._display_format = "HH:mm"
        initial = value if value is not None and value.isValid() else QTime.currentTime()
        self._time = QTime(initial.hour(), initial.minute())
        self._popup = _TimePickerPopup(self)
        self._refresh_text()

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        draw_selector_chevron(self, painter)
        painter.end()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._popup.hide_immediately()
        super().closeEvent(event)

    def setDisplayFormat(self, display_format: str) -> None:
        self._display_format = display_format
        self._refresh_text()

    def setTime(self, value: QTime) -> None:
        self._set_time(value, emit=True)

    def time(self) -> QTime:
        return QTime(self._time)

    def showPopup(self) -> None:
        if self._popup.popup_state in {PopupState.OPENING, PopupState.OPEN}:
            return
        self._popup.show_for_owner()

    def hidePopup(self) -> None:
        self._popup.hide_animated()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self._popup.toggle()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in {
            Qt.Key.Key_Space,
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
        } or (
            event.key() == Qt.Key.Key_Down
            and bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
        ):
            self._popup.toggle()
            event.accept()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._popup.is_expanded():
            self._popup.handle_wheel_event(self, event)
            return
        forward_closed_selector_wheel(self, event)

    def _set_time(self, value: QTime, *, emit: bool) -> None:
        if not value.isValid():
            return
        normalized = QTime(value.hour(), value.minute())
        if normalized == self._time:
            return
        self._time = normalized
        self._refresh_text()
        if emit:
            self.timeChanged.emit(QTime(self._time))

    def _refresh_text(self) -> None:
        self.setText(self._time.toString(self._display_format))


__all__ = ["RoundedTimePicker"]
