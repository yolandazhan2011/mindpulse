"""Dashboard: charts and the summary strip (Prompt A F3, Prompt E §7).

Views never compute coordinates: data goes through the pure mappers in
:mod:`mindpulse.charts`, geometry comes back, and the thin renderers draw it.
Re-rendering on resize is debounced so a drag-resize does not redraw every pixel.
"""

from __future__ import annotations

import contextlib
import tkinter as tk
from tkinter import ttk
from typing import Any

from .. import charts, config, storage
from ..models import Instrument

HEADING = "Dashboard"
STREAK_TEMPLATE = "Current streak: {days} day(s) in a row"
TREND_HEADING = "Mood and stress"
SCATTER_HEADING = "Sleep and mood"
SCREENING_HEADING = "Questionnaire history"
RANGE_LABEL = "Show"
CANVAS_MIN_WIDTH = 120
CANVAS_MIN_HEIGHT = 90
CANVAS_HEIGHT = 220


def build(parent: tk.Misc, state: dict[str, Any]) -> ttk.Frame:
    """Build the dashboard and its first render."""
    frame = ttk.Frame(parent, padding=config.PAD)
    view: dict[str, Any] = {
        "state": state,
        "frame": frame,
        "days": config.DEFAULT_RANGE_DAYS,
        "after_id": None,
        "canvases": {},
        "summary_var": tk.StringVar(master=frame, value=""),
        "trend_var": tk.StringVar(master=frame, value=""),
    }
    _render(frame, view)
    return frame


def _render(frame: ttk.Frame, view: dict[str, Any]) -> None:
    """Rebuild the selector, the summary strip, and the three canvases."""
    for child in frame.winfo_children():
        child.destroy()
    frame.columnconfigure(0, weight=1)
    frame.columnconfigure(1, weight=1)
    ttk.Label(frame, text=HEADING, font=config.FONT_TITLE).grid(
        row=0, column=0, sticky="w", columnspan=2
    )
    _build_selector(frame, view)
    ttk.Label(frame, textvariable=view["summary_var"], font=config.FONT_HEADING).grid(
        row=2, column=0, columnspan=2, sticky="w", pady=(config.PAD_SMALL, 0)
    )
    ttk.Label(
        frame,
        textvariable=view["trend_var"],
        font=config.FONT_BODY,
        wraplength=760,
        justify="left",
    ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, config.PAD))
    view["canvases"] = {
        "line": _add_chart_block(frame, view, 4, 0, TREND_HEADING),
        "scatter": _add_chart_block(frame, view, 4, 1, SCATTER_HEADING),
        "bars": _add_chart_block(frame, view, 6, 0, SCREENING_HEADING),
    }
    frame.rowconfigure(4, weight=1)
    frame.rowconfigure(6, weight=1)
    _draw(view)


def _build_selector(frame: ttk.Frame, view: dict[str, Any]) -> None:
    """Add the range selector (7 / 30 / 90 days / All)."""
    selector = ttk.Frame(frame)
    selector.grid(row=1, column=0, columnspan=2, sticky="w", pady=(config.PAD_SMALL, 0))
    ttk.Label(selector, text=RANGE_LABEL, font=config.FONT_BODY).pack(side="left")
    labels = [label for label, _days in config.RANGE_OPTIONS]
    current = dict(config.RANGE_OPTIONS)
    variable = tk.StringVar(
        master=selector,
        value=next(
            (label for label, days in config.RANGE_OPTIONS if days == view["days"]),
            labels[0],
        ),
    )
    combo = ttk.Combobox(selector, values=labels, textvariable=variable, state="readonly", width=12)
    combo.pack(side="left", padx=(config.PAD_SMALL, 0))

    def on_change(_event: object = None) -> None:
        view["days"] = current[variable.get()]
        _draw(view)

    combo.bind("<<ComboboxSelected>>", on_change)


def _add_chart_block(
    frame: ttk.Frame,
    view: dict[str, Any],
    row: int,
    column: int,
    heading: str,
) -> tk.Canvas:
    """Add a titled canvas block and return the canvas."""
    block = ttk.Frame(frame)
    block.grid(row=row, column=column, sticky="nsew", padx=(0, config.PAD), pady=(0, config.PAD))
    block.columnconfigure(0, weight=1)
    block.rowconfigure(1, weight=1)
    ttk.Label(block, text=heading, font=config.FONT_SMALL, foreground=config.COLOR_TEXT_MUTED).grid(
        row=0, column=0, sticky="w"
    )
    canvas = tk.Canvas(
        block,
        height=CANVAS_HEIGHT,
        background=config.COLOR_CANVAS_BG,
        highlightthickness=0,
        takefocus=True,
    )
    canvas.grid(row=1, column=0, sticky="nsew")
    canvas.view_dict = view  # type: ignore[attr-defined] - keeps callbacks stateless
    canvas.bind("<Configure>", lambda _event: _schedule_draw(view_of(canvas)))
    return canvas


def view_of(canvas: tk.Canvas) -> dict[str, Any]:
    """Return the view dictionary a canvas belongs to (stored on the widget)."""
    return canvas.view_dict  # type: ignore[attr-defined]


def _schedule_draw(view: dict[str, Any]) -> None:
    """Debounce a redraw after a resize."""
    root = view["state"]["root"]
    pending = view["after_id"]
    if pending is not None:
        with contextlib.suppress(tk.TclError):  # already fired
            root.after_cancel(pending)
    view["after_id"] = root.after(config.CHART_REDRAW_DEBOUNCE_MS, lambda: _draw(view))


def _draw(view: dict[str, Any]) -> None:
    """Fetch the data, compute geometry, and render all three charts."""
    view["after_id"] = None
    canvases = view["canvases"]
    if not canvases:
        return
    state = view["state"]
    today = charts.utc_today()
    check_ins = storage.list_check_ins(state["conn"])
    view_ins = charts.filter_by_days(check_ins, view["days"], today)
    screenings = charts.filter_by_days(storage.list_screenings(state["conn"]), view["days"], today)
    _draw_trend(canvases["line"], view_ins)
    _draw_scatter(canvases["scatter"], view_ins)
    _draw_screenings(canvases["bars"], screenings)
    _update_summary(view, check_ins, today)


def _draw_trend(canvas: tk.Canvas, check_ins: tuple[Any, ...]) -> None:
    """Draw the mood/stress dual line chart, or its empty state."""
    message = _empty_message(len(check_ins), config.EMPTY_TREND)
    if message:
        charts.draw_empty_state(canvas, message, config.CHART_PALETTE)
        return
    size = _canvas_size(canvas)
    if size is None:
        return
    width, height = size
    mood = charts.check_ins_to_chart_points(check_ins)
    stress = charts.check_ins_to_stress_points(check_ins)
    try:
        geometry = charts.compute_line_chart_geometry(
            [
                charts.LineSeries(charts.LEGEND_MOOD, "series_1", mood),
                charts.LineSeries(charts.LEGEND_STRESS, "series_2", stress),
            ],
            width,
            height,
            y_range=config.WELLBEING_RANGE,
            today_index=len(mood) - 1,
        )
    except ValueError:
        charts.draw_empty_state(canvas, config.EMPTY_TREND, config.CHART_PALETTE)
        return
    charts.draw_line_chart(canvas, geometry, config.CHART_PALETTE)


def _draw_scatter(canvas: tk.Canvas, check_ins: tuple[Any, ...]) -> None:
    """Draw the sleep-vs-mood scatter with its trend line."""
    message = _empty_message(len(check_ins), config.EMPTY_TREND)
    if message:
        charts.draw_empty_state(canvas, message, config.CHART_PALETTE)
        return
    size = _canvas_size(canvas)
    if size is None:
        return
    width, height = size
    try:
        geometry = charts.compute_scatter_geometry(
            charts.check_ins_to_sleep_mood_points(check_ins),
            width,
            height,
            x_range=config.SLEEP_RANGE,
            y_range=config.WELLBEING_RANGE,
            x_title=config.AXIS_TITLE_SLEEP,
        )
    except ValueError:
        charts.draw_empty_state(canvas, config.EMPTY_TREND, config.CHART_PALETTE)
        return
    charts.draw_scatter(canvas, geometry, config.CHART_PALETTE)


def _draw_screenings(canvas: tk.Canvas, screenings: tuple[Any, ...]) -> None:
    """Draw grouped screening bars over severity stripes, or the empty state."""
    series = charts.screenings_to_bar_series(screenings)
    if not series:
        charts.draw_empty_state(canvas, config.EMPTY_SCREENING, config.CHART_PALETTE)
        return
    size = _canvas_size(canvas)
    if size is None:
        return
    width, height = size
    instrument = _range_instrument(screenings)
    try:
        geometry = charts.compute_bar_chart_layout(
            series,
            width,
            height,
            y_range=_screening_range(instrument),
            bands=charts.severity_bands_for_chart(instrument),
            y_title=config.AXIS_TITLE_SCREENING,
        )
    except ValueError:
        charts.draw_empty_state(canvas, config.EMPTY_SCREENING, config.CHART_PALETTE)
        return
    charts.draw_bar_chart(canvas, geometry, config.CHART_PALETTE)


def _range_instrument(screenings: tuple[Any, ...]) -> Instrument:
    """Return the instrument whose full range governs the bar chart's y axis."""
    if any(record.instrument is Instrument.PHQ9 for record in screenings):
        return Instrument.PHQ9
    return Instrument.GAD7


def _screening_range(instrument: Instrument) -> tuple[float, float]:
    """Return the full 0..max_total range for an instrument (never truncated)."""
    max_total = 27.0 if instrument is Instrument.PHQ9 else 21.0
    return 0.0, max_total


def _update_summary(view: dict[str, Any], check_ins: tuple[Any, ...], today: Any) -> None:
    """Refresh the streak line and the week-over-week sentence."""
    streak = charts.compute_streak([record.created_at for record in check_ins], today)
    view["summary_var"].set(STREAK_TEMPLATE.format(days=streak))
    sentence = charts.compose_trend_sentence(*charts.compute_period_averages(check_ins, today))
    view["trend_var"].set(sentence or config.EMPTY_TREND)


def _empty_message(count: int, fallback: str) -> str:
    """Return the empty-state message for ``count`` points, or ``""`` when drawable."""
    if count == 0:
        return fallback
    if count == 1:
        return config.EMPTY_SINGLE_POINT
    return ""


def _canvas_size(canvas: tk.Canvas) -> tuple[int, int] | None:
    """Return the canvas size, or ``None`` when it is too small to draw."""
    width = canvas.winfo_width()
    height = canvas.winfo_height()
    if width < CANVAS_MIN_WIDTH or height < CANVAS_MIN_HEIGHT:
        return None
    return width, height
