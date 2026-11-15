## Prompt D — Safety Gate & Crisis Dialog Specification

### 0. Relationship to Prompts A, B, and C

This prompt supplements the MindPulse master development prompt (Prompt A), the instruments specification (Prompt B), and the companion specification (Prompt C).

- **Override:** Where Prompt A §S1–S2 gives a high-level outline of crisis handling, **this prompt is authoritative** on everything in `safety.py`, `resources.py`, and the crisis dialog. If the two conflict, follow this prompt.
- **Standing rules from all prompts still hold:** functional style, frozen dataclasses, short pure functions with docstrings and type hints, no classes except frozen dataclasses, Tkinter only, no login, deterministic crisis handling that never depends on an LLM.

**Deliverables from this prompt, in order:**
1. `resources.py` — structured helpline data.
2. `safety.py` — the pure safety gate.
3. `test_safety.py` and `test_resources.py`.
4. `ui/dialogs.py` — the crisis dialog and its wiring rules.

**Build order matters absolutely:** `safety.py` and its tests must be complete and passing **before** any UI screen, any screener flow, and before `ai_companion.py` is allowed to call it. If `ai_companion.py` is already written, verify its crisis short-circuit passes against the final `safety.py` before continuing.

---

### 1. Design principles

1. **Deterministic only.** Crisis detection is plain string and integer logic. No fuzzy matching, no embeddings, no regex engines with lookaround tricks, no AI. A correct answer must be reproducible from unit tests alone.
2. **Fail safe toward help.** When in doubt, show helplines. A false positive costs the user one screen of warm text; a false negative can cost a life. Tune thresholds accordingly and document any judgment call in a comment.
3. **Code before content.** The safety gate runs *before* storage, *before* the AI, and *before* the result screen. Nothing renders between a risky answer and the resources panel except the crisis dialog itself.
4. **One source of truth.** Helpline text, phrase lists, and dialog copy are constants — defined once, tested by literal equality, never generated, never paraphrased by the model.
5. **Everything pure.** All detection and lookup functions take data in and return data out. The only impure parts are the dialog's Tkinter rendering and one `webbrowser`/`os` call to launch `tel:`/`sms:` links.

---

### 2. Deliverable 1 — `resources.py` (structured helpline data)

No logic. Defines a frozen tuple of `CrisisResource` records, each with:

| Field | Type | Meaning |
|---|---|---|
| `id` | `str` | Stable key, e.g. `988_lifeline` |
| `name` | `str` | Display name, verbatim from §2.1 |
| `action_text` | `str` | The instruction shown to the user, verbatim |
| `phone` | `str \| None` | Digits in a form suitable for `tel:` links (may be short codes like `988`) |
| `sms_text` | `str \| None` | Body for an `sms:` link, e.g. `HOME` |
| `url` | `str \| None` | Web link if no direct dial/SMS |
| `region` | `str` | e.g. `US`, `International`, `EU` |
| `display_order` | `int` | Sort key; lower displays first |

#### 2.1 Canonical resource list (verbatim strings, exact order)

| # | `name` | `action_text` |
|---|---|---|
| 1 | `988 Suicide & Crisis Lifeline` | `Call or text 988 (US)` |
| 2 | `Crisis Text Line` | `Text HOME to 741741 (US)` |
| 3 | `Find A Helpline` | `findahelpline.com for help outside the US` |
| 4 | `Emergency services` | `Call 911 (US) / 112 (EU) if you are in immediate danger` |

- Resource 1: `phone = "988"`, no SMS body needed (the short code accepts both).
- Resource 2: `phone = "741741"`, `sms_text = "HOME"`.
- Resource 3: `url = "https://findahelpline.com"`, no phone.
- Resource 4: `phone = "911"` (US), with the action text covering 112 for EU.

Provide one pure lookup function: `resources_in_display_order() -> tuple[CrisisResource, ...]` returning the tuple sorted by `display_order`. If a future region pack is added, it must extend this tuple — never hard-code helplines anywhere else in the codebase.

---

### 3. Deliverable 2 — `safety.py` (the gate)

#### 3.1 Constants

**`CRISIS_PHRASES`** — an immutable frozenset of lowercase strings, matched in user-entered text (journal, chat, questionnaire free text). Initial contents:

```text
kill myself
end my life
suicide
self harm
self-harm
hurt myself
hurt yourself
want to die
wanna die
no reason to live
better off dead
overdose
cut myself
end it all
```

Keep the list in this one constant, easily extended via config or a future settings screen. Do not scatter phrases across modules.

**`SELF_HARM_INDICATOR`** — reserved for PHQ-9 item 9, described in §3.3.

#### 3.2 Pure functions (contracts)

| Function | Contract |
|---|---|
| `normalize_text(text) -> str` | Lowercase, strip outer whitespace, collapse internal runs of whitespace to single spaces. No other transformation — do not remove punctuation, do not stem, do not autocorrect. Determinism and debuggability beat cleverness here. |
| `contains_crisis_phrase(text) -> bool` | True if any phrase in `CRISIS_PHRASES` appears in `normalize_text(text)` as a **whole-phrase match at word boundaries**. A phrase must not match inside a longer word (e.g. `suicide` must not match `suicided`? — no: `suicide` as a substring of `suicides` **should** match; but `hurt` alone is not a phrase, `hurt myself` is). Implement boundary checking as simple padding with spaces on both sides of the normalized text and the phrase (`" " + phrase + " " in " " + normalized + " "`), which is pure, fast, and testable without regex. |
| `phq9_item9_risk(answers) -> bool` | Given the ordered PHQ-9 answer sequence (length 9, weights 0–3), return True iff the weight at item index 8 (item 9) is greater than 0. Reuse Prompt B's validation: wrong length or out-of-range raises `ValueError`. |
| `is_crisis_response_required(screening_answers, journal_text, chat_text) -> bool` | The single entry point. Returns True if **any** of: `phq9_item9_risk(screening_answers)` (when a non-empty sequence is provided), `contains_crisis_phrase(journal_text)`, or `contains_crisis_phrase(chat_text)`. Empty or blank inputs never trigger. An empty screening sequence means "not taken" and must **not** trigger. |
| `risk_sources(screening_answers, journal_text, chat_text) -> tuple[str, ...]` | Diagnostic helper returning the sorted names of what fired (e.g. `("phq9_item9", "journal_phrase")`), for logging and unit tests. Never surfaced to the user. |

#### 3.3 Ordering guarantee (must hold at every call site)

1. User submits an answer or message.
2. **Run `is_crisis_response_required` before anything else** — before scoring is displayed, before SQLite writes of the risky content (write the row if you like, but the *UI* must not linger on it), before any API call.
3. If True → show the crisis dialog (§4) and, per Prompt C §3.3, the companion returns `CRISIS_REPLY` with **no network request**.
4. Only if False → continue to scoring, storage, result screen, or the AI.

This order is a testable property: instrument tests must prove the gate fires before result-screen constants would be chosen.

---

### 4. Deliverable 3 — the crisis dialog (`ui/dialogs.py`)

A modal `tk.Toplevel` that takes focus. Its content is **fixed human text plus helplines** — no AI, no tips, no coping advice, no score, no severity.

#### 4.1 Verbatim copy (single source of truth — define as constants, test by literal equality)

- **Title:** `You matter, and help is available right now`
- **Body (warm, brief, non-clinical):** `Whatever you're feeling right now, you don't have to face it alone. People are ready to listen and help — right now, any time of day or night.`
- **Resource list:** rendered from `resources.py`, each line as `"{name} — {action_text}"` in display order.
- **If risk came from PHQ-9 item 9** (the dialog may receive a `risk_sources` tuple), append exactly this sentence: `Your questionnaire answers included thoughts of self-harm or of being better off dead. You deserve support from a real person right now.`
- **Buttons:**
  - `I'm safe right now` — closes the dialog. After closing, a **persistent help banner** appears at the top of every screen for the rest of the session, reading: `Need support? "Get help now" is always here.` with a `Get help now` button.
  - `Call or text 988` — launches `tel:988` via `webbrowser`/`os` where the platform supports it; if launching fails, show the number in large type with the copy: `Please call or text 988 now.` Never block on launch failure.
  - `Find help in my country` — opens `https://findahelpline.com` in the default browser.

#### 4.2 Dialog behavior rules

1. **Modal and foreground** — grab focus, disable the parent window's input until dismissed. It is the only thing on screen the user must acknowledge.
2. **No close-on-Escape, no X-button without acknowledgment** — the window manager's close maps to `I'm safe right now`, but the persistent banner then appears. The user can never dismiss help without leaving a way back to it.
3. **Keyboard accessible** — Tab moves between the three buttons; Enter activates the focused button. Font ≥ 12pt, high-contrast palette.
4. **Always available afterward** — the global `Get help now` button (Prompt A F6) opens the same dialog with an empty `risk_sources`, so its copy omits the PHQ-9 sentence.
5. **No data collection** — the dialog asks no questions, offers no chat, stores nothing.

---

### 5. Testing requirements

`test_safety.py` — pure functions only, no Tkinter:

1. **Each phrase matches** — every string in `CRISIS_PHRASES` triggers `contains_crisis_phrase` in a sentence wrapper and as the entire input.
2. **Near-misses do not match** — e.g. `I killed it in that game`, `this book has a suicide-related subplot title` style false-positive probes as documented fixtures, `hurt` alone, empty string, whitespace-only string. Document each fixture with a comment stating why it is or isn't a match.
3. **Case and whitespace** — `Hurt MySelf`, `want   to die`, and surrounding punctuation (`"want to die."`) still match after `normalize_text`.
4. **PHQ-9 item 9** — weight 1 with all others 0 → True; all zeros → False; wrong length or weight 4 → `ValueError`.
5. **Gate composition** — each trigger alone suffices; all empty inputs → False; empty screening tuple means "not taken" and does not trigger.
6. **Ordering property** — a test that exercises the composite flow (fake dialog recorder + fake `open_url` transport) and asserts the dialog is invoked and the transport is not, when crisis text is present.

`test_resources.py` — all four resources present; `display_order` values are unique and sorted ascending; each has either a phone or a URL; `sms_text` present only on the Crisis Text Line record; string fields match the §2.1 canonical text exactly.

`test_safety.py` also asserts `CRISIS_PHRASES` is a frozenset of lowercase strings with no duplicates and no empty members.

---

### 6. Explicit non-goals (do not implement)

- No sentiment analysis, no risk scoring, no "severity of crisis" levels. It is binary: show help, or don't.
- No LLM involvement in any detection or dialog path — including "just to be more helpful." If the model is ever asked to produce crisis copy at runtime, that is a defect.
- No localization files yet, but keep strings in constants so a future translation pass touches one module.
- No logging of the triggering text. If you log at all, log only `risk_sources` and a timestamp.

---

### 7. Build order for this prompt

1. `resources.py` (§2) + `test_resources.py`, passing.
2. `safety.py` constants and pure functions (§3.1–§3.2) + `test_safety.py`, passing — this must land before any UI.
3. Crisis dialog constants and behavior (§4) + any dialog tests (headless where possible; at minimum, test the copy constants).
4. Verify integration: run the composite ordering test (§5.6) and re-run Prompt C's crisis short-circuit test against the finished `safety.py`.

Report each step before moving on. Prompt B governs all instrument strings; Prompt C governs the companion; **this prompt governs all safety strings and behavior.**
