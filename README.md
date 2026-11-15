# MindPulse

A **local-first mental fitness companion** for students and young adults (13+).

MindPulse is a Python desktop app for daily check-ins, validated screening
questionnaires (PHQ-9 and GAD-7), hand-drawn trend charts, short cited
neuroscience cards, and an optional AI companion called **Pulse**.

> **MindPulse is a wellness and education tool, not a medical device, and not a
> diagnostic tool.** It does not diagnose or treat any condition. The screening
> questionnaires are validated instruments, but a score here is a snapshot, not an
> assessment. If you are struggling, please talk to a doctor, counselor, or a
> trusted adult.

---

## Privacy

**Your data never leaves this computer except optional AI chat.**

- No accounts, no login, no cloud sync.
- No analytics, no telemetry, no crash reporting, no automatic updates phoning home.
- Everything you enter is stored in a single SQLite file: `~/.mindpulse/mindpulse.db`.
- The only network call in the entire app is the AI companion, and it happens only
  when you press **Send** with an API key configured.
- You can **Export my data** (JSON) or **Erase all my data** at any time from the
  About dialog.

---

## Quick start

MindPulse has **no third-party dependencies** — only the Python standard library.

```bash
# Python 3.11 or newer is required (tkinter must be available)
python3 --version

# Run the app
python3 -m mindpulse

# Run the test suite (227 tests, no display required)
python3 -m unittest discover -t . -s tests

# Lint and, optionally, type-check
ruff check .
```

`requirements.txt` is deliberately empty of packages: see the notes inside it.

### Enabling the AI companion (optional)

The app is fully usable offline. The companion is always visible in the navigation;
without a key it explains how to turn itself on and everything else keeps working.

```bash
export MINDPULSE_API_KEY="sk-or-..."          # OpenRouter key; never committed
export MINDPULSE_MODEL="openai/gpt-4o-mini"   # optional, this is the default
python3 -m mindpulse
```

The key is read from the environment only. It is never written to SQLite, never
logged, and never included in a request body — it lives in the `Authorization`
header of a single HTTPS request.

---

## Screens

| Screen | What it does |
|---|---|
| **Daily check-in** | Mood, stress, energy (1–10), sleep hours (0–24 in half-hour steps), and an optional journal entry with a 2000-character counter. |
| **Questionnaires** | PHQ-9 and GAD-7, one item per screen, with Back / Next / Skip, a progress label, the unscored functional-impairment follow-up, and an optional free-text box. |
| **Dashboard** | Mood & stress line chart, sleep-vs-mood scatter with an OLS trend line, screening history bars over severity-band stripes, a summary strip (streak, this week vs last week), and a 7/30/90-day/All range selector. All charts are drawn manually on a `tk.Canvas`. |
| **Brain facts** | One short, cited education card at a time, chosen by the calendar date so it changes daily. The ten cards cover the amygdala, prefrontal cortex, hippocampus, glymphatic clearance, exercise and plasticity, serotonin/dopamine myths, the HPA axis, affect labelling, sleep and memory, and adult neurogenesis. |
| **Pulse (AI companion)** | A required chat screen with a persistent disclaimer, journal-sharing consent (opt-in, unchecked by default), a "Delete this conversation" button, and graceful degradation when the service is unreachable. |

**Screenshots:** _placeholder — add captured screenshots of the dashboard and the
companion here. Charts use a colour-blind-safe blue/orange palette and label every
series, so meaning never depends on colour alone._

---

## Safety design (the highest priority)

Safety is deterministic code, not a model.

- `safety.py` exposes `is_crisis_response_required(screening_answers, journal_text,
  chat_text)`. It returns `True` when **PHQ-9 item 9** scored above zero, or when a
  phrase from `CRISIS_PHRASES` appears in user text (whole-phrase, word-boundary
  matching; case and spacing insensitive).
- The gate runs **before** storage, **before** scoring is displayed, **before** the
  result screen, and **before** any network request.
- When it fires, a modal dialog shows the four helplines (988, Crisis Text Line,
  findahelpline.com, emergency services) and nothing else. Dismissing it leaves a
  persistent support banner with a **Get help now** button on every screen.
- The AI companion sends **no request at all** while the gate is open: it renders
  `CRISIS_REPLY` from `prompts.py` instead. It also refuses to interpret any
  screening score, locally, with a fixed sentence.
- The companion stays paused while the most recent screening has a risk flag.

The gate deliberately errs toward showing help: a false positive costs one screen
of warm text, a false negative can cost a life.

---

## Architecture

Functional style throughout: **no classes** except `@dataclass(frozen=True)`
records. Pure functions do the computing; I/O lives at thin edges.

```text
mindpulse/
    __main__.py          python -m mindpulse
    config.py            paths, palette, layout, feature flags, fixed copy
    models.py            frozen dataclasses + enums only
    storage.py           SQLite schema, migrations, CRUD, export  (I/O edge)
    instruments.py       canonical PHQ-9 / GAD-7 content, registry, scoring
    scoring.py           scoring facade + result-screen copy
    safety.py            deterministic crisis gate                (pure)
    resources.py         structured helpline data
    charts.py            pure geometry + thin Canvas renderers
    brain_facts.py       curated, cited education cards
    prompts.py           the companion's fixed strings
    ai_companion.py      OpenRouter client, one I/O function      (I/O edge)
    ui/
        app.py           window shell, navigation, help affordances
        check_in_view.py screens_view.py dashboard_view.py
        brain_facts_view.py companion_view.py dialogs.py
tests/                   227 tests, all headless
```

**Rules the code follows:** short single-purpose functions, type hints everywhere,
docstrings on public functions, immutable data, explicit arguments (the database
connection or path is always passed in), no `print`, no bare `except`, and
`ValueError` raised with a clear message for invalid input. User-facing text is
converted to messages only at the UI edge.

### Data model

`check_ins`, `screenings`, `chat_messages`, and `app_meta` (which carries a schema
version and the app version). Timestamps are ISO-8601 UTC strings. Reads return
tuples of frozen dataclasses sorted oldest-first; a corrupt row is logged and
skipped rather than crashing the app. Each screening stores a content checksum of
the instrument's canonical strings, so a future wording change flags old rows
instead of silently rescoring them.

Two columns extend the original layout to satisfy the instrument specification:
`screenings.impairment` (the unscored follow-up answer, nullable) and
`screenings.content_checksum`.

### Charts

`charts.py` is split into two strict layers:

1. **Pure geometry** — `compute_axes`, `compute_plot_area`,
   `compute_line_chart_geometry`, `compute_trend_line`, `compute_scatter_geometry`,
   `compute_bar_chart_layout`, `thin_tick_labels`, plus the dashboard mappers
   (`check_ins_to_chart_points`, `screenings_to_bar_series`, `filter_by_days`,
   `compute_streak`, `compute_period_averages`, `compose_trend_sentence`).
   No Tkinter import; fully tested headlessly.
2. **Thin renderers** — `draw_line_chart`, `draw_scatter`, `draw_bar_chart`,
   `draw_chart_frame`, `draw_empty_state`. They translate geometry into
   `canvas.create_*` calls and nothing else.

Pixel origin is top-left and y grows downward, so data → pixel mapping inverts; the
convention is documented in the module docstring. Mood/stress charts always span
1–10 and screening charts always span 0–27 / 0–21 — axes are never truncated.
Resize redraws are debounced with `after(150, ...)`, and every chart has a designed
empty state.

---

## Accessibility

- Minimum 11pt type; the crisis dialog uses 19pt/13pt.
- Full keyboard operation: Tab order, Enter to submit, Esc to close dialogs,
  `1`–`4` to answer a questionnaire item, Enter to advance, Backspace to go back.
- High-contrast palette, colour-blind-safe series colours (blue + orange), and
  every series labelled in a legend — no meaning conveyed by colour alone.

---

## Testing

```bash
python3 -m unittest discover -t . -s tests
```

| File | Covers |
|---|---|
| `test_instruments.py` | item counts, canonical strings and their single source, scoring, every severity boundary, risk rules, impairment rules, registry integrity |
| `test_scoring.py` | result copy pinned to the specification, score line, band explanations |
| `test_safety.py` | every crisis phrase, documented near-misses, case/whitespace/punctuation, item-9 risk, gate composition, risk-source diagnostics |
| `test_resources.py` | helpline data, ordering, phone/SMS/URL rules |
| `test_storage.py` | schema, migrations, CRUD round-trips, ordering, filters, corrupt-row skipping, export, erase |
| `test_charts.py` | geometry on hand-computed inputs, y-inversion, OLS trend line, bar layout and gaps, tick thinning, formatters, mappers, summaries, degenerate canvases |
| `test_prompts.py` | literal equality of every companion string |
| `test_ai_companion.py` | crisis short-circuit (transport never called), no-key, happy path, malformed responses, status mapping, prompt assembly order, history trimming, secret hygiene |
| `test_brain_facts.py` | card count, word budget, unique titles, citations, non-prescriptive voice, daily rotation (stable within a day, steps daily, one full cycle, any date) |

Instrument text is never duplicated outside `instruments.py` — a test enforces it.

---

## Attribution

- PHQ-9 modified from PRIME-MD. Developed by Drs. Robert L. Spitzer, Janet B.W.
  Williams, and Kurt Kroenke.
- GAD-7 modified from PRIME-MD. Developed by Drs. Robert L. Spitzer, Janet B.W.
  Williams, Kurt Kroenke, and colleagues.
- Kroenke K, Spitzer RL, Williams JBW. The PHQ-9: Validity of a Brief Depression
  Severity Measure. *J Gen Intern Med.* 2001;16(9):606-613.
- Spitzer RL, Kroenke K, Williams JBW, Löwe B. A brief measure for assessing
  generalized anxiety disorder: the GAD-7. *Arch Intern Med.* 2006;166(10):1092-1097.
- The PHQ-9 and GAD-7 are in the public domain. No permission is required to
  reproduce, translate, display, or distribute.

Brain-fact cards cite their sources inline on each card.

---

## Deliberate non-features

MindPulse does **not** implement any diagnostic algorithm (no PHQ-9 provisional-MDD
rule, no DSM criteria logic, no PHQ-8 variant), does not interpret scores with the
AI, does not give medication or treatment advice, and does not collect identifying
details. These are product decisions, not gaps: MindPulse screens and educates.
