## Role

You are a senior Python engineer with experience in clinical software, desktop GUIs, and health-safety standards. Write production-quality Python. Prefer clarity over cleverness. Never invent clinical content beyond what is specified here.

## Product: "MindPulse" — a local-first mental fitness companion

A **Python desktop application** that helps a person (age 13+) check in on their mental health, take validated screening questionnaires, see beautiful charts of their trends, learn a little neuroscience, and talk to a supportive AI companion. It is a **wellness and education tool, not a medical device, and not a diagnostic tool.**

No user login. No cloud storage. All data lives in a local SQLite file.

## Hard constraints (do not violate)

1. **Language/stack:** Python 3.11+ only. Standard library first. Allowed third-party packages: only what is needed for the LLM HTTP call (e.g. `httpx` or `urllib` from stdlib is preferred). **No pandas, no numpy, no matplotlib.**
2. **GUI:** `tkinter` and `tkinter.ttk` only. All charts and graphs are drawn **manually on a `tk.Canvas`** (lines, ovals, rectangles, text, polygons). Do not embed any external plotting library.
3. **Storage:** `sqlite3` from the standard library. One local database file.
4. **Architecture style:** **functional**. See "Functional style rules" below. Follow them exactly.
5. **No login, no network dependency for core features.** The app must be fully usable offline. The AI companion is optional and clearly marked as such.
6. **Crisis safety is deterministic code.** It must never depend on an LLM.

## Functional style rules (mandatory)

- **No classes**, with one exception: `@dataclass(frozen=True)` records for data shapes (e.g. `CheckIn`, `Screening`, `ChartPoint`). No methods on them except maybe simple properties; all behavior lives in module-level functions.
- **Short functions.** Target under ~25 lines. One job per function. If a function needs a comment to explain a second job, split it.
- **Pure functions where possible.** Functions that compute (scoring, severity bands, chart geometry, date filtering, formatting) must take data in and return data out — no I/O, no globals, no `print`. All I/O (SQLite, files, network, Tk widgets) happens at thin edges of the system.
- **Immutability.** Prefer returning new tuples/lists over mutating arguments. Never mutate a dataclass.
- **Explicit arguments.** Pass the database path or connection into functions; do not hide it in globals or singletons. Example: `save_check_in(conn: Connection, check_in: CheckIn) -> int`.
- **Type hints everywhere**, including return types. Use `from __future__ import annotations`. Model domain values with `typing.NewType` or small enums (`Instrument.PHQ9`, `Severity.MODERATE`) where it aids clarity.
- **Descriptive names.** `compute_phq9_total`, `is_crisis_response_required`, `draw_line_chart_on_canvas`. No `x`, `tmp`, `do_stuff`, `helper`.
- **Docstrings on every public function**, describing behavior and units (e.g. "Returns total score in range 0–27"). Inline comments only where the *why* is non-obvious, not the *what*.
- **Comprehensions and `itertools`/`functools`** over imperative loops where it stays readable. Use `match` statements for state/enum dispatch.
- **Errors:** no bare `except`. Raise specific exceptions; convert them to user-facing messages only at the UI boundary. Pure functions must not swallow errors.
- **No `print` in library modules.** Logging via the `logging` module in I/O layers only.
- **Formatting:** PEP 8, 4-space indent, ≤ 100 char lines.

## Module layout

```text
mindpulse/
    __init__.py
    __main__.py          # entry point: python -m mindpulse
    config.py            # paths, constants, colour palette, feature flags
    models.py            # frozen dataclasses + enums only
    storage.py           # SQLite: schema, migrations, CRUD (I/O layer)
    scoring.py           # pure: PHQ-9 / GAD-7 totals + severity bands
    safety.py            # pure: crisis detection + resource lookup data
    charts.py            # pure geometry functions + thin Canvas renderers
    brain_facts.py       # curated, cited neuroscience education content
    ai_companion.py      # LLM client (I/O layer) + prompt assembly (pure)
    prompts.py           # the AI system prompt as a module constant
    resources.py         # crisis helpline data (structured, not code logic)
    ui/
        __init__.py
        app.py           # window shell, navigation, always-visible help button
        check_in_view.py
        screens_view.py  # PHQ-9 / GAD-7 questionnaire flows
        dashboard_view.py# charts + trend summaries
        companion_view.py# chat UI
        dialogs.py       # crisis dialog, about dialog, export dialog
tests/
    test_scoring.py
    test_safety.py
    test_charts.py       # geometry functions, not the Canvas
    test_storage.py      # against a temp DB
    test_prompts.py
requirements.txt
README.md
```

## Data model — SQLite

Database file: `~/.mindpulse/mindpulse.db` (create the directory if missing). Enable `PRAGMA foreign_keys = ON`. Use `WITHOUT ROWID` where sensible. Timestamps stored as ISO-8601 UTC strings.

```sql
CREATE TABLE IF NOT EXISTS check_ins (
    id          INTEGER PRIMARY KEY,
    created_at  TEXT    NOT NULL,
    mood        INTEGER NOT NULL CHECK (mood BETWEEN 1 AND 10),
    stress      INTEGER NOT NULL CHECK (stress BETWEEN 1 AND 10),
    energy      INTEGER NOT NULL CHECK (energy BETWEEN 1 AND 10),
    sleep_hours REAL    NOT NULL CHECK (sleep_hours BETWEEN 0 AND 24),
    journal     TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS screenings (
    id          INTEGER PRIMARY KEY,
    created_at  TEXT    NOT NULL,
    instrument  TEXT    NOT NULL CHECK (instrument IN ('PHQ9','GAD7')),
    answers     TEXT    NOT NULL,           -- JSON array of ints, in item order
    total       INTEGER NOT NULL,
    severity    TEXT    NOT NULL,
    risk_flag   INTEGER NOT NULL DEFAULT 0  -- 1 if item-9 risk or keyword risk
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id          INTEGER PRIMARY KEY,
    created_at  TEXT    NOT NULL,
    role        TEXT    NOT NULL CHECK (role IN ('user','assistant','system')),
    content     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS app_meta (
    key         TEXT PRIMARY KEY,
    value       TEXT    NOT NULL
);
```

All writes go through `storage.py` functions that return the new row id or a frozen dataclass. All reads return tuples/lists of frozen dataclasses sorted by `created_at`. Include `run_migrations(conn)` that creates tables idempotently, and `reset_database(path)` for tests and for a user-facing "erase all my data" action.

## Feature specifications

### F1 — Daily check-in (Screen 1)
Simple form: mood, stress, energy — each a 1–10 scale shown as a row of ten big buttons or a `ttk.Scale` with a live number; sleep hours — a `Spinbox` 0–24 step 0.5; journal — a `Text` box with a 2000-character counter. One **Save check-in** button, one **Clear** button. On save: validate, persist, show a short encouraging confirmation, and immediately run the crisis keyword check on the journal text (see S1).

### F2 — Screeners (Screen 2)
Two questionnaires, each presented **one item per screen** with a "Back / Next / Skip this survey" flow and a progress indicator ("Question 3 of 9").

- **PHQ-9:** 9 items, each scored 0–3 with labels `Not at all / Several days / More than half the days / Nearly every day`, asking about the **past 2 weeks**. Total $0\text{–}27$.
- **GAD-7:** 7 items, same 0–3 scale and 2-week window. Total $0\text{–}21$.

Use the standard, public-domain item wording for these instruments (developed by Kroenke, Spitzer & Williams; no permission required to reproduce). Do not paraphrase the items in a way that changes their meaning.

Severity bands (implement exactly):

| Instrument | Total | Severity |
|---|---|---|
| PHQ-9 | 0–4 | minimal |
| PHQ-9 | 5–9 | mild |
| PHQ-9 | 10–14 | moderate |
| PHQ-9 | 15–19 | moderately severe |
| PHQ-9 | 20–27 | severe |
| GAD-7 | 0–4 | minimal |
| GAD-7 | 5–9 | mild |
| GAD-7 | 10–14 | moderate |
| GAD-7 | 15–21 | severe |

After submission show: total, severity band, a plain-language explanation, and a mandatory line: *"This is a screening tool, not a diagnosis. Only a qualified clinician can diagnose a condition. If you're struggling, please talk to a doctor, counselor, or trusted adult."* Add an **"Explain my result with AI"** button (optional feature) and an always-available **"Get help now"** button.

### F3 — Dashboard (Screen 3), all charts hand-drawn on `tk.Canvas`
1. **Mood & stress trend** — dual line chart, last 30 check-ins or last 30 days, x = date, y = 1–10.
2. **Sleep vs mood** — scatter plot with a light trend line (ordinary least squares computed in pure code).
3. **Screening history** — grouped bar chart of PHQ-9 and GAD-7 totals per date, with horizontal severity-band background stripes.
4. **Summary strip** — text stats computed by pure functions: current streak of check-in days, averages over last 7 vs previous 7 days, and one plain sentence such as *"Your mood averaged 6.1 this week, up from 4.8 last week."*
Include a range selector (7 days / 30 days / 90 days / All).

### F4 — Brain facts (a small panel on the dashboard or its own screen)
8–10 short cards (60–90 words each), each with a title, body, and a source/attribution line. Topics: amygdala and the stress response, prefrontal cortex and emotion regulation, hippocampus and chronic stress, sleep and the glymphatic system, neuroplasticity and exercise, serotonin/ dopamine myths-vs-facts, the HPA axis, why naming emotions helps (affect labeling). Content must be factual, cautious, and non-prescriptive. Keep this content in `brain_facts.py` as an immutable tuple of frozen dataclasses.

### F5 — AI companion (optional, Screen 4)
A chat panel. Requirements:
- The system prompt lives in `prompts.py` (see the companion prompt I supply separately; use it verbatim as `SYSTEM_PROMPT`).
- Conversation history is trimmed to the last N messages (configurable, default 20) before each call; the system prompt is always first.
- The app must **refuse to send** anything to the LLM while the crisis gate is active; it shows helplines instead.
- Journal text is sent **only if the user ticks a consent checkbox** labeled clearly: *"Share my journal entries with the AI service to get feedback."* Default: unchecked.
- API key is read from an environment variable (`MINDPULSE_API_KEY`) or a local config file that is git-ignored. Never hard-code secrets. Never log the key.
- Every assistant message is rendered with a persistent one-line disclaimer under the chat: *"AI responses are generated automatically and may be wrong. This is not therapy or medical advice."*
- If the network fails or no key is configured, the companion screen shows a friendly offline message and the app remains fully functional.
- Store both user and assistant messages in `chat_messages` so the conversation survives restarts, and provide a **"Delete this conversation"** button.

### F6 — Resources & about
A permanently visible **"Get help now"** button in the main window (never hidden behind menus) that opens the crisis dialog described in S1. An About dialog with version, disclaimers, privacy statement ("your data never leaves this computer except optional AI chat"), and a data export action (**Export my data** → JSON or CSV written to a user-chosen path) plus **Erase all my data**.

## Safety specification (highest priority — implement before any other feature)

**S1 — Crisis gate.** A pure function `is_crisis_response_required(screening_answers, journal_text, chat_text) -> bool` that returns `True` when **any** of these hold:
- PHQ-9 **item 9** (thoughts of being better off dead or of self-harm) is scored greater than 0;
- any configured crisis phrase appears in user-entered text (case-insensitive, matched on word boundaries). Initial phrase list: `kill myself`, `end my life`, `suicide`, `self harm`, `self-harm`, `hurt myself`, `want to die`, `no reason to live`, `better off dead`, `overdose`.
Phrase matching must be pure, easily unit-tested, and trivially extendable via config — no regex soup, no fuzzy AI matching.

**S2 — Crisis dialog.** When the gate fires: a modal `Toplevel` dialog that takes focus, shows large friendly text ("You matter, and help is available right now"), and lists resources **without requiring any input**:
- **988 Suicide & Crisis Lifeline** — call or text **988** (US)
- **Crisis Text Line** — text **HOME** to **741741** (US)
- **findahelpline.com** for other countries
- **Emergency services: 911 (US) / 112 (EU)** if there is immediate danger
Buttons: *I'm safe right now* (dismisses but keeps a persistent "Get help now" banner on every screen), *Call/Text 988* (uses `webbrowser`/`os` to open `tel:`/`sms:` links where supported). The dialog must not contain any AI-generated content, tips, or coping advice — only resources and warm, brief, human language.

**S3 — Every screen** shows a compact disclaimer line; the questionnaire result screen shows the full one from F2.

**S4 — The LLM is never a safety mechanism.** If a crisis phrase is detected in a chat message, the client must send **no request** to the API and must display the S2 resources instead.

## Charting specification (`charts.py`)

Split into two layers:
1. **Pure geometry** — functions like `compute_line_chart_geometry(points, width, height, margins) -> ChartGeometry`, `compute_axes(min_value, max_value, tick_count) -> AxisTicks`, `compute_scatter_trend_line(points) -> Line`, `compute_bar_chart_layout(series, width, height) -> BarLayout`. These return plain data (frozen dataclasses of coordinates) and are unit-tested without Tkinter.
2. **Thin renderers** — `draw_line_chart(canvas, geometry, palette)`, `draw_bar_chart(...)`, `draw_scatter(...)` that only translate geometry into `canvas.create_line / create_rectangle / create_oval / create_text` calls.

Visual requirements:
- Consistent palette in `config.py`: background, gridline, two data series colours, an accent for "today" markers, plus a colour-blind-safe choice (e.g. blue + orange, not red + green).
- Crisp 1px gridlines, tick labels on both axes, ISO dates on the x-axis (`2026-10-18` → `Oct 18` in the label), a legend, and a title inside the canvas.
- Charts re-render on window resize by recomputing geometry from the new canvas size (bind `<Configure>`, debounce with `after`).
- Handle **empty states gracefully**: "Not enough data yet — save a few check-ins to see your trends."
- Draw smooth polylines by subdividing segments; avoid overlapping text by limiting tick count to what fits (compute from pixel width).

## Error handling, privacy, accessibility

- Validate all inputs at the UI edge; pure functions assume valid input and raise `ValueError` with clear messages otherwise.
- Database failures show a non-destructive error dialog ("Couldn't save — your data is still safe"), and the app must never crash on a corrupt row (skip and log).
- Privacy: no analytics, no telemetry, no automatic updates phoning home. State this in the README and the About dialog.
- Accessibility: full keyboard navigation (Tab order, Enter to submit, Esc to close dialogs), minimum font size 11pt, high-contrast palette, no meaning conveyed by colour alone (use labels/patterns in charts).

## Testing

Use `unittest` or `pytest` (your choice) with tests focused on the pure core:
- `test_scoring.py`: totals and severity boundaries for both instruments (including exact cutoffs 4/5, 9/10, 14/15, 19/20 and 4/5, 9/10, 14/15), out-of-range answers rejected.
- `test_safety.py`: each crisis phrase matches, near-misses do not match ("I killed it in that game" must not trigger), PHQ-9 item 9 > 0 always triggers, empty input never triggers.
- `test_charts.py`: geometry functions on known inputs, empty data, single point, identical values (flat line must not divide by zero).
- `test_storage.py`: round-trip CRUD against a temporary database file.
- The AI client must be testable with an injected fake transport.

## Deliverables & definition of done

1. All modules listed in the layout, complete and runnable via `python -m mindpulse`.
2. `requirements.txt` (minimal) and a `README.md` with setup, screenshots placeholder, disclaimers, and the privacy statement.
3. Test suite passing.
4. Build order: **models → scoring → safety (+ tests) → storage (+ tests) → charts geometry (+ tests) → UI shell → check-in view → screener view → dashboard → brain facts → dialogs → AI companion last.** Report progress module by module; do not generate everything in one blob.
