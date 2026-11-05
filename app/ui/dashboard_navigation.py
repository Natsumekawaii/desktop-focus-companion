"""Compact, live-layout navigation motion, independent of page/business state."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QRect, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QHideEvent, QIcon, QPainter, QPaintEvent, QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QStyle,
    QStyleOptionToolButton,
    QStylePainter,
    QToolButton,
    QWidget,
)

from app.core.theme import get_theme_manager


class SidebarFrame(QFrame):
    expanded_width = 160
    collapsed_width = 52
    duration_ms = 180
    progress_changed = Signal(float)
    settled = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.progress = 1.0
        self.target_expanded = True
        self.animation = QVariantAnimation(self)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self._apply_progress)
        self.animation.finished.connect(self.finish)
        self.setFixedWidth(self.expanded_width)

    def set_expanded(self, expanded: bool, *, animate: bool) -> None:
        target = float(expanded)
        if expanded == self.target_expanded and animate:
            return  # Resizing must not restart an in-flight transition.
        self.target_expanded = expanded
        self.animation.stop()
        if not animate or not self.isVisible() or self.progress == target:
            self.finish()
            return
        # QVariantAnimation reevaluates its value when endpoints/duration are
        # assigned. Do not let those configuration frames move live widgets or
        # corrupt the starting progress of a reversal.
        current = self.progress
        blocked = self.animation.blockSignals(True)
        self.animation.setStartValue(current)
        self.animation.setEndValue(target)
        self.animation.setDuration(max(1, round(self.duration_ms * abs(target - current))))
        self.animation.setCurrentTime(0)
        self.animation.blockSignals(blocked)
        self.animation.start()

    def _apply_progress(self, value: object) -> None:
        assert isinstance(value, (float, int))
        self.progress = max(0.0, min(1.0, float(value)))
        self.setFixedWidth(
            round(
                self.collapsed_width
                + (self.expanded_width - self.collapsed_width) * self.progress
            )
        )
        self.progress_changed.emit(self.progress)

    def finish(self) -> None:
        self.animation.stop()
        self._apply_progress(float(self.target_expanded))
        self.settled.emit()

    def hideEvent(self, event: QHideEvent) -> None:
        self.finish()
        super().hideEvent(event)


class NavigationButton(QToolButton):
    """Keep native hit-testing/focus, but reveal text without layout jumps."""

    def __init__(self) -> None:
        super().__init__()
        self.reveal = 1.0
        self.full_text = ""
        self.setMinimumWidth(0)

    def sizeHint(self) -> QSize:
        return QSize(40, 42)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def set_navigation_text(self, text: str) -> None:
        self.full_text = text
        self.set_reveal(self.reveal)

    def set_reveal(self, progress: float) -> None:
        self.reveal = progress
        self.setText(self.full_text if progress > 0 else "")
        self.update()

    def label_rect(self) -> QRect:
        left = round(10 - 2 * self.reveal) + 26
        return QRect(left, 0, max(0, self.width() - left - 8), self.height())

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        option = QStyleOptionToolButton()
        self.initStyleOption(option)
        option.text = ""
        option.icon = QIcon()
        painter = QStylePainter(self)
        painter.drawComplexControl(QStyle.ComplexControl.CC_ToolButton, option)
        icon_rect = QRect(
            round(10 - 2 * self.reveal), (self.height() - 20) // 2, 20, 20
        )
        self.icon().paint(
            painter,
            icon_rect,
            Qt.AlignmentFlag.AlignCenter,
            QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled,
            QIcon.State.On if self.isChecked() else QIcon.State.Off,
        )
        if self.reveal > 0:
            tokens = get_theme_manager().tokens
            color = (
                tokens.primary
                if self.isChecked()
                else tokens.text
                if self.underMouse()
                else tokens.muted
            )
            painter.setPen(color)
            painter.setFont(self.font())
            painter.setOpacity(self.reveal)
            painter.setClipRect(self.label_rect())
            painter.drawText(
                self.label_rect(),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self.full_text,
            )


class NavigationGroup(QLabel):
    """A zero-height group remains in layout so spacing never snaps at the end."""

    def __init__(self) -> None:
        super().__init__()
        self.reveal = 1.0
        self.setObjectName("navigationGroup")

    def set_reveal(self, progress: float) -> None:
        self.reveal = progress
        self.setFixedHeight(round((self.fontMetrics().height() + 16) * progress))
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setPen(get_theme_manager().tokens.text_subtle)
        painter.setFont(self.font())
        painter.setOpacity(self.reveal)
        painter.drawText(
            QRect(8, 12, self.width() - 16, self.fontMetrics().height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.text(),
        )


class SidebarToggleHost(QWidget):
    def __init__(self, button: QToolButton) -> None:
        super().__init__()
        self.button = button
        button.setParent(self)
        self.reveal = 1.0
        self.setFixedHeight(32)

    def set_reveal(self, progress: float) -> None:
        self.reveal = progress
        self.button.move(round(max(0, self.width() - 32) * (1 + progress) / 2), 0)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.set_reveal(self.reveal)
