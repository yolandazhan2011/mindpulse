"""Deterministic crisis gate (Prompt D §3).

Everything here is pure string and integer logic: no regex, no fuzzy matching, no
model, no I/O. A correct answer must be reproducible from unit tests alone.

The gate fails safe toward help. A false positive costs the user one screen of
warm text; a false negative can cost a life, so phrase matching is generous about
case and whitespace but strict about word boundaries.
"""

from __future__ import annotations

from collections.abc import Sequence

from .instruments import Instrument, phq9_risk_flag, validate_answers

#: Lowercase phrases that trigger the crisis gate in any user-entered text.
#: Extend this constant (a future settings screen writes to it); never scatter
#: phrases across modules.
CRISIS_PHRASES: frozenset[str] = frozenset(
    {
        "kill myself",
        "end my life",
        "suicide",
        "self harm",
        "self-harm",
        "hurt myself",
        "hurt yourself",
        "want to die",
        "wanna die",
        "no reason to live",
        "better off dead",
        "overdose",
        "cut myself",
        "end it all",
    }
)

#: Name reported by :func:`risk_sources` when PHQ-9 item 9 scored above zero.
SELF_HARM_INDICATOR = "phq9_item9"
#: Name reported when crisis language appeared in a journal entry.
JOURNAL_PHRASE_SOURCE = "journal_phrase"
#: Name reported when crisis language appeared in a chat message.
CHAT_PHRASE_SOURCE = "chat_phrase"


#: Characters that keep a word intact when the boundary text is built. A hyphenated
#: compound ("suicide-related") is one word, so it does not match "suicide".
_WORD_CONTINUATION_CHARS = frozenset({"-", "'", "\u2019"})
#: Suffixes allowed after a phrase's final word, so "suicides" matches "suicide".
_PHRASE_SUFFIXES = ("", "s", "es")


def normalize_text(text: str) -> str:
    """Lowercase, strip, and collapse internal whitespace runs to single spaces.

    Nothing else is transformed: punctuation is kept (boundary handling happens in
    :func:`boundary_text`) and no stemming or autocorrection happens.
    """
    return " ".join(text.lower().split())


def boundary_text(normalized: str) -> str:
    """Return ``normalized`` with separating punctuation replaced by spaces.

    Word-continuation characters (hyphens, apostrophes) are kept, so hyphenated
    compounds stay single words. The result never contains a double space, which
    lets :func:`contains_crisis_phrase` test boundaries by padding with one space
    on each side - the simple, regex-free rule Prompt D asks for.
    """
    separated = "".join(
        char if char.isalnum() or char in _WORD_CONTINUATION_CHARS else " " for char in normalized
    )
    return " ".join(separated.split())


def contains_crisis_phrase(text: str) -> bool:
    """Return True when any phrase in :data:`CRISIS_PHRASES` occurs in ``text``.

    Matching is a whole-phrase match at word boundaries. Text and phrase are both
    padded with single spaces, so ``hurt myself`` matches while ``hurt`` alone (not
    a phrase) and ``suicide`` inside ``suicide-related`` do not. Trailing
    punctuation does not break a match (``"want to die."`` matches) and a plural
    suffix on the phrase's last word still counts (``"suicides"`` matches
    ``suicide``).
    """
    if not text or not text.strip():
        return False
    normalized = normalize_text(text)
    if not normalized:
        return False
    boundary = boundary_text(normalized)
    if not boundary:
        return False
    padded = f" {boundary} "
    return any(
        f" {phrase}{suffix} " in padded for phrase in CRISIS_PHRASES for suffix in _PHRASE_SUFFIXES
    )


def phq9_item9_risk(answers: Sequence[int]) -> bool:
    """Return True when PHQ-9 item 9 (self-harm thoughts) is scored above zero.

    ``answers`` must hold nine integers in ``0..3``; raises ``ValueError`` otherwise.
    """
    return phq9_risk_flag(answers)


def is_crisis_response_required(
    screening_answers: Sequence[int],
    journal_text: str,
    chat_text: str,
) -> bool:
    """Return True when the crisis gate must fire for the given inputs.

    Fires when PHQ-9 item 9 scored above zero, or when a crisis phrase appears in
    ``journal_text`` or ``chat_text``. An empty ``screening_answers`` sequence means
    "no PHQ-9 taken" and never triggers; blank text never triggers.
    """
    return bool(risk_sources(screening_answers, journal_text, chat_text))


def risk_sources(
    screening_answers: Sequence[int],
    journal_text: str,
    chat_text: str,
) -> tuple[str, ...]:
    """Return the sorted names of every trigger that fired (never shown to the user).

    Example: ``("journal_phrase", "phq9_item9")``. Used for logging and tests only.
    """
    sources: list[str] = []
    if screening_answers and phq9_item9_risk(screening_answers):
        sources.append(SELF_HARM_INDICATOR)
    if contains_crisis_phrase(journal_text):
        sources.append(JOURNAL_PHRASE_SOURCE)
    if contains_crisis_phrase(chat_text):
        sources.append(CHAT_PHRASE_SOURCE)
    return tuple(sorted(sources))


def screening_risk_flag(
    instrument_id: Instrument,
    answers: Sequence[int],
    free_text: str = "",
) -> bool:
    """Return the stored risk flag for a submitted screening.

    TRUTH: PHQ-9 item 9 above zero OR a crisis phrase in the optional free text.
    GAD-7 has no self-harm item, so only the keyword gate can flag it.
    """
    if instrument_id == Instrument.PHQ9:
        item_risk = phq9_risk_flag(answers)
    else:
        # GAD-7 has no self-harm item: validate the answers, then rely on keywords.
        validate_answers(instrument_id, answers)
        item_risk = False
    return item_risk or contains_crisis_phrase(free_text)


def crisis_precedes_any_response(*, gate_open: bool) -> bool:
    """Return True when the crisis dialog must appear before any other output.

    A one-line, testable statement of the ordering rule (Prompt D §3.3): when the
    gate is open, nothing renders between the risky input and the resources panel.
    """
    return gate_open
