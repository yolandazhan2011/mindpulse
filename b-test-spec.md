## Prompt B — Screening Instruments Specification (PHQ-9 & GAD-7)

### 0. Relationship to the master prompt

This prompt supplements the MindPulse master development prompt and **overrides it where the two conflict on any instrument-related string**. All other constraints from the master prompt (functional style, frozen dataclasses, short pure functions, Tkinter Canvas only, SQLite, no login, safety gate) remain in force.

**Deliverables from this prompt:** `instruments.py` (data + pure functions), `test_instruments.py`, and the string constants the screener UI must display. Build these first, before any UI code.

### 1. Content-fidelity rules (non-negotiable)

1. The PHQ-9 and GAD-7 are **public-domain screening instruments** (developed by Spitzer, Kroenke, Williams and colleagues). No permission is required to reproduce, translate, display, or distribute them. **Attribution is required anyway** — see §8.
2. The item wording, item order, response-option labels, scoring weights, recall window ("last 2 weeks"), and severity cutoffs given in this prompt are **canonical**. Implement them **verbatim**:
   - Do **not** paraphrase, shorten, "improve", localize, or modernize any string.
   - Do **not** reorder items. Item numbers are part of the instrument.
   - Do **not** change the recall window, the response scale, or any cutoff value.
   - Do **not** invent extra items, examples, or clarifying parentheticals.
3. Punctuation is part of the string. Store and compare exact strings (see §6). Where the literature shows punctuation variants, the strings in this prompt are the ones you must use — one canonical string per item, used consistently everywhere.
4. **Do not implement any diagnostic algorithm.** In particular: do not implement the PHQ-9 "provisional major depressive disorder" algorithm (5+ items at ≥2, with item 1 or 2 ≥2), do not implement DSM criteria logic, and do not implement the PHQ-8 variant. MindPulse **screens and educates; it does not diagnose**. If asked later to add such a feature, refuse with that reason.
5. The displayed strings in the UI are the same constants used in tests. No duplicated text literals anywhere in the codebase.

### 2. Canonical content — instrument A: PHQ-9

**Instrument id:** `PHQ9`
**Recall window:** the past 2 weeks
**Item count:** 9 · **Per-item score range:** 0–3 · **Total score range:** $0\text{–}27$
**Attribution short form:** `PHQ-9 modified from PRIME-MD. Developed by Drs. Robert L. Spitzer, Janet B.W. Williams, and Kurt Kroenke.`

**A.0 — Instruction stem (shown once at the top of the questionnaire and repeated in condensed form on each item screen):**

> Over the last 2 weeks, how often have you been bothered by any of the following problems?

**A.1 — Response options (identical for all 9 items; show label text to the user, keep the weight internal):**

| Weight | Label |
|---:|---|
| 0 | Not at all |
| 1 | Several days |
| 2 | More than half the days |
| 3 | Nearly every day |

**A.2 — Items (verbatim, in order):**

| # | Item text | Weight of every answer for this item |
|---:|---|---:|
| 1 | Little interest or pleasure in doing things | 0–3 |
| 2 | Feeling down, depressed, or hopeless | 0–3 |
| 3 | Trouble falling or staying asleep, or sleeping too much | 0–3 |
| 4 | Feeling tired or having little energy | 0–3 |
| 5 | Poor appetite or overeating | 0–3 |
| 6 | Feeling bad about yourself — or that you are a failure or have let yourself or your family down | 0–3 |
| 7 | Trouble concentrating on things, such as reading the newspaper or watching television | 0–3 |
| 8 | Moving or speaking so slowly that other people could have noticed; or the opposite — being so fidgety or restless that you have been moving around a lot more than usual | 0–3 |
| 9 | Thoughts that you would be better off dead or of hurting yourself in some way | 0–3 |

**A.3 — Scoring:** `total = sum of the 9 item weights`, computed by a pure function that takes an ordered sequence of 9 integers in $0\text{–}3$ and returns an integer in $0\text{–}27$. Reject out-of-range or wrong-length input with `ValueError` before the sum.

**A.4 — Severity bands (exact boundaries):**

| Total | Severity enum | Human label |
|---:|---|---|
| 0–4 | `MINIMAL` | Minimal |
| 5–9 | `MILD` | Mild |
| 10–14 | `MODERATE` | Moderate |
| 15–19 | `MODERATELY_SEVERE` | Moderately severe |
| 20–27 | `SEVERE` | Severe |

Boundary rule: a total of exactly 4 is `MINIMAL`; exactly 5 is `MILD`; exactly 10 is `MODERATE`; exactly 15 is `MODERATELY_SEVERE`; exactly 20 is `SEVERE`.

**A.5 — Risk rule (PHQ-9 only):** if the answer weight for **item 9** is greater than 0, set `risk_flag = 1` and trigger the crisis gate (§7). This rule is independent of the total score — a total of 3 with item 9 = 1 still triggers.

**A.6 — Functional-impairment follow-up (shown after item 9; recorded, NOT scored, not part of the total):**

> If you checked off any problems, how difficult have these problems made it for you to do your work, take care of things at home, or get along with other people?

| Stored value | Label |
|---|---|
| `not_difficult` | Not difficult at all |
| `somewhat_difficult` | Somewhat difficult |
| `very_difficult` | Very difficult |
| `extremely_difficult` | Extremely difficult |

This item is optional for the user and may be answered "Prefer not to say" (stored as `unanswered`, displayed as a fifth button). It is shown only if at least one scored item has weight > 0.

### 3. Canonical content — instrument B: GAD-7

**Instrument id:** `GAD7`
**Recall window:** the past 2 weeks
**Item count:** 7 · **Per-item score range:** 0–3 · **Total score range:** $0\text{–}21$
**Attribution short form:** `GAD-7 modified from PRIME-MD. Developed by Drs. Robert L. Spitzer, Janet B.W. Williams, Kurt Kroenke, and colleagues.`

**B.0 — Instruction stem:**

> Over the last 2 weeks, how often have you been bothered by the following problems?

Note: GAD-7's stem omits "any of" — this is intentional and canonical. Do not harmonize it with the PHQ-9 stem.

**B.1 — Response options:** identical to §A.1 (same four labels, same weights 0–3).

**B.2 — Items (verbatim, in order):**

| # | Item text | Weight of every answer for this item |
|---:|---|---:|
| 1 | Feeling nervous, anxious, or on edge | 0–3 |
| 2 | Not being able to stop or control worrying | 0–3 |
| 3 | Worrying too much about different things | 0–3 |
| 4 | Trouble relaxing | 0–3 |
| 5 | Being so restless that it is hard to sit still | 0–3 |
| 6 | Becoming easily annoyed or irritable | 0–3 |
| 7 | Feeling afraid as if something awful might happen | 0–3 |

**B.3 — Scoring:** `total = sum of the 7 item weights`, pure function, returns integer in $0\text{–}21$; same input validation as A.3.

**B.4 — Severity bands (exact boundaries):**

| Total | Severity enum | Human label |
|---:|---|---|
| 0–4 | `MINIMAL` | Minimal |
| 5–9 | `MILD` | Mild |
| 10–14 | `MODERATE` | Moderate |
| 15–21 | `SEVERE` | Severe |

**B.5 — Risk rule:** GAD-7 has **no** self-harm item. The risk flag for GAD-7 can only be set by the keyword gate on free text (§7), never by an item weight. Do not synthesize one.

**B.6 — Functional-impairment follow-up:** the **same** question and the same four labels as §A.6 (shared constant, defined once). Same display rule: only shown if any item weight > 0.

### 4. Instrument registry

Model both instruments in one place as an immutable registry (a frozen mapping from instrument id to a frozen record) containing, for each instrument: id, display name ("PHQ-9" / "GAD-7"), full name ("Patient Health Questionnaire-9" / "Generalized Anxiety Disorder-7"), attribution string, citation string (§8), instruction stem, ordered items (each with number and verbatim text), response-option tuples (weight, label), max total, severity-band table, impairment question constant, and a `has_risk_item` flag (True for PHQ-9, False for GAD-7). Any future instrument must be added by extending this registry, not by adding special cases to the UI.

### 5. Result-screen copy (strings to define now, used by the UI later)

Define these as constants; the AI may not rewrite them:

- **Title line:** `Your {instrument display name} result`
- **Score line:** `Score: {total} out of {max_total} — {severity human label}`
- **Mandatory disclaimer (always shown, never collapsed, never behind a tooltip):**
  > This is a screening tool, not a diagnosis. Only a qualified clinician can diagnose a mental health condition. If you are struggling, please talk to a doctor, counselor, or a trusted adult.
- **Next-step line (fixed, identical for all severity bands — do not generate band-specific advice):**
  > Whatever your score, it is one snapshot of how you have felt over the past 2 weeks. Consider sharing this result with a doctor or counselor. If anything felt urgent while answering, please use the "Get help now" button.
- **Band explanation (one fixed sentence per band, use exactly these):**
  - `MINIMAL` — `Your answers suggest minimal symptoms right now.`
  - `MILD` — `Your answers suggest mild symptoms right now.`
  - `MODERATE` — `Your answers suggest moderate symptoms right now.`
  - `MODERATELY_SEVERE` — `Your answers suggest moderately severe symptoms right now.`
  - `SEVERE` — `Your answers suggest severe symptoms right now. It is especially important to talk with a doctor or counselor soon.`

Do **not** add band-specific coping tips, do **not** add risk language such as "you are depressed", and do **not** let the AI rewrite these sentences.

### 6. Data-shape and encoding requirements

- Each item is an immutable record with at minimum: `instrument_id`, `item_number: int` (1-based, matches the canonical numbering), `text: str` (verbatim), `max_weight: int = 3`.
- Response options are a tuple of `(weight: int, label: str)` pairs, defined once per instrument (identical for both), and referenced — not copied.
- A screening submission is a frozen record: `instrument_id`, `created_at`, `answers: tuple[int, ...]` (length = item count, ordered by item number), `total: int`, `severity: Severity`, `risk_flag: bool`, `impairment: str | None`.
- Store answers in SQLite as the JSON array in item order (already in the master schema), and include a **schema version key** in `app_meta` so a future instrument revision can be detected. When validating rows read from the database, compare item text length or a per-instrument **content checksum** (a simple hash of the concatenated canonical strings) so that if a future version of the app changes wording, old rows are flagged rather than silently rescored.
- Strings are UTF-8 and must include the em dash characters exactly as given (e.g. item 6 and item 8 of PHQ-9 use "—"). Do not convert them to hyphens.

### 7. Safety interplay (instruments → crisis gate)

1. PHQ-9 item 9 weight > 0 ⇒ `risk_flag = 1` ⇒ the crisis gate in `safety.py` returns `True` ⇒ the S2 crisis dialog from the master prompt is shown **immediately after the questionnaire is submitted, before the result screen**.
2. The keyword gate in `safety.py` also runs on any free text the user typed (journal, chat, and an optional "anything else" box on the questionnaire — if you add such a box, its placeholder must be: `Anything else you want to note? (optional)`).
3. The crisis dialog contains **only** helplines and the fixed warm copy defined in the master prompt. No score, no severity, no explanation, no AI text.
4. When `risk_flag` is 1, the result screen additionally shows the "Get help now" button **above the fold** (before the score), with the fixed line:
   > Your answers included thoughts of self-harm or of being better off dead. You deserve support from a real person right now. The "Get help now" button opens people who want to help.
5. The AI companion must be blocked from running while `risk_flag` is 1 for the most recent screening, and it must **never** interpret, translate, or comment on PHQ-9/GAD-7 totals or severity bands. Its fixed refusal line (defined in `prompts.py`) is:
   > I can't interpret screening scores — I'm not a clinician. A doctor or counselor can walk through your result with you.

### 8. Attribution & citation strings (must appear in the About dialog and in the instruments module)

- `PHQ-9 modified from PRIME-MD. Developed by Drs. Robert L. Spitzer, Janet B.W. Williams, and Kurt Kroenke.`
- `GAD-7 modified from PRIME-MD. Developed by Drs. Robert L. Spitzer, Janet B.W. Williams, Kurt Kroenke, and colleagues.`
- `Kroenke K, Spitzer RL, Williams JBW. The PHQ-9: Validity of a Brief Depression Severity Measure. J Gen Intern Med. 2001;16(9):606-613.`
- `Spitzer RL, Kroenke K, Williams JBW, Löwe B. A brief measure for assessing generalized anxiety disorder: the GAD-7. Arch Intern Med. 2006;166(10):1092-1097.`
- `The PHQ-9 and GAD-7 are in the public domain. No permission is required to reproduce, translate, display, or distribute.`

### 9. UI presentation rules (for the screener flow)

1. **One item per screen.** Top: the instrument name and a progress label such as `Question 3 of 9`. Below: the instruction stem in smaller type, then the item number and verbatim item text in the largest type on the screen.
2. **Answer buttons** show the label text (§A.1) as the primary text. Do **not** display the numeric weights to the user; weights are internal.
3. **No default selection.** The Next button is disabled until an answer is chosen. Back is always enabled (except item 1) and preserves prior answers. Esc offers "Leave this questionnaire?" with choices `Keep going` / `Leave` — leaving keeps partial answers in memory but writes nothing to the database and sets no risk flag.
4. Text must wrap, never clip. On narrow windows, stack the four answer buttons vertically. Keyboard: arrow keys or `1`–`4` select an option (mapped to weights 0–3 in that order, since the labels are displayed in weight order), Enter advances.
5. The impairment question (§A.6/B.6) is shown on its own screen after the last item, with a `Prefer not to say` button, and is not required to finish.
6. After submission: run the scoring function, run the safety gate, persist, then show the result screen (§5) or the crisis dialog (§7.4) first if risk is flagged.

### 10. Testing requirements (`test_instruments.py`)

Cover at minimum:
- **String fidelity:** every item, stem, option label, attribution, and disclaimer string equals the canonical constant exactly (imported from one source of truth — no literals in tests).
- **Scoring:** all-zeros → 0; all-max → 27 / 21; a hand-computed mixed vector; rejection of length-8 or length-10 vectors and of any weight outside $0\text{–}3$ (`ValueError`).
- **Severity boundaries:** totals 4/5, 9/10, 14/15, 19/20 (PHQ-9) and 4/5, 9/10, 14/15 (GAD-7) each land in the expected band.
- **Risk:** item 9 = 1 with every other item 0 ⇒ `risk_flag` True; all items 0 ⇒ False; GAD-7 has no item that can set the risk flag.
- **Impairment item:** never affects the total; `unanswered` allowed.
- **Registry:** both instruments' item counts match (9 and 7); totals match max sums; `has_risk_item` is True only for PHQ9.

### 11. Build order for this prompt

1. `instruments.py` — canonical strings + registry + pure `score_*` and `severity_for_total` functions. Nothing else.
2. `test_instruments.py` — all of §10, passing.
3. Then and only then, the screener UI (§9) and the result-screen constants (§5), wired to `safety.py` per §7.

Report the module and its tests before continuing to UI.
