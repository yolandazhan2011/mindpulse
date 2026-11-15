"""Scoring facade and result-screen copy.

Instrument totals and severity bands live in :mod:`mindpulse.instruments` (Prompt B
requires them there, and they are re-exported here so callers have one scoring
import). This module owns the *display* layer of a result: the title, score line,
mandatory disclaimer, next-step line, and per-band explanation. Those strings are
fixed: never generated, never rewritten by the AI, never band-specific advice.
"""

from __future__ import annotations

from collections.abc import Sequence

from .instruments import (  # noqa: F401  (re-exported scoring API)
    IMPAIRMENT_OPTIONS,
    IMPAIRMENT_UNANSWERED,
    INSTRUMENTS,
    RESPONSE_OPTIONS,
    content_checksum,
    get_instrument,
    risk_flag_for,
    score_gad7,
    score_instrument,
    score_phq9,
    severity_for_total,
    validate_answers,
)
from .models import Instrument, Screening, Severity
from .safety import contains_crisis_phrase

#: Title line: ``Your {instrument display name} result``.
RESULT_TITLE_TEMPLATE = "Your {display_name} result"

#: Score line: ``Score: {total} out of {max_total} — {severity human label}``.
RESULT_SCORE_TEMPLATE = "Score: {total} out of {max_total} — {severity_label}"

#: Mandatory disclaimer. Always shown in full, never collapsed, never a tooltip.
RESULT_DISCLAIMER = (
    "This is a screening tool, not a diagnosis. Only a qualified clinician can diagnose "
    "a mental health condition. If you are struggling, please talk to a doctor, "
    "counselor, or a trusted adult."
)

#: Next-step line. Identical for every severity band - no band-specific advice.
RESULT_NEXT_STEP = (
    "Whatever your score, it is one snapshot of how you have felt over the past 2 weeks. "
    "Consider sharing this result with a doctor or counselor. If anything felt urgent "
    'while answering, please use the "Get help now" button.'
)

#: Shown above the score when the risk flag is set (Prompt B §7.4).
RISK_RESULT_BANNER = (
    "Your answers included thoughts of self-harm or of being better off dead. You deserve "
    'support from a real person right now. The "Get help now" button opens people who want '
    "to help."
)

#: One fixed sentence per severity band, used verbatim.
BAND_EXPLANATIONS: dict[Severity, str] = {
    Severity.MINIMAL: "Your answers suggest minimal symptoms right now.",
    Severity.MILD: "Your answers suggest mild symptoms right now.",
    Severity.MODERATE: "Your answers suggest moderate symptoms right now.",
    Severity.MODERATELY_SEVERE: "Your answers suggest moderately severe symptoms right now.",
    Severity.SEVERE: (
        "Your answers suggest severe symptoms right now. It is especially important to "
        "talk with a doctor or counselor soon."
    ),
}

#: Label of the optional free-text box on the questionnaire.
QUESTIONNAIRE_FREE_TEXT_PLACEHOLDER = "Anything else you want to note? (optional)"


def format_result_title(instrument_id: Instrument) -> str:
    """Return the result screen title, e.g. ``"Your PHQ-9 result"``."""
    return RESULT_TITLE_TEMPLATE.format(display_name=get_instrument(instrument_id).display_name)


def format_score_line(instrument_id: Instrument, total: int) -> str:
    """Return the score line, e.g. ``"Score: 12 out of 27 — Moderate"``.

    Raises ``ValueError`` for a total outside the instrument's range.
    """
    spec = get_instrument(instrument_id)
    severity = severity_for_total(instrument_id, total)
    return RESULT_SCORE_TEMPLATE.format(
        total=total,
        max_total=spec.max_total,
        severity_label=severity.label,
    )


def band_explanation(severity: Severity) -> str:
    """Return the fixed one-sentence explanation for a severity band."""
    try:
        return BAND_EXPLANATIONS[Severity(severity)]
    except KeyError as error:
        raise ValueError(f"No explanation for severity {severity!r}") from error


def assess_answers(
    instrument_id: Instrument,
    answers: Sequence[int],
    free_text: str = "",
) -> tuple[int, Severity, bool]:
    """Return ``(total, severity, risk_flag)`` for a submitted questionnaire.

    Pure: validates the answers, sums them, maps the total to a band, and sets the
    risk flag from PHQ-9 item 9 or from crisis language in the optional free text.
    The caller must run the crisis gate on the returned flag *before* rendering any
    result (Prompt D §3.3).
    """
    total = score_instrument(instrument_id, answers)
    severity = severity_for_total(instrument_id, total)
    item_risk = risk_flag_for(instrument_id, answers)
    risk = item_risk or contains_crisis_phrase(free_text)
    return total, severity, risk


def build_screening(
    instrument_id: Instrument,
    answers: Sequence[int],
    created_at: str,
    *,
    impairment: str | None = None,
    free_text: str = "",
) -> Screening:
    """Return a :class:`Screening` record ready for storage.

    ``impairment`` is recorded but never scored. The content checksum of the
    instrument's canonical strings is attached so future wording changes can be
    detected when old rows are read back.
    """
    validated = validate_answers(instrument_id, answers)
    total, severity, risk = assess_answers(instrument_id, validated, free_text)
    return Screening(
        created_at=created_at,
        instrument=Instrument(instrument_id),
        answers=validated,
        total=total,
        severity=severity,
        risk_flag=risk,
        impairment=impairment,
        content_checksum=content_checksum(instrument_id),
    )


def result_lines(instrument_id: Instrument, screening: Screening) -> tuple[str, ...]:
    """Return the result screen's body lines, in display order.

    Order: optional risk banner, title, score line, band explanation, disclaimer,
    next step. The disclaimer is always present and always before the next step.
    """
    head = (RISK_RESULT_BANNER,) if screening.risk_flag else ()
    return (
        *head,
        format_result_title(instrument_id),
        format_score_line(instrument_id, screening.total),
        band_explanation(screening.severity),
        RESULT_DISCLAIMER,
        RESULT_NEXT_STEP,
    )
