"""Configuration for MindPulse: file paths, constants, colour palette, feature flags.

This module holds data only. Nothing here performs I/O beyond computing a
:class:`pathlib.Path`; no file is created until ``storage.py`` is called.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

APP_NAME = "MindPulse"
APP_VERSION = "1.0.0"
APP_TAGLINE = "A local-first mental fitness companion"

#: Directory holding all local application state. Created on first launch.
DATA_DIR: Path = Path.home() / ".mindpulse"
DATABASE_FILENAME = "mindpulse.db"

#: User-editable configuration file (git-ignored, optional, read-only for the app).
LOCAL_CONFIG_FILENAME = "config.json"

#: Environment variables read by the companion. The API key is never persisted.
ENV_API_KEY = "MINDPULSE_API_KEY"
ENV_MODEL = "MINDPULSE_MODEL"


def default_database_path() -> Path:
    """Return the default SQLite database path (``~/.mindpulse/mindpulse.db``)."""
    return DATA_DIR / DATABASE_FILENAME


# ---------------------------------------------------------------------------
# Feature flags
# ---------------------------------------------------------------------------

#: The AI companion is a required feature; this flag exists for offline builds.
FEATURE_AI_COMPANION = True
#: Journal sharing with the AI service is opt-in and defaults to unchecked.
FEATURE_JOURNAL_SHARING_DEFAULT = False


# ---------------------------------------------------------------------------
# Scales and limits
# ---------------------------------------------------------------------------

SCALE_MIN = 1
SCALE_MAX = 10
SLEEP_MIN_HOURS = 0.0
SLEEP_MAX_HOURS = 24.0
SLEEP_STEP_HOURS = 0.5
JOURNAL_MAX_CHARS = 2000
CHAT_HISTORY_LIMIT = 20
CHAT_MAX_REPLY_CHARS = 4000
MIN_FONT_SIZE_PT = 11

#: Dashboard range selector entries: ``(label, days)``; ``None`` means "All".
RANGE_OPTIONS: tuple[tuple[str, int | None], ...] = (
    ("7 days", 7),
    ("30 days", 30),
    ("90 days", 90),
    ("All", None),
)
DEFAULT_RANGE_DAYS: int | None = 30


# ---------------------------------------------------------------------------
# Palette (colour-blind-safe: blue + orange, never red + green)
# ---------------------------------------------------------------------------

COLOR_CANVAS_BG = "#FAFAF7"  # canvas background (warm off-white)
COLOR_APP_BG = "#FFFFFF"  # main window background
COLOR_PANEL_BG = "#F4F4EF"  # sidebar / banner background
COLOR_GRIDLINE = "#E3E3DC"  # minor/major gridlines
COLOR_AXIS = "#8A8A80"  # axis lines
COLOR_TEXT = "#2B2B2B"  # titles and tick labels
COLOR_TEXT_MUTED = "#6B6B62"  # legend and secondary text
COLOR_SERIES_1 = "#2E6FDB"  # first data series (mood) - blue
COLOR_SERIES_2 = "#E07B00"  # second data series (stress) - orange
COLOR_ACCENT = "#111111"  # "today" marker and newest point
COLOR_BAND_SEVERITY_A = "#F2F2EC"  # alternate severity stripe fill (even bands)
COLOR_BAND_SEVERITY_B = "#E8E8E0"  # alternate severity stripe fill (odd bands)
COLOR_BAND_SEVERITY: tuple[str, str] = (COLOR_BAND_SEVERITY_A, COLOR_BAND_SEVERITY_B)
COLOR_TREND_LINE = "#6B6B62"  # scatter trend line (dashed)
COLOR_BUTTON_BG = "#E8EEF9"  # navigation button background
COLOR_BUTTON_ACTIVE_BG = "#D3E0F7"  # selected navigation button
COLOR_HELP_ACCENT = "#8B2E00"  # "Get help now" button text/outline
COLOR_WARNING_BG = "#FFF4E5"  # persistent support banner background

#: Maps a geometry ``color_key`` to a hex string. Renderers look colours up here,
#: so both layers share one source of truth.
CHART_PALETTE: Mapping[str, str] = MappingProxyType(
    {
        "canvas_bg": COLOR_CANVAS_BG,
        "gridline": COLOR_GRIDLINE,
        "axis": COLOR_AXIS,
        "text": COLOR_TEXT,
        "text_muted": COLOR_TEXT_MUTED,
        "series_1": COLOR_SERIES_1,
        "series_2": COLOR_SERIES_2,
        "accent": COLOR_ACCENT,
        "band_a": COLOR_BAND_SEVERITY_A,
        "band_b": COLOR_BAND_SEVERITY_B,
        "trend_line": COLOR_TREND_LINE,
    }
)


# ---------------------------------------------------------------------------
# Chart layout
# ---------------------------------------------------------------------------

#: (left, top, right, bottom) padding inside a chart canvas, in pixels.
CHART_MARGINS: tuple[int, int, int, int] = (56, 36, 20, 40)
CHART_TITLE_FONT: tuple[str, int, str] = ("TkDefaultFont", 12, "bold")
CHART_LABEL_FONT: tuple[str, int] = ("TkDefaultFont", 10)
CHART_POINT_RADIUS = 4  # scatter dot radius, px
CHART_TODAY_RADIUS = 6  # "today" marker radius, px
CHART_LINE_WIDTH = 2  # polyline width, px
CHART_TICK_MIN_PX = 64  # minimum horizontal spacing between x-tick labels, px
CHART_X_TICK_HINT = 6  # preferred number of x-axis ticks before thinning
CHART_Y_TICK_COUNT = 10  # y-axis tick candidates (1-10 scale yields step 1)
CHART_SMOOTH_SUBDIVISIONS = 8  # segment subdivisions for smooth polylines
CHART_BAR_MIN_LABEL_PX = 24  # omit bar value labels narrower than this, px
CHART_BAR_GAP_PX = 2.0  # gap between grouped bars, px
CHART_BAND_EDGE_WIDTH = 1  # severity band edge line width, px
CHART_REDRAW_DEBOUNCE_MS = 150  # resize debounce delay, ms

CHART_TITLE_TREND = "Mood & stress over time"
CHART_TITLE_SCATTER = "Sleep vs. mood"
CHART_TITLE_SCREENING = "Screening history"
AXIS_TITLE_DATE = "Date"
AXIS_TITLE_WELLBEING = "Score (1–10)"
AXIS_TITLE_SLEEP = "Sleep (hours)"
AXIS_TITLE_SCREENING = "Score"
LEGEND_MOOD = "Mood"
LEGEND_STRESS = "Stress"
LEGEND_PHQ9 = "PHQ-9"
LEGEND_GAD7 = "GAD-7"

#: Forced data ranges - charts never rescale to exaggerate a trend.
WELLBEING_RANGE: tuple[float, float] = (SCALE_MIN + 0.0, SCALE_MAX + 0.0)
SLEEP_RANGE: tuple[float, float] = (SLEEP_MIN_HOURS, SLEEP_MAX_HOURS)


# ---------------------------------------------------------------------------
# Empty states (verbatim strings, tested by literal equality)
# ---------------------------------------------------------------------------

EMPTY_TREND = "Not enough data yet — save a few check-ins to see your trends."
EMPTY_SCREENING = "Complete a questionnaire to start your screening history."
EMPTY_SINGLE_POINT = "One data point so far. Check in again tomorrow to start a trend."


# ---------------------------------------------------------------------------
# Fixed user-facing copy
# ---------------------------------------------------------------------------

#: Compact disclaimer shown on every screen (Prompt A, S3).
APP_DISCLAIMER_SHORT = (
    "MindPulse is a wellness and education tool, not a medical device. "
    "It does not diagnose or treat any condition."
)

PRIVACY_STATEMENT = (
    "Your data never leaves this computer except optional AI chat. "
    "MindPulse has no accounts, no telemetry, no analytics, and no automatic updates "
    "phoning home. Everything you enter is stored in a single SQLite file in your home "
    "folder, which you can export or erase at any time from the About dialog."
)

HELP_BANNER_TEXT = 'Need support? "Get help now" is always here.'
HELP_BUTTON_TEXT = "Get help now"
CHAT_DISCLAIMER_ANCHOR = "Under every reply:"
JOURNAL_CONSENT_LABEL = "Share my journal entries with the AI service to get feedback."

CONFIRM_SAVE_MESSAGE = "Saved. Thanks for checking in with yourself."
QUIT_PROMPT = "Leave this questionnaire?"

#: Navigation labels, in sidebar order.
NAV_ITEMS: tuple[tuple[str, str], ...] = (
    ("check_in", "Daily check-in"),
    ("screeners", "Questionnaires"),
    ("dashboard", "Dashboard"),
    ("brain_facts", "Brain facts"),
    ("companion", "Pulse (AI companion)"),
)


# ---------------------------------------------------------------------------
# Typography and spacing (minimum 11pt for accessibility)
# ---------------------------------------------------------------------------

FONT_TITLE = ("TkDefaultFont", 16, "bold")
FONT_HEADING = ("TkDefaultFont", 13, "bold")
FONT_BODY = ("TkDefaultFont", 12)
FONT_SMALL = ("TkDefaultFont", 11)
FONT_ITEM = ("TkDefaultFont", 17, "bold")
FONT_CRISIS_TITLE = ("TkDefaultFont", 19, "bold")
FONT_CRISIS_BODY = ("TkDefaultFont", 13)
FONT_MONO = ("TkFixedFont", 12)
PAD = 12
PAD_SMALL = 6
WINDOW_MIN_WIDTH = 940
WINDOW_MIN_HEIGHT = 660
SCALE_WIDGET_LENGTH = 260
JOURNAL_TEXT_HEIGHT = 8
CHAT_TEXT_HEIGHT = 18
