"""Restrained motion primitives used only by the Focus Panel."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import cast

from PySide6.QtCore import QEasingCurve, QEvent, QObject, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QHideEvent, QMouseEvent
from PySide6.QtWidgets import QAbstractButton, QProgressBar, QRadioButton, QWidget

from app.core.theme import ThemeTokens, get_theme_manager


class PanelButtonRole(str, Enum):
    PRIMARY = "primary"
    DANGER = "danger"
    ICON = "icon"
    DISCLOSURE = "disclosure"
    SEGMENT = "segment"


@dataclass(frozen=True, slots=True)
class _ButtonColors:
    background: QColor
    foreground: QColor
    border: QColor


def _mix_color(start: QColor, end: QColor, progress: float) -> QColor:
    amount = max(0.0, min(1.0, float(progress)))
    return QColor.fromRgbF(
        start.redF() + (end.redF() - start.redF()) * amount,
        start.greenF() + (end.greenF() - start.greenF()) * amount,
        start.blueF() + (end.blueF() - start.blueF()) * amount,
        start.alphaF() + (end.alphaF() - start.alphaF()) * amount,
    )


def _composite_color(foreground: str, background: str, alpha: int) -> QColor:
    """Return an opaque foreground tint composited over a surface color."""

    amount = max(0, min(255, int(alpha))) / 255.0
    result = _mix_color(QColor(background), QColor(foreground), amount)
    result.setAlpha(255)
    return result


def _qss_color(color: QColor) -> str:
    # Qt can briefly paint rgba(..., 1) as opaque black while reparsing a
    # per-widget stylesheet.  Motion colors are pre-composited, so keep every
    # animation frame on the stable opaque RGB path.
    return QColor(color.red(), color.green(), color.blue()).name()


class FocusPanelButtonFeedback(QObject):
    """Animate Focus Panel button colors without touching button geometry."""

    def __init__(self, button: QAbstractButton, role: PanelButtonRole) -> None:
        super().__init__(button)
        self._button = button
        self._role = role
        self._hovered = False
        self._pressed = False
        self._progress = 1.0
        self._start_colors = self._colors_for_state()
        self._target_colors = self._start_colors
        self._current_colors = self._start_colors

        self._animation = QVariantAnimation(self)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._animation_value_changed)
        self._animation.finished.connect(self._animation_finished)

        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        button.installEventFilter(self)
        button.toggled.connect(self._checked_changed)
        get_theme_manager().theme_changed.connect(self._theme_changed)
        self._apply_colors(self._current_colors)

    @property
    def progress(self) -> float:
        return self._progress

    @property
    def is_running(self) -> bool:
        return self._animation.state() == QVariantAnimation.State.Running

    def finish(self) -> None:
        self._animation.stop()
        self._progress = 1.0
        self._current_colors = self._target_colors
        self._apply_colors(self._current_colors)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is not self._button:
            return False
        event_type = event.type()
        if event_type == QEvent.Type.Enter:
            self._hovered = True
            self._animate_to_current_state(120)
        elif event_type == QEvent.Type.Leave:
            self._hovered = False
            self._pressed = False
            self._animate_to_current_state(150)
        elif event_type == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent):
            if event.button() == Qt.MouseButton.LeftButton and self._button.isEnabled():
                self._pressed = True
                self._animate_to_current_state(0)
        elif event_type == QEvent.Type.MouseButtonRelease and isinstance(event, QMouseEvent):
            if event.button() == Qt.MouseButton.LeftButton:
                self._pressed = False
                self._animate_to_current_state(100)
        elif event_type in {
            QEvent.Type.EnabledChange,
            QEvent.Type.FocusIn,
            QEvent.Type.FocusOut,
        }:
            self._pressed = False
            self._animate_to_current_state(0 if event_type == QEvent.Type.EnabledChange else 100)
        elif event_type in {QEvent.Type.Hide, QEvent.Type.Close, QEvent.Type.Destroy}:
            self._animation.stop()
        return False

    def _checked_changed(self, _checked: bool) -> None:
        self._animate_to_current_state(140)

    def _theme_changed(self, _theme_name: str | None = None) -> None:
        self._animation.stop()
        self._start_colors = self._colors_for_state()
        self._target_colors = self._start_colors
        self._current_colors = self._start_colors
        self._progress = 1.0
        self._apply_colors(self._current_colors)

    def _animate_to_current_state(self, duration_ms: int) -> None:
        target = self._colors_for_state()
        self._animation.stop()
        self._start_colors = self._current_colors
        self._target_colors = target
        if duration_ms <= 0 or not self._button.isVisible():
            self._progress = 1.0
            self._current_colors = target
            self._apply_colors(target)
            return
        self._progress = 0.0
        self._animation.setDuration(duration_ms)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.start()

    def _animation_value_changed(self, value: object) -> None:
        progress = max(0.0, min(1.0, float(cast(float, value))))
        self._progress = progress
        self._current_colors = _ButtonColors(
            _mix_color(
                self._start_colors.background,
                self._target_colors.background,
                progress,
            ),
            _mix_color(
                self._start_colors.foreground,
                self._target_colors.foreground,
                progress,
            ),
            _mix_color(
                self._start_colors.border,
                self._target_colors.border,
                progress,
            ),
        )
        self._apply_colors(self._current_colors)

    def _animation_finished(self) -> None:
        self._progress = 1.0
        self._current_colors = self._target_colors
        self._apply_colors(self._current_colors)

    def _colors_for_state(self) -> _ButtonColors:
        tokens = get_theme_manager().tokens
        if not self._button.isEnabled():
            return _ButtonColors(
                QColor(tokens.surface_alt),
                QColor(tokens.disabled),
                QColor(tokens.separator),
            )
        if self._pressed:
            return self._pressed_colors(tokens)
        return self._hover_or_base_colors(tokens)

    def _hover_or_base_colors(self, tokens: ThemeTokens) -> _ButtonColors:
        focused_border = QColor(tokens.focus_ring) if self._button.hasFocus() else None
        if self._role is PanelButtonRole.PRIMARY:
            color = tokens.primary_hover if self._hovered else tokens.primary
            border = focused_border or QColor(color)
            return _ButtonColors(QColor(color), QColor(tokens.primary_text), border)
        if self._role is PanelButtonRole.DANGER:
            background_color = _composite_color(
                tokens.danger,
                tokens.surface_elevated,
                24 if self._hovered else 0,
            )
            border_color = focused_border or QColor(
                tokens.danger if self._hovered else tokens.surface_elevated
            )
            return _ButtonColors(
                background_color,
                QColor(tokens.danger),
                border_color,
            )
        if self._role is PanelButtonRole.ICON:
            background_color = (
                QColor(tokens.primary_soft)
                if self._hovered
                else QColor(tokens.surface_elevated)
            )
            border_color = focused_border or QColor(background_color)
            return _ButtonColors(
                background_color,
                QColor(tokens.text),
                border_color,
            )
        if self._role is PanelButtonRole.DISCLOSURE:
            background_color = (
                QColor(tokens.surface_hover)
                if self._hovered
                else QColor(tokens.surface_elevated)
            )
            border_color = focused_border or QColor(background_color)
            foreground = tokens.text if self._hovered else tokens.muted
            return _ButtonColors(
                background_color,
                QColor(foreground),
                border_color,
            )

        checked = isinstance(self._button, QRadioButton) and self._button.isChecked()
        if checked:
            background_color = QColor(
                tokens.primary_soft if self._hovered else tokens.surface_elevated
            )
            foreground_color = QColor(tokens.primary)
            border_color = QColor(
                tokens.focus_ring if self._button.hasFocus() else tokens.separator
            )
        else:
            background_color = (
                QColor(tokens.surface_hover)
                if self._hovered
                else QColor(tokens.surface_alt)
            )
            foreground_color = QColor(tokens.text if self._hovered else tokens.muted)
            border_color = (
                QColor(tokens.focus_ring)
                if self._button.hasFocus()
                else QColor(background_color)
            )
        return _ButtonColors(
            background_color,
            foreground_color,
            border_color,
        )

    def _pressed_colors(self, tokens: ThemeTokens) -> _ButtonColors:
        if self._role is PanelButtonRole.PRIMARY:
            return _ButtonColors(
                QColor(tokens.primary_pressed),
                QColor(tokens.primary_text),
                QColor(tokens.primary_pressed),
            )
        if self._role is PanelButtonRole.DANGER:
            return _ButtonColors(
                _composite_color(tokens.danger, tokens.surface_elevated, 42),
                QColor(tokens.danger),
                QColor(tokens.danger),
            )
        if self._role in {PanelButtonRole.ICON, PanelButtonRole.DISCLOSURE}:
            return _ButtonColors(
                QColor(tokens.primary_soft),
                QColor(tokens.text),
                QColor(tokens.separator),
            )
        return _ButtonColors(
            QColor(tokens.primary_soft),
            QColor(tokens.text),
            QColor(tokens.border_strong),
        )

    def _apply_colors(self, colors: _ButtonColors) -> None:
        selector = "QRadioButton" if isinstance(self._button, QRadioButton) else "QPushButton"
        self._button.setStyleSheet(
            f"""
            {selector} {{
                background-color: {_qss_color(colors.background)};
                color: {_qss_color(colors.foreground)};
                border-color: {_qss_color(colors.border)};
            }}
            """
        )


class SmoothProgressBar(QProgressBar):
    """A progress bar whose visible fill retargets without queuing animation."""

    def __init__(
        self, parent: QWidget | None = None, *, duration_ms: int = 200
    ) -> None:
        super().__init__(parent)
        self._duration_ms = max(1, int(duration_ms))
        self._target_value = super().value()
        self._visual_value = float(self._target_value)
        self._initialized = False
        self._animation = QVariantAnimation(self)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._animation_value_changed)
        self._animation.finished.connect(self._animation_finished)

    @property
    def target_value(self) -> int:
        return self._target_value

    @property
    def visual_value(self) -> float:
        return self._visual_value

    @property
    def is_animating(self) -> bool:
        return self._animation.state() == QVariantAnimation.State.Running

    def setValue(self, value: int) -> None:
        target = max(self.minimum(), min(self.maximum(), int(value)))
        self._target_value = target
        if not self._initialized or not self.isVisible():
            self._initialized = True
            self.set_value_immediately(target)
            return
        if round(self._visual_value) == target:
            self.set_value_immediately(target)
            return
        self._animation.stop()
        self._animation.setDuration(self._duration_ms)
        self._animation.setStartValue(self._visual_value)
        self._animation.setEndValue(float(target))
        self._animation.start()

    def set_value_immediately(self, value: int | None = None) -> None:
        target = self._target_value if value is None else int(value)
        target = max(self.minimum(), min(self.maximum(), target))
        self._target_value = target
        self._animation.stop()
        self._visual_value = float(target)
        super().setValue(target)

    def finish(self) -> None:
        self.set_value_immediately()

    def hideEvent(self, event: QHideEvent) -> None:
        self.set_value_immediately()
        super().hideEvent(event)

    def _animation_value_changed(self, value: object) -> None:
        self._visual_value = float(cast(float, value))
        super().setValue(round(self._visual_value))

    def _animation_finished(self) -> None:
        self._visual_value = float(self._target_value)
        super().setValue(self._target_value)


__all__ = [
    "FocusPanelButtonFeedback",
    "PanelButtonRole",
    "SmoothProgressBar",
]
