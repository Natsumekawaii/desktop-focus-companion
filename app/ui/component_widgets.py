"""Reusable display and interaction widgets."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from PySide6.QtCore import QEasingCurve, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QHideEvent, QIcon, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.core.theme import DESIGN, get_theme_manager


class SegmentedControl(QFrame):
    """Exclusive, keyboard-friendly choice control for short related options."""

    current_changed = Signal(int)
    value_changed = Signal(object)

    def __init__(
        self,
        segments: Sequence[tuple[str, object]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("segmentedControl")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(2, 2, 2, 2)
        self._layout.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.idClicked.connect(self._on_clicked)
        self._buttons: list[QPushButton] = []
        self._values: list[object] = []
        for text, value in segments or ():
            self.add_segment(text, value)

    @property
    def current_index(self) -> int:
        return self._group.checkedId()

    @property
    def current_value(self) -> object | None:
        index = self.current_index
        return self._values[index] if 0 <= index < len(self._values) else None

    def add_segment(self, text: str, value: object | None = None) -> QPushButton:
        index = len(self._buttons)
        button = QPushButton(text)
        button.setObjectName("segmentButton")
        button.setCheckable(True)
        button.setAutoExclusive(True)
        button.setAccessibleName(text)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._group.addButton(button, index)
        self._layout.addWidget(button)
        self._buttons.append(button)
        self._values.append(index if value is None else value)
        if index == 0:
            button.setChecked(True)
        return button

    def set_current_index(self, index: int, *, emit: bool = False) -> None:
        button = self._group.button(index)
        if button is None or index == self.current_index:
            return
        button.setChecked(True)
        if emit:
            self._emit_selection(index)

    def set_current_value(self, value: object, *, emit: bool = False) -> None:
        try:
            index = self._values.index(value)
        except ValueError:
            return
        self.set_current_index(index, emit=emit)

    def set_segment_text(self, index: int, text: str) -> None:
        if not 0 <= index < len(self._buttons):
            return
        self._buttons[index].setText(text)
        self._buttons[index].setAccessibleName(text)

    def _on_clicked(self, index: int) -> None:
        self._emit_selection(index)

    def _emit_selection(self, index: int) -> None:
        self.current_changed.emit(index)
        self.value_changed.emit(self._values[index])


class IconButton(QPushButton):
    """Compact icon-only button with consistent accessibility metadata."""

    def __init__(
        self,
        text: str = "",
        parent: QWidget | None = None,
        *,
        icon: QIcon | None = None,
        tooltip: str = "",
    ) -> None:
        super().__init__(text, parent)
        self.setObjectName("iconButton")
        self.setFixedSize(DESIGN.control_height_sm, DESIGN.control_height_sm)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if icon is not None:
            self.setIcon(icon)
            self.setIconSize(QSize(DESIGN.icon_md, DESIGN.icon_md))
        self.set_tooltip(tooltip)

    def set_tooltip(self, tooltip: str) -> None:
        self.setToolTip(tooltip)
        self.setAccessibleName(tooltip)


class ListRow(QFrame):
    """Reusable leading/content/trailing row for lightweight data lists."""

    def __init__(
        self,
        title: str = "",
        supporting_text: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("listRow")
        root = QHBoxLayout(self)
        root.setContentsMargins(
            DESIGN.space_md,
            DESIGN.space_sm,
            DESIGN.space_md,
            DESIGN.space_sm,
        )
        root.setSpacing(DESIGN.space_md)
        self.leading_layout = QHBoxLayout()
        self.leading_layout.setContentsMargins(0, 0, 0, 0)
        self.leading_layout.setSpacing(DESIGN.space_sm)
        root.addLayout(self.leading_layout)
        copy_layout = QVBoxLayout()
        copy_layout.setContentsMargins(0, 0, 0, 0)
        copy_layout.setSpacing(DESIGN.space_2xs)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("title")
        self.title_label.setWordWrap(True)
        self.supporting_label = QLabel(supporting_text)
        self.supporting_label.setObjectName("supportingText")
        self.supporting_label.setWordWrap(True)
        self.supporting_label.setVisible(bool(supporting_text))
        copy_layout.addWidget(self.title_label)
        copy_layout.addWidget(self.supporting_label)
        root.addLayout(copy_layout, 1)
        self.trailing_layout = QHBoxLayout()
        self.trailing_layout.setContentsMargins(0, 0, 0, 0)
        self.trailing_layout.setSpacing(DESIGN.space_sm)
        root.addLayout(self.trailing_layout)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

    def set_supporting_text(self, supporting_text: str) -> None:
        self.supporting_label.setText(supporting_text)
        self.supporting_label.setVisible(bool(supporting_text))

    def add_leading(self, widget: QWidget) -> None:
        self.leading_layout.addWidget(widget)

    def add_trailing(self, widget: QWidget) -> None:
        self.trailing_layout.addWidget(widget)


class StatusPill(QLabel):
    """Compact semantic status label with stable cross-locale sizing."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("statusPill")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumWidth(76)
        self.setWordWrap(False)

    def set_success(self, success: bool) -> None:
        self.setObjectName("successPill" if success else "statusPill")
        self.style().unpolish(self)
        self.style().polish(self)


class CircularTimerWidget(QWidget):
    """Theme-aware ring visual for an already-owned timer state."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._progress = 0.0
        self._display_progress = 0.0
        self._primary_text = "00:00:00"
        self._caption = ""
        self.setFixedSize(204, 204)
        self._progress_animation = QVariantAnimation(self)
        self._progress_animation.setDuration(180)
        self._progress_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._progress_animation.valueChanged.connect(
            self._progress_animation_value_changed
        )
        self._progress_animation.finished.connect(
            self._progress_animation_finished
        )
        get_theme_manager().theme_changed.connect(self.update)

    @property
    def progress(self) -> float:
        return self._progress

    @property
    def display_progress(self) -> float:
        return self._display_progress

    @property
    def is_progress_animating(self) -> bool:
        return self._progress_animation.state() == QVariantAnimation.State.Running

    def set_display(self, progress: float, primary_text: str, caption: str) -> None:
        target = max(0.0, min(1.0, float(progress)))
        previous_target = self._progress
        self._progress = target
        self._primary_text = primary_text
        self._caption = caption
        if (
            not self.isVisible()
            or target >= 1.0
            or target < self._display_progress
            or (previous_target == 0.0 and self._display_progress == 0.0 and target == 0.0)
        ):
            self.finish_progress_animation()
            return
        self._progress_animation.stop()
        self._progress_animation.setStartValue(self._display_progress)
        self._progress_animation.setEndValue(target)
        self._progress_animation.start()
        self.update()

    def finish_progress_animation(self) -> None:
        self._progress_animation.stop()
        self._display_progress = self._progress
        self.update()

    def hideEvent(self, event: QHideEvent) -> None:
        self.finish_progress_animation()
        super().hideEvent(event)

    def _progress_animation_value_changed(self, value: object) -> None:
        self._display_progress = max(0.0, min(1.0, float(cast(float, value))))
        self.update()

    def _progress_animation_finished(self) -> None:
        self._display_progress = self._progress
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tokens = get_theme_manager().tokens
        ring = QRectF(15, 15, self.width() - 30, self.height() - 30)
        painter.setPen(
            QPen(
                QColor(tokens.primary_soft),
                12,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
        )
        painter.drawArc(ring, 0, 360 * 16)
        painter.setPen(
            QPen(
                QColor(tokens.primary),
                12,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
        )
        painter.drawArc(ring, 90 * 16, -round(360 * 16 * self._display_progress))

        value_font = QFont(self.font())
        value_font.setPointSize(20)
        value_font.setWeight(QFont.Weight.Bold)
        painter.setFont(value_font)
        painter.setPen(QColor(tokens.text))
        painter.drawText(
            QRectF(12, 66, self.width() - 24, 48),
            Qt.AlignmentFlag.AlignCenter,
            self._primary_text,
        )
        caption_font = QFont(self.font())
        caption_font.setPointSize(10)
        caption_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(caption_font)
        painter.setPen(QColor(tokens.muted))
        painter.drawText(
            QRectF(20, 112, self.width() - 40, 28),
            Qt.AlignmentFlag.AlignCenter,
            self._caption,
        )
