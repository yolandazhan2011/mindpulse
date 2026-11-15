"""Frozen data records and enumerations for MindPulse.

Only data shapes live here: no behaviour beyond trivial properties, no I/O.
Every record is ``@dataclass(frozen=True)`` and every collection field is a
tuple, so instances are safe to pass between the pure and impure layers.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

_SEVERITY_LABELS: dict[str, str] = {
    "MINIMAL": "Minimal",
    "MILD": "Mild",
    "MODERATE": "Moderate",
    "MODERATELY_SEVERE": "Moderately severe",
    "SEVERE": "Severe",
}


class Instrument(StrEnum):
    """The validated screening questionnaires MindPulse supports."""

    PHQ9 = "PHQ9"
    GAD7 = "GAD7"


class Severity(StrEnum):
    """Severity band for a screening total. Never a diagnosis."""

    MINIMAL = "MINIMAL"
    MILD = "MILD"
    MODERATE = "MODERATE"
    MODERATELY_SEVERE = "MODERATELY_SEVERE"
    SEVERE = "SEVERE"

    @property
    def label(self) -> str:
        """Return the human-readable band label, e.g. ``"Moderately severe"``."""
        return _SEVERITY_LABELS[self.value]


class Role(StrEnum):
    """Author of a chat message."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass(frozen=True)
class CheckIn:
    """One daily check-in.

    ``id`` is ``None`` for a record that has not been persisted yet. Scales:
    mood/stress/energy are integers 1-10, ``sleep_hours`` is a float 0-24, and
    ``created_at`` is an ISO-8601 UTC timestamp.
    """

    created_at: str
    mood: int
    stress: int
    energy: int
    sleep_hours: float
    journal: str = ""
    id: int | None = None


@dataclass(frozen=True)
class Screening:
    """One completed screening questionnaire.

    ``answers`` holds the per-item weights in item order. ``total`` is the sum of
    those weights, ``severity`` the band it falls in, and ``risk_flag`` is set
    when PHQ-9 item 9 scored above zero or crisis language appeared in free text.
    ``impairment`` is the optional functional-impairment answer key (never scored).
    """

    created_at: str
    instrument: Instrument
    answers: tuple[int, ...]
    total: int
    severity: Severity
    risk_flag: bool = False
    impairment: str | None = None
    content_checksum: str = ""
    id: int | None = None


@dataclass(frozen=True)
class ChatMessage:
    """One chat turn. ``role`` is user, assistant, or system."""

    role: Role
    content: str
    created_at: str = ""
    id: int | None = None


@dataclass(frozen=True)
class SeverityBandSpec:
    """An instrument's severity band: an inclusive total range and its label."""

    severity: Severity
    low: int
    high: int


@dataclass(frozen=True)
class InstrumentItem:
    """One questionnaire item, stored verbatim in canonical order."""

    instrument_id: Instrument
    item_number: int
    text: str
    max_weight: int = 3


@dataclass(frozen=True)
class InstrumentSpec:
    """Everything needed to display and score one instrument.

    ``response_options`` is a tuple of ``(weight, label)`` pairs shared by every
    item, ordered from weight 0 upwards (the UI maps keys ``1``-``4`` onto it).
    """

    id: Instrument
    display_name: str
    full_name: str
    attribution: str
    citation: str
    instruction_stem: str
    items: tuple[InstrumentItem, ...]
    response_options: tuple[tuple[int, str], ...]
    max_total: int
    severity_bands: tuple[SeverityBandSpec, ...]
    impairment_question: str
    has_risk_item: bool

    @property
    def item_count(self) -> int:
        """Return the number of scored items in this instrument."""
        return len(self.items)


@dataclass(frozen=True)
class BrainFact:
    """One short, cited neuroscience education card."""

    title: str
    body: str
    source: str
