"""Controller for Dashboard queries and session history mutations."""

from __future__ import annotations

import logging
from datetime import date, datetime, time

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QDialog, QMessageBox

from app.data.focus_item_repository import FocusItemError, FocusItemRepository
from app.data.focus_session_repository import (
    FocusSessionNotFoundError,
    FocusSessionRepository,
)
from app.focus import ManualFocusEntry, ManualFocusEntryService
from app.i18n import tr
from app.statistics import (
    AnalyticsDistributionPeriod,
    MonthlyStatistics,
    StatisticsPeriod,
    StatisticsService,
)
from app.statistics.statistics_service import DashboardStatisticsSnapshot
from app.ui.dashboard import DashboardWindow
from app.ui.message_boxes import ask_confirmation
from app.ui.replay_dialog import FocusReplayDialog
from app.ui.session_editor_dialog import SessionEditorDialog

logger = logging.getLogger(__name__)


class DashboardController(QObject):
    """Keep SQL and statistics calculations outside Dashboard widgets."""

    data_changed = Signal()

    def __init__(
        self,
        window: DashboardWindow,
        statistics_service: StatisticsService,
        focus_item_repository: FocusItemRepository,
        focus_session_repository: FocusSessionRepository,
    ) -> None:
        super().__init__()
        self._window = window
        self._statistics = statistics_service
        self._focus_items = focus_item_repository
        self._focus_sessions = focus_session_repository
        self._manual_entries = ManualFocusEntryService(
            focus_item_repository, focus_session_repository
        )
        self._replay_dialog = FocusReplayDialog(window)
        window.refresh_requested.connect(self.refresh)
        window.period_changed.connect(self.refresh_focus_items)
        window.timeline_date_changed.connect(self.refresh_timeline)
        window.month_changed.connect(self.refresh_month)
        window.add_session_requested.connect(self.add_session)
        window.edit_session_requested.connect(self.edit_session)
        window.delete_session_requested.connect(self.delete_session)
        window.replay_requested.connect(self.show_today_replay)
        window.analytics_period_changed.connect(self.refresh_distribution)

    def show(self) -> None:
        self.refresh()
        self._window.show_overview()

    def show_history(self) -> None:
        self.refresh()
        self._window.show_history()

    def refresh(self) -> None:
        local_now = datetime.now(tz=self._statistics.local_timezone)
        snapshot: DashboardStatisticsSnapshot | None = None
        current_month: MonthlyStatistics | None = None
        self._window.set_focus_item_colors(
            {item.id: item.color for item in self._focus_items.list_all()}
        )
        try:
            snapshot = self._statistics.dashboard_snapshot(local_now)
            self._window.set_today(snapshot.today_total, snapshot.today_sessions)
            self._window.set_heatmap_detail(
                local_now.date(),
                snapshot.today_total,
                snapshot.today_sessions,
                (
                    snapshot.today_focus_item_totals[0].focus_item_name
                    if snapshot.today_focus_item_totals
                    else None
                ),
            )
            self._window.set_weekly(list(snapshot.weekly_daily_totals))
            self._window.set_heatmap(
                self._statistics.heatmap_data(
                    365,
                    local_now,
                    complete_start_week=True,
                )
            )
            self._window.set_overview_focus_items(
                list(snapshot.weekly_focus_item_totals[:5])
            )
            self._window.set_recent_sessions(snapshot.recent_sessions)
            self._window.set_timeline(
                local_now.date(), snapshot.today_sessions, snapshot.today_total
            )
            self._window.set_analytics(snapshot.analytics)
            analytics_period = self._window.selected_analytics_period()
            if analytics_period is AnalyticsDistributionPeriod.DAILY:
                distribution = snapshot.today_focus_item_totals
            elif analytics_period is AnalyticsDistributionPeriod.WEEKLY:
                distribution = snapshot.weekly_focus_item_totals
            else:
                current_month = self._statistics.monthly_statistics(
                    local_now.year, local_now.month
                )
                distribution = current_month.focus_item_totals
            self._window.set_focus_distribution(analytics_period, distribution)
        except Exception:
            logger.exception("Dashboard overview refresh failed")
            self._window.show_data_error("dashboard.area.overview")
        try:
            if snapshot is None:
                snapshot = self._statistics.dashboard_snapshot(local_now)
            self._window.set_focus_item_totals(
                list(snapshot.focus_item_totals_for(self._window.selected_period()))
            )
            self._window.set_history(snapshot.history_sessions)
        except Exception:
            logger.exception("Dashboard history/subject refresh failed")
            self._window.show_data_error("dashboard.area.history_subjects")
        if current_month is None:
            self.refresh_month(local_now.year, local_now.month)
        else:
            try:
                self._set_monthly(current_month)
            except Exception:
                logger.exception(
                    "Monthly statistics refresh failed for %04d-%02d",
                    current_month.year,
                    current_month.month,
                )
                self._window.show_data_error("dashboard.area.monthly")

    def refresh_focus_items(self, period: StatisticsPeriod) -> None:
        self._window.set_focus_item_totals(self._statistics.focus_item_totals(period))

    def refresh_timeline(self, selected_day: date) -> None:
        try:
            reference = datetime.combine(
                selected_day,
                time(hour=12),
                tzinfo=self._statistics.local_timezone,
            )
            total = self._statistics.heatmap_data(1, reference).days[0].duration_seconds
            self._window.set_timeline(
                selected_day,
                self._statistics.sessions_for_day(selected_day),
                total,
            )
        except Exception:
            logger.exception("Timeline refresh failed for %s", selected_day)
            self._window.show_data_error("dashboard.area.selected_day")

    def show_today_replay(self) -> None:
        summary = self._statistics.daily_replay()
        self._replay_dialog.set_summary(summary)
        self._replay_dialog.show()
        self._replay_dialog.raise_()
        self._replay_dialog.activateWindow()

    def refresh_analytics(self, now: datetime | None = None) -> None:
        try:
            local_now = now or datetime.now(tz=self._statistics.local_timezone)
            self._window.set_analytics(self._statistics.analytics_snapshot(local_now))
            self.refresh_distribution(self._window.selected_analytics_period(), local_now)
        except Exception:
            logger.exception("Focus Analytics refresh failed")
            self._window.show_data_error("dashboard.area.analytics")

    def refresh_distribution(
        self,
        period: AnalyticsDistributionPeriod,
        now: datetime | None = None,
    ) -> None:
        local_now = now or datetime.now(tz=self._statistics.local_timezone)
        if period is AnalyticsDistributionPeriod.DAILY:
            totals = self._statistics.focus_item_totals(
                StatisticsPeriod.TODAY, local_now
            )
        elif period is AnalyticsDistributionPeriod.WEEKLY:
            totals = self._statistics.focus_item_totals(
                StatisticsPeriod.THIS_WEEK, local_now
            )
        else:
            totals = list(
                self._statistics.monthly_statistics(
                    local_now.year, local_now.month
                ).focus_item_totals
            )
        self._window.set_focus_distribution(period, totals)

    def refresh_month(self, year: int, month: int) -> None:
        try:
            self._set_monthly(self._statistics.monthly_statistics(year, month))
        except Exception:
            logger.exception("Monthly statistics refresh failed for %04d-%02d", year, month)
            self._window.show_data_error("dashboard.area.monthly")

    def _set_monthly(self, summary: MonthlyStatistics) -> None:
        self._window.set_monthly(summary)

    def add_session(self) -> None:
        dialog = SessionEditorDialog(self._statistics.local_timezone, self._window)
        dialog.set_focus_items(self._focus_items.list_active())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        item_id, start, end, duration, note = dialog.focus_values()
        try:
            self._manual_entries.create(
                ManualFocusEntry(item_id, start, end, duration, note)
            )
        except (FocusItemError, ValueError, RuntimeError) as error:
            QMessageBox.warning(self._window, tr("app.name"), str(error))
            return
        self._after_data_change()

    def edit_session(self, session_id: int) -> None:
        try:
            session = self._focus_sessions.get(session_id)
        except FocusSessionNotFoundError as error:
            QMessageBox.warning(self._window, tr("app.name"), str(error))
            return
        dialog = SessionEditorDialog(self._statistics.local_timezone, self._window)
        dialog.set_focus_items(self._focus_items.list_all(), session.focus_item_id)
        dialog.set_session(session)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        item_id, start, end, duration, note = dialog.focus_values()
        try:
            item = self._focus_items.get(item_id)
            self._focus_sessions.update(session_id, item, start, end, duration, note)
        except (FocusItemError, ValueError, RuntimeError) as error:
            QMessageBox.warning(self._window, tr("app.name"), str(error))
            return
        self._after_data_change()

    def delete_session(self, session_id: int) -> None:
        if not ask_confirmation(
            self._window,
            tr("dashboard.delete_session_title"),
            tr("dashboard.delete_session_confirm"),
            destructive=True,
        ):
            return
        try:
            self._focus_sessions.delete(session_id)
        except FocusSessionNotFoundError as error:
            QMessageBox.warning(self._window, tr("app.name"), str(error))
            return
        self._after_data_change()

    def _after_data_change(self) -> None:
        self.refresh()
        self.data_changed.emit()
