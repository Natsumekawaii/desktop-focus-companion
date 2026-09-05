"""Theme-aware 3-2-1 animation shown before a Focus Session starts."""

from __future__ import annotations

import math

from PySide6.QtCore import QEasingCurve, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from app.core.theme import get_theme_manager
from app.i18n import get_localization, tr


class PreFocusCountdownWidget(QWidget):
    """Render a quiet, cancellable three-second pre-focus countdown."""

    completed = Signal()
    cancelled = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        phase_duration_ms: int = 1_000,
    ) -> None:
        super().__init__(parent)
        self._phase_duration_ms = max(1, int(phase_duration_ms))
        self._active = False
        self._number = 3
        self._phase_progress = 0.0
        self.setObjectName("preFocusCountdown")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(280)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._animation = QVariantAnimation(self)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(3.0)
        self._animation.setDuration(self._phase_duration_ms * 3)
        self._animation.setEasingCurve(QEasingCurve.Type.Linear)
        self._animation.valueChanged.connect(self._on_value_changed)
        self._animation.finished.connect(self._on_finished)

        get_theme_manager().theme_changed.connect(self.update)
        get_localization().language_changed.connect(self._retranslate)
        self._retranslate()

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def current_number(self) -> int:
        return self._number

    def start(self) -> bool:
        """Start once; repeated clicks while running are intentionally ignored."""

        if self._active:
            return False
        self._active = True
        self._number = 3
        self._phase_progress = 0.0
        self._retranslate()
        self._animation.stop()
        self._animation.setDuration(self._phase_duration_ms * 3)
        self._animation.start()
        self.update()
        return True

    def cancel(self) -> bool:
        """Stop without completing or creating any domain timer state."""

        if not self._active:
            return False
        self._animation.stop()
        self._active = False
        self._number = 3
        self._phase_progress = 0.0
        self._retranslate()
        self.update()
        self.cancelled.emit()
        return True

    def _on_value_changed(self, value: float) -> None:
        numeric = max(0.0, min(2.999_999, float(value)))
        phase_index = min(2, int(numeric))
        number = 3 - phase_index
        self._phase_progress = numeric - phase_index
        if number != self._number:
            self._number = number
            self._retranslate()
        self.update()

    def _on_finished(self) -> None:
        if not self._active:
            return
        self._active = False
        self._phase_progress = 1.0
        self.update()
        self.completed.emit()

    def _retranslate(self, _language: str | None = None) -> None:
        self.setAccessibleName(
            tr("quick.prestart_accessible", count=self._number)
        )
        self.setToolTip(tr("quick.prestart_caption"))
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        tokens = get_theme_manager().tokens
        center = self.rect().center()
        available = max(150.0, min(float(self.width()), float(self.height())) - 92.0)
        diameter = min(224.0, available)
        radius = diameter / 2.0
        ring_center_y = float(center.y()) - 13.0
        ring_rect = QRectF(
            float(center.x()) - radius,
            ring_center_y - radius,
            diameter,
            diameter,
        )

        progress = max(0.0, min(1.0, self._phase_progress))
        eased = QEasingCurve(QEasingCurve.Type.OutCubic).valueForProgress(progress)
        breathe = math.sin(math.pi * progress)
        fade_in = min(1.0, progress / 0.14) if progress > 0.0 else 0.0
        fade_out = min(1.0, (1.0 - progress) / 0.20)
        number_opacity = max(0.0, min(fade_in, fade_out))

        soft = QColor(tokens.primary_soft)
        soft.setAlphaF(0.92)
        painter.setPen(
            QPen(
                soft,
                11.0,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
        )
        painter.drawEllipse(ring_rect)

        primary = QColor(tokens.primary)
        pulse = QColor(primary)
        pulse.setAlphaF(0.13 * breathe)
        pulse_width = 2.0 + 3.0 * breathe
        pulse_rect = ring_rect.adjusted(
            -10.0 * eased,
            -10.0 * eased,
            10.0 * eased,
            10.0 * eased,
        )
        painter.setPen(QPen(pulse, pulse_width))
        painter.drawEllipse(pulse_rect)

        arc = QColor(primary)
        arc.setAlphaF(0.72 + 0.28 * breathe)
        painter.setPen(
            QPen(
                arc,
                11.0,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
        )
        painter.drawArc(
            ring_rect,
            90 * 16,
            -round(max(0.035, progress) * 360 * 16),
        )

        scale = 0.84 + 0.19 * eased - 0.03 * progress
        painter.save()
        painter.translate(float(center.x()), ring_center_y)
        painter.scale(scale, scale)
        painter.setOpacity(number_opacity)
        number_font = QFont(self.font())
        number_font.setPointSize(68)
        number_font.setWeight(QFont.Weight.Bold)
        painter.setFont(number_font)
        painter.setPen(primary)
        painter.drawText(
            QRectF(-radius, -radius, diameter, diameter),
            Qt.AlignmentFlag.AlignCenter,
            str(self._number),
        )
        painter.restore()

        caption = (
            tr("quick.prestart_begin")
            if self._number == 1 and progress >= 0.76
            else tr("quick.prestart_caption")
        )
        caption_font = QFont(self.font())
        caption_font.setPointSize(11)
        caption_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(caption_font)
        painter.setPen(QColor(tokens.text if caption == tr("quick.prestart_begin") else tokens.muted))
        painter.drawText(
            QRectF(16.0, ring_rect.bottom() + 18.0, self.width() - 32.0, 30.0),
            Qt.AlignmentFlag.AlignCenter,
            caption,
        )
        painter.end()


__all__ = ["PreFocusCountdownWidget"]
