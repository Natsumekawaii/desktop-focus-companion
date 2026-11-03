"""Private DashboardWindow control construction; behavior stays in the public window."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import (
    Qt,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.i18n import tr
from app.statistics import (
    AnalyticsDistributionPeriod,
)
from app.timer.formatting import format_compact_duration
from app.ui.analytics_widgets import FocusDistributionChart, FocusTrendWidget
from app.ui.components import (
    MetricStrip,
    ResponsiveGrid,
    SegmentedControl,
    ThemedDateEdit,
    apply_elevation,
)
from app.ui.dashboard_widgets import (
    _FocusActivityCard,
    _SessionTableRole,
)
from app.ui.heatmap_widget import FocusActivityMode, HeatmapWidget
from app.ui.monthly_calendar import MonthlyCalendarWidget
from app.ui.rounded_selector import RoundedComboBox, SelectorDensity
from app.ui.timeline_widget import DailyTimelineWidget
from app.ui.weekly_chart import WeeklyChart


class _DashboardWindowBuilders:
    # Construction calls hooks supplied by the concrete Qt window. This bridge
    # is type-checking-only; it does not change runtime attribute lookup.
    if TYPE_CHECKING:
        def __getattr__(self, name: str) -> Any: ...

    def _build_overview_tab(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 22, 24, 28)
        layout.setSpacing(18)
        self._greeting_label = QLabel()
        self._greeting_label.setObjectName("secondary")
        self._greeting_label.setWordWrap(True)
        layout.addWidget(self._greeting_label)

        hero = QFrame()
        hero.setObjectName("heroCard")
        apply_elevation(hero, subtle=True)
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(22, 18, 22, 18)
        hero_layout.setSpacing(24)
        today_column = QVBoxLayout()
        self._hero_today_caption = QLabel()
        self._hero_today_caption.setObjectName("cardCaption")
        self._hero_today_total = QLabel(tr("duration.zero"))
        self._hero_today_total.setObjectName("heroValue")
        self._today_total = self._hero_today_total
        self._goal_label = QLabel(
            f"{tr('duration.zero')} / {format_compact_duration(5 * 60 * 60)}"
        )
        self._goal_label.setObjectName("secondary")
        self._goal_progress = QProgressBar()
        self._goal_progress.setRange(0, 100)
        self._goal_progress.setTextVisible(False)
        self._goal_progress.setFixedHeight(10)
        today_column.addWidget(self._hero_today_caption)
        today_column.addWidget(self._hero_today_total)
        today_column.addWidget(self._goal_label)
        today_column.addWidget(self._goal_progress)
        self._replay_button = QPushButton()
        self._replay_button.setObjectName("ghost")
        self._replay_button.clicked.connect(self.replay_requested)
        today_column.addWidget(
            self._replay_button,
            alignment=Qt.AlignmentFlag.AlignLeft,
        )
        hero_layout.addLayout(today_column, 1)
        layout.addWidget(hero)

        metric_strip = MetricStrip(max_columns=2)
        week_card = metric_strip.add_metric(
            tr("dashboard.focus_week"), tr("duration.zero")
        )
        self._card_titles.append((week_card.caption_label, "dashboard.focus_week"))
        self._weekly_total = week_card.value_label
        self._weekly_goal_label = QLabel()
        self._weekly_goal_label.setObjectName("secondary")
        self._weekly_goal_label.setWordWrap(True)
        self._weekly_goal_progress = QProgressBar()
        self._weekly_goal_progress.setRange(0, 100)
        self._weekly_goal_progress.setTextVisible(False)
        self._weekly_goal_progress.setFixedHeight(10)
        self._card_layout(week_card).addWidget(self._weekly_goal_label)
        self._card_layout(week_card).addWidget(self._weekly_goal_progress)
        progress_card = metric_strip.add_metric(
            tr("dashboard.goal_streak"), tr("dashboard.streak.other", count=0)
        )
        self._card_titles.append((progress_card.caption_label, "dashboard.goal_streak"))
        self._streak_label = progress_card.value_label
        layout.addWidget(metric_strip)

        weekly_card = self._card("dashboard.time_distribution")
        self._weekly_chart = WeeklyChart()
        self._weekly_chart.setMinimumHeight(190)
        self._card_layout(weekly_card).addWidget(self._weekly_chart)
        self._activity_mode_keys = (
            "heatmap.mode.daily",
            "heatmap.mode.weekly",
            "heatmap.mode.cumulative",
        )
        self._activity_mode_control = SegmentedControl(
            (
                (tr(self._activity_mode_keys[0]), FocusActivityMode.DAILY),
                (tr(self._activity_mode_keys[1]), FocusActivityMode.WEEKLY),
                (
                    tr(self._activity_mode_keys[2]),
                    FocusActivityMode.CUMULATIVE,
                ),
            )
        )
        self._activity_mode_control.value_changed.connect(
            self._set_focus_activity_mode
        )
        heatmap_card = _FocusActivityCard(
            tr("dashboard.heatmap_title"), self._activity_mode_control
        )
        self._card_titles.append(
            (heatmap_card.title_label, "dashboard.heatmap_title")
        )
        self._activity_card = heatmap_card
        self._heatmap = HeatmapWidget()
        heatmap_card.content_layout.addWidget(self._heatmap)
        layout.addWidget(heatmap_card)
        layout.addWidget(weekly_card)

        detail_card = self._card("dashboard.day_details")
        detail_header = QHBoxLayout()
        self._day_title = QLabel(tr("common.today"))
        self._day_title.setObjectName("sectionTitle")
        self._day_total = QLabel(tr("duration.zero"))
        self._day_total.setObjectName("metricValue")
        detail_header.addWidget(self._day_title)
        detail_header.addStretch()
        detail_header.addWidget(self._day_total)
        self._card_layout(detail_card).addLayout(detail_header)
        detail_summary = QHBoxLayout()
        self._day_session_count = QLabel()
        self._day_session_count.setObjectName("statusPill")
        self._day_primary_item = QLabel()
        self._day_primary_item.setObjectName("secondary")
        self._day_primary_item.setWordWrap(True)
        detail_summary.addWidget(self._day_session_count)
        detail_summary.addWidget(self._day_primary_item, 1)
        self._card_layout(detail_card).addLayout(detail_summary)
        self._day_empty = QLabel()
        self._day_empty.setObjectName("secondary")
        self._card_layout(detail_card).addWidget(self._day_empty)
        self._day_table = self._new_table(["dashboard.header.start", "dashboard.header.end", "dashboard.header.subject", "dashboard.header.duration"])
        self._day_table.setMaximumHeight(190)
        self._card_layout(detail_card).addWidget(self._day_table)

        bottom = ResponsiveGrid(min_item_width=320, max_columns=2)
        subjects_card = self._card("dashboard.top_subjects_week")
        self._overview_subject_table = self._new_table(["dashboard.header.subject", "dashboard.header.duration"])
        self._overview_subject_table.hide()
        self._card_layout(subjects_card).addWidget(self._overview_subject_table)
        self._overview_focus_cards = QVBoxLayout()
        self._card_layout(subjects_card).addLayout(self._overview_focus_cards)
        recent_card = self._card("dashboard.recent_sessions")
        self._recent_table = self._new_table(["dashboard.header.date", "dashboard.header.start", "dashboard.header.end", "dashboard.header.subject", "dashboard.header.duration"])
        self._recent_table.hide()
        self._card_layout(recent_card).addWidget(self._recent_table)
        self._recent_cards = QVBoxLayout()
        self._card_layout(recent_card).addLayout(self._recent_cards)
        bottom.add_widget(subjects_card)
        bottom.add_widget(recent_card)
        layout.addWidget(bottom)
        layout.addWidget(detail_card)
        return self._scroll(content)

    def _build_monthly_tab(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 22, 24, 28)
        layout.setSpacing(18)
        navigation = QHBoxLayout()
        self._previous_button = QPushButton()
        self._previous_button.setObjectName("ghost")
        self._previous_button.clicked.connect(lambda: self._shift_month(-1))
        self._next_button = QPushButton()
        self._next_button.setObjectName("ghost")
        self._next_button.clicked.connect(lambda: self._shift_month(1))
        self._month_title = QLabel()
        self._month_title.setObjectName("pageTitle")
        navigation.addWidget(self._month_title)
        navigation.addStretch()
        navigation.addWidget(self._previous_button)
        navigation.addWidget(self._next_button)
        layout.addLayout(navigation)
        self._month_empty = QLabel()
        self._month_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._month_empty.setObjectName("secondary")

        primary_strip = MetricStrip(max_columns=4)
        primary_specs = (
            ("dashboard.total_study_time", "_month_total"),
            ("dashboard.daily_average", "_month_average"),
            ("dashboard.study_days", "_month_days"),
            ("dashboard.sessions", "_month_sessions"),
        )
        for label, attribute in primary_specs:
            item = primary_strip.add_metric(tr(label), tr("common.no_value"))
            self._card_titles.append((item.caption_label, label))
            setattr(self, attribute, item.value_label)
        layout.addWidget(primary_strip)

        chart_card = self._card("dashboard.daily_study_time")
        self._card_layout(chart_card).addWidget(self._month_empty)
        self._monthly_calendar = MonthlyCalendarWidget()
        self._card_layout(chart_card).addWidget(self._monthly_calendar)
        layout.addWidget(chart_card)

        insight_card = self._card("dashboard.month_insights")
        secondary_specs = (
            ("dashboard.longest_session", "_month_longest"),
            ("dashboard.best_study_day", "_month_best"),
            ("dashboard.top_subject", "_month_top_subject"),
            ("dashboard.month_comparison", "_month_comparison"),
        )
        for label, attribute in secondary_specs:
            value = self._add_insight_row(insight_card, label)
            setattr(self, attribute, value)
        layout.addWidget(insight_card)

        subjects_card = self._card("dashboard.subject_breakdown")
        self._month_subject_layout = QVBoxLayout()
        self._month_subject_layout.setSpacing(2)
        self._card_layout(subjects_card).addLayout(self._month_subject_layout)
        layout.addWidget(subjects_card)
        layout.addStretch()
        return self._scroll(content)

    def _build_analytics_tab(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 22, 24, 28)
        layout.setSpacing(18)
        self._analytics_title = QLabel()
        self._analytics_title.setObjectName("pageTitle")
        self._analytics_subtitle = QLabel()
        self._analytics_subtitle.setObjectName("secondary")
        self._analytics_subtitle.setWordWrap(True)
        layout.addWidget(self._analytics_title)
        layout.addWidget(self._analytics_subtitle)

        trend_card = self._card("analytics.focus_trend")
        trend_header = QHBoxLayout()
        trend_header.addStretch()
        self._trend_keys = (
            "analytics.trend_period.daily",
            "analytics.trend_period.weekly",
            "analytics.trend_period.monthly",
        )
        self._trend_control = SegmentedControl(
            [(tr(key), index) for index, key in enumerate(self._trend_keys)]
        )
        self._trend_control.current_changed.connect(self._set_trend_index)
        trend_header.addWidget(self._trend_control)
        self._trend_stack = QStackedWidget()
        self._trend_stack.setObjectName("chartStack")
        self._daily_trend = FocusTrendWidget()
        self._weekly_trend = FocusTrendWidget()
        self._monthly_trend = FocusTrendWidget()
        for chart in (self._daily_trend, self._weekly_trend, self._monthly_trend):
            self._trend_stack.addWidget(chart)
        self._card_layout(trend_card).addLayout(trend_header)
        self._card_layout(trend_card).addWidget(self._trend_stack)
        layout.addWidget(trend_card)

        insight_grid = ResponsiveGrid(min_item_width=300, max_columns=2)
        pattern_card = self._card("analytics.pattern_title")
        self._best_focus_time = self._add_insight_row(
            pattern_card, "analytics.best_focus_time"
        )
        self._average_session = self._add_insight_row(
            pattern_card, "analytics.average_session"
        )
        self._common_start_time = self._add_insight_row(
            pattern_card, "analytics.common_start_time"
        )
        consistency_card = self._card("analytics.consistency_title")
        self._current_consistency = self._add_insight_row(
            consistency_card, "analytics.current_consistency"
        )
        self._active_days = self._add_insight_row(
            consistency_card, "analytics.active_days"
        )
        self._longest_consistency = self._add_insight_row(
            consistency_card, "analytics.longest_consistency"
        )
        insight_grid.add_widget(pattern_card)
        insight_grid.add_widget(consistency_card)
        layout.addWidget(insight_grid)

        distribution_card = self._card("analytics.distribution.title")
        period_row = QHBoxLayout()
        period_hint = QLabel(tr("analytics.distribution.hint"))
        period_hint.setObjectName("secondary")
        period_hint.setWordWrap(True)
        self._analytics_period_control = SegmentedControl(
            [
                (tr("analytics.period.daily"), AnalyticsDistributionPeriod.DAILY),
                (tr("analytics.period.weekly"), AnalyticsDistributionPeriod.WEEKLY),
                (tr("analytics.period.monthly"), AnalyticsDistributionPeriod.MONTHLY),
            ]
        )
        self._analytics_period_control.value_changed.connect(
            lambda value: self.analytics_period_changed.emit(value)
        )
        period_row.addWidget(period_hint, 1)
        period_row.addWidget(self._analytics_period_control)
        self._distribution_chart = FocusDistributionChart()
        self._card_layout(distribution_card).addLayout(period_row)
        self._card_layout(distribution_card).addWidget(self._distribution_chart)
        layout.addWidget(distribution_card)

        layout.addStretch()
        return self._scroll(content)

    def _build_timeline_tab(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(22, 18, 22, 22)
        page_layout.setSpacing(14)
        header = QHBoxLayout()
        self._timeline_title = QLabel()
        self._timeline_title.setObjectName("pageTitle")
        self._timeline_date_edit = ThemedDateEdit()
        self._timeline_date_edit.dateChanged.connect(
            lambda value: self.timeline_date_changed.emit(value.toPython())
        )
        self._timeline_today_button = QPushButton()
        self._timeline_today_button.clicked.connect(
            lambda: self.timeline_date_changed.emit(
                datetime.now(tz=self._local_timezone).date()
            )
        )
        header.addWidget(self._timeline_title)
        header.addStretch()
        header.addWidget(self._timeline_date_edit)
        header.addWidget(self._timeline_today_button)
        self._timeline_summary = QLabel()
        self._timeline_summary.setObjectName("metricValue")
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(6, 4, 6, 12)
        self._timeline_widget = DailyTimelineWidget(self._local_timezone)
        content_layout.addWidget(self._timeline_widget)
        content_layout.addStretch()
        scroll = self._scroll(content)
        page_layout.addLayout(header)
        page_layout.addWidget(self._timeline_summary)
        page_layout.addWidget(scroll, 1)
        return page

    def _build_subject_tab(self) -> QWidget:
        widget = QWidget()
        self._period_combo = RoundedComboBox(density=SelectorDensity.COMPACT)
        self._period_combo.currentIndexChanged.connect(
            lambda: self.period_changed.emit(self.selected_period())
        )
        self._subject_table = self._new_table(["dashboard.header.subject", "dashboard.header.duration"])
        self._subject_table.hide()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(24, 22, 24, 28)
        layout.setSpacing(18)
        self._subject_title = QLabel()
        self._subject_title.setObjectName("pageTitle")
        self._subject_title.setWordWrap(True)
        self._subject_title.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        header = QHBoxLayout()
        header.addWidget(self._subject_title, 1)
        header.addWidget(self._period_combo)
        layout.addLayout(header)
        layout.addWidget(self._subject_table)
        card = self._card("dashboard.focus_item_summary")
        self._focus_item_cards = QVBoxLayout()
        self._focus_item_cards.setSpacing(8)
        self._card_layout(card).addLayout(self._focus_item_cards)
        layout.addWidget(card)
        layout.addStretch()
        return self._scroll(widget)

    def _build_history_tab(self) -> QWidget:
        widget = QWidget()
        self._history_table = self._new_table(
            [
                "dashboard.header.date",
                "dashboard.header.start",
                "dashboard.header.end",
                "dashboard.header.subject",
                "dashboard.header.duration",
                "dashboard.header.note",
            ],
            role=_SessionTableRole.ACTIONABLE,
        )
        self._add_button = QPushButton()
        self._add_button.setObjectName("primary")
        self._add_button.clicked.connect(self.add_session_requested)
        self._edit_button = QPushButton()
        self._edit_button.clicked.connect(self._request_edit)
        self._delete_button = QPushButton()
        self._delete_button.setObjectName("danger")
        self._delete_button.clicked.connect(self._request_delete)
        self._refresh_button = QPushButton()
        self._refresh_button.setObjectName("ghost")
        self._refresh_button.clicked.connect(self.refresh_requested)
        primary_actions = QHBoxLayout()
        primary_actions.setSpacing(8)
        primary_actions.addWidget(self._add_button)
        primary_actions.addWidget(self._edit_button)
        primary_actions.addWidget(self._delete_button)
        primary_actions.addStretch()
        primary_actions.addWidget(self._refresh_button)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(24, 22, 24, 28)
        layout.setSpacing(14)
        self._history_title = QLabel()
        self._history_title.setObjectName("pageTitle")
        layout.addWidget(self._history_title)
        layout.addLayout(primary_actions)
        layout.addWidget(self._history_table)
        return widget
