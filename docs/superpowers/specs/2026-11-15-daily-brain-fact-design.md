# Daily brain fact — design

## Intent and why

The Brain Facts tab currently lists all ten education cards in one long scroll.
The reader has to choose what to read and the panel reads like a reference dump.
Showing one card a day turns it into a small daily habit: nothing to pick, and a
reason to come back tomorrow.

## Goals

- The tab shows exactly one card: title, body, citation.
- The card changes once per day, and every card comes up in turn.
- Card bodies are about half their current length (was 60–90 words, now 25–45),
  so the single card is read at a glance.
- Which card is shown is decided by the calendar date alone — no stored state,
  no database writes, no randomness to re-seed.

## Non-goals

- No browsing, "next card", or "show all" control. One card, that is the point.
- No new cards, no new citations, no change to titles or sources.
- No persistence of what was shown before.

## Anti-goals

- A rotation that reshuffles whenever the app restarts, or that needs the user to
  have opened the app yesterday to keep its place.
- Trimming that drops the cautious hedging ("most human evidence is
  correlational", "in rodents", "contested") to save words.

## Constraints

- `brain_facts.py` stays pure: no I/O, no `datetime.now()` inside it.
- Frozen dataclasses, tuples, type hints, docstrings on public functions.
- Copy stays non-prescriptive (no "you should", "try to", "make sure you") and
  every card keeps its source line.
- Existing suite must stay green: 8–10 cards, unique titles, required topics,
  citations present, display order equal to the curated tuple.

## Approaches

1. **Date → index (picked).** `fact_for_date(day) -> BrainFact` returns
   `BRAIN_FACTS[day.toordinal() % len(BRAIN_FACTS)]`. Deterministic, stateless,
   testable with a fixed date, and it cycles through every card exactly once per
   ten days. The view asks the existing `charts.utc_today()` for today's date.
2. **Persist the rotation in `app_meta`.** Pick an unseen card at random each day
   and remember it. Gives a non-fixed order, but costs a schema round-trip and
   state for something a modulo already does, and it makes the panel depend on
   the database it does not otherwise touch. Rejected: more machinery, no gain.

## Decisions made

- Rotation is by UTC date, matching the timestamps stored elsewhere in the app.
- The tab keeps its heading, intro and its "not advice" framing; a muted
  one-line footnote says a different card appears tomorrow.
- Trimming keeps every citation and every hedge clause; the least essential
  explanatory clause in each body is the one that goes.

## Left to the builder

- Exact trimmed wording of the ten bodies, within 25–45 words each.
- Whether the footnote line is worth keeping once the panel is one card.
