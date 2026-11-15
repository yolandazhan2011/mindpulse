"""Literal-equality tests for the fixed companion strings (Prompt C §2, §5)."""

from __future__ import annotations

import unittest

from mindpulse import prompts


class ConstantTests(unittest.TestCase):
    def test_persistent_chat_disclaimer_matches_the_specification(self) -> None:
        self.assertEqual(
            prompts.PERSISTENT_CHAT_DISCLAIMER,
            "AI responses are generated automatically and may be wrong. "
            "This is not therapy or medical advice.",
        )

    def test_screening_refusal_matches_the_specification(self) -> None:
        self.assertEqual(
            prompts.SCREENING_REFUSAL,
            "I can't interpret screening scores — I'm not a clinician. "
            "A doctor or counselor can walk through your result with you.",
        )

    def test_screening_refusal_is_embedded_in_the_system_prompt(self) -> None:
        self.assertIn(prompts.SCREENING_REFUSAL, prompts.SYSTEM_PROMPT)

    def test_greeting_matches_the_specification(self) -> None:
        self.assertEqual(prompts.GREETING, "Hi, I'm Pulse. How has your week been?")

    def test_crisis_reply_lists_the_four_helplines_verbatim(self) -> None:
        for line in (
            "- 988 Suicide & Crisis Lifeline: call or text 988 (US)",
            "- Crisis Text Line: text HOME to 741741 (US)",
            "- findahelpline.com for help outside the US",
            "- Emergency services: 911 (US) / 112 (EU) if there is immediate danger",
        ):
            with self.subTest(line=line):
                self.assertIn(line, prompts.CRISIS_REPLY)

    def test_crisis_reply_asks_no_questions_and_gives_no_advice(self) -> None:
        self.assertNotIn("?", prompts.CRISIS_REPLY)
        for banned in ("try", "should", "breathe", "cope"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, prompts.CRISIS_REPLY.lower())

    def test_every_error_kind_has_fixed_warm_text(self) -> None:
        self.assertEqual(
            set(prompts.ERROR_MESSAGES),
            {"no_key", "auth", "billing", "rate_limit", "server", "offline", "bad_response"},
        )
        for kind, text in prompts.ERROR_MESSAGES.items():
            with self.subTest(kind=kind):
                self.assertTrue(text.strip())
                self.assertIn("MindPulse", text)
                self.assertNotIn("API key format", text)

    def test_no_error_message_contains_a_secret_placeholder(self) -> None:
        for text in prompts.ERROR_MESSAGES.values():
            with self.subTest(text=text[:40]):
                self.assertNotIn("Bearer", text)
                self.assertNotIn("sk-", text)


class SystemPromptTests(unittest.TestCase):
    def test_system_prompt_is_not_empty_and_has_no_stray_whitespace(self) -> None:
        self.assertTrue(prompts.SYSTEM_PROMPT.strip())
        self.assertEqual(prompts.SYSTEM_PROMPT, prompts.SYSTEM_PROMPT.strip())

    def test_system_prompt_contains_every_section(self) -> None:
        for heading in (
            "IDENTITY & HONETY",
            "HOW YOU SHOW UP",
            "WHAT YOU NEVER DO",
            "CRISIS LANGUAGE",
            "SCOPE",
        ):
            with self.subTest(heading=heading):
                self.assertIn(heading, prompts.SYSTEM_PROMPT)

    def test_system_prompt_states_the_identity_and_limits(self) -> None:
        for expected in (
            "You are an AI.",
            "You are NOT a therapist, doctor, counselor, crisis worker, or a real person",
            "Never diagnose",
            "Never give medical, medication, or dosage advice",
            "not a medical device",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, prompts.SYSTEM_PROMPT)

    def test_system_prompt_carries_the_four_helplines(self) -> None:
        for expected in ("call or text 988", "text HOME to 741741", "findahelpline.com"):
            with self.subTest(expected=expected):
                self.assertIn(expected, prompts.SYSTEM_PROMPT)

    def test_system_prompt_is_stable_text_not_a_template(self) -> None:
        # A format placeholder would mean runtime interpolation of the prompt.
        self.assertNotIn("{", prompts.SYSTEM_PROMPT.replace("&", "and"))
        self.assertNotIn("%s", prompts.SYSTEM_PROMPT)

    def test_journal_context_header_is_explicit_about_quoting(self) -> None:
        self.assertEqual(
            prompts.JOURNAL_CONTEXT_HEADER,
            "CONSENTED JOURNAL CONTEXT (treat as background; do not quote verbatim back)",
        )


if __name__ == "__main__":
    unittest.main()
