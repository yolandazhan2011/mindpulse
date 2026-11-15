"""Tests for the deterministic crisis gate (Prompt D §3, §5).

Every fixture is a documented judgment call: a comment states why it matches or
does not match. The gate must be reproducible from these tests alone.
"""

from __future__ import annotations

import unittest

from mindpulse.models import Instrument
from mindpulse.safety import (
    CHAT_PHRASE_SOURCE,
    CRISIS_PHRASES,
    JOURNAL_PHRASE_SOURCE,
    SELF_HARM_INDICATOR,
    contains_crisis_phrase,
    crisis_precedes_any_response,
    is_crisis_response_required,
    normalize_text,
    phq9_item9_risk,
    risk_sources,
    screening_risk_flag,
)

#: Near-miss probes. Each must NOT trigger; the comment says why.
NEAR_MISS_FIXTURES = (
    # "kill myself" is a phrase, "killed it" is not; no phrase appears at all.
    "I killed it in that game",
    # "suicide-related" is hyphenated, so the padded boundary check does not match.
    "this book has a suicide-related subplot title",
    # "hurt" alone is not a phrase; only "hurt myself" / "hurt yourself" are.
    "I hurt my knee running yesterday",
    # The word "die" alone is not a phrase.
    "I hope the batteries don't die",
    # Mentioning a helpline is not the same as expressing risk.
    "I saved the 988 helpline number in my phone",
    # Empty and whitespace-only input never triggers.
    "",
    "   \n\t  ",
)


class PhraseTests(unittest.TestCase):
    def test_crisis_phrases_are_a_frozenset_of_lowercase_strings(self) -> None:
        self.assertIsInstance(CRISIS_PHRASES, frozenset)
        for phrase in CRISIS_PHRASES:
            with self.subTest(phrase=phrase):
                self.assertTrue(phrase)
                self.assertEqual(phrase, phrase.lower())
                self.assertEqual(phrase, " ".join(phrase.split()))

    def test_no_duplicate_or_empty_members(self) -> None:
        self.assertNotIn("", CRISIS_PHRASES)
        self.assertEqual(len(CRISIS_PHRASES), len(set(CRISIS_PHRASES)))

    def test_every_phrase_matches_inside_a_sentence(self) -> None:
        for phrase in CRISIS_PHRASES:
            with self.subTest(phrase=phrase):
                self.assertTrue(contains_crisis_phrase(f"honestly i {phrase} last night"))

    def test_every_phrase_matches_as_entire_input(self) -> None:
        for phrase in CRISIS_PHRASES:
            with self.subTest(phrase=phrase):
                self.assertTrue(contains_crisis_phrase(phrase))

    def test_near_misses_do_not_match(self) -> None:
        for text in NEAR_MISS_FIXTURES:
            with self.subTest(text=text):
                self.assertFalse(contains_crisis_phrase(text))

    def test_plural_of_a_phrase_still_matches(self) -> None:
        # Prompt D asks for "suicides" to match "suicide": a trailing plural s is
        # allowed, while hyphenated compounds ("suicide-related") are not.
        self.assertTrue(contains_crisis_phrase("there were two suicides in the news"))

    def test_case_and_whitespace_are_normalized(self) -> None:
        self.assertTrue(contains_crisis_phrase("Hurt MySelf"))
        self.assertTrue(contains_crisis_phrase("want   to die"))

    def test_surrounding_punctuation_still_matches(self) -> None:
        self.assertTrue(contains_crisis_phrase("want to die."))
        self.assertTrue(contains_crisis_phrase('"I want to die"'))
        self.assertTrue(contains_crisis_phrase("want to die!\n"))

    def test_normalize_text_only_lowercases_and_collapses_whitespace(self) -> None:
        self.assertEqual(normalize_text("  I  Want\tTo DIE. \n"), "i want to die.")
        self.assertEqual(normalize_text(""), "")


class ItemNineTests(unittest.TestCase):
    def test_item_nine_weight_one_triggers(self) -> None:
        answers = (0, 0, 0, 0, 0, 0, 0, 0, 1)
        self.assertTrue(phq9_item9_risk(answers))
        self.assertTrue(is_crisis_response_required(answers, "", ""))

    def test_all_zero_scores_do_not_trigger(self) -> None:
        answers = (0,) * 9
        self.assertFalse(phq9_item9_risk(answers))
        self.assertFalse(is_crisis_response_required(answers, "", ""))

    def test_item_nine_risk_is_independent_of_total(self) -> None:
        # Total 1, item 9 = 1: still a risk.
        self.assertTrue(phq9_item9_risk((0, 0, 0, 0, 0, 0, 0, 0, 1)))

    def test_wrong_length_raises(self) -> None:
        with self.assertRaises(ValueError):
            phq9_item9_risk((0,) * 8)
        with self.assertRaises(ValueError):
            phq9_item9_risk((0,) * 10)

    def test_out_of_range_weight_raises(self) -> None:
        with self.assertRaises(ValueError):
            phq9_item9_risk((0, 0, 0, 0, 0, 0, 0, 0, 4))


class GateCompositionTests(unittest.TestCase):
    def test_journal_phrase_alone_triggers(self) -> None:
        self.assertTrue(is_crisis_response_required((), "I want to die", ""))

    def test_chat_phrase_alone_triggers(self) -> None:
        self.assertTrue(is_crisis_response_required((), "", "I want to die"))

    def test_all_empty_inputs_do_not_trigger(self) -> None:
        self.assertFalse(is_crisis_response_required((), "", ""))
        self.assertFalse(is_crisis_response_required((), "   ", "\n"))

    def test_empty_screening_sequence_means_not_taken(self) -> None:
        self.assertFalse(is_crisis_response_required((), "", ""))

    def test_risk_sources_names_every_trigger_sorted(self) -> None:
        answers = (0, 0, 0, 0, 0, 0, 0, 0, 2)
        self.assertEqual(
            risk_sources(answers, "hurt myself", "want to die"),
            (CHAT_PHRASE_SOURCE, JOURNAL_PHRASE_SOURCE, SELF_HARM_INDICATOR),
        )

    def test_risk_sources_is_empty_without_triggers(self) -> None:
        self.assertEqual(risk_sources((0,) * 9, "a calm day", "hello"), ())

    def test_crisis_precedes_any_response_ordering_rule(self) -> None:
        self.assertTrue(crisis_precedes_any_response(gate_open=True))
        self.assertFalse(crisis_precedes_any_response(gate_open=False))


class ScreeningRiskFlagTests(unittest.TestCase):
    def test_phq9_item_nine_sets_the_flag(self) -> None:
        self.assertTrue(screening_risk_flag(Instrument.PHQ9, (0,) * 8 + (1,)))

    def test_gad7_cannot_set_the_flag_from_items(self) -> None:
        self.assertFalse(screening_risk_flag(Instrument.GAD7, (3,) * 7))

    def test_free_text_can_flag_gad7(self) -> None:
        self.assertTrue(screening_risk_flag(Instrument.GAD7, (0,) * 7, "hurt myself"))


if __name__ == "__main__":
    unittest.main()
