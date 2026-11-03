"""Stable theme definitions and normalization (no Qt widget dependencies)."""
from __future__ import annotations

from dataclasses import dataclass

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
