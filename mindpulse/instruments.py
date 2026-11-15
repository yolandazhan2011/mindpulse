"""Canonical PHQ-9 and GAD-7 content, registry, and pure scoring functions.

Prompt B is authoritative for every string in this module. The item wording,
item order, response labels, recall window, and severity cutoffs are canonical:
do not paraphrase, reorder, or "improve" them. The PHQ-9 and GAD-7 are in the
public domain; attribution is included anyway (see ``ATTRIBUTIONS``).

MindPulse screens and educates. Nothing here implements a diagnostic algorithm.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from types import MappingProxyType

from .models import Instrument, InstrumentItem, InstrumentSpec, Severity, SeverityBandSpec

# ---------------------------------------------------------------------------
# Shared strings (defined once, referenced by both instruments)
# ---------------------------------------------------------------------------

#: Response scale for every item of both instruments: ``(weight, label)`` pairs.
RESPONSE_OPTIONS: tuple[tuple[int, str], ...] = (
    (0, "Not at all"),
    (1, "Several days"),
    (2, "More than half the days"),
    (3, "Nearly every day"),
)

#: Functional-impairment follow-up, shared by both instruments and never scored.
IMPAIRMENT_QUESTION = (
    "If you checked off any problems, how difficult have these problems made it for you "
    "to do your work, take care of things at home, or get along with other people?"
)

#: ``(stored value, label)`` pairs for the impairment follow-up.
IMPAIRMENT_OPTIONS: tuple[tuple[str, str], ...] = (
    ("not_difficult", "Not difficult at all"),
    ("somewhat_difficult", "Somewhat difficult"),
    ("very_difficult", "Very difficult"),
    ("extremely_difficult", "Extremely difficult"),
)

#: Stored value used when the user chooses not to answer the follow-up.
IMPAIRMENT_UNANSWERED = "unanswered"
#: Label of the optional fifth impairment button.
IMPAIRMENT_UNANSWERED_LABEL = "Prefer not to say"
#: Placeholder for the optional free-text box (canonical per Prompt B §7).
FREE_TEXT_PLACEHOLDER = "Anything else you want to note? (optional)"

#: Attribution and citation strings, shown in the About dialog and here.
ATTRIBUTIONS: tuple[str, ...] = (
    "PHQ-9 modified from PRIME-MD. Developed by Drs. Robert L. Spitzer, "
    "Janet B.W. Williams, and Kurt Kroenke.",
    "GAD-7 modified from PRIME-MD. Developed by Drs. Robert L. Spitzer, "
    "Janet B.W. Williams, Kurt Kroenke, and colleagues.",
)
CITATIONS: tuple[str, ...] = (
    "Kroenke K, Spitzer RL, Williams JBW. The PHQ-9: Validity of a Brief Depression "
    "Severity Measure. J Gen Intern Med. 2001;16(9):606-613.",
    "Spitzer RL, Kroenke K, Williams JBW, Löwe B. A brief measure for assessing "
    "generalized anxiety disorder: the GAD-7. Arch Intern Med. 2006;166(10):1092-1097.",
    "The PHQ-9 and GAD-7 are in the public domain. No permission is required to "
    "reproduce, translate, display, or distribute.",
)

#: Recall window shown to the user (both instruments).
RECALL_WINDOW_LABEL = "the past 2 weeks"

# ---------------------------------------------------------------------------
# PHQ-9
# ---------------------------------------------------------------------------

PHQ9_INSTRUCTION_STEM = (
    "Over the last 2 weeks, how often have you been bothered by any of the following problems?"
)

_PHQ9_ITEM_TEXTS: tuple[str, ...] = (
    "Little interest or pleasure in doing things",
    "Feeling down, depressed, or hopeless",
    "Trouble falling or staying asleep, or sleeping too much",
    "Feeling tired or having little energy",
    "Poor appetite or overeating",
    "Feeling bad about yourself — or that you are a failure or have let yourself or your "
    "family down",
    "Trouble concentrating on things, such as reading the newspaper or watching television",
    "Moving or speaking so slowly that other people could have noticed; or the opposite — "
    "being so fidgety or restless that you have been moving around a lot more than usual",
    "Thoughts that you would be better off dead or of hurting yourself in some way",
)

PHQ9_ITEMS: tuple[InstrumentItem, ...] = tuple(
    InstrumentItem(instrument_id=Instrument.PHQ9, item_number=index, text=text)
    for index, text in enumerate(_PHQ9_ITEM_TEXTS, start=1)
)

#: Index of the PHQ-9 self-harm item inside an answers tuple (item 9, zero-based 8).
PHQ9_RISK_ITEM_INDEX = 8

PHQ9_SEVERITY_BANDS: tuple[SeverityBandSpec, ...] = (
    SeverityBandSpec(Severity.MINIMAL, 0, 4),
    SeverityBandSpec(Severity.MILD, 5, 9),
    SeverityBandSpec(Severity.MODERATE, 10, 14),
    SeverityBandSpec(Severity.MODERATELY_SEVERE, 15, 19),
    SeverityBandSpec(Severity.SEVERE, 20, 27),
)

PHQ9_SPEC = InstrumentSpec(
    id=Instrument.PHQ9,
    display_name="PHQ-9",
    full_name="Patient Health Questionnaire-9",
    attribution=ATTRIBUTIONS[0],
    citation=CITATIONS[0],
    instruction_stem=PHQ9_INSTRUCTION_STEM,
    items=PHQ9_ITEMS,
    response_options=RESPONSE_OPTIONS,
    max_total=27,
    severity_bands=PHQ9_SEVERITY_BANDS,
    impairment_question=IMPAIRMENT_QUESTION,
    has_risk_item=True,
)

# ---------------------------------------------------------------------------
# GAD-7
# ---------------------------------------------------------------------------

#: GAD-7's stem omits "any of" - intentional and canonical; do not harmonize.
GAD7_INSTRUCTION_STEM = (
    "Over the last 2 weeks, how often have you been bothered by the following problems?"
)

_GAD7_ITEM_TEXTS: tuple[str, ...] = (
    "Feeling nervous, anxious, or on edge",
    "Not being able to stop or control worrying",
    "Worrying too much about different things",
    "Trouble relaxing",
    "Being so restless that it is hard to sit still",
    "Becoming easily annoyed or irritable",
    "Feeling afraid as if something awful might happen",
)

GAD7_ITEMS: tuple[InstrumentItem, ...] = tuple(
    InstrumentItem(instrument_id=Instrument.GAD7, item_number=index, text=text)
    for index, text in enumerate(_GAD7_ITEM_TEXTS, start=1)
)

GAD7_SEVERITY_BANDS: tuple[SeverityBandSpec, ...] = (
    SeverityBandSpec(Severity.MINIMAL, 0, 4),
    SeverityBandSpec(Severity.MILD, 5, 9),
    SeverityBandSpec(Severity.MODERATE, 10, 14),
    SeverityBandSpec(Severity.SEVERE, 15, 21),
)

GAD7_SPEC = InstrumentSpec(
    id=Instrument.GAD7,
    display_name="GAD-7",
    full_name="Generalized Anxiety Disorder-7",
    attribution=ATTRIBUTIONS[1],
    citation=CITATIONS[1],
    instruction_stem=GAD7_INSTRUCTION_STEM,
    items=GAD7_ITEMS,
    response_options=RESPONSE_OPTIONS,
    max_total=21,
    severity_bands=GAD7_SEVERITY_BANDS,
    impairment_question=IMPAIRMENT_QUESTION,
    has_risk_item=False,
)

#: The instrument registry. New instruments are added here, never special-cased in the UI.
INSTRUMENTS: Mapping[Instrument, InstrumentSpec] = MappingProxyType(
    {Instrument.PHQ9: PHQ9_SPEC, Instrument.GAD7: GAD7_SPEC}
)


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def get_instrument(instrument_id: Instrument) -> InstrumentSpec:
    """Return the registry record for ``instrument_id``.

    Raises ``KeyError`` (via ``dict`` lookup) if the instrument is unknown.
    """
    return INSTRUMENTS[Instrument(instrument_id)]


def validate_answers(instrument_id: Instrument, answers: Sequence[int]) -> tuple[int, ...]:
    """Return ``answers`` as a tuple after validating length and weight range.

    ``answers`` must hold one integer per item, in item order, each within
    ``0..3``. Raises ``ValueError`` otherwise; never rescales or pads input.
    """
    spec = get_instrument(instrument_id)
    values = tuple(answers)
    if len(values) != spec.item_count:
        raise ValueError(
            f"{spec.display_name} needs exactly {spec.item_count} answers, got {len(values)}"
        )
    for index, weight in enumerate(values, start=1):
        if not isinstance(weight, int) or isinstance(weight, bool):
            raise ValueError(f"Answer {index} must be an integer, got {weight!r}")
        if weight < 0 or weight > 3:
            raise ValueError(f"Answer {index} must be between 0 and 3, got {weight}")
    return values


def score_instrument(instrument_id: Instrument, answers: Sequence[int]) -> int:
    """Return the total score for validated ``answers`` (PHQ-9 0-27, GAD-7 0-21)."""
    spec = get_instrument(instrument_id)
    values = validate_answers(instrument_id, answers)
    total = sum(values)
    if total > spec.max_total:
        raise ValueError(f"{spec.display_name} total {total} exceeds {spec.max_total}")
    return total


def score_phq9(answers: Sequence[int]) -> int:
    """Return the PHQ-9 total score in range 0-27."""
    return score_instrument(Instrument.PHQ9, answers)


def score_gad7(answers: Sequence[int]) -> int:
    """Return the GAD-7 total score in range 0-21."""
    return score_instrument(Instrument.GAD7, answers)


def severity_for_total(instrument_id: Instrument, total: int) -> Severity:
    """Return the severity band for ``total`` using the instrument's canonical cutoffs.

    A total of exactly 4 is MINIMAL and exactly 5 is MILD; boundaries belong to the
    lower band's upper edge as listed in the instrument table. Raises ``ValueError``
    for a total outside ``0..max_total``.
    """
    spec = get_instrument(instrument_id)
    if not isinstance(total, int) or isinstance(total, bool):
        raise ValueError(f"Total must be an integer, got {total!r}")
    if total < 0 or total > spec.max_total:
        raise ValueError(f"{spec.display_name} total must be 0-{spec.max_total}, got {total}")
    for band in spec.severity_bands:
        if band.low <= total <= band.high:
            return band.severity
    raise ValueError(f"No severity band for {spec.display_name} total {total}")


def phq9_risk_flag(answers: Sequence[int]) -> bool:
    """Return True when PHQ-9 item 9 scored above zero (independent of the total).

    Raises ``ValueError`` for wrong-length or out-of-range answers.
    """
    values = validate_answers(Instrument.PHQ9, answers)
    return values[PHQ9_RISK_ITEM_INDEX] > 0


def risk_flag_for(instrument_id: Instrument, answers: Sequence[int]) -> bool:
    """Return the item-based risk flag: only PHQ-9 has a self-harm item.

    GAD-7 returns ``False`` always; its risk flag can only come from free-text
    keyword detection (see ``safety.py``).
    """
    if get_instrument(instrument_id).has_risk_item:
        return phq9_risk_flag(answers)
    validate_answers(instrument_id, answers)
    return False


def any_item_answered(instrument_id: Instrument, answers: Sequence[int]) -> bool:
    """Return True when at least one scored item has a weight above zero.

    Used to decide whether the functional-impairment follow-up is shown.
    """
    return any(weight > 0 for weight in validate_answers(instrument_id, answers))


def canonical_strings(instrument_id: Instrument) -> tuple[str, ...]:
    """Return every canonical display string for an instrument, in a fixed order.

    Order: display name, full name, attribution, citation, instruction stem, each
    item text in item order, each response label in weight order, impairment
    question, each impairment label.
    """
    spec = get_instrument(instrument_id)
    return (
        spec.display_name,
        spec.full_name,
        spec.attribution,
        spec.citation,
        spec.instruction_stem,
        *(item.text for item in spec.items),
        *(label for _, label in spec.response_options),
        spec.impairment_question,
        *(label for _, label in IMPAIRMENT_OPTIONS),
    )


def content_checksum(instrument_id: Instrument) -> str:
    """Return a short SHA-256 digest of an instrument's canonical strings.

    Stored alongside each screening so that wording changes in a future release
    flag old rows instead of silently rescoring them.
    """
    joined = "\n".join(canonical_strings(instrument_id))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def instrument_ids() -> tuple[Instrument, ...]:
    """Return the registered instrument ids in a stable display order."""
    return (Instrument.PHQ9, Instrument.GAD7)


def response_label_for_weight(weight: int) -> str:
    """Return the response label for a weight in ``0..3``.

    Raises ``ValueError`` for any other weight.
    """
    for option_weight, label in RESPONSE_OPTIONS:
        if option_weight == weight:
            return label
    raise ValueError(f"No response label for weight {weight}")


def impairment_label(value: str | None) -> str:
    """Return the display label for a stored impairment value.

    ``None`` and ``unanswered`` both display as "Prefer not to say".
    """
    if value is None or value == IMPAIRMENT_UNANSWERED:
        return IMPAIRMENT_UNANSWERED_LABEL
    for stored_value, label in IMPAIRMENT_OPTIONS:
        if stored_value == value:
            return label
    raise ValueError(f"Unknown impairment value {value!r}")


def is_valid_impairment_value(value: str | None) -> bool:
    """Return True when ``value`` is a storable impairment answer."""
    if value is None or value == IMPAIRMENT_UNANSWERED:
        return True
    return any(stored == value for stored, _ in IMPAIRMENT_OPTIONS)
