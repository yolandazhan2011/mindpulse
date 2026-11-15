"""Chart geometry and thin ``tk.Canvas`` renderers (Prompt E).

Two strict layers live here:

1. **Pure geometry** - dates and values in, pixel geometry out, as frozen
   dataclasses. No Tkinter import, no globals, no I/O. Everything in this layer is
   unit-tested headlessly.
2. **Renderers** - geometry in, ``canvas.create_*`` calls out. A renderer never
   computes a coordinate that this module's pure helpers do not already provide.

Coordinate convention (followed everywhere): the canvas pixel origin is the
top-left corner and pixel y grows **downward**, while data y grows **upward**, so
every mapping inverts:

    pixel_y = plot.y + plot.height - (value - y_min) / (y_max - y_min) * plot.height

x is a numeric day count (days since 1970-01-01) with the human label carried on
:class:`ChartPoint`, so no geometry function ever parses a string for positioning.
Every function accepts ``width`` and ``height`` explicitly so tests can use tiny
canvases. Degenerate input raises ``ValueError`` (documented per function) rather
than dividing by zero.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from . import config as _config
from .config import (
    AXIS_TITLE_DATE,
    AXIS_TITLE_WELLBEING,
    CHART_BAND_EDGE_WIDTH,
    CHART_BAR_GAP_PX,
    CHART_BAR_MIN_LABEL_PX,
    CHART_LABEL_FONT,
    CHART_LINE_WIDTH,
    CHART_MARGINS,
    CHART_POINT_RADIUS,
    CHART_SMOOTH_SUBDIVISIONS,
    CHART_TICK_MIN_PX,
    CHART_TITLE_FONT,
    CHART_TITLE_SCATTER,
    CHART_TITLE_SCREENING,
    CHART_TITLE_TREND,
    CHART_TODAY_RADIUS,
    LEGEND_MOOD,
    LEGEND_STRESS,
)
from .instruments import get_instrument
from .models import CheckIn, Instrument, Screening

#: Tick hints, read through the config module so the values live in one place.
DEFAULT_X_TICK_HINT: int = _config.CHART_X_TICK_HINT
DEFAULT_Y_TICK_COUNT: int = _config.CHART_Y_TICK_COUNT

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps this module Tk-free
    from tkinter import Canvas

MONTH_ABBREVIATIONS: tuple[str, ...] = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)

_EPOCH = date(1970, 1, 1)
_EPSILON = 1e-9


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChartPoint:
    """One data point: numeric x (day count), numeric y, and a display label."""

    x: float
    y: float
    label: str = ""


@dataclass(frozen=True)
class Margins:
    """Canvas padding in pixels."""

    left: int
    top: int
    right: int
    bottom: int


#: Default margins as a module singleton, so signatures can name it directly.
DEFAULT_MARGINS = Margins(*CHART_MARGINS)


@dataclass(frozen=True)
class AxisTicks:
    """Tick positions in data space, their labels, and the axis span.

    ``pixel_positions`` is filled in by the geometry functions so renderers never
    repeat the data-to-pixel mapping.
    """

    positions: tuple[float, ...]
    labels: tuple[str, ...]
    min: float
    max: float
    pixel_positions: tuple[float, ...] = ()


@dataclass(frozen=True)
class PlotArea:
    """The inner drawing rectangle, in pixels."""

    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class LineSeries:
    """Input series for a line chart: a name, a palette key, and its points."""

    name: str
    color_key: str
    points: tuple[ChartPoint, ...]


@dataclass(frozen=True)
class LineSeriesGeometry:
    """Pixel geometry for one line series."""

    name: str
    color_key: str
    pixel_points: tuple[tuple[float, float], ...]
    smoothed_path: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class LineChartGeometry:
    """Everything needed to draw a line chart."""

    plot: PlotArea
    x_ticks: AxisTicks
    y_ticks: AxisTicks
    series: tuple[LineSeriesGeometry, ...]
    today_marker: tuple[float, float] | None
    title: str = CHART_TITLE_TREND
    x_title: str = AXIS_TITLE_DATE
    y_title: str = AXIS_TITLE_WELLBEING
    legend: tuple[tuple[str, str], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ScatterGeometry:
    """Everything needed to draw a scatter plot with a trend line."""

    plot: PlotArea
    x_ticks: AxisTicks
    y_ticks: AxisTicks
    points: tuple[tuple[float, float], ...]
    trend_line: tuple[tuple[float, float], tuple[float, float]] | None
    title: str = CHART_TITLE_SCATTER
    x_title: str = ""
    y_title: str = AXIS_TITLE_WELLBEING


@dataclass(frozen=True)
class BarSeries:
    """Input series for a grouped bar chart."""

    name: str
    color_key: str
    points: tuple[ChartPoint, ...]


@dataclass(frozen=True)
class BarGeometry:
    """Pixel rectangles and value labels for one bar series."""

    name: str
    color_key: str
    rects: tuple[tuple[float, float, float, float], ...]
    value_labels: tuple[str, ...]


@dataclass(frozen=True)
class BarChartGeometry:
    """Everything needed to draw a grouped bar chart with severity stripes."""

    plot: PlotArea
    x_ticks: AxisTicks
    y_ticks: AxisTicks
    bars: tuple[BarGeometry, ...]
    band_rects: tuple[tuple[float, float, float, float, str], ...]
    title: str = CHART_TITLE_SCREENING
    x_title: str = AXIS_TITLE_DATE
    y_title: str = ""
    legend: tuple[tuple[str, str], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SeverityBand:
    """A severity band in data space, for the background stripes."""

    label: str
    y_low: float
    y_high: float


# ---------------------------------------------------------------------------
# Formatting (pure)
# ---------------------------------------------------------------------------


def format_value_label(value: float) -> str:
    """Return ``value`` with at most 2 decimals and no trailing zeros.

    ``6.0`` -> ``"6"``, ``6.25`` -> ``"6.25"``, ``0`` -> ``"0"``.
    """
    if not math.isfinite(float(value)):
        raise ValueError(f"Cannot format a non-finite value: {value!r}")
    rounded = round(float(value), 2)
    if rounded == 0:
        return "0"
    return f"{rounded:.2f}".rstrip("0").rstrip(".")


def format_date_label(iso_timestamp: str) -> str:
    """Format an ISO-8601 timestamp or date as ``Oct 18``.

    Accepts ``2026-10-18T09:30:00Z``, ``2026-10-18T09:30:00+00:00``, and
    ``2026-10-18``. Raises ``ValueError`` on anything else.
    """
    if not iso_timestamp:
        raise ValueError("Cannot format an empty timestamp")
    text = iso_timestamp.strip()
    parsed = _parse_date(text)
    return f"{MONTH_ABBREVIATIONS[parsed.month - 1]} {parsed.day}"


def _parse_date(iso_timestamp: str) -> date:
    """Parse an ISO-8601 date or timestamp to a :class:`datetime.date`."""
    text = iso_timestamp.strip()
    if "T" not in text:
        try:
            return datetime.strptime(text, "%Y-%m-%d").date()  # noqa: DTZ007 - date only
        except ValueError as error:
            raise ValueError(f"Not an ISO-8601 date: {iso_timestamp!r}") from error
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError as error:
        raise ValueError(f"Not an ISO-8601 timestamp: {iso_timestamp!r}") from error


def day_number(iso_timestamp: str) -> float:
    """Return days since 1970-01-01 for an ISO-8601 date or timestamp."""
    return float((_parse_date(iso_timestamp) - _EPOCH).days)


# ---------------------------------------------------------------------------
# Geometry primitives (pure)
# ---------------------------------------------------------------------------


def compute_plot_area(width: float, height: float, margins: Margins) -> PlotArea:
    """Return the inner plot rectangle after subtracting ``margins``.

    Raises ``ValueError`` when the result would be non-positive in either
    dimension, so degenerate canvases fail loudly instead of dividing by zero.
    """
    inner_width = float(width) - margins.left - margins.right
    inner_height = float(height) - margins.top - margins.bottom
    if inner_width <= 0 or inner_height <= 0:
        raise ValueError(f"Canvas {width}x{height} is too small for margins {margins}")
    return PlotArea(
        x=float(margins.left),
        y=float(margins.top),
        width=inner_width,
        height=inner_height,
    )


def _nice_step(raw_step: float) -> float:
    """Round ``raw_step`` up to the nearest 1, 2, or 5 times a power of ten."""
    if raw_step <= 0 or not math.isfinite(raw_step):
        raise ValueError(f"Cannot compute a tick step from {raw_step!r}")
    exponent = math.floor(math.log10(raw_step))
    magnitude = 10.0**exponent
    for multiplier in (1.0, 2.0, 5.0, 10.0):
        if raw_step <= multiplier * magnitude + _EPSILON:
            return multiplier * magnitude
    return 10.0 * magnitude


def compute_axes(min_value: float, max_value: float, tick_count: int) -> AxisTicks:
    """Return "nice" ticks spanning ``[min_value, max_value]``.

    Tick positions are multiples of 1, 2, or 5 times a power of ten, kept inside
    the requested span, with at most 2 decimals in the labels. ``0-27`` yields
    steps of 5 and ``1-10`` yields the integers 1..10. Raises ``ValueError`` when
    the span is empty (``min_value >= max_value``) or ``tick_count < 2``; a forced
    range is the caller's job, e.g. passing ``y_range=(1, 10)``.
    """
    if tick_count < 2:
        raise ValueError(f"tick_count must be at least 2, got {tick_count}")
    if max_value <= min_value:
        raise ValueError(f"Cannot build axes for an empty range ({min_value}, {max_value})")
    step = _nice_step((max_value - min_value) / (tick_count - 1))
    first = math.ceil(min_value / step - _EPSILON) * step
    positions: list[float] = []
    value = first
    while value <= max_value + _EPSILON:
        positions.append(round(value, 10))
        value += step
    if len(positions) < 2:
        positions = [float(min_value), float(max_value)]
    return AxisTicks(
        positions=tuple(positions),
        labels=tuple(format_value_label(position) for position in positions),
        min=float(min_value),
        max=float(max_value),
    )


def data_to_pixel_y(value: float, plot: PlotArea, ticks: AxisTicks) -> float:
    """Map a data y value to a canvas y pixel (inverting the downward axis)."""
    span = ticks.max - ticks.min
    if span <= 0:
        raise ValueError("Cannot map values on an axis with no span")
    fraction = (float(value) - ticks.min) / span
    return plot.y + plot.height - fraction * plot.height


def data_to_pixel_x(value: float, plot: PlotArea, ticks: AxisTicks) -> float:
    """Map a data x value to a canvas x pixel, centring a zero-width domain."""
    span = ticks.max - ticks.min
    if span <= 0:
        return plot.x + plot.width / 2
    fraction = (float(value) - ticks.min) / span
    return plot.x + fraction * plot.width


def smooth_path(
    pixel_points: Sequence[tuple[float, float]],
    subdivisions: int = CHART_SMOOTH_SUBDIVISIONS,
) -> tuple[tuple[float, float], ...]:
    """Densify a polyline by linear interpolation.

    Produces ``(len(points) - 1) * subdivisions + 1`` points, preserving both
    endpoints exactly. Linear interpolation only: the line never implies data that
    is not there. Fewer than 2 points (or ``subdivisions < 1``) yields ``()``.
    """
    points = tuple(pixel_points)
    if len(points) < 2 or subdivisions < 1:
        return ()
    path: list[tuple[float, float]] = []
    for (x_start, y_start), (x_end, y_end) in zip(points, points[1:], strict=False):
        for step in range(subdivisions):
            fraction = step / subdivisions
            path.append(
                (
                    x_start + (x_end - x_start) * fraction,
                    y_start + (y_end - y_start) * fraction,
                )
            )
    path.append(points[-1])
    return tuple(path)


def thin_tick_labels(
    ticks: AxisTicks,
    available_px: float,
    min_px: float = CHART_TICK_MIN_PX,
) -> AxisTicks:
    """Drop every k-th label so x labels never overlap on a narrow canvas.

    ``k = ceil(n * min_px / available_px)``; the first and last ticks are always
    kept. Zero or one tick is returned unchanged.
    """
    count = len(ticks.positions)
    if count <= 1 or available_px <= 0 or min_px <= 0:
        return ticks
    stride = math.ceil(count * min_px / available_px)
    if stride <= 1:
        return ticks
    indices = list(range(0, count, stride))
    if indices[-1] != count - 1:
        indices.append(count - 1)
    has_pixels = len(ticks.pixel_positions) == count
    return AxisTicks(
        positions=tuple(ticks.positions[index] for index in indices),
        labels=tuple(ticks.labels[index] for index in indices),
        min=ticks.min,
        max=ticks.max,
        pixel_positions=(
            tuple(ticks.pixel_positions[index] for index in indices) if has_pixels else ()
        ),
    )


def _empty_ticks(minimum: float = 0.0, maximum: float = 1.0) -> AxisTicks:
    """Return an axis record with no ticks, for the empty states."""
    return AxisTicks(positions=(), labels=(), min=minimum, max=maximum)


def _evenly_spaced(values: Sequence[float], wanted: int) -> tuple[float, ...]:
    """Pick ``wanted`` values evenly spaced across ``values``, endpoints included."""
    if wanted >= len(values) or wanted < 2:
        return tuple(values)
    step = (len(values) - 1) / (wanted - 1)
    picked = [values[round(index * step)] for index in range(wanted)]
    return tuple(dict.fromkeys(picked))


def _labels_by_x(series: Iterable[LineSeries | BarSeries]) -> dict[float, str]:
    """Collect the first non-empty display label for each x value."""
    labels: dict[float, str] = {}
    for one_series in series:
        for point in one_series.points:
            if point.label and point.x not in labels:
                labels[point.x] = point.label
    return labels


def _x_axis_ticks(
    x_values: Sequence[float],
    labels: Mapping[float, str],
    plot: PlotArea,
    x_ticks_hint: int = DEFAULT_X_TICK_HINT,
) -> AxisTicks:
    """Build x ticks over ``x_values``, thinned to fit ``plot.width``."""
    if not x_values:
        return _empty_ticks()
    chosen = _evenly_spaced(x_values, x_ticks_hint)
    ticks = AxisTicks(
        positions=tuple(chosen),
        labels=tuple(labels.get(x, format_value_label(x)) for x in chosen),
        min=float(x_values[0]),
        max=float(x_values[-1]),
        pixel_positions=tuple(
            data_to_pixel_x(
                x,
                plot,
                AxisTicks((), (), float(x_values[0]), float(x_values[-1])),
            )
            for x in chosen
        ),
    )
    return thin_tick_labels(ticks, plot.width)


# ---------------------------------------------------------------------------
# Chart geometry (pure)
# ---------------------------------------------------------------------------


def compute_line_chart_geometry(
    series_data: Sequence[LineSeries],
    width: float,
    height: float,
    margins: Margins = DEFAULT_MARGINS,
    y_range: tuple[float, float] = (1.0, 10.0),
    x_ticks_hint: int = DEFAULT_X_TICK_HINT,
    today_index: int | None = None,
    y_tick_count: int = DEFAULT_Y_TICK_COUNT,
    title: str = CHART_TITLE_TREND,
    x_title: str = AXIS_TITLE_DATE,
    y_title: str = AXIS_TITLE_WELLBEING,
) -> LineChartGeometry:
    """Return pixel geometry for a multi-series line chart.

    ``y_range`` is forced by the caller (e.g. ``(1, 10)``) so wellbeing charts never
    rescale. ``today_index`` indexes the **first** series and marks that point as
    the "today" ring; an out-of-range index yields no marker. Empty input returns
    geometry with empty ticks and no series rather than raising.
    """
    plot = compute_plot_area(width, height, margins)
    y_ticks = compute_axes(y_range[0], y_range[1], y_tick_count)
    x_values = sorted({point.x for series in series_data for point in series.points})
    if not x_values:
        return LineChartGeometry(
            plot=plot,
            x_ticks=_empty_ticks(),
            y_ticks=y_ticks,
            series=(),
            today_marker=None,
            title=title,
            x_title=x_title,
            y_title=y_title,
            legend=tuple((series.name, series.color_key) for series in series_data),
        )
    labels = _labels_by_x(series_data)
    x_ticks = _x_axis_ticks(x_values, labels, plot, x_ticks_hint)
    x_span = AxisTicks((), (), float(x_values[0]), float(x_values[-1]))
    geometries = tuple(
        LineSeriesGeometry(
            name=series.name,
            color_key=series.color_key,
            pixel_points=tuple(
                (
                    data_to_pixel_x(point.x, plot, x_span),
                    data_to_pixel_y(point.y, plot, y_ticks),
                )
                for point in series.points
            ),
            smoothed_path=(
                smooth_path(
                    tuple(
                        (
                            data_to_pixel_x(point.x, plot, x_span),
                            data_to_pixel_y(point.y, plot, y_ticks),
                        )
                        for point in series.points
                    )
                )
                if len(series.points) > 1
                else ()
            ),
        )
        for series in series_data
    )
    marker: tuple[float, float] | None = None
    if today_index is not None and series_data and 0 <= today_index < len(series_data[0].points):
        marker = geometries[0].pixel_points[today_index]
    return LineChartGeometry(
        plot=plot,
        x_ticks=x_ticks,
        y_ticks=y_ticks,
        series=geometries,
        today_marker=marker,
        title=title,
        x_title=x_title,
        y_title=y_title,
        legend=tuple((series.name, series.color_key) for series in series_data),
    )


def compute_trend_line(
    points: Sequence[ChartPoint],
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Return the ordinary-least-squares line through ``points``, in data space.

    Slope ``m = sum((x-xbar)(y-ybar)) / sum((x-xbar)^2)``, intercept
    ``b = ybar - m*xbar``. The segment runs from the smallest to the largest x.
    Returns ``None`` for fewer than 2 points or when every x is identical (no
    vertical lines, no division by zero).
    """
    data = tuple(points)
    if len(data) < 2:
        return None
    count = len(data)
    mean_x = sum(point.x for point in data) / count
    mean_y = sum(point.y for point in data) / count
    variance = sum((point.x - mean_x) ** 2 for point in data)
    if variance <= _EPSILON:
        return None
    covariance = sum((point.x - mean_x) * (point.y - mean_y) for point in data)
    slope = covariance / variance
    intercept = mean_y - slope * mean_x
    x_start = min(point.x for point in data)
    x_end = max(point.x for point in data)
    return (
        (x_start, slope * x_start + intercept),
        (x_end, slope * x_end + intercept),
    )


def compute_scatter_geometry(
    points: Sequence[ChartPoint],
    width: float,
    height: float,
    margins: Margins = DEFAULT_MARGINS,
    x_range: tuple[float, float] | None = None,
    y_range: tuple[float, float] = (1.0, 10.0),
    x_ticks_hint: int = DEFAULT_X_TICK_HINT,
    y_tick_count: int = DEFAULT_Y_TICK_COUNT,
    title: str = CHART_TITLE_SCATTER,
    x_title: str = "",
    y_title: str = AXIS_TITLE_WELLBEING,
) -> ScatterGeometry:
    """Return pixel geometry for a scatter plot with its OLS trend line.

    ``x_range`` defaults to the data's own span, widened slightly when every x is
    identical so zero-variance input still maps inside the plot.
    """
    plot = compute_plot_area(width, height, margins)
    data = tuple(points)
    y_ticks = compute_axes(y_range[0], y_range[1], y_tick_count)
    x_low, x_high = _resolve_x_range(data, x_range)
    x_axis = AxisTicks((), (), x_low, x_high, ())
    x_ticks = _x_axis_ticks(
        sorted({point.x for point in data}) or [x_low], _labels_by_x(()), plot, x_ticks_hint
    )
    x_ticks = AxisTicks(
        positions=x_ticks.positions,
        labels=x_ticks.labels,
        min=x_low,
        max=x_high,
        pixel_positions=tuple(data_to_pixel_x(x, plot, x_axis) for x in x_ticks.positions),
    )
    trend = compute_trend_line(data)
    trend_pixels = (
        (
            (
                data_to_pixel_x(trend[0][0], plot, x_axis),
                data_to_pixel_y(trend[0][1], plot, y_ticks),
            ),
            (
                data_to_pixel_x(trend[1][0], plot, x_axis),
                data_to_pixel_y(trend[1][1], plot, y_ticks),
            ),
        )
        if trend is not None
        else None
    )
    return ScatterGeometry(
        plot=plot,
        x_ticks=x_ticks,
        y_ticks=y_ticks,
        points=tuple(
            (data_to_pixel_x(point.x, plot, x_axis), data_to_pixel_y(point.y, plot, y_ticks))
            for point in data
        ),
        trend_line=trend_pixels,
        title=title,
        x_title=x_title,
        y_title=y_title,
    )


def _resolve_x_range(
    points: Sequence[ChartPoint],
    x_range: tuple[float, float] | None,
) -> tuple[float, float]:
    """Return a usable x span, padding a zero-width domain so pixels stay finite."""
    if x_range is not None and x_range[1] > x_range[0]:
        return float(x_range[0]), float(x_range[1])
    if not points:
        return 0.0, 1.0
    low = min(point.x for point in points)
    high = max(point.x for point in points)
    if high - low <= _EPSILON:
        return low - 0.5, high + 0.5
    return float(low), float(high)


def compute_bar_chart_layout(
    series: Sequence[BarSeries],
    width: float,
    height: float,
    margins: Margins = DEFAULT_MARGINS,
    y_range: tuple[float, float] = (0.0, 27.0),
    bands: Sequence[SeverityBand] = (),
    x_ticks_hint: int = DEFAULT_X_TICK_HINT,
    y_tick_count: int = DEFAULT_Y_TICK_COUNT,
    title: str = CHART_TITLE_SCREENING,
    x_title: str = AXIS_TITLE_DATE,
    y_title: str = "",
) -> BarChartGeometry:
    """Return pixel geometry for grouped bars over severity band stripes.

    Bars grow upward from ``y_range[0]``; within one x position the group width is
    split evenly between series with a ``CHART_BAR_GAP_PX`` gap. Band rectangles
    span the full plot width and are ordered by ``y_low``.
    """
    plot = compute_plot_area(width, height, margins)
    y_ticks = compute_axes(y_range[0], y_range[1], y_tick_count)
    groups = sorted({point.x for one_series in series for point in one_series.points})
    if not groups:
        return BarChartGeometry(
            plot=plot,
            x_ticks=_empty_ticks(),
            y_ticks=y_ticks,
            bars=(),
            band_rects=(),
            title=title,
            x_title=x_title,
            y_title=y_title,
        )
    labels = _labels_by_x(series)
    x_ticks = _x_axis_ticks(groups, labels, plot, x_ticks_hint)
    group_index = {value: index for index, value in enumerate(groups)}
    group_width = plot.width / len(groups)
    inset = min(8.0, group_width * 0.1)
    inner_width = max(group_width - 2 * inset, 1.0)
    bar_count = max(len(series), 1)
    bar_width = max((inner_width - CHART_BAR_GAP_PX * (bar_count - 1)) / bar_count, 1.0)
    baseline = data_to_pixel_y(max(y_range[0], 0.0), plot, y_ticks)
    bars = tuple(
        BarGeometry(
            name=one_series.name,
            color_key=one_series.color_key,
            rects=tuple(
                (
                    plot.x
                    + group_index[point.x] * group_width
                    + inset
                    + position * (bar_width + CHART_BAR_GAP_PX),
                    data_to_pixel_y(point.y, plot, y_ticks),
                    bar_width,
                    max(baseline - data_to_pixel_y(point.y, plot, y_ticks), 0.0),
                )
                for point in one_series.points
            ),
            value_labels=tuple(format_value_label(point.y) for point in one_series.points),
        )
        for position, one_series in enumerate(series)
    )
    band_rects = tuple(
        (
            plot.x,
            data_to_pixel_y(min(band.y_high, y_range[1]), plot, y_ticks),
            plot.width,
            data_to_pixel_y(max(band.y_low, y_range[0]), plot, y_ticks)
            - data_to_pixel_y(min(band.y_high, y_range[1]), plot, y_ticks),
            "band_a" if position % 2 == 0 else "band_b",
        )
        for position, band in enumerate(sorted(bands, key=lambda band: band.y_low))
    )
    return BarChartGeometry(
        plot=plot,
        x_ticks=x_ticks,
        y_ticks=y_ticks,
        bars=bars,
        band_rects=band_rects,
        title=title,
        x_title=x_title,
        y_title=y_title,
        legend=tuple((one_series.name, one_series.color_key) for one_series in series),
    )


# ---------------------------------------------------------------------------
# Dashboard mappers and summaries (pure)
# ---------------------------------------------------------------------------


def filter_by_days(
    records: Sequence[CheckIn] | Sequence[Screening],
    days: int | None,
    today: date,
) -> tuple[Any, ...]:
    """Return records created within the last ``days`` days (``None`` means all).

    Filtering happens here, in the mapper - never inside the geometry functions.
    """
    if days is None:
        return tuple(records)
    if days <= 0:
        raise ValueError("The day range must be positive")
    earliest = today - timedelta(days=days - 1)
    return tuple(record for record in records if _parse_date(record.created_at) >= earliest)


def check_ins_to_chart_points(check_ins: Sequence[CheckIn]) -> tuple[ChartPoint, ...]:
    """Return mood points: x = day count, y = mood, label = ``Oct 18``."""
    return tuple(
        ChartPoint(
            x=day_number(record.created_at),
            y=float(record.mood),
            label=format_date_label(record.created_at),
        )
        for record in check_ins
    )


def check_ins_to_stress_points(check_ins: Sequence[CheckIn]) -> tuple[ChartPoint, ...]:
    """Return stress points: x = day count, y = stress, label = ``Oct 18``."""
    return tuple(
        ChartPoint(
            x=day_number(record.created_at),
            y=float(record.stress),
            label=format_date_label(record.created_at),
        )
        for record in check_ins
    )


def check_ins_to_sleep_mood_points(check_ins: Sequence[CheckIn]) -> tuple[ChartPoint, ...]:
    """Return scatter points: x = sleep hours, y = mood, label = ``Oct 18``."""
    return tuple(
        ChartPoint(
            x=float(record.sleep_hours),
            y=float(record.mood),
            label=format_date_label(record.created_at),
        )
        for record in check_ins
    )


def screenings_to_bar_series(
    screenings: Sequence[Screening],
) -> tuple[BarSeries, ...]:
    """Return one bar series per instrument, newest value per date.

    Both instruments share the x axis (day count), so the two series group
    side-by-side per date.
    """
    series: list[BarSeries] = []
    for instrument, name, color_key in (
        (Instrument.PHQ9, "PHQ-9", "series_1"),
        (Instrument.GAD7, "GAD-7", "series_2"),
    ):
        points = tuple(
            ChartPoint(
                x=day_number(record.created_at),
                y=float(record.total),
                label=format_date_label(record.created_at),
            )
            for record in screenings
            if record.instrument == instrument
        )
        if points:
            series.append(BarSeries(name=name, color_key=color_key, points=points))
    return tuple(series)


def severity_bands_for_chart(instrument: Instrument) -> tuple[SeverityBand, ...]:
    """Return an instrument's severity bands as chart stripes (cutoffs imported)."""
    spec = get_instrument(instrument)
    return tuple(
        SeverityBand(
            label=band.severity.label,
            y_low=float(band.low),
            y_high=float(band.high),
        )
        for band in spec.severity_bands
    )


def compute_streak(check_in_timestamps: Sequence[str], today: date) -> int:
    """Return the run of consecutive check-in days ending today (0 if today is empty)."""
    days = {_parse_date(stamp) for stamp in check_in_timestamps}
    streak = 0
    cursor = today
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def compute_period_averages(
    check_ins: Sequence[CheckIn],
    today: date,
) -> tuple[float | None, float | None]:
    """Return mean mood for the last 7 days and for the 7 days before that.

    Each value is ``None`` when its window holds no check-ins.
    """
    this_week = [record for record in filter_by_days(check_ins, 7, today)]
    last_week_start = today - timedelta(days=13)
    last_week_end = today - timedelta(days=7)
    last_week = [
        record
        for record in check_ins
        if last_week_start <= _parse_date(record.created_at) <= last_week_end
    ]
    return _mean_mood(this_week), _mean_mood(last_week)


def _mean_mood(records: Sequence[CheckIn]) -> float | None:
    """Return the mean mood of ``records``, or ``None`` when empty."""
    if not records:
        return None
    return sum(record.mood for record in records) / len(records)


def trend_direction(this_week: float, last_week: float) -> str:
    """Return ``up``, ``down``, or ``unchanged`` for two weekly averages."""
    if round(this_week, 1) > round(last_week, 1):
        return "up"
    if round(this_week, 1) < round(last_week, 1):
        return "down"
    return "unchanged"


def compose_trend_sentence(
    this_week: float | None,
    last_week: float | None,
) -> str:
    """Return ``Your mood averaged 6.1 this week, up from 4.8 last week.``

    Returns an empty string when either week has no data; the view then shows the
    empty-state message instead of inventing a comparison.
    """
    if this_week is None or last_week is None:
        return ""
    direction = trend_direction(this_week, last_week)
    return (
        f"Your mood averaged {this_week:.1f} this week, {direction} from {last_week:.1f} last week."
    )


# ---------------------------------------------------------------------------
# Render layer (thin: geometry in, canvas calls out)
# ---------------------------------------------------------------------------


def _palette_color(palette: Mapping[str, str], key: str) -> str:
    """Look up a palette entry, failing loudly on a typo'd key."""
    try:
        return palette[key]
    except KeyError as error:
        raise ValueError(f"Unknown palette colour {key!r}") from error


def _prepare_canvas(canvas: Canvas, palette: Mapping[str, str]) -> None:
    """Clear the canvas and paint its background."""
    canvas.delete("all")
    canvas.configure(background=_palette_color(palette, "canvas_bg"))


def draw_empty_state(
    canvas: Canvas,
    message: str,
    palette: Mapping[str, str],
) -> None:
    """Draw a single centred muted message: no axes, no fake data."""
    _prepare_canvas(canvas, palette)
    width = max(int(canvas.winfo_width()), 120)
    height = max(int(canvas.winfo_height()), 80)
    canvas.create_line(
        width / 2 - 24,
        height / 2 - 26,
        width / 2 + 24,
        height / 2 - 26,
        fill=_palette_color(palette, "gridline"),
        width=2,
    )
    canvas.create_text(
        width / 2,
        height / 2,
        text=message,
        fill=_palette_color(palette, "text_muted"),
        font=CHART_LABEL_FONT,
        width=width - 40,
        anchor="center",
        justify="center",
    )


def draw_chart_frame(
    canvas: Canvas,
    plot: PlotArea,
    x_ticks: AxisTicks,
    y_ticks: AxisTicks,
    title: str,
    palette: Mapping[str, str],
    x_title: str = "",
    y_title: str = "",
) -> None:
    """Draw gridlines, axes, tick labels, axis titles, and the chart title."""
    gridline = _palette_color(palette, "gridline")
    axis = _palette_color(palette, "axis")
    text_color = _palette_color(palette, "text")
    for index, value in enumerate(y_ticks.positions):
        pixel_y = data_to_pixel_y(value, plot, y_ticks)
        canvas.create_line(plot.x, pixel_y, plot.x + plot.width, pixel_y, fill=gridline, width=1)
        canvas.create_text(
            plot.x - 6,
            pixel_y,
            text=y_ticks.labels[index],
            fill=text_color,
            font=CHART_LABEL_FONT,
            anchor="e",
        )
    for index, pixel_x in enumerate(_x_tick_pixels(x_ticks, plot)):
        canvas.create_line(pixel_x, plot.y, pixel_x, plot.y + plot.height, fill=gridline, width=1)
        canvas.create_text(
            pixel_x,
            plot.y + plot.height + 6,
            text=x_ticks.labels[index],
            fill=text_color,
            font=CHART_LABEL_FONT,
            anchor="n",
        )
    canvas.create_line(
        plot.x,
        plot.y + plot.height,
        plot.x + plot.width,
        plot.y + plot.height,
        fill=axis,
        width=1,
    )
    canvas.create_line(plot.x, plot.y, plot.x, plot.y + plot.height, fill=axis, width=1)
    if x_title:
        canvas.create_text(
            plot.x + plot.width / 2,
            plot.y + plot.height + 26,
            text=x_title,
            fill=_palette_color(palette, "text_muted"),
            font=CHART_LABEL_FONT,
            anchor="n",
        )
    if y_title:
        canvas.create_text(
            plot.x - 6,
            plot.y - 10,
            text=y_title,
            fill=_palette_color(palette, "text_muted"),
            font=CHART_LABEL_FONT,
            anchor="se",
        )
    canvas.create_text(
        plot.x + plot.width / 2,
        10,
        text=title,
        fill=text_color,
        font=CHART_TITLE_FONT,
        anchor="n",
    )


def _x_tick_pixels(ticks: AxisTicks, plot: PlotArea) -> tuple[float, ...]:
    """Return x tick pixel positions, mapping from data space when needed."""
    if len(ticks.pixel_positions) == len(ticks.positions):
        return ticks.pixel_positions
    baseline = AxisTicks((), (), ticks.min, ticks.max, ())
    return tuple(data_to_pixel_x(position, plot, baseline) for position in ticks.positions)


def draw_legend(
    canvas: Canvas,
    entries: Sequence[tuple[str, str]],
    plot: PlotArea,
    palette: Mapping[str, str],
) -> None:
    """Draw a legend of ``(label, color_key)`` entries inside the top-right corner."""
    if not entries:
        return
    right = plot.x + plot.width
    for index, (label, color_key) in enumerate(entries):
        top = plot.y + 10 + index * 16
        canvas.create_line(
            right - 108,
            top,
            right - 92,
            top,
            fill=_palette_color(palette, color_key),
            width=CHART_LINE_WIDTH,
        )
        canvas.create_text(
            right - 86,
            top,
            text=label,
            fill=_palette_color(palette, "text_muted"),
            font=CHART_LABEL_FONT,
            anchor="w",
        )


def draw_line_chart(
    canvas: Canvas,
    geometry: LineChartGeometry,
    palette: Mapping[str, str],
) -> None:
    """Draw a dual line chart: smooth polylines, "today" ring, legend, frame."""
    _prepare_canvas(canvas, palette)
    plot = geometry.plot
    draw_chart_frame(
        canvas,
        plot,
        geometry.x_ticks,
        geometry.y_ticks,
        geometry.title,
        palette,
        geometry.x_title,
        geometry.y_title,
    )
    for series in geometry.series:
        path = series.smoothed_path or series.pixel_points
        if len(path) >= 2:
            canvas.create_line(
                *[coordinate for point in path for coordinate in point],
                fill=_palette_color(palette, series.color_key),
                width=CHART_LINE_WIDTH,
                smooth=False,
            )
        for pixel_x, pixel_y in series.pixel_points:
            canvas.create_oval(
                pixel_x - 2,
                pixel_y - 2,
                pixel_x + 2,
                pixel_y + 2,
                fill=_palette_color(palette, series.color_key),
                outline="",
            )
    if geometry.today_marker is not None:
        marker_x, marker_y = geometry.today_marker
        canvas.create_oval(
            marker_x - CHART_TODAY_RADIUS,
            marker_y - CHART_TODAY_RADIUS,
            marker_x + CHART_TODAY_RADIUS,
            marker_y + CHART_TODAY_RADIUS,
            outline=_palette_color(palette, "accent"),
            width=2,
        )
    draw_legend(canvas, geometry.legend, plot, palette)


def draw_scatter(
    canvas: Canvas,
    geometry: ScatterGeometry,
    palette: Mapping[str, str],
) -> None:
    """Draw scatter dots and the dashed OLS trend line."""
    _prepare_canvas(canvas, palette)
    plot = geometry.plot
    draw_chart_frame(
        canvas,
        plot,
        geometry.x_ticks,
        geometry.y_ticks,
        geometry.title,
        palette,
        geometry.x_title,
        geometry.y_title,
    )
    if geometry.trend_line is not None:
        (x_start, y_start), (x_end, y_end) = geometry.trend_line
        canvas.create_line(
            x_start,
            y_start,
            x_end,
            y_end,
            fill=_palette_color(palette, "trend_line"),
            width=CHART_LINE_WIDTH,
            dash=(4, 3),
        )
    for pixel_x, pixel_y in geometry.points:
        canvas.create_oval(
            pixel_x - CHART_POINT_RADIUS,
            pixel_y - CHART_POINT_RADIUS,
            pixel_x + CHART_POINT_RADIUS,
            pixel_y + CHART_POINT_RADIUS,
            fill=_palette_color(palette, "series_1"),
            outline="",
        )


def draw_bar_chart(
    canvas: Canvas,
    geometry: BarChartGeometry,
    palette: Mapping[str, str],
) -> None:
    """Draw severity band stripes, grouped bars, and value labels where they fit."""
    _prepare_canvas(canvas, palette)
    plot = geometry.plot
    for left, top, width, height, color_key in geometry.band_rects:
        canvas.create_rectangle(
            left,
            top,
            left + width,
            top + height,
            fill=_palette_color(palette, color_key),
            outline=_palette_color(palette, "gridline"),
            width=CHART_BAND_EDGE_WIDTH,
        )
    draw_chart_frame(
        canvas,
        plot,
        geometry.x_ticks,
        geometry.y_ticks,
        geometry.title,
        palette,
        geometry.x_title,
        geometry.y_title,
    )
    for bar in geometry.bars:
        for index, (left, top, width, height) in enumerate(bar.rects):
            canvas.create_rectangle(
                left,
                top,
                left + width,
                top + height,
                fill=_palette_color(palette, bar.color_key),
                outline="",
            )
            if width >= CHART_BAR_MIN_LABEL_PX:
                canvas.create_text(
                    left + width / 2,
                    top - 4,
                    text=bar.value_labels[index],
                    fill=_palette_color(palette, "text"),
                    font=CHART_LABEL_FONT,
                    anchor="s",
                )
    draw_legend(canvas, geometry.legend, plot, palette)


def legend_for_line_chart() -> tuple[tuple[str, str], ...]:
    """Return the canonical mood/stress legend entries."""
    return ((LEGEND_MOOD, "series_1"), (LEGEND_STRESS, "series_2"))


def utc_today() -> date:
    """Return the current UTC date (a thin I/O helper used by the dashboard)."""
    return datetime.now(UTC).date()
