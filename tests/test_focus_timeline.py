"""Visual Focus Timeline presentation tests."""

from datetime import datetime, timedelta, timezone

import pytest
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QSignalSpy, QTest

from app.core.theme import COLOR_THEMES, get_theme_manager
from app.data.models import FocusSession, FocusSessionSource
from app.focus_mode import FocusMode
from app.ui.dashboard import DashboardWindow
from app.ui.info_bubble import install_animated_tooltips
from app.ui.timeline_widget import DailyTimelineWidget


def _session(session_id: int, hour: int, minutes: int, duration: int) -> FocusSession:
    start = datetime(2026, 8, 15, hour, minutes, tzinfo=timezone.utc)
    return FocusSession(
        session_id,
        session_id,
        "Writing" if session_id == 1 else "Reading",
        start,
        start + timedelta(seconds=duration),
        duration,
        FocusMode.STOPWATCH,
        None,
        "Deep work" if session_id == 1 else "",
        FocusSessionSource.TIMER,
        start,
        start,
    )


def _render_timeline(widget: DailyTimelineWidget, width: int) -> QImage:
    widget.resize(width, widget.minimumHeight())
    image = QImage(widget.size(), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("#000000"))
    widget.render(image)
    return image


def test_timeline_orders_sessions_and_uses_calendar_time_positions(qt_application) -> None:
    window = DashboardWindow(timezone.utc)
    later = _session(2, 15, 0, 1800)
    earlier = _session(1, 9, 0, 3000)

    window.set_timeline(earlier.start_time.date(), [later, earlier], 4800)

    assert [block.session.id for block in window._timeline_widget.blocks] == [1, 2]
    assert window._timeline_widget.visible_minute_range == (9 * 60, 16 * 60)
    assert "1h 20min" in window._timeline_summary.text()
    window.close()


def test_timeline_splits_overlaps_and_clips_cross_midnight(qt_application) -> None:
    window = DashboardWindow(timezone.utc)
    first = _session(1, 9, 0, 90 * 60)
    overlap = _session(2, 9, 30, 60 * 60)
    cross_midnight = _session(3, 23, 30, 60 * 60)

    window.set_timeline(first.start_time.date(), [first, overlap], 150 * 60)

    blocks = window._timeline_widget.blocks
    assert blocks[0].lane_count == blocks[1].lane_count == 2
    assert {blocks[0].lane, blocks[1].lane} == {0, 1}

    next_day = cross_midnight.start_time.date() + timedelta(days=1)
    window.set_timeline(next_day, [cross_midnight], 30 * 60)
    clipped = window._timeline_widget.blocks[0]
    assert clipped.start.date() == next_day
    assert clipped.start.hour == clipped.start.minute == 0
    assert clipped.end.hour == 0 and clipped.end.minute == 30
    assert clipped.duration_seconds == 30 * 60
    window.close()


def test_timeline_date_control_emits_local_date(qt_application) -> None:
    window = DashboardWindow(timezone.utc)
    spy = QSignalSpy(window.timeline_date_changed)

    window._timeline_date_edit.setDate(window._timeline_date_edit.date().addDays(-1))

    assert spy.count() == 1
    window.close()


@pytest.mark.parametrize("width", [420, 760, 1024])
def test_timeline_uses_compact_centered_bounds_at_supported_widths(
    qt_application,
    width: int,
) -> None:
    del qt_application
    widget = DailyTimelineWidget(timezone.utc)
    session = _session(1, 7, 0, 10 * 60 * 60)
    widget.set_values(session.start_time.date(), [session], {1: "#35C8B0"})

    _render_timeline(widget, width)

    timeline_rect = widget._timeline_rect()
    expected_width = min(720.0, width - 24.0)
    assert timeline_rect.width() == pytest.approx(expected_width)
    assert timeline_rect.center().x() == pytest.approx(width / 2)
    assert widget.minimumHeight() == widget.maximumHeight() == 554
    block = widget.blocks[0]
    assert block.rect.height() == pytest.approx(516.0)
    assert block.rect.left() >= timeline_rect.left()
    assert block.rect.right() <= timeline_rect.right()
    widget.close()


def test_timeline_centers_only_the_title_and_hides_text_on_short_bars(
    qt_application,
) -> None:
    del qt_application
    widget = DailyTimelineWidget(timezone.utc)
    long_session = _session(1, 7, 0, 10 * 60 * 60)
    widget.set_values(
        long_session.start_time.date(),
        [long_session],
        {1: "#35C8B0"},
    )
    _render_timeline(widget, 1024)

    long_block = widget.blocks[0]
    title_rect = widget._block_title_rect(long_block)
    assert title_rect is not None
    assert title_rect.center().y() == pytest.approx(long_block.rect.center().y())

    short_session = _session(2, 9, 0, 3 * 60)
    widget.set_values(
        short_session.start_time.date(),
        [short_session],
        {2: "#FF6B4A"},
    )
    _render_timeline(widget, 1024)
    assert widget.blocks[0].rect.height() == pytest.approx(6.0)
    assert widget._block_title_rect(widget.blocks[0]) is None
    widget.close()


def test_timeline_short_bars_do_not_cover_later_non_overlapping_sessions(
    qt_application,
) -> None:
    del qt_application
    widget = DailyTimelineWidget(timezone.utc)
    tiny = _session(1, 17, 2, 3 * 60)
    later = _session(2, 17, 19, 60 * 60)
    widget.set_values(tiny.start_time.date(), [tiny, later], {})

    _render_timeline(widget, 760)

    tiny_block, later_block = widget.blocks
    assert tiny_block.rect.height() == pytest.approx(6.0)
    assert tiny_block.rect.bottom() <= later_block.rect.top()
    assert tiny_block.lane_count == later_block.lane_count == 1
    assert tiny_block.rect.left() == pytest.approx(later_block.rect.left())
    widget.close()


def test_timeline_dense_short_bars_shrink_inside_fixed_time_slots(
    qt_application,
) -> None:
    del qt_application
    widget = DailyTimelineWidget(timezone.utc)
    first = _session(1, 17, 0, 3 * 60)
    second = _session(2, 17, 3, 5 * 60)
    third = _session(3, 17, 8, 30 * 60)
    widget.set_values(first.start_time.date(), [first, second, third], {})

    _render_timeline(widget, 760)

    blocks = widget.blocks
    assert blocks[0].rect.bottom() <= blocks[1].rect.top()
    assert blocks[1].rect.bottom() <= blocks[2].rect.top()
    assert all(block.lane_count == 1 for block in blocks)
    assert widget._minute_to_y(18 * 60) - widget._minute_to_y(17 * 60) == 52
    widget.close()


def test_timeline_short_bar_hit_targets_choose_the_nearest_record(
    qt_application,
) -> None:
    del qt_application
    widget = DailyTimelineWidget(timezone.utc)
    first = _session(1, 17, 0, 3 * 60)
    second = _session(2, 17, 3, 5 * 60)
    widget.set_values(first.start_time.date(), [first, second], {})
    _render_timeline(widget, 760)

    first_block, second_block = widget.blocks
    assert first_block.hit_rect.height() == second_block.hit_rect.height() == 18
    first_target = first_block.rect.center()
    second_target = second_block.rect.center()
    assert widget._block_at(first_target) == 0
    assert widget._block_at(second_target) == 1
    widget.close()


def test_timeline_hover_uses_shared_animated_detailed_bubble(
    qt_application,
) -> None:
    manager = install_animated_tooltips(qt_application)
    manager.hide_immediately()
    widget = DailyTimelineWidget(timezone.utc)
    session = _session(1, 9, 0, 60 * 60)
    widget.set_values(session.start_time.date(), [session], {1: "#35C8B0"})
    widget.show()
    _render_timeline(widget, 760)

    QTest.mouseMove(widget, widget.blocks[0].rect.center().toPoint())
    qt_application.processEvents()

    assert manager.owner is widget
    assert manager.bubble.isVisible()
    assert "09:00–10:00" in manager.bubble.text
    assert "1h" in manager.bubble.text
    manager.hide_immediately(owner=widget)
    widget.close()


def test_timeline_block_colors_are_opaque_soft_and_hover_strengthens_them(
    qt_application,
) -> None:
    del qt_application
    manager = get_theme_manager()
    original_theme = manager.theme_name
    widget = DailyTimelineWidget(timezone.utc)
    first = _session(1, 9, 0, 60 * 60)
    second = _session(2, 11, 0, 60 * 60)
    project_colors = {1: "#35C8B0", 2: "#FF6B4A"}
    widget.set_values(first.start_time.date(), [first, second], project_colors)
    try:
        for theme_name in COLOR_THEMES:
            manager.set_theme(theme_name)
            manager._transition.finish_all()
            widget._hovered_index = None
            resting = widget._block_background(0)
            widget._hovered_index = 0
            hovered = widget._block_background(0)
            muted = widget._block_background(1)
            project = QColor(project_colors[1])

            assert resting.alpha() == hovered.alpha() == muted.alpha() == 255
            assert _rgb_distance(hovered, project) < _rgb_distance(resting, project)
            assert _rgb_distance(resting, project) < _rgb_distance(muted, project)
    finally:
        widget.close()
        manager.set_theme(original_theme)
        manager._transition.finish_all()


def _rgb_distance(first: QColor, second: QColor) -> int:
    return (
        abs(first.red() - second.red())
        + abs(first.green() - second.green())
        + abs(first.blue() - second.blue())
    )
