"""Tests for scoring composition and result-screen copy (Prompt B §4.3, §5).

The copy literals below are intentional: they pin the strings to the specification
so an accidental paraphrase fails the suite.
"""

from __future__ import annotations

import unittest

from mindpulse.models import Instrument, Screening, Severity
from mindpulse.scoring import (
    BAND_EXPLANATIONS,
    RESULT_DISCLAIMER,
    RESULT_NEXT_STEP,
    RISK_RESULT_BANNER,
    assess_answers,
    band_explanation,
    build_screening,
    format_result_title,
    format_score_line,
    result_lines,
)

CANONICAL_DISCLAIMER = (
    "This is a screening tool, not a diagnosis. Only a qualified clinician can diagnose "
    "a mental health condition. If you are struggling, please talk to a doctor, "
    "counselor, or a trusted adult."
)

CANONICAL_NEXT_STEP = (
    "Whatever your score, it is one snapshot of how you have felt over the past 2 weeks. "
    "Consider sharing this result with a doctor or counselor. If anything felt urgent "
    'while answering, please use the "Get help now" button.'
)

CANONICAL_RISK_BANNER = (
    "Your answers included thoughts of self-harm or of being better off dead. You deserve "
    'support from a real person right now. The "Get help now" button opens people who want '
    "to help."
)

CANONICAL_BAND_EXPLANATIONS = {
    Severity.MINIMAL: "Your answers suggest minimal symptoms right now.",
    Severity.MILD: "Your answers suggest mild symptoms right now.",
    Severity.MODERATE: "Your answers suggest moderate symptoms right now.",
    Severity.MODERATELY_SEVERE: "Your answers suggest moderately severe symptoms right now.",
    Severity.SEVERE: (
        "Your answers suggest severe symptoms right now. It is especially important to "
        "talk with a doctor or counselor soon."
    ),
}


class ResultCopyTests(unittest.TestCase):
    def test_disclaimer_matches_the_specification(self) -> None:
        self.assertEqual(RESULT_DISCLAIMER, CANONICAL_DISCLAIMER)

    def test_next_step_matches_the_specification(self) -> None:
        self.assertEqual(RESULT_NEXT_STEP, CANONICAL_NEXT_STEP)

    def test_risk_banner_matches_the_specification(self) -> None:
        self.assertEqual(RISK_RESULT_BANNER, CANONICAL_RISK_BANNER)

    def test_band_explanations_match_the_specification(self) -> None:
        self.assertEqual(BAND_EXPLANATIONS, CANONICAL_BAND_EXPLANATIONS)

    def test_every_band_has_an_explanation(self) -> None:
        for severity in Severity:
            with self.subTest(severity=severity):
                self.assertEqual(band_explanation(severity), CANONICAL_BAND_EXPLANATIONS[severity])

    def test_unknown_band_raises(self) -> None:
        with self.assertRaises(ValueError):
            band_explanation("EXTREME")  # type: ignore[arg-type]

    def test_title_and_score_line_formats(self) -> None:
        self.assertEqual(format_result_title(Instrument.PHQ9), "Your PHQ-9 result")
        self.assertEqual(format_result_title(Instrument.GAD7), "Your GAD-7 result")
        self.assertEqual(format_score_line(Instrument.PHQ9, 12), "Score: 12 out of 27 — Moderate")
        self.assertEqual(format_score_line(Instrument.GAD7, 21), "Score: 21 out of 21 — Severe")

    def test_score_line_rejects_out_of_range_totals(self) -> None:
        with self.assertRaises(ValueError):
            format_score_line(Instrument.GAD7, 22)


class AssessAnswersTests(unittest.TestCase):
    def test_assess_returns_total_severity_and_no_risk(self) -> None:
        total, severity, risk = assess_answers(Instrument.PHQ9, (1, 1, 1, 0, 0, 0, 0, 0, 0))
        self.assertEqual(total, 3)
        self.assertIs(severity, Severity.MINIMAL)
        self.assertFalse(risk)

    def test_assess_flags_item_nine(self) -> None:
        _, _, risk = assess_answers(Instrument.PHQ9, (0,) * 8 + (1,))
        self.assertTrue(risk)

    def test_assess_flags_free_text_language(self) -> None:
        _, _, risk = assess_answers(Instrument.GAD7, (0,) * 7, "I want to die")
        self.assertTrue(risk)

    def test_assess_rejects_invalid_answers(self) -> None:
        with self.assertRaises(ValueError):
            assess_answers(Instrument.PHQ9, (0,) * 3)


class BuildScreeningTests(unittest.TestCase):
    def test_build_screening_attaches_total_band_and_checksum(self) -> None:
        screening = build_screening(
            Instrument.PHQ9,
            (2, 2, 2, 2, 2, 0, 0, 0, 0),
            "2026-10-18T09:30:00Z",
            impairment="somewhat_difficult",
        )
        self.assertEqual(screening.total, 10)
        self.assertIs(screening.severity, Severity.MODERATE)
        self.assertFalse(screening.risk_flag)
        self.assertEqual(screening.impairment, "somewhat_difficult")
        self.assertEqual(len(screening.content_checksum), 16)
        self.assertIs(screening.instrument, Instrument.PHQ9)

    def test_build_screening_sets_the_risk_flag(self) -> None:
        screening = build_screening(Instrument.PHQ9, (0,) * 8 + (3,), "2026-10-18T09:30:00Z")
        self.assertTrue(screening.risk_flag)
        self.assertIs(screening.severity, Severity.MINIMAL)

    def test_build_screening_keeps_answers_immutable(self) -> None:
        answers = [1, 0, 0, 0, 0, 0, 0, 0, 0]
        screening = build_screening(Instrument.PHQ9, answers, "2026-10-18T09:30:00Z")
        self.assertIsInstance(screening.answers, tuple)
        self.assertEqual(answers, [1, 0, 0, 0, 0, 0, 0, 0, 0])


class ResultLinesTests(unittest.TestCase):
    def test_result_lines_include_the_full_disclaimer_before_next_step(self) -> None:
        screening = build_screening(Instrument.GAD7, (1,) * 7, "2026-10-18T09:30:00Z")
        lines = result_lines(Instrument.GAD7, screening)
        self.assertIn(RESULT_DISCLAIMER, lines)
        self.assertIn(RESULT_NEXT_STEP, lines)
        self.assertLess(lines.index(RESULT_DISCLAIMER), lines.index(RESULT_NEXT_STEP))

    def test_risk_banner_comes_first_and_only_when_flagged(self) -> None:
        flagged = Screening(
            created_at="2026-10-18T09:30:00Z",
            instrument=Instrument.PHQ9,
            answers=(0,) * 9,
            total=0,
            severity=Severity.MINIMAL,
            risk_flag=True,
        )
        self.assertEqual(result_lines(Instrument.PHQ9, flagged)[0], RISK_RESULT_BANNER)

        calm = Screening(
            created_at="2026-10-18T09:30:00Z",
            instrument=Instrument.PHQ9,
            answers=(0,) * 9,
            total=0,
            severity=Severity.MINIMAL,
        )
        self.assertNotIn(RISK_RESULT_BANNER, result_lines(Instrument.PHQ9, calm))


if __name__ == "__main__":
    unittest.main()
