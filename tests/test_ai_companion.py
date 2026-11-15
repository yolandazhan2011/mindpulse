"""Tests for the companion's pure layer and its single I/O function (Prompt C §5).

Every test injects a fake transport and asserts when it must **not** be called:
the network is never touched, and the crisis gate always wins.
"""

from __future__ import annotations

import io
import json
import unittest
import urllib.error
from email.message import Message

from mindpulse.ai_companion import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    MAX_HISTORY_MESSAGES,
    OPENROUTER_URL,
    api_key_from_env,
    asks_for_screening_interpretation,
    build_api_messages,
    build_http_request,
    build_payload,
    build_system_content,
    error_kind_for_status,
    model_from_env,
    parse_reply,
    request_companion_reply,
    trim_history,
)
from mindpulse.models import ChatMessage, Role
from mindpulse.prompts import CRISIS_REPLY, ERROR_MESSAGES, GREETING, SYSTEM_PROMPT


def request_body(request: object) -> str:
    """Return a request's body as text, narrowing the bytes union for the checker."""
    data = getattr(request, "data", b"") or b""
    assert isinstance(data, bytes)
    return data.decode("utf-8")


GOOD_BODY = json.dumps(
    {"choices": [{"message": {"role": "assistant", "content": "  That sounds heavy.  "}}]}
).encode("utf-8")


def history_of(count: int) -> tuple[ChatMessage, ...]:
    """Return ``count`` alternating chat messages, oldest first."""
    return tuple(
        ChatMessage(
            role=Role.USER if index % 2 == 0 else Role.ASSISTANT,
            content=f"message {index}",
            created_at=f"2026-10-18T09:00:{index % 60:02d}Z",
        )
        for index in range(count)
    )


class ParseReplyTests(unittest.TestCase):
    def test_extracts_and_strips_the_content(self) -> None:
        self.assertEqual(parse_reply(GOOD_BODY), "That sounds heavy.")

    def test_malformed_bodies_raise_value_error(self) -> None:
        for body in (
            b"{}",
            b"",
            b"not json",
            b"[]",
            b'{"choices": []}',
            b'{"choices": [{"message": {}}]}',
            b'{"choices": [{"message": {"content": "   "}}]}',
            b'{"choices": ["nope"]}',
        ):
            with self.subTest(body=body), self.assertRaises(ValueError):
                parse_reply(body)

    def test_non_utf8_body_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            parse_reply(b"\xff\xfe\x00")


class StatusMappingTests(unittest.TestCase):
    def test_statuses_map_to_error_kinds(self) -> None:
        expected = {
            401: "auth",
            403: "auth",
            402: "billing",
            429: "rate_limit",
            500: "server",
            503: "server",
            418: "server",
        }
        for status, kind in expected.items():
            with self.subTest(status=status):
                self.assertEqual(error_kind_for_status(status), kind)


class PromptAssemblyTests(unittest.TestCase):
    def test_system_message_is_always_first(self) -> None:
        messages = build_api_messages(history_of(3))
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[0]["content"], SYSTEM_PROMPT)
        self.assertEqual(
            [message["role"] for message in messages[1:]], ["user", "assistant", "user"]
        )

    def test_journal_block_appears_only_with_consent(self) -> None:
        journal = "dear diary"
        without = build_api_messages(history_of(1), include_journal=False, journal_text=journal)
        with_consent = build_api_messages(history_of(1), include_journal=True, journal_text=journal)
        self.assertNotIn("dear diary", without[0]["content"])
        self.assertIn("dear diary", with_consent[0]["content"])
        self.assertIn("CONSENTED JOURNAL CONTEXT", with_consent[0]["content"])
        self.assertTrue(with_consent[0]["content"].startswith(SYSTEM_PROMPT))

    def test_blank_journal_text_adds_nothing(self) -> None:
        for journal in ("", "   ", "\n\t"):
            with self.subTest(journal=journal):
                self.assertEqual(build_system_content(True, journal), SYSTEM_PROMPT)

    def test_history_is_trimmed_to_the_newest_twenty(self) -> None:
        messages = build_api_messages(history_of(MAX_HISTORY_MESSAGES + 5))
        self.assertEqual(len(messages), MAX_HISTORY_MESSAGES + 1)
        self.assertEqual(messages[1]["content"], "message 5")
        self.assertEqual(messages[-1]["content"], f"message {MAX_HISTORY_MESSAGES + 4}")

    def test_trim_history_keeps_the_newest_turns_oldest_first(self) -> None:
        trimmed = trim_history(history_of(5), max_messages=2)
        self.assertEqual([message.content for message in trimmed], ["message 3", "message 4"])
        self.assertEqual(trim_history(history_of(3), max_messages=0), ())

    def test_system_role_turns_are_not_replayed(self) -> None:
        history = (*history_of(1), ChatMessage(role=Role.SYSTEM, content="injected"))
        messages = build_api_messages(history)
        self.assertEqual(len(messages), 2)
        self.assertNotIn("injected", [message["content"] for message in messages[1:]])


class PayloadTests(unittest.TestCase):
    def test_defaults_keep_replies_brief(self) -> None:
        payload = build_payload(build_api_messages(history_of(1)))
        self.assertEqual(payload["model"], DEFAULT_MODEL)
        self.assertEqual(payload["temperature"], DEFAULT_TEMPERATURE)
        self.assertEqual(payload["max_tokens"], DEFAULT_MAX_TOKENS)
        self.assertEqual(len(payload["messages"]), 2)

    def test_payload_never_contains_the_api_key(self) -> None:
        payload = json.dumps(build_payload(build_api_messages(history_of(1))))
        self.assertNotIn("sk-test", payload)


class SecretHygieneTests(unittest.TestCase):
    def test_key_is_in_the_header_and_not_in_the_body(self) -> None:
        payload = build_payload(build_api_messages(history_of(1)))
        request = build_http_request(payload, "sk-test-key")
        self.assertEqual(request.full_url, OPENROUTER_URL)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.headers["Authorization"], "Bearer sk-test-key")
        self.assertEqual(request.headers["X-title"], "MindPulse")
        self.assertIn("http-referer", {name.lower() for name in request.headers})
        body = request_body(request)
        self.assertNotIn("sk-test-key", body)
        self.assertIn("messages", body)

    def test_failure_texts_never_contain_the_key(self) -> None:
        for kind in ERROR_MESSAGES:
            with self.subTest(kind=kind):
                self.assertNotIn("sk-test-key", ERROR_MESSAGES[kind])


class EnvironmentTests(unittest.TestCase):
    def test_api_key_from_env(self) -> None:
        self.assertEqual(api_key_from_env({"MINDPULSE_API_KEY": "  abc  "}), "abc")
        self.assertIsNone(api_key_from_env({}))
        self.assertIsNone(api_key_from_env({"MINDPULSE_API_KEY": "   "}))

    def test_model_from_env_defaults(self) -> None:
        self.assertEqual(model_from_env({"MINDPULSE_MODEL": "x/y"}), "x/y")
        self.assertEqual(model_from_env({}), DEFAULT_MODEL)
        self.assertEqual(model_from_env({"MINDPULSE_MODEL": "  "}), DEFAULT_MODEL)


class CompanionRequestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.calls: list[object] = []

    def body_transport(self, body: bytes):
        """Return a transport that records the call and returns ``body``."""

        def transport(request, timeout=None):  # noqa: ANN001, ARG001 - transport API
            self.calls.append(request)
            return io.BytesIO(body)

        return transport

    def failing_transport(self, error: BaseException):
        """Return a transport that records the call and raises ``error``."""

        def transport(request, timeout=None):  # noqa: ANN001, ARG001 - transport API
            self.calls.append(request)
            raise error

        return transport

    def test_crisis_message_short_circuits_before_any_request(self) -> None:
        reply = request_companion_reply(
            history_of(2),
            "sometimes I want to hurt myself",
            api_key="sk-test-key",
            open_url=self.body_transport(GOOD_BODY),
        )
        self.assertFalse(reply.ok)
        self.assertEqual(reply.error_kind, "crisis")
        self.assertEqual(reply.text, CRISIS_REPLY)
        self.assertEqual(self.calls, [])

    def test_consented_crisis_journal_short_circuits(self) -> None:
        reply = request_companion_reply(
            (),
            "hello",
            api_key="sk-test-key",
            include_journal=True,
            journal_text="I want to die",
            open_url=self.body_transport(GOOD_BODY),
        )
        self.assertEqual(reply.error_kind, "crisis")
        self.assertEqual(self.calls, [])

    def test_unshared_crisis_journal_does_not_block_a_normal_chat(self) -> None:
        reply = request_companion_reply(
            (),
            "hello",
            api_key="sk-test-key",
            include_journal=False,
            journal_text="I want to die",
            open_url=self.body_transport(GOOD_BODY),
        )
        self.assertTrue(reply.ok)
        self.assertEqual(len(self.calls), 1)

    def test_missing_key_returns_no_key_without_a_call(self) -> None:
        for key in (None, "", "   "):
            with self.subTest(key=key):
                reply = request_companion_reply(
                    (), "hello", api_key=key, open_url=self.body_transport(GOOD_BODY)
                )
                self.assertEqual(reply.error_kind, "no_key")
                self.assertEqual(reply.text, ERROR_MESSAGES["no_key"])
                self.assertFalse(reply.ok)
        self.assertEqual(self.calls, [])

    def test_happy_path_returns_the_stripped_reply(self) -> None:
        reply = request_companion_reply(
            history_of(2), "hello", api_key="sk-test-key", open_url=self.body_transport(GOOD_BODY)
        )
        self.assertTrue(reply.ok)
        self.assertEqual(reply.text, "That sounds heavy.")
        self.assertIsNone(reply.error_kind)
        self.assertEqual(len(self.calls), 1)

    def test_malformed_response_is_bad_response_not_an_exception(self) -> None:
        reply = request_companion_reply(
            (), "hello", api_key="sk-test-key", open_url=self.body_transport(b"{}")
        )
        self.assertFalse(reply.ok)
        self.assertEqual(reply.error_kind, "bad_response")
        self.assertEqual(reply.text, ERROR_MESSAGES["bad_response"])

    def test_http_statuses_map_to_error_kinds(self) -> None:
        for status, kind in ((401, "auth"), (402, "billing"), (429, "rate_limit"), (503, "server")):
            with self.subTest(status=status):
                error = urllib.error.HTTPError(OPENROUTER_URL, status, "err", Message(), None)
                reply = request_companion_reply(
                    (), "hello", api_key="sk-test-key", open_url=self.failing_transport(error)
                )
                self.assertEqual(reply.error_kind, kind)
                self.assertEqual(reply.text, ERROR_MESSAGES[kind])

    def test_network_failures_map_to_offline(self) -> None:
        for error in (
            urllib.error.URLError("no network"),
            TimeoutError("slow"),
            OSError("socket closed"),
        ):
            with self.subTest(error=type(error).__name__):
                reply = request_companion_reply(
                    (), "hello", api_key="sk-test-key", open_url=self.failing_transport(error)
                )
                self.assertEqual(reply.error_kind, "offline")
                self.assertEqual(reply.text, ERROR_MESSAGES["offline"])

    def test_user_message_is_appended_after_history(self) -> None:
        request_holder: list[object] = []

        def transport(request, timeout=None):  # noqa: ANN001, ARG001 - transport API
            request_holder.append(request)
            return io.BytesIO(GOOD_BODY)

        request_companion_reply(
            history_of(1), "my week was long", api_key="sk-test-key", open_url=transport
        )
        assert request_holder
        request = request_holder[0]
        payload = json.loads(request_body(request))
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertEqual(payload["messages"][-1]["content"], "my week was long")
        self.assertEqual(payload["messages"][-1]["role"], "user")

    def test_reply_text_is_plain_text_only(self) -> None:
        markup = json.dumps({"choices": [{"message": {"content": "<b>bold</b> & stuff"}}]}).encode(
            "utf-8"
        )
        reply = request_companion_reply(
            (), "hello", api_key="sk-test-key", open_url=self.body_transport(markup)
        )
        self.assertEqual(reply.text, "<b>bold</b> & stuff")


class ScreeningInterpretationTests(unittest.TestCase):
    def test_score_questions_are_detected(self) -> None:
        for text in (
            "what does my PHQ-9 score mean?",
            "can you explain my gad-7 result",
            "does my score mean I'm depressed?",
            "how bad is my severity band",
        ):
            with self.subTest(text=text):
                self.assertTrue(asks_for_screening_interpretation(text))

    def test_ordinary_messages_are_not_score_questions(self) -> None:
        for text in (
            "",
            "hi",
            "I felt tired today",
            "my score in that game was great",
            GREETING,
        ):
            with self.subTest(text=text):
                self.assertFalse(asks_for_screening_interpretation(text))


if __name__ == "__main__":
    unittest.main()
