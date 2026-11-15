"""Tests for the curated education cards (Prompt A, F4)."""

from __future__ import annotations

import unittest
from datetime import date, timedelta

from mindpulse.brain_facts import (
    BRAIN_FACTS,
    fact_by_title,
    fact_count,
    fact_for_date,
    facts_in_display_order,
)


class BrainFactTests(unittest.TestCase):
    def test_between_eight_and_ten_cards(self) -> None:
        self.assertGreaterEqual(fact_count(), 8)
        self.assertLessEqual(fact_count(), 10)

    def test_each_card_is_twenty_five_to_fifty_words(self) -> None:
        for fact in BRAIN_FACTS:
            words = len(fact.body.split())
            with self.subTest(title=fact.title):
                self.assertGreaterEqual(words, 25)
                self.assertLessEqual(words, 50)

    def test_every_card_is_titled_and_cited(self) -> None:
        for fact in BRAIN_FACTS:
            with self.subTest(title=fact.title):
                self.assertTrue(fact.title.strip())
                self.assertTrue(fact.source.strip())
                self.assertTrue(fact.body.strip())

    def test_titles_are_unique(self) -> None:
        titles = [fact.title for fact in BRAIN_FACTS]
        self.assertEqual(len(titles), len(set(titles)))

    def test_cards_are_non_prescriptive(self) -> None:
        # Education, not advice: no imperative instructions to the reader.
        for fact in BRAIN_FACTS:
            lowered = fact.body.lower()
            with self.subTest(title=fact.title):
                for phrase in ("you should", "you must", "try to", "make sure you"):
                    self.assertNotIn(phrase, lowered)

    def test_required_topics_are_covered(self) -> None:
        titles = " ".join(fact.title.lower() for fact in BRAIN_FACTS)
        for topic in ("amygdala", "prefrontal", "hippocampus", "sleep", "exercise", "hpa"):
            with self.subTest(topic=topic):
                self.assertIn(topic, titles)

    def test_display_order_matches_the_curated_tuple(self) -> None:
        self.assertEqual(facts_in_display_order(), BRAIN_FACTS)

    def test_lookup_by_title(self) -> None:
        self.assertEqual(fact_by_title(BRAIN_FACTS[0].title), BRAIN_FACTS[0])
        with self.assertRaises(KeyError):
            fact_by_title("not a card")


class DailyFactTests(unittest.TestCase):
    def test_same_day_always_returns_the_same_card(self) -> None:
        day = date(2024, 5, 17)
        self.assertEqual(fact_for_date(day), fact_for_date(date(2024, 5, 17)))

    def test_consecutive_days_return_different_cards(self) -> None:
        day = date(2024, 5, 17)
        self.assertNotEqual(fact_for_date(day), fact_for_date(day + timedelta(days=1)))

    def test_one_cycle_shows_every_card_once(self) -> None:
        start = date(2024, 5, 17)
        shown = [fact_for_date(start + timedelta(days=offset)) for offset in range(fact_count())]
        self.assertEqual(len(set(shown)), fact_count())

    def test_cycle_repeats_after_fact_count_days(self) -> None:
        start = date(2024, 5, 17)
        later = start + timedelta(days=fact_count())
        self.assertEqual(fact_for_date(start), fact_for_date(later))

    def test_returns_one_of_the_curated_cards(self) -> None:
        self.assertIn(fact_for_date(date(2024, 5, 17)), BRAIN_FACTS)

    def test_accepts_any_date(self) -> None:
        for day in (date(1, 1, 1), date(9999, 12, 31)):
            with self.subTest(day=day):
                self.assertIn(fact_for_date(day), BRAIN_FACTS)


if __name__ == "__main__":
    unittest.main()
