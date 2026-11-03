"""Compatibility entry point and runtime theme coordinator."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from app.core.theme_styles import (
    _base_style_sheet,
    _control_style_sheet,
    _floating_style_sheet,
    _input_style_sheet,
    _navigation_style_sheet,
    _palette,
    _style_sheet,
    _surface_style_sheet,
    _typography_style_sheet,
)
from app.core.theme_tokens import (
    COLOR_THEMES,
    DEFAULT_COLOR_THEME,
    DEFAULT_FONT_LANGUAGE,
    DESIGN,
    FONT_FAMILY_STACKS,
    THEME_TOKENS,
    DesignMetrics,
    ThemeTokens,
    font_families_for_language,
    normalize_color_theme,
)
from app.core.theme_transitions import (
    _snapshot_is_opaque,
    _ThemeSnapshotOverlay,
    _ThemeTransitionCoordinator,
)

__all__ = [
    "COLOR_THEMES",
    "DEFAULT_COLOR_THEME",
    "DEFAULT_FONT_LANGUAGE",
    "DESIGN",
    "FONT_FAMILY_STACKS",
    "THEME_TOKENS",
    "DesignMetrics",
    "ThemeManager",
    "ThemeTokens",
    "_ThemeSnapshotOverlay",
    "_ThemeTransitionCoordinator",
    "_base_style_sheet",
    "_control_style_sheet",
    "_floating_style_sheet",
    "_input_style_sheet",
    "_navigation_style_sheet",
    "_palette",
    "_snapshot_is_opaque",
    "_style_sheet",
    "_surface_style_sheet",
    "_typography_style_sheet",
    "font_families_for_language",
    "get_theme_manager",
    "normalize_color_theme",
]


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
