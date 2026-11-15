## Prompt E — Charting Specification (`charts.py`, Tkinter Canvas)

### 0. Relationship to Prompts A–D

This prompt supplements the MindPulse master development prompt (Prompt A) and overrides nothing in Prompts B (instruments), C (companion), or D (safety). It is authoritative for `charts.py`, the chart-related constants in `config.py`, and the chart tests.

Standing rules hold: functional style, frozen dataclasses, short pure functions with docstrings and type hints, no classes except frozen dataclasses, **Tkinter Canvas only — no matplotlib, numpy, or any plotting package**.

**Deliverables, in order:**
1. Chart palette and layout constants in `config.py`.
2. `charts.py` §3 pure geometry layer + §4 render layer.
3. `test_charts.py` (§6), passing — geometry only, no Tkinter in tests.
4. Dashboard wiring rules (§7), used later by `ui/dashboard_view.py`.

Build the pure layer and its tests **before** writing a single Canvas call.

---

### 1. Design principles

1. **Two strict layers.** All computation is pure: dates and values in, pixel geometry out, as frozen dataclasses. All drawing is thin: geometry in, `Canvas` item calls out, no math beyond coordinates already computed.
2. **Testable without a display.** The pure layer must run in a headless test runner with no Tk import. If a function needs a widget to be tested, it is in the wrong layer.
3. **Charts are for understanding, not decoration.** Every chart carries axis labels, a title, a legend where there are multiple series, and honest scales. Never truncate a y-axis to exaggerate a trend; mood/stress/energy charts always span $1\text{–}10$ in full; screening charts span $0\text{–}27$ (PHQ-9) and $0\text{–}21$ (GAD-7) in full.
4. **Graceful emptiness.** No data is a normal state, not an error. Every chart has a designed empty state (§5).
5. **Accessible by construction.** Colour-blind-safe palette, no meaning carried by colour alone (every series is also labeled), readable font sizes, and sufficient contrast against the canvas background.

---

### 2. Constants (`config.py`)

#### 2.1 Palette (colour-blind-safe; blue + orange, never red + green)

| Constant | Purpose | Suggested value |
|---|---|---|
| `COLOR_CANVAS_BG` | Canvas background | `#FAFAF7` (warm off-white) |
| `COLOR_GRIDLINE` | Minor/major gridlines | `#E3E3DC` |
| `COLOR_AXIS` | Axis lines | `#8A8A80` |
| `COLOR_TEXT` | Titles, tick labels | `#2B2B2B` |
| `COLOR_TEXT_MUTED` | Legend/secondary text | `#6B6B62` |
| `COLOR_SERIES_1` | First data series (mood) | `#2E6FDB` (blue) |
| `COLOR_SERIES_2` | Second data series (stress) | `#E07B00` (orange) |
| `COLOR_ACCENT` | "Today" marker, latest point | `#111111` |
| `COLOR_BAND_SEVERITY` | Screening severity band stripes | two alternating fills, e.g. `#F2F2EC` / `#E8E8E0`, with band-edge lines in `COLOR_GRIDLINE` |
| `COLOR_TREND_LINE` | Scatter trend line | `#6B6B62` dashed |

Every value is a hex string constant with a comment stating its role. Changing a chart's look means changing these constants — never hard-coding colours in `charts.py`.

#### 2.2 Layout

| Constant | Meaning | Default |
|---|---|---|
| `CHART_MARGINS` | (left, top, right, bottom) padding inside the canvas | `(56, 36, 20, 40)` |
| `CHART_TITLE_FONT` | Title typeface/size | `("TkDefaultFont", 12, "bold")` |
| `CHART_LABEL_FONT` | Tick and legend typeface/size | `("TkDefaultFont", 10)` |
| `CHART_POINT_RADIUS` | Scatter dot radius (px) | `4` |
| `CHART_TODAY_RADIUS` | "Today" marker radius (px) | `6` |
| `CHART_LINE_WIDTH` | Polyline width | `2` |
| `CHART_TICK_MIN_PX` | Minimum horizontal spacing between x-tick labels | `64` |
| `CHART_SMOOTH_SUBDIVISIONS` | Segment subdivisions for smooth polylines | `8` |

---

### 3. Pure geometry layer (contracts)

All functions are pure: no Tkinter, no globals, no side effects. All records below are frozen dataclasses.

#### 3.1 Data shapes

| Record | Fields |
|---|---|
| `ChartPoint` | `x: float` (matplotlib-style numeric date or a plain index — see §3.2), `y: float`, `label: str` (e.g. `Oct 18`, for tooltips/labels) |
| `Margins` | `left: int`, `top: int`, `right: int`, `bottom: int` |
| `AxisTicks` | `positions: tuple[float, ...]` (data-space), `labels: tuple[str, ...]`, `min: float`, `max: float` |
| `PlotArea` | `x: float`, `y: float`, `width: float`, `height: float` (pixel rect inside margins) |
| `LineSeriesGeometry` | `name: str`, `color_key: str` (references a palette constant name, not a literal), `pixel_points: tuple[tuple[float, float], ...]`, `smoothed_path: tuple[tuple[float, float], ...]` |
| `LineChartGeometry` | `plot: PlotArea`, `x_ticks: AxisTicks`, `y_ticks: AxisTicks`, `series: tuple[LineSeriesGeometry, ...]`, `today_marker: tuple[float, float] \| None` |
| `ScatterGeometry` | `plot: PlotArea`, `x_ticks`, `y_ticks`, `points: tuple[tuple[float, float], ...]`, `trend_line: tuple[tuple[float, float], tuple[float, float]] \| None` |
| `BarGeometry` | `name: str`, `color_key: str`, `rects: tuple[tuple[float, float, float, float], ...]` (x, y, width, height), `value_labels: tuple[str, ...]` |
| `BarChartGeometry` | `plot`, `x_ticks`, `y_ticks`, `bars: tuple[BarGeometry, ...]`, `band_rects: tuple[tuple[float, float, float, float, str], ...]` (severity stripe fills, `(x, y, w, h, color_key)`) |
| `SeverityBand` | `label: str`, `y_low: float`, `y_high: float` (data space) |

#### 3.2 Coordinate convention (state it in module docstring and follow everywhere)

- Canvas pixel origin is top-left; **y grows downward**. Data y grows upward, so all mappings invert: `pixel_y = plot_bottom - (value - y_min) / (y_max - y_min) * plot_height`.
- x is a numeric date (days since an epoch, or a monotone index when dates are sparse) with the human label carried in `ChartPoint.label`. Pure functions never parse strings for positioning.
- Geometry functions accept `width` and `height` as arguments so tests can use tiny canvases (e.g. $320 \times 240$).

#### 3.3 Function contracts

| Function | Contract |
|---|---|
| `compute_plot_area(width, height, margins) -> PlotArea` | Inner rectangle after margins. Raise `ValueError` if the result would be non-positive in either dimension. |
| `compute_axes(min_value, max_value, tick_count) -> AxisTicks` | "Nice" ticks at 1/2/5×$10^k$ steps covering $[min, max]$, with labels trimmed to at most 2 decimals (no trailing zeros). For the fixed $1\text{–}10$ wellbeing scale, use `tick_count=10` and integer labels. Raise `ValueError` if `min_value == max_value` unless the caller passed a forced range (see chart contracts). |
| `compute_line_chart_geometry(series_data, width, height, margins, y_range, x_ticks_hint, today_index) -> LineChartGeometry` | Map each series' `ChartPoint`s to pixels. `y_range` is a `(min, max)` tuple forced by the caller (e.g. `(1, 10)`) so wellbeing charts never rescale. `today_index` marks the newest point as `today_marker`. If a series has one point, produce a single pixel point and empty `smoothed_path`. |
| `smooth_path(pixel_points, subdivisions=CHART_SMOOTH_SUBDIVISIONS) -> tuple[tuple[float, float], ...]` | Densify each segment by linear interpolation (cosine-eased is acceptable) so lines render crisply. Empty input → empty tuple. Never invent curvature beyond segment subdivision — charts must not visually imply data that doesn't exist. |
| `compute_scatter_geometry(points, width, height, margins, x_range, y_range) -> ScatterGeometry` | Map points to pixels; compute `trend_line` via `compute_trend_line`. |
| `compute_trend_line(points) -> tuple[tuple[float, float], tuple[float, float]] \| None` | Ordinary least squares in data space: slope $m = \dfrac{\sum (x_i-\bar{x})(y_i-\bar{y})}{\sum (x_i-\bar{x})^2}$, intercept $b = \bar{y} - m\bar{x}$. Return the line segment from the smallest to the largest $x$ in the data. Return `None` when there are fewer than 2 points or the $x$ variance is zero (all identical $x$) — never divide by zero, never invent a vertical line. |
| `compute_bar_chart_layout(series, width, height, margins, y_range, bands) -> BarChartGeometry` | Grouped bars: within each x position, divide the group width evenly among the series with a small gap (≥ 2px). `bands` (tuple of `SeverityBand`) become full-width background `band_rects` behind the bars. |
| `thin_tick_labels(ticks, available_px, min_px=CHART_TICK_MIN_PX) -> AxisTicks` | Return every $k$-th tick where $k = \lceil n \cdot min\_px / available\_px \rceil$, always keeping the first and last. Prevents overlapping x labels on narrow windows. |
| `format_date_label(iso_timestamp: str) -> str` | `2026-10-18T09:30:00Z` → `Oct 18`. Pure string formatting; raise `ValueError` on malformed input. |
| `format_value_label(value: float) -> str` | At most 2 decimals, trailing zeros trimmed (`6.0` → `6`, `6.25` → `6.25`). |

Every function returns new data; none mutates inputs.

---

### 4. Render layer (thin, no math)

Each renderer takes a geometry record and a `tk.Canvas`, clears the canvas (`canvas.delete("all")`), and draws in a fixed z-order: **bands → gridlines → axes → bars/lines/points → markers → labels → title → legend.** Renderers perform only `canvas.create_rectangle / create_line / create_oval / create_text / create_polygon` calls and palette lookups; if a renderer needs to compute a coordinate that isn't already in the geometry record, that computation belongs in §3.

| Function | Draws |
|---|---|
| `draw_line_chart(canvas, geometry, palette)` | Two smooth polylines (mood = `COLOR_SERIES_1`, stress = `COLOR_SERIES_2`), per-series legend, "today" marker as a ring in `COLOR_ACCENT`, grid, both axes, title text `Mood & stress over time`. |
| `draw_scatter(canvas, geometry, palette)` | Dots in `COLOR_SERIES_1`, dashed trend line in `COLOR_TREND_LINE`, axes, title `Sleep vs. mood`. |
| `draw_bar_chart(canvas, geometry, palette)` | Severity band fills, grouped bars, per-bar value labels above bars (only if bar width ≥ 24px, else omit), legend naming both instruments, title `Screening history`. |
| `draw_chart_frame(canvas, plot, x_ticks, y_ticks, title, palette)` | Shared frame: title text, gridlines aligned to ticks, axis lines, tick labels, axis titles (`Date` on x; caller-supplied y title such as `Score (1–10)`). |
| `draw_empty_state(canvas, message, palette)` | A single centered muted message (§5) plus an optional small decorative dash pattern — no axes, no fake data. |

**Text rules:** every `create_text` uses `CHART_LABEL_FONT` or `CHART_TITLE_FONT` and `fill=COLOR_TEXT*`. x tick labels anchored `n` (below axis), y tick labels anchored `e` (left of axis). Titles anchored `n` at the top center of the canvas.

**Line rules:** `smooth=TRUE` is allowed but geometry must already be densified (§3.3) — do not rely on the canvas for smoothing.

---

### 5. Empty states (verbatim strings)

Define as constants in `config.py` and test by literal equality:

| Constant | Text | When |
|---|---|---|
| `EMPTY_TREND` | `Not enough data yet — save a few check-ins to see your trends.` | Fewer than 2 check-ins for line/scatter |
| `EMPTY_SCREENING` | `Complete a questionnaire to start your screening history.` | No screenings stored |
| `EMPTY_SINGLE_POINT` | `One data point so far. Check in again tomorrow to start a trend.` | Exactly 1 check-in |

---

### 6. Testing requirements (`test_charts.py`)

Pure layer only; **no `tkinter` import anywhere in this file.** Use small canvases ($320 \times 240$ and $200 \times 120$) and assert exact coordinates for hand-computed cases.

1. **Plot area** — margins subtracted correctly; `ValueError` on over-large margins.
2. **Axes** — known ranges produce expected ticks ($0\text{–}27$ → steps of 5; $1\text{–}10$ → integers 1..10); `ValueError` on `min == max`; labels never have more than 2 decimals.
3. **Line geometry** — y-inversion verified: value $max$ maps to the top of the plot area; 2-point series produce the right endpoints; single point → empty smoothed path; `today_marker` matches the last point.
4. **Smooth path** — subdivision count is `len(points)-1` × subdivisions + 1; endpoints preserved exactly; empty input safe.
5. **Trend line** — perfect line data ($y = 2x + 1$) returns that exact line; all-identical x → `None`; 0 or 1 point → `None`; noisy data matches a hand-computed OLS within a small epsilon.
6. **Scatter geometry** — zero-variance data does not raise; points map into the plot area.
7. **Bar layout** — grouped bars don't overlap (right edge of bar $i$ < left edge of bar $i+1$ minus gap); band rects span the full plot width and are ordered by `y_low`.
8. **Tick thinning** — for 30 ticks in 320px at min 64px, returns ~5–6 labels including first and last; a single tick is returned unchanged.
9. **Date/value formatting** — `format_date_label` on a known ISO string; malformed input raises; `format_value_label` cases (6.0→`6`, 6.25→`6.25`, 0→`0`).
10. **Degenerate canvases** — $1 \times 1$ and zero-sized inputs either raise `ValueError` or return empty geometry, never crash or divide by zero. Pick one behavior per function and document it in the docstring.

---

### 7. Dashboard wiring rules (for `ui/dashboard_view.py`, built later)

1. On window `<Configure>`, **debounce** re-rendering with `after(150, ...)`: cancel any pending scheduled render before scheduling a new one. Never render on every pixel of a drag-resize.
2. Data is fetched via `storage.py` read functions, converted to `ChartPoint`s by a pure mapper (`check_ins_to_chart_points`, `screenings_to_bar_series` — put these in `charts.py` §3 and test them), then passed to geometry, then rendered. Views never compute coordinates.
3. Range selector (`7 days / 30 days / 90 days / All`) filters by date in the mapper, not in the geometry functions.
4. The summary strip (current streak, 7-day vs. previous-7-day averages, one-sentence comparison) is computed by pure functions in `charts.py` (`compute_streak`, `compute_period_averages`, `compose_trend_sentence`) and tested like everything else. The sentence template is: `Your mood averaged {this_week} this week, {direction} from {last_week} last week.` with `direction` ∈ `up` / `down` / `unchanged`.
5. Screening bars are drawn with severity band stripes using `SeverityBand` values supplied from Prompt B's severity tables — do not duplicate cutoff numbers in chart code; import the tables.

---

### 8. Build order for this prompt

1. Palette + layout + empty-state constants in `config.py`.
2. `charts.py` §3.1–3.2 data shapes and coordinate convention docstring.
3. Pure functions in §3.3, one at a time with tests in this order: `compute_plot_area` → `compute_axes` → `format_*` → `smooth_path` → `compute_line_chart_geometry` → `compute_trend_line` → `compute_scatter_geometry` → `compute_bar_chart_layout` → `thin_tick_labels` → the pure dashboard mappers.
4. `test_charts.py` complete and passing headlessly.
5. Only then: render layer (§4) and the dashboard view (§7).

Report each step before moving on. Charts must look good — but geometry correctness and empty-state honesty come first.
