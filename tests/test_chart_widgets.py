"""Rendering contracts for the non-bar statistical visualizations."""

from datetime import date, timedelta

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

from app.statistics import DailyTotal, TrendPoint
from app.ui.analytics_widgets import FocusTrendWidget
from app.ui.replay_dialog import HourlyDistributionWidget, _hour_intensity
from app.ui.trend_callout import TrendCalloutPlacement
from app.ui.weekly_chart import WeeklyChart


def test_weekly_chart_renders_seven_day_line_and_area(qt_application) -> None:
    start = date(2026, 8, 17)
    chart = WeeklyChart()
    chart.set_values(
        [
            DailyTotal(start + timedelta(days=index), duration)
            for index, duration in enumerate((0, 900, 1800, 3600, 2400, 5400, 1200))
        ]
    )
    chart.resize(680, 230)
    chart.show()
    QTest.qWait(5)
    chart.repaint()
    qt_application.processEvents()

    assert len(chart.values) == 7
    assert len(chart.chart_points) == 7
    assert all(
        first.x() < second.x()
        for first, second in zip(chart.chart_points, chart.chart_points[1:])
    )
    assert chart.chart_points[5].y() < chart.chart_points[1].y()
    assert not chart.grab().isNull()
    chart.close()


def test_focus_trend_is_a_pure_point_path_and_handles_single_value(
    qt_application,
) -> None:
    chart = FocusTrendWidget()
    chart.set_values(
        (
            TrendPoint("2026-08-17", 1200),
            TrendPoint("2026-08-18", 3600),
            TrendPoint("2026-08-19", 1800),
        )
    )
    chart.resize(520, 170)
    chart.show()
    QTest.qWait(5)
    chart.repaint()
    qt_application.processEvents()

    assert len(chart.chart_points) == 3
    assert chart.chart_points[1].y() < chart.chart_points[0].y()

    chart.set_values((TrendPoint("2026-08", 7200),))
    chart.repaint()
    qt_application.processEvents()
    assert len(chart.chart_points) == 1
    assert chart.chart_points[0].x() == pytest.approx(chart.width() / 2)
    chart.close()


def test_focus_trend_callout_is_fixed_to_column_and_flips_below_peak(
    qt_application,
) -> None:
    chart = FocusTrendWidget()
    chart.set_values(
        (
            TrendPoint("2026-08-17", 1200),
            TrendPoint("2026-08-18", 3600),
            TrendPoint("2026-08-19", 1800),
        )
    )
    chart.resize(520, 170)
    chart.show()
    QTest.qWait(5)
    chart.repaint()
    qt_application.processEvents()

    first_point = chart.chart_points[0].toPoint()
    QTest.mouseMove(chart, first_point)
    qt_application.processEvents()
    assert chart._callout.isVisible()
    assert chart._callout.placement is TrendCalloutPlacement.ABOVE
    first_position = chart._callout.pos()
    assert chart._callout.text == "2026-08-17 · 20 min"

    QTest.mouseMove(chart, first_point + type(first_point)(0, 28))
    qt_application.processEvents()
    assert chart._callout.pos() == first_position

    peak_point = chart.chart_points[1].toPoint()
    QTest.mouseMove(chart, peak_point)
    qt_application.processEvents()
    assert chart._callout.placement is TrendCalloutPlacement.BELOW
    assert chart._callout.geometry().top() > peak_point.y()
    assert chart._callout.text == "2026-08-18 · 1h"
    chart.close()


def test_weekly_chart_callout_clamps_edges_and_clears_with_data(
    qt_application,
) -> None:
    start = date(2026, 8, 17)
    chart = WeeklyChart()
    values = [
        DailyTotal(start + timedelta(days=index), duration)
        for index, duration in enumerate((0, 900, 1800, 3600, 2400, 5400, 1200))
    ]
    chart.set_values(values)
    chart.resize(420, 230)
    chart.show()
    QTest.qWait(5)
    chart.repaint()
    qt_application.processEvents()

    QTest.mouseMove(chart, chart.chart_points[0].toPoint())
    qt_application.processEvents()
    assert chart._callout.isVisible()
    assert chart._callout.geometry().left() >= chart.rect().left()

    QTest.mouseMove(chart, chart.chart_points[-1].toPoint())
    qt_application.processEvents()
    assert chart._callout.geometry().right() <= chart.rect().right()

    chart.set_values(values[:3])
    qt_application.processEvents()
    assert not chart._callout.isVisible()
    chart.close()


def test_trend_callout_maps_embedded_chart_and_hides_on_window_resize(
    qt_application,
) -> None:
    host = QWidget()
    host.resize(720, 320)
    chart = FocusTrendWidget(host)
    chart.setGeometry(84, 72, 520, 170)
    chart.set_values(
        (
            TrendPoint("2026-08-17", 1200),
            TrendPoint("2026-08-18", 3600),
            TrendPoint("2026-08-19", 1800),
        )
    )
    host.show()
    QTest.qWait(5)
    chart.repaint()
    qt_application.processEvents()

    QTest.mouseMove(chart, chart.chart_points[0].toPoint())
    qt_application.processEvents()
    assert chart._callout.parentWidget() is host
    assert chart._callout.isVisible()
    chart_left = chart.mapTo(host, QPoint()).x()
    chart_right = chart_left + chart.width() - 1
    assert chart._callout.geometry().left() >= chart_left
    assert chart._callout.geometry().right() <= chart_right

    host.resize(740, 340)
    qt_application.processEvents()
    assert not chart._callout.isVisible()
    host.close()


def test_hourly_distribution_uses_equal_height_heat_cells(qt_application) -> None:
    values = tuple(float(index * 300) for index in range(24))
    ribbon = HourlyDistributionWidget()
    ribbon.set_values(values)
    ribbon.resize(680, 140)
    ribbon.show()
    QTest.qWait(5)
    ribbon.repaint()
    qt_application.processEvents()

    assert len(ribbon.cells) == 24
    assert len({round(cell.height(), 3) for cell in ribbon.cells}) == 1
    assert ribbon.intensity_levels[0] == 0
    assert ribbon.intensity_levels[-1] == 4
    assert set(ribbon.intensity_levels).issubset({0, 1, 2, 3, 4})
    assert not ribbon.grab().isNull()
    ribbon.close()


def test_hourly_distribution_validates_length_and_intensity_boundaries(
    qt_application,
) -> None:
    ribbon = HourlyDistributionWidget()
    with pytest.raises(ValueError, match="24 values"):
        ribbon.set_values((0.0,) * 23)
    assert _hour_intensity(0, 100) == 0
    assert _hour_intensity(25, 100) == 1
    assert _hour_intensity(50, 100) == 2
    assert _hour_intensity(75, 100) == 3
    assert _hour_intensity(100, 100) == 4
    ribbon.close()
