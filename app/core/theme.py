"""Central, runtime-switchable design system for every Desktop Focus Companion surface."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QEvent,
    QObject,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent, QPalette, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QFileDialog,
    QMenu,
    QMessageBox,
    QWidget,
)

DEFAULT_COLOR_THEME = "lavender"
COLOR_THEMES = ("default", "lavender", "pink", "blue", "dark", "charcoal")
DEFAULT_FONT_LANGUAGE = "en-US"
FONT_FAMILY_STACKS: dict[str, tuple[str, ...]] = {
    "zh-CN": (
        "Microsoft YaHei UI",
        "Microsoft YaHei",
        "DengXian",
        "Noto Sans SC",
        "SimHei",
        "sans-serif",
    ),
    "en-US": (
        "Segoe UI",
        "Microsoft YaHei UI",
        "Microsoft YaHei",
        "Noto Sans SC",
        "Arial",
        "sans-serif",
    ),
}


@dataclass(frozen=True, slots=True)
class DesignMetrics:
    """Shared geometry and type tokens used by hand-built Qt layouts."""

    space_2xs: int = 2
    space_xs: int = 4
    space_sm: int = 8
    space_md: int = 12
    space_lg: int = 16
    space_xl: int = 24
    space_2xl: int = 32
    space_3xl: int = 48
    radius_xs: int = 6
    radius_sm: int = 8
    radius_md: int = 12
    radius_lg: int = 16
    radius_xl: int = 22
    control_height_sm: int = 30
    control_height: int = 36
    control_height_lg: int = 44
    icon_sm: int = 16
    icon_md: int = 20
    icon_lg: int = 24
    font_caption: int = 11
    font_body: int = 13
    font_body_lg: int = 14
    font_section: int = 17
    font_title: int = 28
    font_display: int = 36
    sidebar_width: int = 208
    sidebar_collapsed_width: int = 60
    sidebar_breakpoint: int = 900
    content_max_width: int = 1320


DESIGN = DesignMetrics()


@dataclass(frozen=True, slots=True)
class ThemeTokens:
    canvas: str
    surface: str
    surface_alt: str
    surface_elevated: str
    surface_hover: str
    input: str
    text: str
    muted: str
    text_subtle: str
    primary: str
    primary_soft: str
    primary_hover: str
    primary_pressed: str
    primary_text: str
    border: str
    border_strong: str
    separator: str
    disabled: str
    focus_ring: str
    shadow: str
    success: str
    warning: str
    danger: str
    chart_grid: str
    chart_palette: tuple[str, str, str, str, str, str, str, str]
    heatmap_levels: tuple[str, str, str, str, str, str]

    @property
    def elevated(self) -> str:
        """Compatibility-friendly semantic alias for elevated surfaces."""
        return self.surface_elevated

    @property
    def accent(self) -> str:
        """Semantic alias used by newer presentation components."""
        return self.primary


THEME_TOKENS: dict[str, ThemeTokens] = {
    "default": ThemeTokens(
        canvas="#f4f6f8",
        surface="#ffffff",
        surface_alt="#f8fafb",
        surface_elevated="#ffffff",
        surface_hover="#eef2f5",
        input="#ffffff",
        text="#20262c",
        muted="#66717c",
        text_subtle="#89939d",
        primary="#506b7b",
        primary_soft="#e7edf1",
        primary_hover="#435d6c",
        primary_pressed="#364f5e",
        primary_text="#ffffff",
        border="#d9dfe4",
        border_strong="#c1cbd2",
        separator="#e7ebee",
        disabled="#9aa3ab",
        focus_ring="#6f8b9b",
        shadow="#1d2933",
        success="#377a5b",
        warning="#9b622d",
        danger="#aa4149",
        chart_grid="#e8ecef",
        chart_palette=("#506b7b", "#6f8ea0", "#78a08c", "#b78a57", "#997ba8", "#bf6f77", "#5f8d9b", "#8b9380"),
        heatmap_levels=("#edf1f3", "#d3dfe4", "#adc3cd", "#84a6b5", "#628897", "#426876"),
    ),
    "lavender": ThemeTokens(
        canvas="#f7f5f9",
        surface="#ffffff",
        surface_alt="#fbfafc",
        surface_elevated="#ffffff",
        surface_hover="#f1edf4",
        input="#ffffff",
        text="#29252e",
        muted="#6f6877",
        text_subtle="#918998",
        primary="#74558d",
        primary_soft="#eee8f3",
        primary_hover="#65477e",
        primary_pressed="#563a6e",
        primary_text="#ffffff",
        border="#e2dce6",
        border_strong="#cdc3d3",
        separator="#ece8ef",
        disabled="#9b929f",
        focus_ring="#8d6da5",
        shadow="#2b2232",
        success="#397b5d",
        warning="#9b622f",
        danger="#aa4655",
        chart_grid="#ece8ef",
        chart_palette=("#74558d", "#9676ad", "#6f92a0", "#71977e", "#b28459", "#bd7080", "#817ba8", "#9b8b71"),
        heatmap_levels=("#f0edf2", "#ded4e5", "#c4afd1", "#a587b7", "#84649a", "#624575"),
    ),
    "pink": ThemeTokens(
        canvas="#fbf6f8",
        surface="#ffffff",
        surface_alt="#fdfafb",
        surface_elevated="#ffffff",
        surface_hover="#f8edf1",
        input="#ffffff",
        text="#30262a",
        muted="#75686e",
        text_subtle="#97888e",
        primary="#a84f72",
        primary_soft="#f5e5eb",
        primary_hover="#963f63",
        primary_pressed="#823352",
        primary_text="#ffffff",
        border="#e8dbe0",
        border_strong="#d5c1c9",
        separator="#f0e7ea",
        disabled="#a2959a",
        focus_ring="#bd6e8c",
        shadow="#34232a",
        success="#3e7d60",
        warning="#9d622c",
        danger="#ad3f50",
        chart_grid="#f0e7ea",
        chart_palette=("#a84f72", "#c07892", "#8173a3", "#5d8d9d", "#729480", "#b48557", "#927484", "#6f8892"),
        heatmap_levels=("#f6ecef", "#ecd2dc", "#dcaabd", "#c97e9b", "#ad5778", "#833c59"),
    ),
    "blue": ThemeTokens(
        canvas="#f4f8fb",
        surface="#ffffff",
        surface_alt="#f9fbfd",
        surface_elevated="#ffffff",
        surface_hover="#eaf2f7",
        input="#ffffff",
        text="#222b31",
        muted="#63727c",
        text_subtle="#85939d",
        primary="#3f7196",
        primary_soft="#e3eef5",
        primary_hover="#336384",
        primary_pressed="#29546f",
        primary_text="#ffffff",
        border="#d7e2e9",
        border_strong="#bcced9",
        separator="#e6edf1",
        disabled="#94a1a9",
        focus_ring="#5e88a7",
        shadow="#1e2d37",
        success="#35795f",
        warning="#99612c",
        danger="#a9434d",
        chart_grid="#e5edf2",
        chart_palette=("#3f7196", "#6390af", "#6b9480", "#a58158", "#8574a3", "#b96d7b", "#4f8998", "#8d9275"),
        heatmap_levels=("#eaf1f5", "#cedee8", "#a7c5d6", "#7eabc3", "#588dab", "#3b6d89"),
    ),
    "dark": ThemeTokens(
        canvas="#19191d",
        surface="#222227",
        surface_alt="#29292f",
        surface_elevated="#303037",
        surface_hover="#34343b",
        input="#1e1e23",
        text="#f2f0f4",
        muted="#b2acb7",
        text_subtle="#8f8995",
        primary="#b18ad0",
        primary_soft="#3b3143",
        primary_hover="#c09bdc",
        primary_pressed="#9d75bd",
        primary_text="#211826",
        border="#414148",
        border_strong="#5b5962",
        separator="#35353b",
        disabled="#77737c",
        focus_ring="#c09bdc",
        shadow="#070708",
        success="#69b58e",
        warning="#d49a65",
        danger="#df7882",
        chart_grid="#35353c",
        chart_palette=("#b18ad0", "#7ea9c7", "#7fb493", "#d1a16d", "#d08091", "#8f87c3", "#68aab2", "#b0ae7e"),
        heatmap_levels=("#2c2c32", "#453b4d", "#604b6d", "#7d5c8f", "#9d71b4", "#bd8bd4"),
    ),
    "charcoal": ThemeTokens(
        canvas="#101114",
        surface="#181A1E",
        surface_alt="#1E2126",
        surface_elevated="#25282E",
        surface_hover="#2D3138",
        input="#14161A",
        text="#FFFFFF",
        muted="#D2D5DA",
        text_subtle="#9EA4AD",
        primary="#D8DCE2",
        primary_soft="#30343A",
        primary_hover="#EEF0F3",
        primary_pressed="#BDC3CB",
        primary_text="#111317",
        border="#3B3F46",
        border_strong="#5A606A",
        separator="#2B2E34",
        disabled="#767C85",
        focus_ring="#FFFFFF",
        shadow="#000000",
        success="#70C596",
        warning="#E0A368",
        danger="#EF7C88",
        chart_grid="#2B2F35",
        chart_palette=("#D8DCE2", "#82AFD1", "#7FC09A", "#D9A76F", "#D18495", "#A69AD6", "#70B3BC", "#B6BB82"),
        heatmap_levels=("#22252A", "#2F3339", "#3B4048", "#484E57", "#565D67", "#646D79"),
    ),
}


def normalize_color_theme(value: object) -> str:
    """Return a supported theme, falling back safely to Lavender."""
    return value if isinstance(value, str) and value in COLOR_THEMES else DEFAULT_COLOR_THEME


def font_families_for_language(language: object) -> tuple[str, ...]:
    """Return a stable UI font stack without allowing a serif CJK fallback."""
    target = (
        language
        if isinstance(language, str) and language in FONT_FAMILY_STACKS
        else DEFAULT_FONT_LANGUAGE
    )
    return FONT_FAMILY_STACKS[target]


def _snapshot_is_opaque(snapshot: QPixmap) -> bool:
    """Use representative pixels to select the safe backing-store paint mode."""

    if snapshot.isNull():
        return False
    image = snapshot.toImage()
    if image.isNull() or image.width() <= 0 or image.height() <= 0:
        return False
    right = image.width() - 1
    bottom = image.height() - 1
    points = (
        (0, 0),
        (right, 0),
        (0, bottom),
        (right, bottom),
        (right // 2, bottom // 2),
    )
    return all(image.pixelColor(x, y).alpha() == 255 for x, y in points)


class _ThemeSnapshotOverlay(QWidget):
    """Mouse-transparent dual snapshot that never exposes an unpainted window."""

    finished = Signal(object)

    def __init__(self, parent: QWidget, snapshot: QPixmap, duration_ms: int) -> None:
        super().__init__(parent)
        self._source_snapshot = snapshot
        self._target_snapshot: QPixmap | None = None
        self._opacity = 1.0
        self._finished = False
        self._duration_ms = duration_ms
        self.setObjectName("themeTransitionOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(
            Qt.WidgetAttribute.WA_OpaquePaintEvent,
            _snapshot_is_opaque(snapshot),
        )
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet("background: transparent; border: 0;")
        self.setGeometry(parent.rect())
        parent.installEventFilter(self)

        self._animation = QPropertyAnimation(self, b"overlayOpacity", self)
        self._animation.setDuration(duration_ms)
        self._animation.setStartValue(1.0)
        self._animation.setEndValue(0.0)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.finished.connect(self.finish)
        self._deadline_timer = QTimer(self)
        self._deadline_timer.setSingleShot(True)
        self._deadline_timer.timeout.connect(self.finish)

    def start(self) -> None:
        if self._target_snapshot is None:
            self.finish()
            return
        self.show()
        self.raise_()
        self.repaint()
        self._animation.start()
        self._deadline_timer.start(self._duration_ms + 20)

    def capture_target(self) -> bool:
        """Capture the fully themed parent while remaining hidden from the grab."""

        parent = self.parentWidget()
        if parent is None or not parent.isVisible():
            return False
        self.hide()
        target = parent.grab()
        self.show()
        self.raise_()
        if target.isNull():
            return False
        self._target_snapshot = target
        self.setAttribute(
            Qt.WidgetAttribute.WA_OpaquePaintEvent,
            _snapshot_is_opaque(self._source_snapshot)
            and _snapshot_is_opaque(target),
        )
        self.repaint()
        return True

    def current_frame(self) -> QPixmap:
        """Return the exact composited frame used as a rapid-switch source."""

        ratio = max(1.0, self.devicePixelRatioF())
        frame = QPixmap(
            max(1, round(self.width() * ratio)),
            max(1, round(self.height() * ratio)),
        )
        frame.setDevicePixelRatio(ratio)
        frame.fill(Qt.GlobalColor.transparent)
        painter = QPainter(frame)
        self._paint_snapshots(painter, self.rect())
        painter.end()
        return frame

    def finish(self) -> None:
        if self._finished:
            return
        self._finished = True
        self._animation.stop()
        self._deadline_timer.stop()
        parent = self.parentWidget()
        if parent is not None:
            parent.removeEventFilter(self)
        self.hide()
        self.finished.emit(self)
        self.deleteLater()

    def opacity(self) -> float:
        return self._opacity

    def set_opacity(self, value: float) -> None:
        self._opacity = max(0.0, min(1.0, float(value)))
        self.update()

    overlayOpacity = Property(float, opacity, set_opacity)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.parentWidget():
            if event.type() == QEvent.Type.Resize:
                parent = self.parentWidget()
                if parent is not None:
                    self.setGeometry(parent.rect())
                return False
            if event.type() in {
                QEvent.Type.Hide,
                QEvent.Type.Close,
            }:
                self.finish()
        return False

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        if not self.testAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent):
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceOver
            )
        self._paint_snapshots(painter, self.rect())
        painter.end()

    def _paint_snapshots(self, painter: QPainter, target_rect: QRect) -> None:
        if self._target_snapshot is not None:
            painter.setOpacity(1.0)
            painter.drawPixmap(target_rect, self._target_snapshot)
        painter.setOpacity(self._opacity)
        painter.drawPixmap(target_rect, self._source_snapshot)
        painter.setOpacity(1.0)


class _ThemeTransitionCoordinator(QObject):
    """Capture and fade all eligible visible application surfaces together."""

    duration_ms = 220

    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        self._overlays: list[_ThemeSnapshotOverlay] = []

    @property
    def active_overlays(self) -> tuple[_ThemeSnapshotOverlay, ...]:
        return tuple(self._overlays)

    def prepare(self, application: QApplication) -> bool:
        self._dismiss_transient_windows(application)
        candidates = [
            widget
            for widget in application.topLevelWidgets()
            if self._is_eligible(widget)
        ]
        existing_by_parent = {
            overlay.parentWidget(): overlay for overlay in self._overlays
        }
        snapshots = [
            (
                widget,
                existing_by_parent[widget].current_frame()
                if widget in existing_by_parent
                else widget.grab(),
            )
            for widget in candidates
        ]
        self.finish_all()
        for widget, snapshot in snapshots:
            if snapshot.isNull() or not widget.isVisible():
                continue
            overlay = _ThemeSnapshotOverlay(widget, snapshot, self.duration_ms)
            overlay.finished.connect(self._overlay_finished)
            overlay.show()
            overlay.raise_()
            overlay.repaint()
            self._overlays.append(overlay)
        return bool(self._overlays)

    def start(self) -> None:
        for overlay in tuple(self._overlays):
            if overlay.capture_target():
                overlay.start()
            else:
                parent = overlay.parentWidget()
                overlay.finish()
                # A failed target grab must degrade to a fully painted instant
                # switch.  Repaint synchronously before yielding to Windows so
                # the backing store can never expose an intermediate black frame.
                if parent is not None and parent.isVisible():
                    parent.repaint()

    def finish_all(self) -> None:
        for overlay in tuple(self._overlays):
            overlay.finish()
        self._overlays.clear()

    def _overlay_finished(self, value: object) -> None:
        if isinstance(value, _ThemeSnapshotOverlay) and value in self._overlays:
            self._overlays.remove(value)

    @staticmethod
    def _is_eligible(widget: QWidget) -> bool:
        if not widget.isVisible() or bool(widget.property("themeTransitionExcluded")):
            return False
        if isinstance(widget, (QColorDialog, QFileDialog, QMenu, QMessageBox)):
            return False
        return widget.windowType() not in {
            Qt.WindowType.Popup,
            Qt.WindowType.ToolTip,
        }

    @staticmethod
    def _dismiss_transient_windows(application: QApplication) -> None:
        for widget in application.topLevelWidgets():
            if not widget.isVisible() or not bool(
                widget.property("themeTransitionTransient")
            ):
                continue
            hide_immediately = getattr(widget, "hide_immediately", None)
            if callable(hide_immediately):
                hide_immediately()
            else:
                widget.hide()


class ThemeManager(QObject):
    """Apply one global Qt palette and stylesheet and broadcast token changes."""

    theme_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._theme_name = DEFAULT_COLOR_THEME
        self._font_language = DEFAULT_FONT_LANGUAGE
        self._transition = _ThemeTransitionCoordinator(self)

    @property
    def theme_name(self) -> str:
        return self._theme_name

    @property
    def tokens(self) -> ThemeTokens:
        return THEME_TOKENS[self._theme_name]

    @property
    def font_language(self) -> str:
        return self._font_language

    @property
    def font_families(self) -> tuple[str, ...]:
        return font_families_for_language(self._font_language)

    def set_theme(self, theme_name: object) -> str:
        target = normalize_color_theme(theme_name)
        if target == self._theme_name:
            return target
        application = QApplication.instance()
        prepared = False
        if isinstance(application, QApplication):
            prepared = self._transition.prepare(application)
        self._theme_name = target
        self._apply()
        self.theme_changed.emit(target)
        if prepared:
            self._transition.start()
        return target

    def set_language(self, language: object) -> str:
        """Apply the locale-appropriate UI font immediately to every window."""
        self._font_language = (
            language
            if isinstance(language, str) and language in FONT_FAMILY_STACKS
            else DEFAULT_FONT_LANGUAGE
        )
        self._apply()
        return self._font_language

    def _apply(self) -> None:
        application = QApplication.instance()
        if not isinstance(application, QApplication):
            return
        font = QFont(application.font())
        font.setFamilies(list(self.font_families))
        application.setFont(font)
        application.setPalette(_palette(self.tokens))
        application.setStyleSheet(_style_sheet(self.tokens))


_theme_manager: ThemeManager | None = None


def get_theme_manager() -> ThemeManager:
    global _theme_manager
    if _theme_manager is None:
        _theme_manager = ThemeManager()
    return _theme_manager


def _palette(tokens: ThemeTokens) -> QPalette:
    palette = QPalette()
    colors = {
        QPalette.ColorRole.Window: tokens.canvas,
        QPalette.ColorRole.WindowText: tokens.text,
        QPalette.ColorRole.Base: tokens.input,
        QPalette.ColorRole.AlternateBase: tokens.surface_alt,
        QPalette.ColorRole.ToolTipBase: tokens.surface,
        QPalette.ColorRole.ToolTipText: tokens.text,
        QPalette.ColorRole.Text: tokens.text,
        QPalette.ColorRole.Button: tokens.surface,
        QPalette.ColorRole.ButtonText: tokens.text,
        QPalette.ColorRole.Highlight: tokens.primary,
        QPalette.ColorRole.HighlightedText: tokens.primary_text,
        QPalette.ColorRole.PlaceholderText: tokens.muted,
        QPalette.ColorRole.Link: tokens.primary,
        QPalette.ColorRole.LinkVisited: tokens.primary_pressed,
        QPalette.ColorRole.Light: tokens.surface_elevated,
        QPalette.ColorRole.Mid: tokens.border,
        QPalette.ColorRole.Dark: tokens.border_strong,
    }
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(tokens.disabled))
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.ButtonText,
        QColor(tokens.disabled),
    )
    return palette


def _style_sheet(tokens: ThemeTokens) -> str:
    return "".join(
        (
            _base_style_sheet(tokens),
            _navigation_style_sheet(tokens),
            _surface_style_sheet(tokens),
            _typography_style_sheet(tokens),
            _control_style_sheet(tokens),
            _input_style_sheet(tokens),
            _floating_style_sheet(tokens),
        )
    )


def _base_style_sheet(tokens: ThemeTokens) -> str:
    return f"""
        * {{
            font-size: {DESIGN.font_body}px;
        }}
        QMainWindow, QDialog, QMessageBox, QScrollArea {{
            background: {tokens.canvas}; color: {tokens.text};
        }}
        QWidget {{
            color: {tokens.text};
            selection-background-color: {tokens.primary};
            selection-color: {tokens.primary_text};
        }}
        QLabel {{ background: transparent; }}
        QFrame#appShell, QFrame#settingsPage, QWidget#settingsPage,
        QStackedWidget#focusPanelStack, QStackedWidget#timerVisualStack {{
            background: transparent; border: 0;
        }}

"""


def _navigation_style_sheet(tokens: ThemeTokens) -> str:
    return f"""        /* Navigation shells */
        QFrame#sidebar, QFrame#settingsSidebar {{
            background: {tokens.surface};
            border: 0; border-right: 1px solid {tokens.separator};
        }}
        QLabel#navigationGroup {{
            color: {tokens.text_subtle}; font-size: {DESIGN.font_caption}px;
            font-weight: 700; padding: 12px 12px 4px 12px;
        }}
        QToolButton#navigationButton, QPushButton#navigationButton,
        QPushButton#sidebarNavButton {{
            background: transparent; color: {tokens.muted};
            border: 1px solid transparent; border-radius: {DESIGN.radius_sm}px;
            min-height: 24px; padding: 8px 12px; text-align: left;
            font-weight: 600;
        }}
        QToolButton#navigationButton:hover, QPushButton#navigationButton:hover,
        QPushButton#sidebarNavButton:hover {{
            background: {tokens.surface_hover}; color: {tokens.text};
        }}
        QToolButton#navigationButton:pressed, QPushButton#navigationButton:pressed,
        QPushButton#sidebarNavButton:pressed {{
            background: {tokens.primary_soft}; color: {tokens.primary};
        }}
        QToolButton#navigationButton:checked, QPushButton#navigationButton:checked,
        QPushButton#sidebarNavButton:checked {{
            background: {tokens.primary_soft}; color: {tokens.primary};
            border-color: {tokens.separator};
        }}
        QToolButton#navigationButton:focus, QPushButton#navigationButton:focus,
        QPushButton#sidebarNavButton:focus {{
            border-color: {tokens.focus_ring};
        }}

"""


def _surface_style_sheet(tokens: ThemeTokens) -> str:
    return f"""        /* Surface hierarchy */
        QDialog#quickPanel {{
            background: transparent; border: none;
        }}
        QFrame#focusPanelSurface {{
            background: {tokens.surface_elevated}; border: 1px solid {tokens.border_strong};
            border-radius: {DESIGN.radius_lg}px;
        }}
        QFrame#card {{
            background: {tokens.surface}; border: 1px solid {tokens.separator};
            border-radius: {DESIGN.radius_md}px;
        }}
        QFrame#heroCard {{
            background: {tokens.primary_soft}; border: 1px solid {tokens.border};
            border-radius: {DESIGN.radius_lg}px;
        }}
        QFrame#softCard {{
            background: {tokens.surface_alt}; border: 1px solid transparent;
            border-radius: {DESIGN.radius_md}px;
        }}
        QFrame#sectionSurface {{
            background: {tokens.surface}; border: 1px solid {tokens.separator};
            border-radius: {DESIGN.radius_lg}px;
        }}
        QFrame#settingsSection {{
            background: {tokens.surface}; border: 1px solid {tokens.separator};
            border-radius: {DESIGN.radius_lg}px;
        }}
        QFrame#focusSummary {{
            background: {tokens.primary_soft}; border: 1px solid {tokens.separator};
            border-radius: {DESIGN.radius_md}px;
        }}
        QFrame#metricStrip {{
            background: {tokens.surface_alt}; border: 1px solid {tokens.separator};
            border-radius: {DESIGN.radius_md}px;
        }}
        QFrame#metricItem {{ background: transparent; border: 0; }}
        QFrame#emptyState {{
            background: {tokens.surface_alt}; border: 1px solid {tokens.separator};
            border-radius: {DESIGN.radius_md}px;
        }}
        QFrame#listRow {{
            background: transparent; border: 1px solid transparent;
            border-radius: {DESIGN.radius_sm}px;
        }}
        QFrame#listRow:hover {{
            background: {tokens.surface_hover}; border-color: {tokens.separator};
        }}
        QFrame#focusItemCard {{
            background: {tokens.surface}; border: 1px solid {tokens.separator};
            border-radius: {DESIGN.radius_md}px;
        }}
        QFrame#focusItemCard:hover {{
            background: {tokens.surface_hover}; border-color: {tokens.border_strong};
        }}
        QListWidget#focusItemManagementList {{
            padding: 4px 0; border-radius: {DESIGN.radius_md}px;
            outline: 0; selection-background-color: transparent;
        }}
        QListWidget#focusItemManagementList::item {{
            background: transparent; border: 0; padding: 0; outline: 0;
        }}
        QListWidget#focusItemManagementList::item:hover,
        QListWidget#focusItemManagementList::item:selected {{
            background: transparent; color: {tokens.text};
        }}
        QFrame#focusItemManagementCard {{
            background: {tokens.surface}; border: 1px solid {tokens.separator};
            border-radius: {DESIGN.radius_md + 2}px;
        }}
        QFrame#focusItemManagementCard:hover {{
            background: {tokens.surface_hover}; border-color: {tokens.border_strong};
        }}
        QFrame#focusItemManagementCard[selected="true"] {{
            background: {tokens.primary_soft}; border-color: {tokens.focus_ring};
        }}
        QWidget#distributionRow {{
            background: transparent; border-radius: {DESIGN.radius_sm}px;
        }}
        QWidget#distributionRow:hover {{ background: {tokens.surface_hover}; }}

"""


def _typography_style_sheet(tokens: ThemeTokens) -> str:
    return f"""        /* Type hierarchy */
        QLabel#pageTitle {{
            color: {tokens.text}; font-size: {DESIGN.font_title}px; font-weight: 700;
        }}
        QLabel#pageSubtitle {{
            color: {tokens.muted}; font-size: {DESIGN.font_body_lg}px;
        }}
        QLabel#sectionTitle, QLabel#title {{
            color: {tokens.text}; font-size: {DESIGN.font_section}px; font-weight: 700;
        }}
        QLabel#cardCaption {{
            color: {tokens.muted}; font-size: 12px; font-weight: 600;
        }}
        QLabel#metricValue, QLabel#todayValue, QLabel#timerValue {{
            color: {tokens.primary}; font-size: 25px; font-weight: 700;
        }}
        QLabel#stopwatchTimerValue {{
            color: {tokens.primary}; font-size: 42px; font-weight: 700;
        }}
        QLabel#heroValue {{
            color: {tokens.primary}; font-size: {DESIGN.font_display}px; font-weight: 700;
        }}
        QLabel#emptyStateIcon {{
            color: {tokens.primary}; font-size: 26px; font-weight: 600;
        }}
        QLabel#emptyStateTitle {{
            color: {tokens.text}; font-size: {DESIGN.font_section}px; font-weight: 700;
        }}
        QLabel#emptyStateMessage, QLabel#supportingText {{
            color: {tokens.muted}; font-size: {DESIGN.font_body}px;
        }}
        QLabel#statusPill {{
            background: {tokens.primary}; color: {tokens.primary_text};
            border-radius: 10px; padding: 3px 10px; font-size: 12px;
            font-weight: 700;
        }}
        QLabel#successPill {{
            background: {tokens.success}; color: #ffffff;
            border-radius: 10px; padding: 3px 10px; font-size: 12px;
            font-weight: 700;
        }}
        QLabel#pausedPill {{
            background: {tokens.warning}; color: #ffffff;
            border-radius: 10px; padding: 3px 10px; font-size: 12px;
            font-weight: 700;
        }}
        QLabel#secondary {{ color: {tokens.muted}; }}
        QLabel#insightValue {{
            color: {tokens.text}; font-size: {DESIGN.font_body_lg}px; font-weight: 700;
        }}
        QLabel#settingsRowTitle {{ color: {tokens.text}; font-weight: 700; }}

"""


def _control_style_sheet(tokens: ThemeTokens) -> str:
    return f"""        /* Buttons and segmented controls */
        QPushButton {{
            background: {tokens.surface}; color: {tokens.text};
            border: 1px solid {tokens.border}; border-radius: {DESIGN.radius_sm}px;
            min-height: 20px; padding: 7px 13px; font-weight: 600;
        }}
        QPushButton:hover {{
            background: {tokens.surface_hover}; border-color: {tokens.border_strong};
        }}
        QPushButton:pressed {{ background: {tokens.primary_soft}; }}
        QPushButton:focus {{ border-color: {tokens.focus_ring}; }}
        QPushButton:disabled {{
            background: {tokens.surface_alt}; color: {tokens.disabled};
            border-color: {tokens.separator};
        }}
        QPushButton#primary {{
            background: {tokens.primary}; color: {tokens.primary_text};
            border-color: {tokens.primary};
        }}
        QPushButton#primary:hover {{
            background: {tokens.primary_hover}; color: {tokens.primary_text};
            border-color: {tokens.primary_hover};
        }}
        QPushButton#primary:pressed {{
            background: {tokens.primary_pressed}; color: {tokens.primary_text};
            border-color: {tokens.primary_pressed};
        }}
        QPushButton#primary:focus {{ border-color: {tokens.focus_ring}; }}
        QPushButton#ghost {{
            background: transparent; border-color: transparent; color: {tokens.muted};
        }}
        QPushButton#ghost:hover {{ background: {tokens.surface_hover}; color: {tokens.text}; }}
        QPushButton#disclosureButton {{
            background: transparent; color: {tokens.muted}; border-color: transparent;
            text-align: left; padding: 6px 4px;
        }}
        QPushButton#disclosureButton:hover {{
            background: {tokens.surface_hover}; color: {tokens.text};
        }}
        QPushButton#danger {{
            background: transparent; color: {tokens.danger}; border-color: {tokens.separator};
        }}
        QPushButton#danger:hover {{ background: {tokens.surface_hover}; border-color: {tokens.danger}; }}
        QPushButton#iconButton {{
            background: transparent; border: 0; padding: 0;
            min-width: {DESIGN.control_height_sm}px; max-width: {DESIGN.control_height_sm}px;
            min-height: {DESIGN.control_height_sm}px; max-height: {DESIGN.control_height_sm}px;
            font-size: 18px; font-weight: 600;
        }}
        QPushButton#iconButton:hover {{ background: {tokens.primary_soft}; }}
        QPushButton#iconButton:focus {{
            border: 1px solid {tokens.focus_ring}; border-radius: {DESIGN.radius_sm}px;
        }}
        QPushButton#themeSwatch {{
            background: {tokens.surface}; border: 1px solid {tokens.border};
            border-radius: {DESIGN.radius_md}px; padding: 5px;
        }}
        QPushButton#themeSwatch:hover {{
            background: {tokens.surface_hover}; border-color: {tokens.border_strong};
        }}
        QPushButton#themeSwatch:checked {{
            background: {tokens.primary_soft}; border: 2px solid {tokens.primary};
        }}
        QPushButton#themeSwatch:focus {{ border-color: {tokens.focus_ring}; }}
        QFrame#segmentedControl {{
            background: {tokens.surface_alt}; border: 1px solid {tokens.border};
            border-radius: {DESIGN.radius_sm}px;
        }}
        QFrame#segmentedControl QPushButton,
        QPushButton#segmentButton, QFrame#segmentedControl QRadioButton,
        QRadioButton#segmentButton {{
            background: transparent; color: {tokens.muted}; border: 1px solid transparent;
            border-radius: {DESIGN.radius_xs}px; padding: 5px 12px; min-height: 22px;
        }}
        QFrame#segmentedControl QPushButton:hover,
        QPushButton#segmentButton:hover, QFrame#segmentedControl QRadioButton:hover,
        QRadioButton#segmentButton:hover {{
            background: {tokens.surface_hover}; color: {tokens.text};
        }}
        QFrame#segmentedControl QPushButton:checked,
        QPushButton#segmentButton:checked, QFrame#segmentedControl QRadioButton:checked,
        QRadioButton#segmentButton:checked {{
            background: {tokens.surface_elevated}; color: {tokens.primary};
            border-color: {tokens.separator};
        }}
        QFrame#segmentedControl QPushButton:focus,
        QPushButton#segmentButton:focus, QFrame#segmentedControl QRadioButton:focus,
        QRadioButton#segmentButton:focus {{ border-color: {tokens.focus_ring}; }}
        QFrame#segmentedControl QRadioButton::indicator,
        QRadioButton#segmentButton::indicator {{ width: 0; height: 0; }}
        QDialog#quickPanel QRadioButton#segmentButton {{
            padding-left: 5px; padding-right: 5px;
        }}
        QComboBox[roundedSelector="true"],
        QDateEdit[roundedSelector="true"],
        QPushButton[roundedSelector="true"] {{
            background: {tokens.input}; color: {tokens.text};
            border: 1px solid {tokens.border};
            padding: 0 42px 0 14px;
        }}
        QComboBox[roundedSelector="true"][selectorDensity="large"],
        QDateEdit[roundedSelector="true"][selectorDensity="large"],
        QPushButton[roundedSelector="true"][selectorDensity="large"] {{
            border-radius: {DESIGN.radius_md}px;
            min-height: 46px; max-height: 46px;
            font-size: {DESIGN.font_body_lg}px;
        }}
        QComboBox[roundedSelector="true"][selectorDensity="compact"],
        QDateEdit[roundedSelector="true"][selectorDensity="compact"],
        QPushButton[roundedSelector="true"][selectorDensity="compact"] {{
            border-radius: 10px;
            min-height: 38px; max-height: 38px;
            font-size: {DESIGN.font_body}px;
        }}
        QPushButton[roundedSelector="true"] {{ text-align: left; }}
        QComboBox[roundedSelector="true"]:hover,
        QDateEdit[roundedSelector="true"]:hover,
        QPushButton[roundedSelector="true"]:hover {{
            background: {tokens.surface_hover}; border-color: {tokens.border_strong};
        }}
        QComboBox[roundedSelector="true"]:focus,
        QDateEdit[roundedSelector="true"]:focus,
        QPushButton[roundedSelector="true"]:focus {{
            border-color: {tokens.focus_ring};
        }}
        QComboBox[roundedSelector="true"]:disabled,
        QDateEdit[roundedSelector="true"]:disabled,
        QPushButton[roundedSelector="true"]:disabled {{
            background: {tokens.surface_alt}; color: {tokens.disabled};
            border-color: {tokens.separator};
        }}
        QComboBox[roundedSelector="true"]::drop-down,
        QDateEdit[roundedSelector="true"]::drop-down {{
            subcontrol-origin: padding; subcontrol-position: top right;
            width: 38px; border: 0; background: transparent;
        }}
        QComboBox[roundedSelector="true"]::down-arrow,
        QDateEdit[roundedSelector="true"]::down-arrow {{
            image: none; width: 10px; height: 10px;
        }}
        QDateEdit[roundedSelector="true"]::up-button,
        QDateEdit[roundedSelector="true"]::down-button {{
            width: 0; height: 0; border: 0; background: transparent;
        }}
        QFrame#focusItemSelectorPopup, QFrame#roundedSelectorPopup {{
            background: transparent; border: 0;
        }}
        QFrame#roundedSelectorPopupSurface {{
            background: {tokens.surface_elevated};
            border: 1px solid {tokens.border_strong};
            border-radius: {DESIGN.radius_md}px;
        }}
        QFrame#focusItemSelectorPopupSurface {{
            background: {tokens.surface_elevated};
            border: 1px solid {tokens.border};
            border-radius: {DESIGN.radius_md}px;
        }}
        QListView#focusItemSelectorPopupView, QListView#roundedSelectorPopupView {{
            background: transparent; color: {tokens.text}; border: 0;
            padding: 6px; outline: 0;
            selection-background-color: transparent;
            selection-color: {tokens.text};
        }}
        QListView#focusItemSelectorPopupView::item,
        QListView#roundedSelectorPopupView::item {{
            min-height: 34px; padding: 4px 10px;
            border-radius: {DESIGN.radius_sm}px;
        }}
        QListView#focusItemSelectorPopupView::item:selected,
        QListView#roundedSelectorPopupView::item:selected {{
            background: {tokens.primary_soft}; color: {tokens.text};
        }}
        QFrame#roundedTimePickerPopup {{ background: transparent; border: 0; }}
        QFrame#roundedTimePickerPopupSurface {{
            background: {tokens.surface_elevated};
            border: 1px solid {tokens.border_strong};
            border-radius: {DESIGN.radius_md}px;
        }}
        QLabel#selectorPopupHeader {{
            color: {tokens.muted}; font-size: {DESIGN.font_caption}px;
            font-weight: 600; padding: 2px 4px;
        }}
        QListWidget#roundedTimePickerList {{
            background: transparent; color: {tokens.text}; border: 0;
            outline: 0; padding: 3px;
            selection-background-color: {tokens.primary_soft};
            selection-color: {tokens.text};
        }}
        QListWidget#roundedTimePickerList::item {{
            min-height: 32px; border-radius: {DESIGN.radius_sm}px;
        }}
        QWidget#themedCalendarPopup {{ background: transparent; border: 0; }}
        QScrollArea#themedCalendarScroll,
        QScrollArea#themedCalendarScroll QWidget#qt_scrollarea_viewport {{
            background: transparent; border: 0;
        }}
        QCalendarWidget#themedCalendar {{
            background: {tokens.surface_elevated}; color: {tokens.text};
            border: 1px solid {tokens.border_strong};
            border-radius: {DESIGN.radius_md}px;
        }}
        QCalendarWidget#themedCalendar QWidget#qt_calendar_navigationbar {{
            background: {tokens.surface_alt};
            border-top-left-radius: {DESIGN.radius_md}px;
            border-top-right-radius: {DESIGN.radius_md}px;
        }}
        QCalendarWidget#themedCalendar QToolButton {{
            background: transparent; color: {tokens.text}; border: 0;
            border-radius: {DESIGN.radius_sm}px; padding: 5px;
        }}
        QCalendarWidget#themedCalendar QToolButton:hover {{
            background: {tokens.surface_hover};
        }}
        QCalendarWidget#themedCalendar QAbstractItemView {{
            background: {tokens.surface_elevated}; color: {tokens.text}; border: 0;
            border-bottom-left-radius: {DESIGN.radius_md}px;
            border-bottom-right-radius: {DESIGN.radius_md}px;
            selection-background-color: {tokens.primary};
            selection-color: {tokens.primary_text};
        }}

"""


def _input_style_sheet(tokens: ThemeTokens) -> str:
    return f"""        /* Inputs */
        QLineEdit, QComboBox, QDateEdit, QTimeEdit, QSpinBox, QListWidget,
        QTableWidget, QTextEdit, QPlainTextEdit {{
            background: {tokens.input}; color: {tokens.text};
            border: 1px solid {tokens.border}; border-radius: {DESIGN.radius_sm}px;
            padding: 6px 8px; min-height: 22px;
            selection-background-color: {tokens.primary};
            selection-color: {tokens.primary_text};
        }}
        QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTimeEdit:focus,
        QSpinBox:focus, QListWidget:focus, QTableWidget:focus, QTextEdit:focus,
        QPlainTextEdit:focus {{
            border-color: {tokens.focus_ring};
        }}
        QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled,
        QTimeEdit:disabled, QSpinBox:disabled, QTextEdit:disabled,
        QPlainTextEdit:disabled {{
            background: {tokens.surface_alt}; color: {tokens.disabled};
            border-color: {tokens.separator};
        }}
        QComboBox QAbstractItemView {{
            background: {tokens.surface_elevated}; color: {tokens.text};
            selection-background-color: {tokens.primary};
            selection-color: {tokens.primary_text};
        }}
        QScrollArea#focusPanelScroll,
        QScrollArea#focusPanelScroll > QWidget > QWidget {{
            background: transparent; border: 0;
        }}
        QTableWidget {{
            alternate-background-color: {tokens.surface_alt};
            gridline-color: transparent; border: 0;
        }}
        QTableWidget#sessionDataTable {{
            background: {tokens.surface}; alternate-background-color: {tokens.surface};
            selection-background-color: transparent; selection-color: {tokens.text};
            gridline-color: transparent; border: 0; border-radius: {DESIGN.radius_sm}px;
            padding: 0; outline: 0;
        }}
        QTableWidget#sessionDataTable::item {{
            background: transparent; border: 0; padding: 4px 8px;
        }}
        QHeaderView::section {{
            background: {tokens.surface_alt}; color: {tokens.muted};
            border: 0; border-bottom: 1px solid {tokens.separator};
            padding: 10px 8px; font-weight: 600;
        }}
        QTableWidget#sessionDataTable QHeaderView::section {{
            background: {tokens.surface}; color: {tokens.muted};
            border: 0; border-bottom: 1px solid {tokens.separator};
            padding: 8px; font-weight: 600;
        }}
        QProgressBar {{
            background: {tokens.border}; color: {tokens.text};
            border: 0; border-radius: 5px;
            min-height: 10px; text-align: center;
        }}
        QProgressBar::chunk {{ background: {tokens.primary}; border-radius: 4px; }}
        QSlider::groove:horizontal {{
            height: 6px; background: {tokens.primary_soft}; border-radius: 3px;
        }}
        QSlider::handle:horizontal {{
            width: 16px; margin: -5px 0; background: {tokens.primary};
            border: 2px solid {tokens.surface}; border-radius: 8px;
        }}

"""


def _floating_style_sheet(tokens: ThemeTokens) -> str:
    return f"""        /* Floating surfaces */
        QMenu {{
            background: {tokens.surface_elevated}; color: {tokens.text};
            border: 1px solid {tokens.border_strong}; border-radius: {DESIGN.radius_md}px;
            padding: 6px;
        }}
        QMenu::item {{
            background: transparent; padding: 9px 32px 9px 34px;
            border-radius: {DESIGN.radius_sm}px;
        }}
        QMenu::item:selected {{
            background: {tokens.primary_soft}; color: {tokens.text};
        }}
        QMenu::item:disabled {{ color: {tokens.disabled}; }}
        QMenu::separator {{
            height: 1px; background: {tokens.separator}; margin: 5px 8px;
        }}
        QToolTip {{
            background: {tokens.surface_elevated}; color: {tokens.text};
            border: 1px solid {tokens.border_strong}; border-radius: 6px; padding: 6px;
        }}
        QStatusBar {{ background: {tokens.surface}; color: {tokens.text}; }}
        QScrollBar:vertical {{
            background: transparent; width: 10px; margin: 2px;
        }}
        QScrollBar::handle:vertical {{
            background: {tokens.border_strong}; min-height: 28px; border-radius: 4px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {tokens.muted}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar:horizontal {{
            background: transparent; height: 10px; margin: 2px;
        }}
        QScrollBar::handle:horizontal {{
            background: {tokens.border_strong}; min-width: 28px; border-radius: 4px;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        QCheckBox, QRadioButton {{ spacing: 8px; }}
        QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; }}
        /* Segmented radio buttons are text-only choices.  Keep this override
           after the generic radio style so the native indicator cannot leak
           back in through QSS source-order precedence. */
        QRadioButton#segmentButton {{ spacing: 0px; }}
        QRadioButton#segmentButton::indicator {{
            width: 0px; height: 0px; margin: 0px; padding: 0px;
            image: none; background: transparent; border: none;
        }}
    """
