"""Tests for the pure chart layer (Prompt E §6).

No ``tkinter`` import anywhere in this file: only geometry, mappers, and summaries
are exercised, so the suite runs headlessly.
"""

from __future__ import annotations

import pathlib
import unittest
from datetime import date

from mindpulse import charts
from mindpulse.charts import (
    AxisTicks,
    BarSeries,
    ChartPoint,
    LineSeries,
    Margins,
    check_ins_to_chart_points,
    check_ins_to_sleep_mood_points,
    check_ins_to_stress_points,
    compose_trend_sentence,
    compute_axes,
    compute_bar_chart_layout,
    compute_line_chart_geometry,
    compute_period_averages,
    compute_plot_area,
    compute_scatter_geometry,
    compute_streak,
    compute_trend_line,
    filter_by_days,
    format_date_label,
    format_value_label,
    screenings_to_bar_series,
    severity_bands_for_chart,
    smooth_path,
    thin_tick_labels,
    trend_direction,
)
from mindpulse.config import CHART_BAR_GAP_PX, CHART_MARGINS, CHART_SMOOTH_SUBDIVISIONS
from mindpulse.models import CheckIn, Instrument, Screening, Severity

MARGINS = Margins(*CHART_MARGINS)
TODAY = date(2026, 10, 18)


def make_check_in(day: int, mood: int, stress: int = 4, sleep_hours: float = 7.0) -> CheckIn:
    """Return a check-in on October ``day`` 2026."""
    return CheckIn(
        created_at=f"2026-10-{day:02d}T09:00:00Z",
        mood=mood,
        stress=stress,
        energy=5,
        sleep_hours=sleep_hours,
    )


def make_screening(day: int, instrument: Instrument, total: int) -> Screening:
    """Return a screening on October ``day`` 2026 with the given total."""
    return Screening(
        created_at=f"2026-10-{day:02d}T10:00:00Z",
        instrument=instrument,
        answers=(0,) * (9 if instrument is Instrument.PHQ9 else 7),
        total=total,
        severity=Severity.MINIMAL,
    )


class PlotAreaTests(unittest.TestCase):
    def test_margins_are_subtracted_from_the_canvas(self) -> None:
        plot = compute_plot_area(320, 240, MARGINS)
        self.assertEqual(plot, charts.PlotArea(56.0, 36.0, 244.0, 164.0))

    def test_over_large_margins_raise(self) -> None:
        with self.assertRaises(ValueError):
            compute_plot_area(60, 240, MARGINS)

    def test_degenerate_canvas_raises(self) -> None:
        # Documented behaviour: a canvas that cannot hold the plot raises ValueError.
        for width, height in ((1, 1), (0, 0), (320, 0)):
            with self.subTest(width=width, height=height), self.assertRaises(ValueError):
                compute_plot_area(width, height, MARGINS)


class AxesTests(unittest.TestCase):
    def test_screening_range_uses_steps_of_five(self) -> None:
        ticks = compute_axes(0, 27, 10)
        self.assertEqual(ticks.positions, (0.0, 5.0, 10.0, 15.0, 20.0, 25.0))
        self.assertEqual(ticks.labels, ("0", "5", "10", "15", "20", "25"))
        self.assertEqual((ticks.min, ticks.max), (0.0, 27.0))

    def test_wellbeing_range_uses_integer_labels(self) -> None:
        ticks = compute_axes(1, 10, 10)
        self.assertEqual(ticks.positions, tuple(float(value) for value in range(1, 11)))
        self.assertEqual(ticks.labels, tuple(str(value) for value in range(1, 11)))

    def test_gad7_range(self) -> None:
        ticks = compute_axes(0, 21, 10)
        self.assertEqual(ticks.positions, (0.0, 5.0, 10.0, 15.0, 20.0))

    def test_labels_never_have_more_than_two_decimals(self) -> None:
        for minimum, maximum, count in ((0, 1, 5), (0, 0.5, 6), (2.5, 8.5, 7)):
            for label in compute_axes(minimum, maximum, count).labels:
                with self.subTest(label=label):
                    self.assertLessEqual(len(label.split(".")[1]) if "." in label else 0, 2)

    def test_empty_range_raises(self) -> None:
        with self.assertRaises(ValueError):
            compute_axes(5, 5, 10)
        with self.assertRaises(ValueError):
            compute_axes(10, 1, 10)

    def test_tick_count_below_two_raises(self) -> None:
        with self.assertRaises(ValueError):
            compute_axes(0, 10, 1)


class LineGeometryTests(unittest.TestCase):
    def test_y_axis_is_inverted(self) -> None:
        plot = compute_plot_area(320, 240, MARGINS)
        ticks = compute_axes(1, 10, 10)
        self.assertAlmostEqual(charts.data_to_pixel_y(10, plot, ticks), plot.y)
        self.assertAlmostEqual(charts.data_to_pixel_y(1, plot, ticks), plot.y + plot.height)

    def test_two_point_series_maps_to_plot_endpoints(self) -> None:
        series = LineSeries(
            "Mood",
            "series_1",
            (ChartPoint(0.0, 10.0, "Oct 16"), ChartPoint(10.0, 1.0, "Oct 17")),
        )
        geometry = compute_line_chart_geometry([series], 320, 240)
        plot = geometry.plot
        self.assertEqual(
            geometry.series[0].pixel_points,
            ((plot.x, plot.y), (plot.x + plot.width, plot.y + plot.height)),
        )

    def test_single_point_has_no_smoothed_path(self) -> None:
        series = LineSeries("Mood", "series_1", (ChartPoint(5.0, 5.0, "Oct 17"),))
        geometry = compute_line_chart_geometry([series], 320, 240)
        self.assertEqual(len(geometry.series[0].pixel_points), 1)
        self.assertEqual(geometry.series[0].smoothed_path, ())

    def test_today_marker_matches_the_last_point(self) -> None:
        points = (ChartPoint(0.0, 5.0), ChartPoint(1.0, 6.0), ChartPoint(2.0, 7.0))
        geometry = compute_line_chart_geometry(
            [LineSeries("Mood", "series_1", points)], 320, 240, today_index=2
        )
        self.assertEqual(geometry.today_marker, geometry.series[0].pixel_points[-1])

    def test_out_of_range_today_index_yields_no_marker(self) -> None:
        points = (ChartPoint(0.0, 5.0),)
        geometry = compute_line_chart_geometry(
            [LineSeries("Mood", "series_1", points)], 320, 240, today_index=4
        )
        self.assertIsNone(geometry.today_marker)

    def test_empty_input_returns_empty_geometry(self) -> None:
        geometry = compute_line_chart_geometry([], 320, 240)
        self.assertEqual(geometry.series, ())
        self.assertEqual(geometry.x_ticks.positions, ())
        self.assertIsNone(geometry.today_marker)

    def test_two_series_share_the_x_axis(self) -> None:
        mood = LineSeries("Mood", "series_1", (ChartPoint(0.0, 6.0), ChartPoint(1.0, 7.0)))
        stress = LineSeries("Stress", "series_2", (ChartPoint(0.0, 4.0), ChartPoint(1.0, 3.0)))
        geometry = compute_line_chart_geometry([mood, stress], 320, 240)
        self.assertEqual(len(geometry.series), 2)
        self.assertEqual(
            [point[0] for point in geometry.series[0].pixel_points],
            [point[0] for point in geometry.series[1].pixel_points],
        )
        self.assertEqual(geometry.legend, (("Mood", "series_1"), ("Stress", "series_2")))


class SmoothPathTests(unittest.TestCase):
    def test_subdivision_count(self) -> None:
        points = ((0.0, 0.0), (10.0, 10.0), (20.0, 0.0))
        path = smooth_path(points)
        self.assertEqual(len(path), (len(points) - 1) * CHART_SMOOTH_SUBDIVISIONS + 1)

    def test_endpoints_are_preserved_exactly(self) -> None:
        points = ((1.5, 2.5), (30.0, 40.0))
        path = smooth_path(points, subdivisions=4)
        self.assertEqual(path[0], points[0])
        self.assertEqual(path[-1], points[-1])

    def test_interpolation_stays_on_the_segment(self) -> None:
        path = smooth_path(((0.0, 0.0), (8.0, 8.0)), subdivisions=4)
        for x, y in path:
            self.assertAlmostEqual(x, y)

    def test_empty_and_single_inputs_are_safe(self) -> None:
        self.assertEqual(smooth_path(()), ())
        self.assertEqual(smooth_path(((1.0, 1.0),)), ())
        self.assertEqual(smooth_path(((0.0, 0.0), (1.0, 1.0)), subdivisions=0), ())


class TrendLineTests(unittest.TestCase):
    def test_perfect_line_is_returned_exactly(self) -> None:
        points = tuple(ChartPoint(float(x), 2.0 * x + 1.0) for x in range(5))
        self.assertEqual(compute_trend_line(points), ((0.0, 1.0), (4.0, 9.0)))

    def test_identical_x_values_return_none(self) -> None:
        points = (ChartPoint(3.0, 1.0), ChartPoint(3.0, 9.0), ChartPoint(3.0, 5.0))
        self.assertIsNone(compute_trend_line(points))

    def test_too_few_points_return_none(self) -> None:
        self.assertIsNone(compute_trend_line(()))
        self.assertIsNone(compute_trend_line((ChartPoint(1.0, 1.0),)))

    def test_noisy_data_matches_hand_computed_ols(self) -> None:
        points = (
            ChartPoint(1.0, 2.0),
            ChartPoint(2.0, 4.0),
            ChartPoint(3.0, 5.0),
            ChartPoint(4.0, 4.0),
            ChartPoint(5.0, 5.0),
        )
        # Hand-computed: mean_x = 3, mean_y = 4, cov = 6, var = 10, m = 0.6, b = 2.2.
        line = compute_trend_line(points)
        assert line is not None
        self.assertAlmostEqual(line[0][1], 0.6 * 1.0 + 2.2, places=9)
        self.assertAlmostEqual(line[1][1], 0.6 * 5.0 + 2.2, places=9)


class ScatterGeometryTests(unittest.TestCase):
    def test_points_land_inside_the_plot(self) -> None:
        points = (
            ChartPoint(4.0, 3.0),
            ChartPoint(6.0, 5.0),
            ChartPoint(8.0, 7.0),
            ChartPoint(9.0, 9.0),
        )
        geometry = compute_scatter_geometry(points, 320, 240)
        plot = geometry.plot
        for pixel_x, pixel_y in geometry.points:
            self.assertGreaterEqual(pixel_x, plot.x - 1e-9)
            self.assertLessEqual(pixel_x, plot.x + plot.width + 1e-9)
            self.assertGreaterEqual(pixel_y, plot.y - 1e-9)
            self.assertLessEqual(pixel_y, plot.y + plot.height + 1e-9)

    def test_zero_variance_does_not_raise(self) -> None:
        points = (ChartPoint(7.0, 3.0), ChartPoint(7.0, 6.0), ChartPoint(7.0, 9.0))
        geometry = compute_scatter_geometry(points, 320, 240)
        self.assertIsNone(geometry.trend_line)
        self.assertEqual(len(geometry.points), 3)

    def test_empty_points_do_not_raise(self) -> None:
        geometry = compute_scatter_geometry((), 320, 240)
        self.assertEqual(geometry.points, ())
        self.assertIsNone(geometry.trend_line)


class BarLayoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.phq9 = BarSeries(
            "PHQ-9",
            "series_1",
            (ChartPoint(0.0, 6.0, "Oct 16"), ChartPoint(1.0, 9.0, "Oct 17")),
        )
        self.gad7 = BarSeries(
            "GAD-7",
            "series_2",
            (ChartPoint(0.0, 4.0, "Oct 16"), ChartPoint(1.0, 5.0, "Oct 17")),
        )
        self.geometry = compute_bar_chart_layout(
            [self.phq9, self.gad7], 320, 240, y_range=(0.0, 27.0)
        )

    def test_grouped_bars_keep_at_least_the_minimum_gap(self) -> None:
        for bar_series in self.geometry.bars:
            rects = bar_series.rects
            for left, right in zip(rects, rects[1:], strict=False):
                left_edge, width = right[0], right[2]
                self.assertGreaterEqual(left_edge - (left[0] + left[2]), CHART_BAR_GAP_PX - 1e-9)
                self.assertGreater(width, 0)

    def test_bars_grow_upward_from_the_range_floor(self) -> None:
        baseline = charts.data_to_pixel_y(0.0, self.geometry.plot, self.geometry.y_ticks)
        for bar_series in self.geometry.bars:
            for _, top, _, height in bar_series.rects:
                self.assertAlmostEqual(top + height, baseline)

    def test_band_rects_span_the_full_plot_width_and_are_ordered(self) -> None:
        bands = severity_bands_for_chart(Instrument.PHQ9)
        geometry = compute_bar_chart_layout([self.phq9], 320, 240, y_range=(0.0, 27.0), bands=bands)
        self.assertEqual(len(geometry.band_rects), len(bands))
        for left, _top, width, height, color_key in geometry.band_rects:
            self.assertAlmostEqual(left, geometry.plot.x)
            self.assertAlmostEqual(width, geometry.plot.width)
            self.assertGreaterEqual(height, 0)
            self.assertIn(color_key, ("band_a", "band_b"))
        tops = [rect[1] for rect in geometry.band_rects]
        self.assertEqual(tops, sorted(tops, reverse=True))

    def test_value_labels_match_the_totals(self) -> None:
        self.assertEqual(self.geometry.bars[0].value_labels, ("6", "9"))
        self.assertEqual(self.geometry.bars[1].value_labels, ("4", "5"))

    def test_empty_series_returns_empty_geometry(self) -> None:
        geometry = compute_bar_chart_layout([], 320, 240)
        self.assertEqual(geometry.bars, ())
        self.assertEqual(geometry.band_rects, ())


class TickThinningTests(unittest.TestCase):
    def test_thirty_ticks_in_a_narrow_plot_are_thinned(self) -> None:
        ticks = AxisTicks(
            positions=tuple(float(index) for index in range(30)),
            labels=tuple(f"d{index}" for index in range(30)),
            min=0.0,
            max=29.0,
        )
        thinned = thin_tick_labels(ticks, 320, min_px=64)
        self.assertGreaterEqual(len(thinned.positions), 5)
        self.assertLessEqual(len(thinned.positions), 6)
        self.assertEqual(thinned.positions[0], 0.0)
        self.assertEqual(thinned.positions[-1], 29.0)
        self.assertEqual(len(thinned.labels), len(thinned.positions))

    def test_a_single_tick_is_returned_unchanged(self) -> None:
        ticks = AxisTicks((5.0,), ("Oct 18",), 5.0, 5.0)
        self.assertEqual(thin_tick_labels(ticks, 320), ticks)

    def test_wide_plot_keeps_every_tick(self) -> None:
        ticks = AxisTicks((0.0, 1.0, 2.0), ("a", "b", "c"), 0.0, 2.0)
        self.assertEqual(thin_tick_labels(ticks, 1000), ticks)

    def test_pixel_positions_are_thinned_with_the_labels(self) -> None:
        ticks = AxisTicks(
            positions=tuple(float(index) for index in range(30)),
            labels=tuple(f"d{index}" for index in range(30)),
            min=0.0,
            max=29.0,
            pixel_positions=tuple(float(index * 10) for index in range(30)),
        )
        thinned = thin_tick_labels(ticks, 320, min_px=64)
        self.assertEqual(len(thinned.pixel_positions), len(thinned.positions))


class FormattingTests(unittest.TestCase):
    def test_date_labels(self) -> None:
        self.assertEqual(format_date_label("2026-10-18T09:30:00Z"), "Oct 18")
        self.assertEqual(format_date_label("2026-10-18T09:30:00+00:00"), "Oct 18")
        self.assertEqual(format_date_label("2026-01-05"), "Jan 5")

    def test_malformed_dates_raise(self) -> None:
        for value in ("", "18/10/2026", "2026-13-01", "not a date"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                format_date_label(value)

    def test_value_labels(self) -> None:
        self.assertEqual(format_value_label(6.0), "6")
        self.assertEqual(format_value_label(6.25), "6.25")
        self.assertEqual(format_value_label(0), "0")
        self.assertEqual(format_value_label(6.1), "6.1")
        self.assertEqual(format_value_label(-3.5), "-3.5")

    def test_non_finite_values_raise(self) -> None:
        for value in (float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                format_value_label(value)


class MapperTests(unittest.TestCase):
    def test_check_ins_map_to_mood_and_stress_points(self) -> None:
        check_ins = (make_check_in(17, mood=6, stress=3), make_check_in(18, mood=8, stress=5))
        mood = check_ins_to_chart_points(check_ins)
        stress = check_ins_to_stress_points(check_ins)
        self.assertEqual([point.y for point in mood], [6.0, 8.0])
        self.assertEqual([point.y for point in stress], [3.0, 5.0])
        self.assertEqual(mood[0].label, "Oct 17")
        self.assertAlmostEqual(mood[1].x - mood[0].x, 1.0)

    def test_sleep_scatter_uses_sleep_as_x(self) -> None:
        points = check_ins_to_sleep_mood_points((make_check_in(17, 6, sleep_hours=6.5),))
        self.assertEqual((points[0].x, points[0].y), (6.5, 6.0))

    def test_range_filter(self) -> None:
        check_ins = (make_check_in(1, 5), make_check_in(17, 6), make_check_in(18, 7))
        within = filter_by_days(check_ins, 2, TODAY)
        self.assertEqual([record.mood for record in within], [6, 7])
        self.assertEqual(len(filter_by_days(check_ins, None, TODAY)), 3)

    def test_range_filter_rejects_non_positive_days(self) -> None:
        with self.assertRaises(ValueError):
            filter_by_days((), 0, TODAY)

    def test_screenings_group_into_one_series_per_instrument(self) -> None:
        screenings = (
            make_screening(16, Instrument.PHQ9, 6),
            make_screening(17, Instrument.GAD7, 4),
            make_screening(18, Instrument.PHQ9, 9),
        )
        series = screenings_to_bar_series(screenings)
        self.assertEqual([one.name for one in series], ["PHQ-9", "GAD-7"])
        self.assertEqual([point.y for point in series[0].points], [6.0, 9.0])
        self.assertEqual([point.y for point in series[1].points], [4.0])

    def test_screenings_without_data_produce_no_series(self) -> None:
        self.assertEqual(screenings_to_bar_series(()), ())

    def test_severity_bands_come_from_the_instrument_tables(self) -> None:
        bands = severity_bands_for_chart(Instrument.PHQ9)
        self.assertEqual(len(bands), 5)
        self.assertEqual(bands[0].label, "Minimal")
        self.assertEqual((bands[-1].y_low, bands[-1].y_high), (20.0, 27.0))
        self.assertEqual(len(severity_bands_for_chart(Instrument.GAD7)), 4)


class SummaryTests(unittest.TestCase):
    def test_streak_counts_consecutive_days_ending_today(self) -> None:
        stamps = (
            "2026-10-18T09:00:00Z",
            "2026-10-17T09:00:00Z",
            "2026-10-16T09:00:00Z",
            "2026-10-14T09:00:00Z",
        )
        self.assertEqual(compute_streak(stamps, TODAY), 3)

    def test_streak_is_zero_when_today_has_no_check_in(self) -> None:
        self.assertEqual(compute_streak(("2026-10-17T09:00:00Z",), TODAY), 0)
        self.assertEqual(compute_streak((), TODAY), 0)

    def test_period_averages_compare_this_week_with_last_week(self) -> None:
        check_ins = (
            make_check_in(18, mood=6),
            make_check_in(17, mood=8),
            make_check_in(7, mood=4),
        )
        this_week, last_week = compute_period_averages(check_ins, TODAY)
        assert this_week is not None
        assert last_week is not None
        self.assertAlmostEqual(this_week, 7.0)
        self.assertAlmostEqual(last_week, 4.0)

    def test_period_averages_are_none_without_data(self) -> None:
        self.assertEqual(compute_period_averages((), TODAY), (None, None))

    def test_trend_sentence_matches_the_template(self) -> None:
        self.assertEqual(
            compose_trend_sentence(6.1, 4.8),
            "Your mood averaged 6.1 this week, up from 4.8 last week.",
        )
        self.assertEqual(
            compose_trend_sentence(4.0, 6.0),
            "Your mood averaged 4.0 this week, down from 6.0 last week.",
        )
        self.assertEqual(
            compose_trend_sentence(5.0, 5.0),
            "Your mood averaged 5.0 this week, unchanged from 5.0 last week.",
        )

    def test_trend_sentence_is_empty_without_a_comparison(self) -> None:
        self.assertEqual(compose_trend_sentence(None, 5.0), "")
        self.assertEqual(compose_trend_sentence(5.0, None), "")

    def test_trend_direction_compares_rounded_values(self) -> None:
        self.assertEqual(trend_direction(5.04, 5.0), "unchanged")
        self.assertEqual(trend_direction(5.2, 5.0), "up")
        self.assertEqual(trend_direction(4.7, 5.0), "down")


class PurityTests(unittest.TestCase):
    def test_geometry_layer_does_not_import_tkinter(self) -> None:
        source = pathlib.Path(charts.__file__ or "").read_text(encoding="utf-8")
        self.assertNotIn("\nimport tkinter", source)
        self.assertNotIn("\nfrom tkinter", source)


if __name__ == "__main__":
    unittest.main()
