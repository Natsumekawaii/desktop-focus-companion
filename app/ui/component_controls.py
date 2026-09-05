"""Reusable input controls backed by the global design system."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QDate, QObject, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QFont,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QTextCharFormat,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QCalendarWidget,
    QCheckBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.core.theme import DESIGN, get_theme_manager
from app.i18n import get_localization, tr
from app.ui.anchored_popup import AnimatedAnchoredPopup, PopupState
from app.ui.rounded_selector import (
    RoundedComboBox,
    SelectorDensity,
    draw_selector_chevron,
    forward_closed_selector_wheel,
)


def apply_elevation(widget: QWidget, *, subtle: bool = False) -> None:
    """Apply restrained elevation to floating or intentionally raised surfaces."""

    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(10 if subtle else 18)
    shadow.setOffset(0, 1 if subtle else 3)
    color = QColor(get_theme_manager().tokens.shadow)
    color.setAlpha(16 if subtle else 30)
    shadow.setColor(color)
    widget.setGraphicsEffect(shadow)


class RoundedCheckBox(QCheckBox):
    """A compact, theme-aware checkbox without a native platform indicator."""

    _indicator_size = 20
    _indicator_radius = 6
    _text_gap = 8

    def __init__(
        self,
        text: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(28)
        get_theme_manager().theme_changed.connect(self.update)

    def sizeHint(self) -> QSize:
        metrics = self.fontMetrics()
        width = self._indicator_size + self._text_gap + metrics.horizontalAdvance(self.text())
        return QSize(width, max(28, metrics.height() + 8))

    def minimumSizeHint(self) -> QSize:
        return QSize(self._indicator_size + self._text_gap + 24, self.sizeHint().height())

    def indicator_rect(self) -> QRectF:
        top = (self.height() - self._indicator_size) / 2
        return QRectF(2, top, self._indicator_size, self._indicator_size)

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tokens = get_theme_manager().tokens
        indicator = self.indicator_rect()
        enabled = self.isEnabled()
        checked = self.isChecked()

        if self.hasFocus():
            focus_rect = indicator.adjusted(-2, -2, 2, 2)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(tokens.focus_ring), 2))
            painter.drawRoundedRect(
                focus_rect,
                self._indicator_radius + 2,
                self._indicator_radius + 2,
            )

        if not enabled:
            background = QColor(tokens.surface_alt)
            border = QColor(tokens.disabled)
        elif checked:
            background = QColor(
                tokens.primary_pressed if self.isDown() else tokens.primary
            )
            border = background
        elif self.isDown():
            background = QColor(tokens.primary_soft)
            border = QColor(tokens.primary)
        elif self.underMouse():
            background = QColor(tokens.surface_hover)
            border = QColor(tokens.border_strong)
        else:
            background = QColor(tokens.input)
            border = QColor(tokens.border_strong)

        painter.setPen(QPen(border, 1.5))
        painter.setBrush(background)
        painter.drawRoundedRect(
            indicator,
            self._indicator_radius,
            self._indicator_radius,
        )

        if checked:
            check_color = QColor(tokens.primary_text if enabled else tokens.disabled)
            check = QPainterPath()
            check.moveTo(indicator.left() + 5.0, indicator.center().y())
            check.lineTo(indicator.left() + 8.5, indicator.bottom() - 5.0)
            check.lineTo(indicator.right() - 4.5, indicator.top() + 5.0)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(
                QPen(
                    check_color,
                    2.2,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            painter.drawPath(check)

        text_left = int(indicator.right()) + self._text_gap
        text_rect = self.rect().adjusted(text_left, 0, -2, 0)
        text = self.fontMetrics().elidedText(
            self.text(),
            Qt.TextElideMode.ElideRight,
            max(0, text_rect.width()),
        )
        painter.setFont(self.font())
        painter.setPen(QColor(tokens.text if enabled else tokens.disabled))
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            text,
        )
        painter.end()


class _DatePickerPopup(AnimatedAnchoredPopup):
    """Downward-only calendar surface used by :class:`ThemedDateEdit`."""

    def __init__(self, owner: ThemedDateEdit) -> None:
        super().__init__(owner)
        self._date_owner = owner
        self._wheel_remainder = 0
        self._wheel_uses_pixels = False
        self.setObjectName("themedCalendarPopup")

        self.calendar = QCalendarWidget()
        self.calendar.setObjectName("themedCalendar")
        self.calendar.setVerticalHeaderFormat(
            QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader
        )

        self._scroll = QScrollArea()
        self._scroll.setObjectName("themedCalendarScroll")
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setWidgetResizable(False)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll.setWidget(self.calendar)
        self._scroll.verticalScrollBar().setSingleStep(24)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._scroll)

        self.calendar.clicked.connect(self._date_selected)
        self.calendar.activated.connect(self._date_selected)

    def _prepare_to_show(self) -> None:
        self.calendar.setSelectedDate(self._date_owner.date())
        self.calendar.showSelectedDate()
        hint = self.calendar.sizeHint()
        self.calendar.setFixedSize(hint)

    def _ideal_size(self) -> QSize:
        hint = self.calendar.sizeHint()
        return QSize(max(self._date_owner.width(), hint.width()), hint.height())

    def _focus_popup(self) -> None:
        self.calendar.setFocus(Qt.FocusReason.PopupFocusReason)

    def _handle_wheel(self, watched: QObject, event: QWheelEvent) -> bool:
        del watched
        pixel_delta = event.pixelDelta().y()
        uses_pixels = bool(pixel_delta)
        delta = pixel_delta if uses_pixels else event.angleDelta().y()
        threshold = 40 if uses_pixels else 120
        if uses_pixels != self._wheel_uses_pixels:
            self._wheel_remainder = 0
            self._wheel_uses_pixels = uses_pixels
        self._wheel_remainder += delta
        while abs(self._wheel_remainder) >= threshold:
            if self._wheel_remainder < 0:
                self.calendar.showNextMonth()
                self._wheel_remainder += threshold
            else:
                self.calendar.showPreviousMonth()
                self._wheel_remainder -= threshold
        event.accept()
        return True

    def _date_selected(self, value: QDate) -> None:
        self._date_owner.setDate(value)
        self.hide_animated()


class ThemedDateEdit(QPushButton):
    """Locale-aware date editor whose popup never uses Qt's red weekends."""

    dateChanged = Signal(QDate)

    def __init__(
        self,
        value: QDate | None = None,
        parent: QWidget | None = None,
        *,
        density: SelectorDensity = SelectorDensity.COMPACT,
    ) -> None:
        super().__init__(parent)
        self.setProperty("roundedSelector", True)
        self.setProperty("selectorDensity", density.value)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._date = QDate(value) if value is not None and value.isValid() else QDate.currentDate()
        self._display_format = "yyyy-MM-dd"
        self._popup = _DatePickerPopup(self)
        get_theme_manager().theme_changed.connect(self._refresh_calendar)
        get_localization().language_changed.connect(self._refresh_calendar)
        self._refresh_calendar()

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        draw_selector_chevron(self, painter)
        painter.end()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._popup.hide_immediately()
        super().closeEvent(event)

    def setDate(self, value: QDate) -> None:
        if not value.isValid():
            return
        normalized = QDate(value)
        changed = normalized != self._date
        self._date = normalized
        self._popup.calendar.setSelectedDate(normalized)
        self._refresh_text()
        if changed:
            self.dateChanged.emit(QDate(self._date))

    def date(self) -> QDate:
        return QDate(self._date)

    def setDisplayFormat(self, display_format: str) -> None:
        self._display_format = display_format
        self._refresh_text()

    def calendarWidget(self) -> QCalendarWidget:
        return self._popup.calendar

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

    def _refresh_calendar(self, _value: str | None = None) -> None:
        localization = get_localization()
        tokens = get_theme_manager().tokens
        self.setLocale(localization.locale)
        calendar = self._popup.calendar
        calendar.setLocale(localization.locale)
        for widget in (calendar, self._popup):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()

        weekday_format = QTextCharFormat()
        weekday_format.setForeground(QColor(tokens.text))
        for weekday in Qt.DayOfWeek:
            calendar.setWeekdayTextFormat(weekday, weekday_format)

        today_format = QTextCharFormat()
        today_format.setForeground(QColor(tokens.primary))
        today_format.setFontWeight(QFont.Weight.DemiBold)
        calendar.setDateTextFormat(QDate.currentDate(), today_format)
        self._refresh_text()

    def _refresh_text(self) -> None:
        self.setText(self._date.toString(self._display_format))


class DurationPicker(QWidget):
    """Two scrollable hour/minute selectors with stable minute output."""

    valueChanged = Signal(int)
    HOUR_VALUES = tuple(range(25))
    MINUTE_VALUES = tuple(range(0, 61, 5))

    def __init__(
        self,
        minimum_minutes: int,
        maximum_minutes: int,
        parent: QWidget | None = None,
        *,
        minute_step: int = 5,
        hour_values: Sequence[int] | None = None,
        minute_values: Sequence[int] | None = None,
        density: SelectorDensity = SelectorDensity.COMPACT,
    ) -> None:
        super().__init__(parent)
        if minimum_minutes <= 0 or maximum_minutes < minimum_minutes:
            raise ValueError("DurationPicker requires a positive, ordered range.")
        if minute_step <= 0:
            raise ValueError("DurationPicker requires a positive minute step.")
        self._hour_values = tuple(hour_values or self.HOUR_VALUES)
        self._minute_values = tuple(minute_values or self.MINUTE_VALUES)
        if not self._hour_values or not self._minute_values:
            raise ValueError("DurationPicker values cannot be empty.")
        if maximum_minutes > max(self._hour_values) * 60 + max(self._minute_values):
            raise ValueError("DurationPicker range exceeds its selectable values.")
        self._minimum_minutes = int(minimum_minutes)
        self._maximum_minutes = int(maximum_minutes)
        self._minute_step = int(minute_step)
        self._updating = False
        self._last_value = 0
        self.setObjectName("durationPicker")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._hours_combo = RoundedComboBox(density=density)
        self._hours_combo.setObjectName("durationHours")
        self._minutes_combo = RoundedComboBox(density=density)
        self._minutes_combo.setObjectName("durationMinutes")
        for value in self._hour_values:
            self._hours_combo.addItem("", value)
        for value in self._minute_values:
            self._minutes_combo.addItem("", value)
        for combo in (self._hours_combo, self._minutes_combo):
            combo.setMinimumWidth(96)
            combo.setMaxVisibleItems(8)
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            combo.view().setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOn
            )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(DESIGN.space_sm)
        layout.addWidget(self._hours_combo, 1)
        layout.addWidget(self._minutes_combo, 1)

        self._hours_combo.currentIndexChanged.connect(self._on_part_changed)
        self._minutes_combo.currentIndexChanged.connect(self._on_part_changed)
        get_localization().language_changed.connect(self.retranslate_ui)
        self.retranslate_ui()
        self.setValue(self._minimum_minutes)

    def value(self) -> int:
        hours = self._hours_combo.currentData()
        minutes = self._minutes_combo.currentData()
        return int(hours or 0) * 60 + int(minutes or 0)

    def setValue(self, minutes: int) -> None:
        normalized = self._normalized_value(minutes)
        if normalized == self._last_value:
            return
        self._set_parts(normalized)
        self._last_value = normalized
        self.valueChanged.emit(normalized)

    def retranslate_ui(self, _language: str | None = None) -> None:
        hours_blocked = self._hours_combo.blockSignals(True)
        minutes_blocked = self._minutes_combo.blockSignals(True)
        for index, value in enumerate(self._hour_values):
            self._hours_combo.setItemText(
                index, f"{value}{tr('quick.hours_suffix')}"
            )
        for index, value in enumerate(self._minute_values):
            self._minutes_combo.setItemText(
                index, f"{value}{tr('quick.minutes_suffix')}"
            )
        self._hours_combo.blockSignals(hours_blocked)
        self._minutes_combo.blockSignals(minutes_blocked)
        self._hours_combo.setAccessibleName(tr("settings.duration_hours"))
        self._hours_combo.setToolTip(tr("settings.duration_hours"))
        self._minutes_combo.setAccessibleName(tr("settings.duration_minutes"))
        self._minutes_combo.setToolTip(tr("settings.duration_minutes"))

    def _normalized_value(self, minutes: int) -> int:
        value = max(self._minimum_minutes, min(self._maximum_minutes, int(minutes)))
        remainder = value % self._minute_step
        if remainder:
            value = min(
                self._maximum_minutes,
                value + self._minute_step - remainder,
            )
        return value

    def _set_parts(self, total_minutes: int) -> None:
        maximum_hour = max(self._hour_values)
        if total_minutes > maximum_hour * 60:
            hours = maximum_hour
            minutes = total_minutes - maximum_hour * 60
        else:
            hours, minutes = divmod(total_minutes, 60)
        self._updating = True
        try:
            self._hours_combo.setCurrentIndex(self._hours_combo.findData(hours))
            self._minutes_combo.setCurrentIndex(self._minutes_combo.findData(minutes))
        finally:
            self._updating = False

    def _on_part_changed(self, _index: int) -> None:
        if self._updating:
            return
        normalized = self._normalized_value(self.value())
        # Always render the canonical hour/minute representation.  In particular,
        # selecting ``60 minutes`` carries into the next hour instead of leaving
        # two equivalent representations such as ``3 hours / 60 minutes``.
        self._set_parts(normalized)
        if normalized != self._last_value:
            self._last_value = normalized
            self.valueChanged.emit(normalized)
