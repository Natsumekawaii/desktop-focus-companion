"""Focused tests for reusable design-system tokens and presentation primitives."""

from PySide6.QtWidgets import QLabel, QPushButton

from app.core.theme import COLOR_THEMES, DESIGN, THEME_TOKENS
from app.ui.components import (
    CardFrame,
    EmptyState,
    IconButton,
    ListRow,
    MetricStrip,
    PageHeader,
    ResponsiveGrid,
    SectionSurface,
    SegmentedControl,
)


def _relative_luminance(hex_color: str) -> float:
    channels = [int(hex_color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        channel / 12.92
        if channel <= 0.04045
        else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(first: str, second: str) -> float:
    light, dark = sorted(
        (_relative_luminance(first), _relative_luminance(second)),
        reverse=True,
    )
    return (light + 0.05) / (dark + 0.05)


def test_theme_presets_expose_complete_visualization_and_surface_tokens() -> None:
    assert set(THEME_TOKENS) == set(COLOR_THEMES)
    assert DESIGN.sidebar_width > DESIGN.sidebar_collapsed_width
    assert DESIGN.sidebar_breakpoint >= 760

    for tokens in THEME_TOKENS.values():
        assert len(tokens.chart_palette) == 8
        assert len(set(tokens.chart_palette)) == 8
        assert tokens.elevated == tokens.surface_elevated
        assert tokens.accent == tokens.primary
        assert _contrast(tokens.text, tokens.canvas) >= 7.0
        assert _contrast(tokens.primary_text, tokens.primary) >= 4.5


def test_flat_surfaces_and_structured_headers_preserve_public_content_access(
    qt_application,
) -> None:
    card = CardFrame()
    raised_card = CardFrame(elevated=True)
    assert card.graphicsEffect() is None
    assert raised_card.graphicsEffect() is not None

    header = PageHeader("Overview", "A calm summary")
    action = QPushButton("Today")
    header.add_action(action)
    header.set_subtitle("")
    assert header.title_label.text() == "Overview"
    assert header.subtitle_label.isHidden()
    assert header.actions_layout.indexOf(action) == 0

    section = SectionSurface("Weekly rhythm", "Seven-day focus pattern")
    content = QLabel("content")
    section.add_widget(content)
    assert section.content_layout.indexOf(content) == 0
    assert section.objectName() == "sectionSurface"


def test_metric_strip_and_responsive_grid_reflow_without_recreating_widgets(
    qt_application,
) -> None:
    strip = MetricStrip(max_columns=3)
    metric = strip.add_metric("Sessions", "12")
    metric.set_value("13")
    assert metric.value_label.text() == "13"
    assert strip.grid.widgets == (metric,)

    grid = ResponsiveGrid(min_item_width=180, max_columns=4, spacing=12)
    widgets = [QLabel(str(index)) for index in range(6)]
    for widget in widgets:
        grid.add_widget(widget)
    grid.resize(800, 200)
    grid.show()
    qt_application.processEvents()
    assert grid.column_count == 4
    assert grid.widgets == tuple(widgets)

    grid.resize(400, 200)
    qt_application.processEvents()
    assert grid.column_count == 2
    assert grid.widgets == tuple(widgets)
    grid.close()


def test_interaction_primitives_are_localizable_and_accessible(qt_application) -> None:
    control = SegmentedControl((("Day", "day"), ("Week", "week")))
    selections: list[object] = []
    control.value_changed.connect(selections.append)
    control.set_current_value("week", emit=True)
    assert control.current_index == 1
    assert control.current_value == "week"
    assert selections == ["week"]

    icon_button = IconButton("×", tooltip="Close")
    assert icon_button.toolTip() == "Close"
    assert icon_button.accessibleName() == "Close"

    empty_state = EmptyState("No sessions", "Start a focus session to see it here.")
    action = QPushButton("Start focus")
    empty_state.set_action(action)
    assert not empty_state.action_container.isHidden()

    row = ListRow("Reading", "Last focused today")
    row.add_trailing(QLabel("42 min"))
    assert row.title_label.text() == "Reading"
    assert row.trailing_layout.count() == 1
