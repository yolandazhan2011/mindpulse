# Daily Brain Fact Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Brain Facts tab's ten-card scroll with a single card that changes daily.

**Architecture:** A pure `fact_for_date(day) -> BrainFact` in `mindpulse/brain_facts.py` maps a calendar date to one card by modulo over the curated tuple. `mindpulse/ui/brain_facts_view.py` renders that one card, no canvas and no scrollbar, using the existing `charts.utc_today()` as its only time source. Card bodies are rewritten at about half their current length; the in-card citation and hedge clauses survive the trim.

**Tech Stack:** Python 3.15, Tkinter/ttk, `unittest` (no pytest installed).

**Spec:** `docs/superpowers/specs/2026-11-15-daily-brain-fact-design.md`

## Global Constraints

- `brain_facts.py` stays pure: no I/O, no `datetime.now()` in it.
- Copy stays non-prescriptive: no "you should", "you must", "try to", "make sure you".
- Every card keeps a non-empty title, body, and source; titles stay unique; the
  required topics (amygdala, prefrontal, hippocampus, sleep, exercise, hpa) stay in titles.
- Trimmed bodies: 25–45 words each, about half of today's 60–90.
- Frozen dataclasses, type hints everywhere, docstrings on public functions.
- Test command: `python3 -m unittest discover -s tests -q` (227 tests green at start).

## Review Focus

- A date at the edge of the cycle (e.g. the day the modulo wraps) must not skip or
  repeat a card, and `fact_for_date` must be total for any `date`, including year 1
  and far-future dates.
- The panel must render when `facts_in_display_order()` order changes: it asks for
  one card, never indexes the tuple itself.
- Trimming must not quietly drop a hedge ("contested", "in rodents",
  "correlational") or a citation — that would make a cautious card read as a claim.
- The view must not crash on a zero-length body or missing source (the dataclass
  permits them); labels must tolerate an empty string.
- Removing the scroll canvas must leave no dead code (`_bind_scroll`, scroll
  bindings) and no stray `tk.Canvas` import usage.

---

### Task 1: Pure daily selection

**Files:**
- Modify: `mindpulse/brain_facts.py` (add `fact_for_date`, import `date`)
- Test: `tests/test_brain_facts.py` (new `DailyFactTests` class)

**Interfaces:**
- Produces: `fact_for_date(day: datetime.date) -> BrainFact` — same-day stable,
  steps one card per day, repeats after `fact_count()` days.

- [ ] **Step 1: Write the failing tests**

```python
class DailyFactTests(unittest.TestCase):
    def test_same_day_always_returns_the_same_card(self) -> None:
        day = date(2024, 5, 17)
        self.assertEqual(fact_for_date(day), fact_for_date(date(2024, 5, 17)))

    def test_consecutive_days_return_different_cards(self) -> None:
        day = date(2024, 5, 17)
        self.assertNotEqual(fact_for_date(day), fact_for_date(day + timedelta(days=1)))

    def test_one_cycle_shows_every_card_once(self) -> None:
        start = date(2024, 5, 17)
        shown = [fact_for_date(start + timedelta(days=n)) for n in range(fact_count())]
        self.assertEqual(len(set(shown)), fact_count())

    def test_cycle_repeats_after_fact_count_days(self) -> None:
        start = date(2024, 5, 17)
        self.assertEqual(fact_for_date(start), fact_for_date(start + timedelta(days=fact_count())))

    def test_returns_one_of_the_curated_cards(self) -> None:
        self.assertIn(fact_for_date(date(2024, 5, 17)), BRAIN_FACTS)

    def test_accepts_any_date(self) -> None:
        for day in (date(1, 1, 1), date(9999, 12, 31)):
            with self.subTest(day=day):
                self.assertIn(fact_for_date(day), BRAIN_FACTS)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_brain_facts -q`
Expected: FAIL — `ImportError: cannot import name 'fact_for_date'`.

- [ ] **Step 3: Implement `fact_for_date`**

Add `from datetime import date` and, below `facts_in_display_order`:

```python
def fact_for_date(day: date) -> BrainFact:
    """Return the card shown on ``day``.

    The rotation is deterministic: each day steps to the next card in the curated
    order and the sequence repeats every ``fact_count()`` days, so the same date
    always shows the same card and every card comes up in turn.
    """
    return BRAIN_FACTS[day.toordinal() % len(BRAIN_FACTS)]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_brain_facts -q`
Expected: PASS (existing `BrainFactTests` still green).

---

### Task 2: Trim the card copy

**Files:**
- Modify: `mindpulse/brain_facts.py` (all ten `body=` strings, module docstring)
- Test: `tests/test_brain_facts.py` (word-budget test renamed and re-bounded)

**Interfaces:**
- Consumes: nothing new.
- Produces: the same `BRAIN_FACTS` tuple, same titles and sources, bodies now 25–45 words.

- [ ] **Step 1: Re-bound the failing word-budget test**

Replace `test_each_card_is_sixty_to_ninety_words` with:

```python
    def test_each_card_is_twenty_five_to_fifty_words(self) -> None:
        for fact in BRAIN_FACTS:
            words = len(fact.body.split())
            with self.subTest(title=fact.title):
                self.assertGreaterEqual(words, 25)
                self.assertLessEqual(words, 50)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m unittest tests.test_brain_facts -q`
Expected: FAIL on every card — bodies are still 60–90 words.

- [ ] **Step 3: Rewrite the ten bodies at about half length**

Trim the least essential explanatory clause from each body, keeping the citation
implied by `source=`, every hedge ("correlational", "in rodents", "contested",
"most direct evidence"), and the non-prescriptive voice. Reference lengths:
amygdala ~42, prefrontal ~43, hippocampus ~42, glymphatic ~42, exercise ~42,
serotonin/dopamine ~44, HPA axis ~44, affect labelling ~40, sleep and memory ~43,
adult neurogenesis ~46 words. Update the module docstring to say the cards are
shown one per day.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_brain_facts -q`
Expected: PASS, including the citation, non-prescriptive, and topic tests.

---

### Task 3: Render one card

**Files:**
- Modify: `mindpulse/ui/brain_facts_view.py` (full rewrite, ~60 lines)
- Modify: `README.md` (Brain facts row in Screens table; test table row)
- Test: `tests/test_brain_facts.py` (no UI test exists; Task 4 verifies by import)

**Interfaces:**
- Consumes: `fact_for_date` (Task 1), `charts.utc_today()`, `config.FONT_*`,
  `config.PAD*`, `config.COLOR_TEXT_MUTED`.
- Produces: `build(parent: tk.Misc, _state: dict[str, Any]) -> ttk.Frame`, matching
  the `VIEW_BUILDERS` signature in `mindpulse/ui/app.py`.

- [ ] **Step 1: Verify the view fails before the change**

Run: `python3 -c "import mindpulse.ui.brain_facts_view as v; print(hasattr(v, 'HEADING'))"`
Expected: prints `True` today; after the rewrite it must still import cleanly, and
`python3 -m unittest discover -s tests -q` must stay green. A failing import of
`fact_for_date` in the new view is the red signal to watch for in Step 2.

- [ ] **Step 2: Rewrite the panel**

Replace the canvas/scrollbar/card-list with: heading label, intro label, one
bordered card (`fact_for_date(charts.utc_today())`) holding title, body, and
muted source labels, then a muted one-line footnote ("A different fact appears
here tomorrow."). Use `grid` on the outer frame with `columnconfigure(0, weight=1)`
and a trailing weighted spacer row so content sits at the top. Delete `_bind_scroll`
and the `tk.Canvas` usage.

- [ ] **Step 3: Update the README**

Screens table: describe the panel as one cited card that rotates daily, with the
topic list kept. Tests table: describe the word budget and the daily rotation test.

- [ ] **Step 4: Verify**

Run: `python3 -m unittest discover -s tests -q`
Expected: PASS, 233+ tests, no import errors.

---

### Task 4: Whole-suite and behaviour check

**Files:**
- Read: `mindpulse/brain_facts.py`, `mindpulse/ui/brain_facts_view.py`

- [ ] **Step 1: Run the full suite**

Run: `python3 -m unittest discover -s tests -q`
Expected: PASS, no warnings.

- [ ] **Step 2: Prove the rotation across ten days**

Run:

```bash
python3 -c "
from datetime import date, timedelta
from mindpulse.brain_facts import fact_count, fact_for_date
start = date.today()
for n in range(fact_count()):
    d = start + timedelta(days=n)
    print(d, fact_for_date(d).title)
"
```

Expected: ten distinct titles, one per day, in curated order.

- [ ] **Step 3: Prove the panel builds headlessly**

Run:

```bash
python3 -c "
import tkinter as tk
from mindpulse.ui.brain_facts_view import build
root = tk.Tk()
root.withdraw()
frame = build(root, {})
print(len(frame.winfo_children()), 'widgets')
root.destroy()
"
```

Expected: prints a widget count with no traceback (skip if no display; note it).

- [ ] **Step 4: Lint**

Run: `python3 -m ruff check mindpulse tests` (ruff cache present in repo)
Expected: clean; report any pre-existing finding separately.
