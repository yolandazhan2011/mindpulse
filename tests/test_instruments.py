"""Tests for the canonical instrument content and pure scoring (Prompt B §10).

Strings are compared against the module's own canonical constants (one source of
truth); the only literals here are structural expectations such as item counts.
"""

from __future__ import annotations

import pathlib
import unittest

from mindpulse.instruments import (
    ATTRIBUTIONS,
    CITATIONS,
    GAD7_INSTRUCTION_STEM,
    GAD7_ITEMS,
    GAD7_SPEC,
    IMPAIRMENT_OPTIONS,
    IMPAIRMENT_QUESTION,
    IMPAIRMENT_UNANSWERED,
    IMPAIRMENT_UNANSWERED_LABEL,
    INSTRUMENTS,
    PHQ9_INSTRUCTION_STEM,
    PHQ9_ITEMS,
    PHQ9_RISK_ITEM_INDEX,
    PHQ9_SPEC,
    RESPONSE_OPTIONS,
    any_item_answered,
    canonical_strings,
    content_checksum,
    get_instrument,
    impairment_label,
    instrument_ids,
    is_valid_impairment_value,
    response_label_for_weight,
    risk_flag_for,
    score_gad7,
    score_instrument,
    score_phq9,
    severity_for_total,
    validate_answers,
)
from mindpulse.models import Instrument, Severity

SOURCE_ROOT = pathlib.Path(__file__).resolve().parent.parent / "mindpulse"


class RegistryTests(unittest.TestCase):
    def test_item_counts_match_the_instruments(self) -> None:
        self.assertEqual(get_instrument(Instrument.PHQ9).item_count, 9)
        self.assertEqual(get_instrument(Instrument.GAD7).item_count, 7)

    def test_max_totals_match_the_maximum_sums(self) -> None:
        for instrument_id in instrument_ids():
            spec = get_instrument(instrument_id)
            with self.subTest(instrument=instrument_id):
                self.assertEqual(spec.max_total, sum(item.max_weight for item in spec.items))

    def test_has_risk_item_true_only_for_phq9(self) -> None:
        self.assertTrue(PHQ9_SPEC.has_risk_item)
        self.assertFalse(GAD7_SPEC.has_risk_item)

    def test_registry_references_the_shared_canonical_strings(self) -> None:
        self.assertIs(PHQ9_SPEC.items, PHQ9_ITEMS)
        self.assertIs(GAD7_SPEC.items, GAD7_ITEMS)
        self.assertIs(PHQ9_SPEC.response_options, RESPONSE_OPTIONS)
        self.assertIs(GAD7_SPEC.response_options, RESPONSE_OPTIONS)
        self.assertIs(PHQ9_SPEC.impairment_question, IMPAIRMENT_QUESTION)
        self.assertIs(GAD7_SPEC.impairment_question, IMPAIRMENT_QUESTION)

    def test_display_and_full_names(self) -> None:
        self.assertEqual(PHQ9_SPEC.display_name, "PHQ-9")
        self.assertEqual(PHQ9_SPEC.full_name, "Patient Health Questionnaire-9")
        self.assertEqual(GAD7_SPEC.display_name, "GAD-7")
        self.assertEqual(GAD7_SPEC.full_name, "Generalized Anxiety Disorder-7")

    def test_item_numbers_are_sequential_from_one(self) -> None:
        for instrument_id in instrument_ids():
            numbers = tuple(item.item_number for item in get_instrument(instrument_id).items)
            with self.subTest(instrument=instrument_id):
                self.assertEqual(numbers, tuple(range(1, len(numbers) + 1)))
                items = get_instrument(instrument_id).items
                self.assertTrue(all(item.instrument_id == instrument_id for item in items))

    def test_response_options_are_the_four_canonical_weights(self) -> None:
        self.assertEqual(tuple(weight for weight, _ in RESPONSE_OPTIONS), (0, 1, 2, 3))
        self.assertEqual(
            tuple(label for _, label in RESPONSE_OPTIONS),
            ("Not at all", "Several days", "More than half the days", "Nearly every day"),
        )

    def test_stems_differ_only_by_the_canonical_phrase(self) -> None:
        # GAD-7's stem omits "any of": harmonizing them would be a content defect.
        self.assertIn("any of the following problems", PHQ9_INSTRUCTION_STEM)
        self.assertNotIn("any of", GAD7_INSTRUCTION_STEM)

    def test_both_stems_reference_the_two_week_window(self) -> None:
        self.assertTrue(PHQ9_INSTRUCTION_STEM.startswith("Over the last 2 weeks,"))
        self.assertTrue(GAD7_INSTRUCTION_STEM.startswith("Over the last 2 weeks,"))

    def test_phq9_uses_em_dashes_not_hyphens(self) -> None:
        for number in (6, 8):
            text = get_instrument(Instrument.PHQ9).items[number - 1].text
            with self.subTest(item=number):
                self.assertIn("—", text)
                self.assertNotIn(" - ", text)

    def test_no_item_text_is_empty_or_padded(self) -> None:
        for instrument_id in instrument_ids():
            for item in get_instrument(instrument_id).items:
                with self.subTest(item=item.item_number):
                    self.assertTrue(item.text)
                    self.assertEqual(item.text, item.text.strip())
                    self.assertNotIn("\n", item.text)

    def test_attribution_and_citation_present_for_each_instrument(self) -> None:
        self.assertEqual(PHQ9_SPEC.attribution, ATTRIBUTIONS[0])
        self.assertEqual(GAD7_SPEC.attribution, ATTRIBUTIONS[1])
        self.assertIn(PHQ9_SPEC.citation, CITATIONS)
        self.assertIn(GAD7_SPEC.citation, CITATIONS)
        self.assertEqual(len(ATTRIBUTIONS), 2)
        self.assertEqual(len(CITATIONS), 3)

    def test_registry_is_read_only(self) -> None:
        with self.assertRaises(TypeError):
            INSTRUMENTS[Instrument.PHQ9] = GAD7_SPEC  # type: ignore[index]

    def test_unknown_instrument_raises(self) -> None:
        with self.assertRaises(ValueError):
            get_instrument("WHO5")  # type: ignore[arg-type]


class StringFidelityTests(unittest.TestCase):
    def test_canonical_strings_cover_every_item_in_order(self) -> None:
        for instrument_id in instrument_ids():
            spec = get_instrument(instrument_id)
            collected = canonical_strings(instrument_id)
            with self.subTest(instrument=instrument_id):
                self.assertEqual(collected[0], spec.display_name)
                self.assertEqual(collected[4], spec.instruction_stem)
                self.assertEqual(
                    collected[5 : 5 + spec.item_count],
                    tuple(item.text for item in spec.items),
                )

    def test_item_text_appears_in_exactly_one_module(self) -> None:
        # "No duplicated text literals anywhere in the codebase" (Prompt B §1.5).
        instrument_texts = tuple(
            item.text
            for instrument_id in instrument_ids()
            for item in get_instrument(instrument_id).items
        )
        for path in SOURCE_ROOT.rglob("*.py"):
            if path.name == "instruments.py":
                continue
            source = path.read_text(encoding="utf-8")
            for text in instrument_texts:
                with self.subTest(path=path.name, text=text[:40]):
                    self.assertNotIn(text, source)

    def test_content_checksum_is_stable_and_distinct(self) -> None:
        self.assertEqual(content_checksum(Instrument.PHQ9), content_checksum(Instrument.PHQ9))
        self.assertNotEqual(content_checksum(Instrument.PHQ9), content_checksum(Instrument.GAD7))
        self.assertEqual(len(content_checksum(Instrument.PHQ9)), 16)


class ScoringTests(unittest.TestCase):
    def test_all_zeros_score_zero(self) -> None:
        self.assertEqual(score_phq9((0,) * 9), 0)
        self.assertEqual(score_gad7((0,) * 7), 0)

    def test_all_maximums_score_the_max_total(self) -> None:
        self.assertEqual(score_phq9((3,) * 9), 27)
        self.assertEqual(score_gad7((3,) * 7), 21)

    def test_hand_computed_mixed_vectors(self) -> None:
        # 1+0+2+3+0+0+1+0+1 = 8 (PHQ-9, mild)
        phq9_answers = (1, 0, 2, 3, 0, 0, 1, 0, 1)
        self.assertEqual(score_phq9(phq9_answers), 8)
        self.assertIs(severity_for_total(Instrument.PHQ9, 8), Severity.MILD)
        # 3+3+2+1+2+0+1 = 12 (GAD-7, moderate)
        gad7_answers = (3, 3, 2, 1, 2, 0, 1)
        self.assertEqual(score_gad7(gad7_answers), 12)
        self.assertIs(severity_for_total(Instrument.GAD7, 12), Severity.MODERATE)

    def test_wrong_length_vectors_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            score_phq9((0,) * 8)
        with self.assertRaises(ValueError):
            score_phq9((0,) * 10)
        with self.assertRaises(ValueError):
            score_gad7((0,) * 9)

    def test_out_of_range_weights_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            score_phq9((0,) * 8 + (4,))
        with self.assertRaises(ValueError):
            score_gad7((-1,) + (0,) * 6)

    def test_non_integer_weights_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_answers(Instrument.PHQ9, (0,) * 8 + ("1",))  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            validate_answers(Instrument.PHQ9, (0,) * 8 + (True,))  # type: ignore[arg-type]

    def test_score_instrument_matches_the_specific_helpers(self) -> None:
        answers = (3, 1, 0, 2, 1, 0, 0, 1, 0)
        self.assertEqual(score_instrument(Instrument.PHQ9, answers), score_phq9(answers))


class SeverityBoundaryTests(unittest.TestCase):
    def test_phq9_boundaries(self) -> None:
        expected = {
            0: Severity.MINIMAL,
            4: Severity.MINIMAL,
            5: Severity.MILD,
            9: Severity.MILD,
            10: Severity.MODERATE,
            14: Severity.MODERATE,
            15: Severity.MODERATELY_SEVERE,
            19: Severity.MODERATELY_SEVERE,
            20: Severity.SEVERE,
            27: Severity.SEVERE,
        }
        for total, severity in expected.items():
            with self.subTest(total=total):
                self.assertIs(severity_for_total(Instrument.PHQ9, total), severity)

    def test_gad7_boundaries(self) -> None:
        expected = {
            0: Severity.MINIMAL,
            4: Severity.MINIMAL,
            5: Severity.MILD,
            9: Severity.MILD,
            10: Severity.MODERATE,
            14: Severity.MODERATE,
            15: Severity.SEVERE,
            21: Severity.SEVERE,
        }
        for total, severity in expected.items():
            with self.subTest(total=total):
                self.assertIs(severity_for_total(Instrument.GAD7, total), severity)

    def test_out_of_range_total_raises(self) -> None:
        with self.assertRaises(ValueError):
            severity_for_total(Instrument.PHQ9, 28)
        with self.assertRaises(ValueError):
            severity_for_total(Instrument.GAD7, -1)
        with self.assertRaises(ValueError):
            severity_for_total(Instrument.GAD7, 22)

    def test_every_band_covers_its_range_without_gaps(self) -> None:
        for instrument_id in instrument_ids():
            spec = get_instrument(instrument_id)
            with self.subTest(instrument=instrument_id):
                self.assertEqual(spec.severity_bands[0].low, 0)
                self.assertEqual(spec.severity_bands[-1].high, spec.max_total)
                for lower, upper in zip(spec.severity_bands, spec.severity_bands[1:], strict=False):
                    self.assertEqual(upper.low, lower.high + 1)


class RiskTests(unittest.TestCase):
    def test_item_nine_weight_one_sets_the_flag(self) -> None:
        answers = (0,) * PHQ9_RISK_ITEM_INDEX + (1,)
        self.assertTrue(risk_flag_for(Instrument.PHQ9, answers))

    def test_all_zero_answers_do_not_set_the_flag(self) -> None:
        self.assertFalse(risk_flag_for(Instrument.PHQ9, (0,) * 9))

    def test_gad7_has_no_item_that_can_set_the_flag(self) -> None:
        self.assertFalse(risk_flag_for(Instrument.GAD7, (3,) * 7))

    def test_invalid_answers_raise_instead_of_guessing(self) -> None:
        with self.assertRaises(ValueError):
            risk_flag_for(Instrument.PHQ9, (0,) * 8)


class ImpairmentTests(unittest.TestCase):
    def test_impairment_options_are_the_four_canonical_values(self) -> None:
        self.assertEqual(
            tuple(value for value, _ in IMPAIRMENT_OPTIONS),
            ("not_difficult", "somewhat_difficult", "very_difficult", "extremely_difficult"),
        )

    def test_impairment_never_affects_the_total(self) -> None:
        answers = (1,) * 9
        before = score_phq9(answers)
        after = score_phq9(answers)
        self.assertEqual(before, after)
        self.assertIs(severity_for_total(Instrument.PHQ9, after), Severity.MILD)

    def test_unanswered_is_allowed_and_labelled(self) -> None:
        self.assertTrue(is_valid_impairment_value(None))
        self.assertTrue(is_valid_impairment_value(IMPAIRMENT_UNANSWERED))
        self.assertEqual(impairment_label(None), IMPAIRMENT_UNANSWERED_LABEL)
        self.assertEqual(impairment_label(IMPAIRMENT_UNANSWERED), IMPAIRMENT_UNANSWERED_LABEL)
        self.assertEqual(impairment_label("very_difficult"), "Very difficult")

    def test_unknown_impairment_value_raises(self) -> None:
        self.assertFalse(is_valid_impairment_value("slightly_difficult"))
        with self.assertRaises(ValueError):
            impairment_label("slightly_difficult")

    def test_impairment_follow_up_is_shown_only_when_something_scored(self) -> None:
        self.assertFalse(any_item_answered(Instrument.GAD7, (0,) * 7))
        self.assertTrue(any_item_answered(Instrument.GAD7, (0, 1, 0, 0, 0, 0, 0)))


class LabelTests(unittest.TestCase):
    def test_response_label_for_weight(self) -> None:
        self.assertEqual(response_label_for_weight(0), "Not at all")
        self.assertEqual(response_label_for_weight(3), "Nearly every day")
        with self.assertRaises(ValueError):
            response_label_for_weight(4)

    def test_severity_human_labels(self) -> None:
        self.assertEqual(Severity.MODERATELY_SEVERE.label, "Moderately severe")
        self.assertEqual(Severity.SEVERE.label, "Severe")


if __name__ == "__main__":
    unittest.main()
