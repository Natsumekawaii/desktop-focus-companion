"""Responsive Focus Dashboard and editable Focus History."""

from __future__ import annotations

from app.ui.analytics_widgets import FocusDistributionChart, FocusTrendWidget
from app.ui.components import (
    MetricStrip,
    ResponsiveGrid,
    SegmentedControl,
    ThemedDateEdit,
    apply_elevation,
)
from app.ui.dashboard_widgets import _FocusActivityCard
from app.ui.heatmap_widget import HeatmapWidget
from app.ui.monthly_calendar import MonthlyCalendarWidget
from app.ui.rounded_selector import RoundedComboBox, SelectorDensity
from app.ui.timeline_widget import DailyTimelineWidget
from app.ui.weekly_chart import WeeklyChart

# Compatibility exports for existing integrations and focused UI tests.
__all__ = ["DailyTimelineWidget", "DashboardPage", "DashboardWindow", "FocusDistributionChart", "FocusTrendWidget", "HeatmapWidget", "MetricStrip", "MonthlyCalendarWidget", "ResponsiveGrid", "RoundedComboBox", "SegmentedControl", "SelectorDensity", "ThemedDateEdit", "WeeklyChart", "_DashboardPageStack", "_FocusActivityCard", "_SessionTableDelegate", "_SessionTableRole", "_SessionTableWidget", "apply_elevation"]

from collections.abc import Sequence
from datetime import UTC, date, datetime, tzinfo
from enum import IntEnum
from typing import cast

from PySide6.QtCore import (
    QDate,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QKeyEvent,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QBoxLayout,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.core.icon_system import IconName, IconSystem
from app.core.theme import get_theme_manager
from app.data.models import FocusSession
from app.data.settings_repository import normalize_dashboard_sidebar_mode
from app.gamification import GamificationSnapshot
from app.i18n import format_date, format_month_year, get_localization, tr
from app.statistics import (
    AnalyticsDistributionPeriod,
    DailyTotal,
    FocusAnalyticsSnapshot,
    FocusItemTotal,
    HeatmapData,
    MonthlyStatistics,
    StatisticsPeriod,
)
from app.timer.formatting import format_compact_duration
from app.ui.agent_page import AgentPage
from app.ui.dashboard_builders import _DashboardWindowBuilders
from app.ui.dashboard_navigation import (
    NavigationButton,
    NavigationGroup,
    SidebarFrame,
    SidebarToggleHost,
)
from app.ui.dashboard_widgets import (
    _DashboardPageStack,
    _SessionTableDelegate,
    _SessionTableRole,
    _SessionTableWidget,
)
from app.ui.heatmap_widget import FocusActivityMode


class DashboardPage(IntEnum):
    """Stable page identifiers used by navigation and external entry points."""

    OVERVIEW = 0
    TIMELINE = 1
    ANALYTICS = 2
    MONTHLY = 3
    FOCUS_ITEMS = 4
    HISTORY = 5
    AI_ASSISTANT = 6


class _SidebarToggleButton(QToolButton):
    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not event.isAutoRepeat():
                self.click()
            event.accept()
            return
        super().keyPressEvent(event)


class DashboardWindow(_DashboardWindowBuilders, QMainWindow):
    """Display service-owned data with consistent cards and responsive scrolling."""

    refresh_requested = Signal()
    period_changed = Signal(object)
    timeline_date_changed = Signal(object)
    month_changed = Signal(int, int)
    add_session_requested = Signal()
    edit_session_requested = Signal(int)
    delete_session_requested = Signal(int)
    replay_requested = Signal()
    analytics_period_changed = Signal(object)
    sidebar_mode_changed = Signal(str)

    def __init__(self, local_timezone: tzinfo) -> None:
        super().__init__()
        self._local_timezone = local_timezone
        self._sidebar_mode = "auto"
        local_now = datetime.now(tz=local_timezone)
        self._month_year = local_now.year
        self._month_number = local_now.month
        self._card_titles: list[tuple[QLabel, str]] = []
        self._table_headers: list[tuple[QTableWidget, list[str]]] = []
        self._today_data: tuple[float, list[FocusSession]] = (0.0, [])
        self._weekly_data: list[DailyTotal] = []
        self._day_detail_data: tuple[
            date, float, list[FocusSession], str | None
        ] = (local_now.date(), 0.0, [], None)
        self._overview_subject_data: list[FocusItemTotal] = []
        self._recent_session_data: list[FocusSession] = []
        self._timeline_data: tuple[date, list[FocusSession], float] = (
            local_now.date(),
            [],
            0.0,
        )
        self._analytics_data: FocusAnalyticsSnapshot | None = None
        self._analytics_distribution_period = AnalyticsDistributionPeriod.DAILY
        self._analytics_distribution_data: list[FocusItemTotal] = []
        self._monthly_data: MonthlyStatistics | None = None
        self._subject_total_data: list[FocusItemTotal] = []
        self._history_data: list[FocusSession] = []
        self._focus_item_colors: dict[int, str] = {}
        self._gamification_data: GamificationSnapshot | None = None
        self._month_total: QLabel
        self._month_average: QLabel
        self._month_days: QLabel
        self._month_sessions: QLabel
        self._month_longest: QLabel
        self._month_best: QLabel
        self._month_top_subject: QLabel
        self._month_comparison: QLabel
        self._best_focus_time: QLabel
        self._average_session: QLabel
        self._common_start_time: QLabel
        self._current_consistency: QLabel
        self._active_days: QLabel
        self._longest_consistency: QLabel
        self.resize(1060, 720)
        self.setMinimumSize(760, 520)

        self._pages = _DashboardPageStack()
        self._pages.add_page(self._build_overview_tab())
        self._pages.add_page(self._build_timeline_tab())
        self._pages.add_page(self._build_analytics_tab())
        self._pages.add_page(self._build_monthly_tab())
        self._pages.add_page(self._build_subject_tab())
        self._pages.add_page(self._build_history_tab())
        self.agent_page = AgentPage()
        self._pages.add_page(self.agent_page)
        # Transitional alias retained for integrations that only read page metadata.
        self._tabs = self._pages
        self._history_tab_index = int(DashboardPage.HISTORY)
        self._sidebar = self._build_sidebar()
        self._sidebar.progress_changed.connect(self._update_sidebar_progress)
        self._sidebar.settled.connect(self._sidebar_settled)
        shell = QFrame()
        shell.setObjectName("appShell")
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        shell_layout.addWidget(self._sidebar)
        shell_layout.addWidget(self._pages, 1)
        self.setCentralWidget(shell)
        self.set_current_page(DashboardPage.OVERVIEW)
        self._refresh_icons()
        get_theme_manager().theme_changed.connect(self._refresh_icons)
        get_theme_manager().theme_changed.connect(self._finish_sidebar_motion)
        get_localization().language_changed.connect(self.retranslate_ui)
        self.retranslate_ui()

    def retranslate_ui(self, _language: str | None = None) -> None:
        self._finish_sidebar_motion()
        self.setWindowTitle(tr("dashboard.title"))
        for index, key in enumerate((
            "dashboard.tab.overview",
            "dashboard.tab.timeline",
            "dashboard.tab.analytics",
            "dashboard.tab.monthly",
            "dashboard.tab.subjects",
            "dashboard.tab.history",
            "agent.title",
        )):
            self._tabs.setTabText(index, tr(key))
            button = self._nav_buttons[DashboardPage(index)]
            button.setToolTip(tr(key))
            button.setAccessibleName(tr(key))
        overview_page = self._pages.widget(int(DashboardPage.OVERVIEW))
        if overview_page is not None:
            overview_page.setAccessibleName(tr("dashboard.tab.overview"))
        self._nav_focus_label.setText(tr("dashboard.navigation.focus"))
        self._nav_insights_label.setText(tr("dashboard.navigation.insights"))
        self._nav_library_label.setText(tr("dashboard.navigation.library"))
        self._update_navigation_mode()
        for label, key in self._card_titles:
            label.setText(tr(key))
        for table, keys in self._table_headers:
            table.setHorizontalHeaderLabels([tr(key) if key else "" for key in keys])
        self._greeting_label.setText(_greeting())
        self._hero_today_caption.setText(tr("dashboard.focus_today"))
        self._day_empty.setText(tr("dashboard.no_sessions"))
        self._timeline_title.setText(tr("timeline.title"))
        self._timeline_today_button.setText(tr("timeline.today"))
        self._replay_button.setText(tr("replay.view_today"))
        self._timeline_date_edit.setDisplayFormat(tr("date.input_format"))
        self._analytics_title.setText(tr("analytics.title"))
        self._analytics_subtitle.setText(tr("analytics.subtitle"))
        for index, key in enumerate(self._trend_keys):
            self._trend_control.set_segment_text(index, tr(key))
        for index, key in enumerate(self._activity_mode_keys):
            self._activity_mode_control.set_segment_text(index, tr(key))
        self._previous_button.setText(tr("dashboard.previous"))
        self._next_button.setText(tr("dashboard.next"))
        self._subject_title.setText(tr("dashboard.subject_statistics"))
        self._history_title.setText(tr("dashboard.session_history"))
        self._add_button.setText(tr("dashboard.add_manual"))
        self._edit_button.setText(tr("common.edit"))
        self._delete_button.setText(tr("common.delete"))
        self._refresh_button.setText(tr("common.refresh"))
        selected_period = self.selected_period()
        self._period_combo.blockSignals(True)
        self._period_combo.clear()
        self._period_combo.addItem(tr("dashboard.period.today"), StatisticsPeriod.TODAY)
        self._period_combo.addItem(tr("dashboard.period.week"), StatisticsPeriod.THIS_WEEK)
        self._period_combo.addItem(tr("dashboard.period.all"), StatisticsPeriod.ALL_TIME)
        selected_index = self._period_combo.findData(selected_period)
        self._period_combo.setCurrentIndex(max(0, selected_index))
        self._period_combo.blockSignals(False)
        analytics_period = self.selected_analytics_period()
        for index, key in enumerate((
            "analytics.period.daily",
            "analytics.period.weekly",
            "analytics.period.monthly",
        )):
            self._analytics_period_control.set_segment_text(index, tr(key))
        self._analytics_period_control.set_current_value(analytics_period)
        self.set_today(*self._today_data)
        self.set_weekly(self._weekly_data)
        self.set_heatmap_detail(*self._day_detail_data)
        self.set_overview_focus_items(self._overview_subject_data)
        self.set_recent_sessions(self._recent_session_data)
        self.set_timeline(*self._timeline_data)
        if self._analytics_data is not None:
            self.set_analytics(self._analytics_data)
        self.set_focus_distribution(
            self._analytics_distribution_period,
            self._analytics_distribution_data,
        )
        if self._monthly_data is not None:
            self.set_monthly(self._monthly_data)
        self.set_focus_item_totals(self._subject_total_data)
        self.set_history(self._history_data)
        if self._gamification_data is not None:
            self.set_gamification(self._gamification_data)

    def set_today(
        self, total_seconds: float, sessions: Sequence[FocusSession]
    ) -> None:
        self._today_data = (total_seconds, list(sessions))
        self._today_total.setText(format_compact_duration(total_seconds))
        self._hero_today_total.setText(format_compact_duration(total_seconds))
        self._populate_session_table(self._day_table, sessions, include_date=False)

    def set_weekly(self, totals: list[DailyTotal]) -> None:
        self._weekly_data = list(totals)
        self._weekly_chart.set_values(totals)
        self._weekly_total.setText(format_compact_duration(sum(item.duration_seconds for item in totals)))

    def set_heatmap(self, data: HeatmapData) -> None:
        self._heatmap.set_data(data)

    def _set_focus_activity_mode(self, value: object) -> None:
        if isinstance(value, FocusActivityMode):
            self._heatmap.set_mode(value)

    def set_heatmap_detail(
        self,
        selected_day: date,
        total_seconds: float,
        sessions: Sequence[FocusSession],
        primary_focus_item: str | None = None,
    ) -> None:
        if primary_focus_item is None and sessions:
            totals: dict[str, float] = {}
            for session in sessions:
                totals[session.focus_item_name] = (
                    totals.get(session.focus_item_name, 0.0)
                    + session.duration_seconds
                )
            primary_focus_item = (
                max(totals, key=lambda item: totals[item]) if totals else None
            )
        self._day_detail_data = (
            selected_day,
            total_seconds,
            list(sessions),
            primary_focus_item,
        )
        self._day_title.setText(format_date(selected_day))
        self._day_total.setText(format_compact_duration(total_seconds))
        count_key = "count.sessions.one" if len(sessions) == 1 else "count.sessions.other"
        self._day_session_count.setText(tr(count_key, count=len(sessions)))
        self._day_primary_item.setText(
            tr(
                "dashboard.primary_focus_item",
                item=primary_focus_item or tr("common.no_value"),
            )
        )
        self._populate_session_table(self._day_table, sessions, include_date=False)
        self._day_empty.setVisible(not sessions)

    def set_overview_focus_items(self, totals: list[FocusItemTotal]) -> None:
        self._overview_subject_data = list(totals)
        self._overview_subject_table.setRowCount(len(totals))
        for row, total in enumerate(totals):
            item = QTableWidgetItem(total.focus_item_name)
            item.setForeground(
                QColor(self._focus_item_colors.get(total.focus_item_id, "#7C5CFC"))
            )
            self._overview_subject_table.setItem(row, 0, item)
            self._overview_subject_table.setItem(
                row, 1, QTableWidgetItem(format_compact_duration(total.duration_seconds))
            )
        self._clear_layout(self._overview_focus_cards)
        if not totals:
            self._overview_focus_cards.addWidget(self._empty_label("dashboard.no_focus_items"))
        for total in totals:
            card = QFrame()
            card.setObjectName("softCard")
            row_layout = QHBoxLayout(card)
            row_layout.setContentsMargins(12, 9, 12, 9)
            color = self._focus_item_colors.get(total.focus_item_id, "#7C5CFC")
            name = QLabel(total.focus_item_name)
            name.setObjectName("sectionTitle")
            name.setStyleSheet(f"color: {color};")
            duration = QLabel(format_compact_duration(total.duration_seconds))
            duration.setObjectName("cardCaption")
            row_layout.addWidget(name, 1)
            row_layout.addWidget(duration)
            self._overview_focus_cards.addWidget(card)

    def set_recent_sessions(self, sessions: Sequence[FocusSession]) -> None:
        self._recent_session_data = list(sessions)
        self._populate_session_table(self._recent_table, sessions, include_date=True)
        self._clear_layout(self._recent_cards)
        if not sessions:
            self._recent_cards.addWidget(self._empty_label("dashboard.no_sessions"))
        for session in sessions:
            local_start = session.start_time.astimezone(self._local_timezone)
            card = QFrame()
            card.setObjectName("softCard")
            row_layout = QHBoxLayout(card)
            row_layout.setContentsMargins(12, 9, 12, 9)
            when = QLabel(
                f"{format_date(local_start, long=False)}  ·  {local_start:%H:%M}"
            )
            when.setObjectName("cardCaption")
            color = self._focus_item_colors.get(session.focus_item_id, "#7C5CFC")
            item = QLabel(session.focus_item_name)
            item.setObjectName("sectionTitle")
            item.setStyleSheet(f"color: {color};")
            duration = QLabel(format_compact_duration(session.duration_seconds))
            duration.setObjectName("cardCaption")
            text = QVBoxLayout()
            text.setSpacing(2)
            text.addWidget(item)
            text.addWidget(when)
            row_layout.addLayout(text, 1)
            row_layout.addWidget(duration)
            self._recent_cards.addWidget(card)

    def set_timeline(
        self,
        selected_day: date,
        sessions: Sequence[FocusSession],
        total_seconds: float,
    ) -> None:
        """Render one local day as a visual session timeline."""

        ordered = sorted(sessions, key=lambda session: session.start_time)
        self._timeline_data = (selected_day, list(ordered), total_seconds)
        blocked = self._timeline_date_edit.blockSignals(True)
        self._timeline_date_edit.setDate(
            QDate(selected_day.year, selected_day.month, selected_day.day)
        )
        self._timeline_date_edit.blockSignals(blocked)
        count_key = "count.sessions.one" if len(ordered) == 1 else "count.sessions.other"
        self._timeline_summary.setText(
            tr(
                "timeline.summary",
                duration=format_compact_duration(total_seconds),
                sessions=tr(count_key, count=len(ordered)),
            )
        )
        self._timeline_widget.set_values(
            selected_day, ordered, self._focus_item_colors
        )

    def set_analytics(self, snapshot: FocusAnalyticsSnapshot) -> None:
        """Present computed trends and factual Focus patterns."""

        self._analytics_data = snapshot
        self._daily_trend.set_values(snapshot.daily_trend)
        self._weekly_trend.set_values(snapshot.weekly_trend)
        self._monthly_trend.set_values(snapshot.monthly_trend)
        pattern = snapshot.pattern
        self._best_focus_time.setText(
            tr(
                "analytics.time_range",
                start=f"{pattern.best_start_hour:02d}:00",
                end=f"{pattern.best_end_hour:02d}:00",
            )
            if pattern.best_start_hour is not None and pattern.best_end_hour is not None
            else tr("common.no_value")
        )
        self._average_session.setText(
            format_compact_duration(pattern.average_session_seconds)
        )
        self._common_start_time.setText(
            tr("analytics.hour_value", hour=pattern.common_start_hour)
            if pattern.common_start_hour is not None
            else tr("common.no_value")
        )
        consistency = snapshot.consistency
        self._current_consistency.setText(
            tr("count.days", count=consistency.current_streak_days)
        )
        self._active_days.setText(
            tr("count.days", count=consistency.active_days)
        )
        self._longest_consistency.setText(
            tr("count.days", count=consistency.longest_streak_days)
        )

    def set_focus_distribution(
        self,
        period: AnalyticsDistributionPeriod,
        totals: Sequence[FocusItemTotal],
    ) -> None:
        animate = period is not self._analytics_distribution_period
        self._analytics_distribution_period = period
        self._analytics_distribution_data = list(totals)
        self._analytics_period_control.set_current_value(period)
        self._distribution_chart.set_values(
            self._analytics_distribution_data,
            self._focus_item_colors,
            animate=animate,
        )

    def set_monthly(self, summary: MonthlyStatistics) -> None:
        self._monthly_data = summary
        self._month_year = summary.year
        self._month_number = summary.month
        self._month_title.setText(format_month_year(summary.year, summary.month))
        self._month_total.setText(format_compact_duration(summary.total_seconds))
        self._month_average.setText(format_compact_duration(summary.daily_average_seconds))
        self._month_days.setText(str(summary.focus_days))
        self._month_sessions.setText(str(summary.total_sessions))
        self._month_longest.setText(format_compact_duration(summary.longest_session_seconds))
        self._month_best.setText(
            tr("dashboard.best_day_value", date=format_date(summary.best_day.day, long=False), duration=format_compact_duration(summary.best_day.duration_seconds))
            if summary.best_day else tr("common.no_value")
        )
        self._month_top_subject.setText(
            tr("dashboard.subject_value", subject=summary.top_focus_item.focus_item_name, duration=format_compact_duration(summary.top_focus_item.duration_seconds))
            if summary.top_focus_item else tr("common.no_value")
        )
        if summary.comparison_percent is None:
            self._month_comparison.setText(tr("dashboard.no_previous_month"))
        else:
            arrow = "↑" if summary.comparison_percent >= 0 else "↓"
            previous_name = get_localization().locale.standaloneMonthName(12 if summary.month == 1 else summary.month - 1)
            self._month_comparison.setText(tr("dashboard.month_comparison_value", arrow=arrow, percent=abs(summary.comparison_percent), month=previous_name))
        self._monthly_calendar.set_values(summary.daily_totals)
        self._set_month_subjects(summary.focus_item_totals)
        self._month_empty.setText(tr("dashboard.no_month_data", month=format_month_year(summary.year, summary.month)))
        self._month_empty.setVisible(summary.total_seconds <= 0)

    def set_focus_item_totals(self, totals: list[FocusItemTotal]) -> None:
        self._subject_total_data = list(totals)
        self._subject_table.setRowCount(len(totals))
        for row, total in enumerate(totals):
            item = QTableWidgetItem(total.focus_item_name)
            item.setForeground(
                QColor(self._focus_item_colors.get(total.focus_item_id, "#7C5CFC"))
            )
            self._subject_table.setItem(row, 0, item)
            self._subject_table.setItem(
                row, 1, QTableWidgetItem(format_compact_duration(total.duration_seconds))
            )
        self._clear_layout(self._focus_item_cards)
        if not totals:
            self._focus_item_cards.addWidget(
                self._empty_label("dashboard.no_focus_items")
            )
            return
        for total in totals:
            card = QFrame()
            card.setObjectName("focusItemCard")
            card.setAccessibleName(total.focus_item_name)
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(16, 13, 16, 13)
            card_layout.setSpacing(12)
            color = self._focus_item_colors.get(total.focus_item_id, "#7C5CFC")
            name = QLabel(total.focus_item_name)
            name.setObjectName("sectionTitle")
            name.setStyleSheet(f"color: {color};")
            name.setWordWrap(True)
            duration = QLabel(format_compact_duration(total.duration_seconds))
            duration.setObjectName("metricValue")
            duration.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            card_layout.addWidget(name, 1)
            card_layout.addWidget(duration)
            self._focus_item_cards.addWidget(card)

    def set_history(self, sessions: Sequence[FocusSession]) -> None:
        self._history_data = list(sessions)
        self._populate_session_table(
            self._history_table,
            sessions,
            include_date=True,
            include_details=True,
        )

    def set_focus_item_colors(self, colors: dict[int, str]) -> None:
        self._focus_item_colors = dict(colors)
        if hasattr(self, "_distribution_chart"):
            self._distribution_chart.set_values(
                self._analytics_distribution_data,
                self._focus_item_colors,
            )

    def set_gamification(self, snapshot: GamificationSnapshot) -> None:
        self._gamification_data = snapshot
        self._goal_label.setText(
            f"{format_compact_duration(snapshot.today_seconds)} / "
            f"{format_compact_duration(snapshot.daily_goal_seconds)}"
        )
        self._goal_progress.setValue(round(snapshot.goal_progress * 100))
        self._weekly_goal_label.setText(
            tr(
                "focus.weekly_goal_value",
                current=format_compact_duration(snapshot.weekly_seconds),
                goal=format_compact_duration(snapshot.weekly_goal_seconds),
            )
        )
        self._weekly_goal_progress.setValue(round(snapshot.weekly_goal_progress * 100))
        streak_key = "dashboard.streak.one" if snapshot.streak_days == 1 else "dashboard.streak.other"
        self._streak_label.setText(tr(streak_key, count=snapshot.streak_days))

    def selected_period(self) -> StatisticsPeriod:
        return self._period_combo.currentData()

    def selected_analytics_period(self) -> AnalyticsDistributionPeriod:
        value = self._analytics_period_control.current_value
        return (
            value
            if isinstance(value, AnalyticsDistributionPeriod)
            else self._analytics_distribution_period
        )

    def selected_history_id(self) -> int | None:
        row = self._history_table.currentRow()
        if row < 0:
            return None
        item = self._history_table.item(row, 0)
        return int(item.data(Qt.ItemDataRole.UserRole)) if item is not None else None

    def show_and_raise(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def show_overview(self) -> None:
        self.set_current_page(DashboardPage.OVERVIEW)
        self.show_and_raise()

    def show_history(self) -> None:
        self.set_current_page(DashboardPage.HISTORY)
        self.show_and_raise()

    def set_current_page(self, page: DashboardPage | int) -> None:
        """Switch pages immediately without page-level graphics effects."""

        target = DashboardPage(int(page))
        self._pages.setCurrentIndex(int(target))
        for nav_page, button in self._nav_buttons.items():
            blocked = button.blockSignals(True)
            button.setChecked(nav_page is target)
            button.blockSignals(blocked)

    def current_page(self) -> DashboardPage:
        return DashboardPage(self._pages.currentIndex())

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_sidebar"):
            self._update_navigation_mode(animate=self.isVisible())

    def show_data_error(self, area: str) -> None:
        self.statusBar().showMessage(tr("dashboard.load_error", area=tr(area)), 8000)

    @property
    def sidebar_mode(self) -> str:
        return self._sidebar_mode

    def set_sidebar_mode(self, mode: str) -> None:
        """Restore a preference without treating it as a user action or saving it."""
        self._sidebar_mode = normalize_dashboard_sidebar_mode(mode)
        self._update_navigation_mode()

    def show_sidebar_save_error(self) -> None:
        self.statusBar().showMessage(tr("dashboard.sidebar.save_error"), 8000)

    def _navigation_is_compact(self) -> bool:
        return self._sidebar_mode == "collapsed" or (
            self._sidebar_mode == "auto" and self.width() < 900
        )

    def _toggle_sidebar(self) -> None:
        target = "expanded" if self._navigation_is_compact() else "collapsed"
        self._sidebar_mode = target
        self._update_navigation_mode(animate=True)
        self.sidebar_mode_changed.emit(target)

    def _build_sidebar(self) -> SidebarFrame:
        sidebar = SidebarFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(6, 18, 6, 14)
        sidebar_layout.setSpacing(5)

        self._sidebar_toggle = _SidebarToggleButton()
        self._sidebar_toggle.setObjectName("dashboardSidebarToggle")
        self._sidebar_toggle.setFixedSize(32, 32)
        self._sidebar_toggle.setIconSize(QSize(20, 20))
        self._sidebar_toggle.setCheckable(True)
        self._sidebar_toggle.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._sidebar_toggle.clicked.connect(self._toggle_sidebar)
        self._sidebar_toggle_host = SidebarToggleHost(self._sidebar_toggle)
        sidebar_layout.addWidget(self._sidebar_toggle_host)

        self._navigation_group = QButtonGroup(self)
        self._navigation_group.setExclusive(True)
        self._nav_buttons: dict[DashboardPage, NavigationButton] = {}
        self._nav_text_keys = {
            DashboardPage.OVERVIEW: "dashboard.tab.overview",
            DashboardPage.TIMELINE: "dashboard.tab.timeline",
            DashboardPage.ANALYTICS: "dashboard.tab.analytics",
            DashboardPage.MONTHLY: "dashboard.tab.monthly",
            DashboardPage.FOCUS_ITEMS: "dashboard.tab.subjects",
            DashboardPage.HISTORY: "dashboard.tab.history",
            DashboardPage.AI_ASSISTANT: "agent.title",
        }

        self._nav_focus_label = self._navigation_label()
        sidebar_layout.addWidget(self._nav_focus_label)
        self._add_navigation_button(sidebar_layout, DashboardPage.OVERVIEW)
        self._add_navigation_button(sidebar_layout, DashboardPage.TIMELINE)
        sidebar_layout.addSpacing(12)

        self._nav_insights_label = self._navigation_label()
        sidebar_layout.addWidget(self._nav_insights_label)
        self._add_navigation_button(sidebar_layout, DashboardPage.ANALYTICS)
        self._add_navigation_button(sidebar_layout, DashboardPage.MONTHLY)
        sidebar_layout.addSpacing(12)

        self._nav_library_label = self._navigation_label()
        sidebar_layout.addWidget(self._nav_library_label)
        self._add_navigation_button(sidebar_layout, DashboardPage.FOCUS_ITEMS)
        self._add_navigation_button(sidebar_layout, DashboardPage.HISTORY)
        self._add_navigation_button(sidebar_layout, DashboardPage.AI_ASSISTANT)
        sidebar_layout.addStretch()
        return sidebar

    def _navigation_label(self) -> NavigationGroup:
        return NavigationGroup()

    def _add_navigation_button(
        self, layout: QVBoxLayout, page: DashboardPage
    ) -> None:
        button = NavigationButton()
        button.setObjectName("navigationButton")
        button.setCheckable(True)
        button.setAutoExclusive(True)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setIconSize(QSize(20, 20))
        button.setFixedHeight(42)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.clicked.connect(lambda _checked=False, target=page: self.set_current_page(target))
        self._navigation_group.addButton(button, int(page))
        self._nav_buttons[page] = button
        layout.addWidget(button)

    def _update_navigation_mode(self, *, animate: bool = False) -> None:
        compact = self._navigation_is_compact()
        width = SidebarFrame.collapsed_width if compact else SidebarFrame.expanded_width
        if self._sidebar.width() != width:
            self._pages.finish_transition()
        self._sidebar_toggle.setChecked(compact)
        action = tr("dashboard.sidebar.expand" if compact else "dashboard.sidebar.collapse")
        self._sidebar_toggle.setToolTip(action)
        self._sidebar_toggle.setAccessibleName(action)
        # Resolve breakpoint-dependent layouts once against the destination,
        # not against every intermediate pixel of the width animation.
        self.agent_page.set_layout_width_override(self.width() - width)
        # Manual expansion makes a previously unreachable narrow content width
        # possible. Reflow only this header instead of squeezing its text.
        narrow_content = self.width() - width < 600
        self._analytics_period_row.setDirection(
            QBoxLayout.Direction.TopToBottom
            if narrow_content else QBoxLayout.Direction.LeftToRight
        )
        self._analytics_period_row.setStretch(0, 0 if narrow_content else 1)
        self._analytics_period_row.setAlignment(
            self._analytics_period_control,
            Qt.AlignmentFlag.AlignRight if narrow_content else Qt.AlignmentFlag(0),
        )
        for page, button in self._nav_buttons.items():
            button.set_navigation_text(tr(self._nav_text_keys[page]))
        self._sidebar.set_expanded(not compact, animate=animate)
        self._update_sidebar_progress(self._sidebar.progress)

    def _update_sidebar_progress(self, progress: float) -> None:
        self._sidebar_toggle_host.set_reveal(progress)
        for label in (
            self._nav_focus_label,
            self._nav_insights_label,
            self._nav_library_label,
        ):
            label.set_reveal(progress)
        for button in self._nav_buttons.values():
            button.set_reveal(progress)

    def _sidebar_settled(self) -> None:
        self.agent_page.set_layout_width_override(None)

    def _finish_sidebar_motion(self, _value: object = None) -> None:
        self._sidebar.finish()

    def _set_trend_index(self, index: int) -> None:
        self._trend_stack.setCurrentIndex(index)
        self._trend_control.set_current_index(index)

    def _add_insight_row(self, card: QFrame, title_key: str) -> QLabel:
        row = QWidget()
        row.setObjectName("insightRow")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 7, 0, 7)
        title = QLabel(tr(title_key))
        title.setObjectName("cardCaption")
        title.setWordWrap(True)
        value = QLabel(tr("common.no_value"))
        value.setObjectName("insightValue")
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row_layout.addWidget(title, 1)
        row_layout.addWidget(value)
        self._card_layout(card).addWidget(row)
        self._card_titles.append((title, title_key))
        return value

    def _refresh_icons(self) -> None:
        self._sidebar_toggle.setIcon(IconSystem.icon(IconName.SIDEBAR))
        icons = (
            IconName.OVERVIEW,
            IconName.TIMELINE,
            IconName.ANALYTICS,
            IconName.MONTHLY,
            IconName.FOCUS_ITEMS,
            IconName.HISTORY,
            IconName.ASSISTANT,
        )
        for index, name in enumerate(icons):
            icon = IconSystem.icon(name)
            self._tabs.setTabIcon(index, icon)
            self._nav_buttons[DashboardPage(index)].setIcon(icon)

    def _card(self, title_key: str) -> QFrame:
        card = QFrame()
        card.setObjectName("sectionSurface")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(8)
        label = QLabel(tr(title_key))
        label.setObjectName("sectionTitle")
        label.setWordWrap(True)
        self._card_titles.append((label, title_key))
        layout.addWidget(label)
        return card

    @staticmethod
    def _card_layout(card: QFrame) -> QVBoxLayout:
        """Return the layout installed by the Dashboard card factories."""

        return cast(QVBoxLayout, card.layout())

    def _scroll(self, content: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        return scroll

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()

    def _empty_label(self, key: str) -> QLabel:
        label = QLabel(tr(key))
        label.setObjectName("secondary")
        label.setWordWrap(True)
        return label

    def _new_table(
        self,
        header_keys: list[str],
        role: _SessionTableRole = _SessionTableRole.READ_ONLY,
    ) -> QTableWidget:
        table = _SessionTableWidget(0, len(header_keys))
        table.setObjectName("sessionDataTable")
        table.setHorizontalHeaderLabels([tr(key) if key else "" for key in header_keys])
        self._table_headers.append((table, header_keys))
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        if role is _SessionTableRole.ACTIONABLE:
            table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        else:
            table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
            table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(False)
        table.setShowGrid(False)
        table.setItemDelegate(_SessionTableDelegate(table))
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(40)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setMinimumSectionSize(72)
        table.horizontalHeader().setFixedHeight(38)
        get_theme_manager().theme_changed.connect(table.refresh_theme)
        return table

    def _populate_session_table(
        self,
        table: QTableWidget,
        sessions: Sequence[FocusSession],
        include_date: bool,
        include_details: bool = False,
    ) -> None:
        table.setRowCount(len(sessions))
        for row, session in enumerate(sessions):
            local_start = session.start_time.astimezone(self._local_timezone)
            local_end = session.end_time.astimezone(self._local_timezone)
            values: list[str] = []
            if include_date:
                values.append(format_date(local_start, long=False))
            values.extend(
                [
                    local_start.strftime("%H:%M"),
                    local_end.strftime("%H:%M"),
                    session.focus_item_name,
                    format_compact_duration(session.duration_seconds),
                ]
            )
            if include_details:
                values.append(getattr(session, "note", ""))
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, session.id)
                item_column = 3 if include_date else 2
                if column == item_column:
                    color = self._focus_item_colors.get(
                        session.focus_item_id, "#7C5CFC"
                    )
                    item.setForeground(QColor(color))
                table.setItem(row, column, item)

    def _set_month_subjects(self, totals: tuple[FocusItemTotal, ...]) -> None:
        while self._month_subject_layout.count():
            item = self._month_subject_layout.takeAt(0)
            if item is not None:
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
        if not totals:
            empty = QLabel(tr("dashboard.no_month_subjects"))
            empty.setObjectName("secondary")
            self._month_subject_layout.addWidget(empty)
            return
        grand_total = sum(item.duration_seconds for item in totals) or 1.0
        for rank, total in enumerate(totals, start=1):
            row = QWidget()
            row.setObjectName("distributionRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(8, 9, 8, 9)
            row_layout.setSpacing(10)
            rank_label = QLabel(f"{rank:02d}")
            rank_label.setObjectName("cardCaption")
            rank_label.setFixedWidth(28)
            color = self._focus_item_colors.get(total.focus_item_id, "#7C5CFC")
            name = QLabel(total.focus_item_name)
            name.setObjectName("sectionTitle")
            name.setStyleSheet(f"color: {color};")
            name.setWordWrap(True)
            percent = QLabel(f"{total.duration_seconds / grand_total:.0%}")
            percent.setObjectName("cardCaption")
            duration = QLabel(format_compact_duration(total.duration_seconds))
            duration.setObjectName("insightValue")
            duration.setMinimumWidth(72)
            duration.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row_layout.addWidget(rank_label)
            row_layout.addWidget(name, 1)
            row_layout.addWidget(percent)
            row_layout.addWidget(duration)
            self._month_subject_layout.addWidget(row)

    def _shift_month(self, offset: int) -> None:
        zero_based = self._month_year * 12 + self._month_number - 1 + offset
        self._month_year, month_index = divmod(zero_based, 12)
        self._month_number = month_index + 1
        self.month_changed.emit(self._month_year, self._month_number)

    def _request_edit(self) -> None:
        session_id = self.selected_history_id()
        if session_id is not None:
            self.edit_session_requested.emit(session_id)

    def _request_delete(self) -> None:
        session_id = self.selected_history_id()
        if session_id is not None:
            self.delete_session_requested.emit(session_id)

def _greeting() -> str:
    hour = datetime.now(tz=UTC).astimezone().hour
    if hour < 12:
        return tr("dashboard.greeting.morning")
    if hour < 18:
        return tr("dashboard.greeting.afternoon")
    return tr("dashboard.greeting.evening")
