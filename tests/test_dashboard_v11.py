"""Focused widget tests for V1.1 dashboard analytics interactions."""

from datetime import date, datetime, timedelta, timezone

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QAbstractItemView, QLabel

from app.data.models import FocusSession, FocusSessionSource
from app.focus_mode import FocusMode
from app.i18n import tr
from app.statistics import (
    DailyTotal,
    FocusItemTotal,
    HeatmapData,
    HeatmapDay,
    MonthlyStatistics,
)
from app.timer.formatting import format_compact_duration
from app.ui.dashboard import DashboardWindow


def test_heatmap_click_does_not_change_today_detail(qt_application) -> None:
    window = DashboardWindow(timezone(timedelta(hours=8)))
    selected_day = date(2026, 8, 14)
    days = tuple(
        HeatmapDay(selected_day - timedelta(days=2 - offset), offset * 1800, offset)
        for offset in range(3)
    )
    window.set_heatmap(HeatmapData(days[0].day, days[-1].day, days))
    window.show()
    QTest.qWait(10)
    window._heatmap.repaint()
    QTest.qWait(5)
    window.set_heatmap_detail(selected_day, 1800, [])
    detail_before = window._day_detail_data
    rect, _expected = window._heatmap._hit_regions[-1]

    QTest.mouseClick(
        window._heatmap,
        Qt.MouseButton.LeftButton,
        pos=rect.center().toPoint(),
    )

    assert not hasattr(window, "heatmap_day_requested")
    assert window._day_detail_data == detail_before
    assert not hasattr(window._heatmap, "_selected_day")
    window.close()


def test_monthly_empty_and_populated_states_render_at_minimum_size(qt_application) -> None:
    window = DashboardWindow(timezone.utc)
    window.set_focus_item_colors({1: "#9575CD"})
    daily = tuple(DailyTotal(date(2024, 2, day), 3600 if day == 14 else 0) for day in range(1, 30))
    focus_item = FocusItemTotal(1, "C++", 3600)
    summary = MonthlyStatistics(
        year=2024,
        month=2,
        total_seconds=3600,
        daily_average_seconds=3600,
        focus_days=1,
        total_sessions=1,
        longest_session_seconds=3600,
        best_day=daily[13],
        top_focus_item=focus_item,
        daily_totals=daily,
        focus_item_totals=(focus_item,),
        previous_month_total_seconds=0,
        comparison_percent=None,
    )

    window.resize(760, 520)
    window.set_monthly(summary)
    window.show()
    QTest.qWait(10)

    assert window._month_title.text() == "February 2024"
    assert window._month_days.text() == "1"
    assert window._month_comparison.text() == "No previous month data"
    assert not window._month_empty.isVisible()
    assert len(window._monthly_calendar.values) == 29
    assert not hasattr(window, "_monthly_chart")
    assert window.minimumWidth() <= window.width()
    monthly_row = window._month_subject_layout.itemAt(0).widget()
    assert monthly_row is not None
    monthly_names = [
        label for label in monthly_row.findChildren(QLabel) if label.text() == "C++"
    ]
    assert len(monthly_names) == 1
    assert "#9575CD" in monthly_names[0].styleSheet().upper()
    assert all("●" not in label.text() for label in monthly_row.findChildren(QLabel))
    window.close()


def test_focus_dashboard_prioritizes_heatmap_and_time_distribution(
    qt_application,
) -> None:
    window = DashboardWindow(timezone.utc)
    overview_scroll = window._tabs.widget(0)
    content = overview_scroll.widget()
    layout = content.layout()

    heatmap_index = layout.indexOf(window._heatmap.parentWidget())
    distribution_index = layout.indexOf(window._weekly_chart.parentWidget())
    day_detail_index = layout.indexOf(window._day_table.parentWidget())

    assert 0 <= heatmap_index < distribution_index < day_detail_index
    visible_text = " ".join(
        label.text() for label in window.findChildren(QLabel)
    ).casefold()
    assert "xp" not in visible_text
    assert "level" not in visible_text
    assert "等级" not in visible_text
    assert window._card_titles[0][1] == "dashboard.focus_week"
    assert window._card_titles[1][1] == "dashboard.goal_streak"
    window.close()


def test_read_only_session_tables_do_not_keep_selection(qt_application) -> None:
    window = DashboardWindow(timezone.utc)
    now = datetime(2026, 8, 15, 8, 0, tzinfo=timezone.utc)
    session = FocusSession(
        1, 3, "Writing", now, now + timedelta(minutes=30), 1800,
        FocusMode.STOPWATCH, None, "", FocusSessionSource.TIMER, now, now,
    )
    window.set_today(1800, [session])
    window.show()
    QTest.qWait(10)

    table = window._day_table
    assert table.selectionMode() is QAbstractItemView.SelectionMode.NoSelection
    assert table.focusPolicy() is Qt.FocusPolicy.NoFocus
    cell = table.visualItemRect(table.item(0, 0)).center()
    QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=cell)

    assert not table.selectedIndexes()
    assert not table.selectedItems()
    window.close()


def test_dashboard_hero_keeps_today_and_replay_without_live_status(qt_application) -> None:
    window = DashboardWindow(timezone.utc)
    replay_spy = QSignalSpy(window.replay_requested)

    window.set_today(5400, [])

    assert window._hero_today_total.text() == format_compact_duration(5400)
    assert window._replay_button.objectName() == "ghost"
    assert not hasattr(window, "_focus_status_pill")
    window._replay_button.click()
    assert replay_spy.count() == 1
    window.close()


def test_overview_uses_cards_for_recent_sessions_and_focus_items(qt_application) -> None:
    window = DashboardWindow(timezone.utc)
    now = datetime(2026, 8, 15, 8, 0, tzinfo=timezone.utc)
    session = FocusSession(
        1, 3, "Writing", now, now + timedelta(minutes=30), 1800,
        FocusMode.STOPWATCH, None, "", FocusSessionSource.TIMER, now, now,
    )

    window.set_focus_item_colors({3: "#EC4899"})
    window.set_overview_focus_items([FocusItemTotal(3, "Writing", 1800)])
    window.set_recent_sessions([session])

    assert window._overview_subject_table.isHidden()
    assert window._recent_table.isHidden()
    assert window._overview_focus_cards.count() == 1
    assert window._recent_cards.count() == 1
    recent_card = window._recent_cards.itemAt(0).widget()
    assert recent_card is not None
    recent_names = [
        label for label in recent_card.findChildren(QLabel) if label.text() == "Writing"
    ]
    assert len(recent_names) == 1
    assert "#EC4899" in recent_names[0].styleSheet().upper()
    assert all("●" not in label.text() for label in recent_card.findChildren(QLabel))
    window.close()


def test_focus_item_color_is_used_in_dashboard_distribution(qt_application) -> None:
    window = DashboardWindow(timezone.utc)
    window.set_focus_item_colors({7: "#EC4899"})
    window.set_overview_focus_items([FocusItemTotal(7, "Writing", 3600)])
    window.set_focus_item_totals([FocusItemTotal(7, "Writing", 3600)])

    overview_item = window._overview_subject_table.item(0, 0)
    distribution_item = window._subject_table.item(0, 0)
    assert overview_item.text() == "Writing"
    assert distribution_item.text() == "Writing"
    assert overview_item.foreground().color().name().upper() == "#EC4899"
    assert distribution_item.foreground().color().name().upper() == "#EC4899"

    overview_card = window._overview_focus_cards.itemAt(0).widget()
    distribution_card = window._focus_item_cards.itemAt(0).widget()
    assert overview_card is not None
    assert distribution_card is not None
    for card in (overview_card, distribution_card):
        labels = [label for label in card.findChildren(QLabel) if label.text() == "Writing"]
        assert len(labels) == 1
        assert "#EC4899" in labels[0].styleSheet().upper()
    window.close()


def test_heatmap_day_detail_summarizes_sessions_and_main_item(qt_application) -> None:
    from app.data.models import FocusSession, FocusSessionSource
    from app.focus_mode import FocusMode

    window = DashboardWindow(timezone.utc)
    now = datetime(2026, 8, 15, 8, 0, tzinfo=timezone.utc)
    sessions = [
        FocusSession(
            1,
            3,
            "Writing",
            now,
            now + timedelta(minutes=30),
            1800,
            FocusMode.STOPWATCH,
            None,
            "",
            FocusSessionSource.TIMER,
            now,
            now,
        )
    ]

    window.set_heatmap_detail(now.date(), 1800, sessions, "Writing")

    assert tr("count.sessions.one", count=1) == window._day_session_count.text()
    assert "Writing" in window._day_primary_item.text()
    window.close()
