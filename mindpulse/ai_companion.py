"""OpenRouter client for the "Pulse" companion (Prompt C §3).

Standard library only: ``json``, ``urllib.request``, ``urllib.error``, ``os``, and
``contextlib``. No third-party HTTP library is used or needed.

Everything that can be pure is pure: history trimming, payload construction,
request construction, response parsing, and error classification. Exactly one
function performs I/O (:func:`request_companion_reply`) and it accepts an injected
transport so tests never touch the network.

Safety ordering is a property of this module: the deterministic crisis gate runs
*before* the key check and *before* any request object exists. Nothing the model
returns is ever executed, parsed as markup, or trusted.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass
from typing import Any

from . import prompts
from .config import CHAT_HISTORY_LIMIT, ENV_API_KEY, ENV_MODEL
from .models import ChatMessage, Role
from .safety import is_crisis_response_required, normalize_text

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"
DEFAULT_TEMPERATURE = 0.6
DEFAULT_MAX_TOKENS = 400
DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_HISTORY_MESSAGES = CHAT_HISTORY_LIMIT

#: Identifies the app to OpenRouter; never contains secrets.
HTTP_REFERER = "https://github.com/mindpulse/mindpulse"
APP_TITLE = "MindPulse"

#: Signature of the injected transport: ``(request, timeout) -> readable response``.
OpenUrl = Callable[..., Any]

#: Words that mark a question about a screening result, and words that ask for
#: interpretation. Both must be present before the local refusal is used.
_SCORE_WORDS: tuple[str, ...] = (
    "phq",
    "phq-9",
    "phq9",
    "gad",
    "gad-7",
    "gad7",
    "score",
    "scores",
    "severity",
    "screening",
    "questionnaire result",
    "my result",
    "my results",
)
_INTERPRET_WORDS: tuple[str, ...] = (
    "mean",
    "means",
    "meaning",
    "interpret",
    "explain",
    "diagnose",
    "diagnosis",
    "do i have",
    "am i depressed",
    "am i anxious",
    "how bad",
    "how serious",
    "what does",
)


@dataclass(frozen=True)
class CompanionReply:
    """One companion reply: ``error_kind`` is ``None`` only on success."""

    ok: bool
    text: str
    error_kind: str | None = None


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def trim_history(
    messages: Sequence[ChatMessage],
    max_messages: int = MAX_HISTORY_MESSAGES,
) -> tuple[ChatMessage, ...]:
    """Return only the newest ``max_messages`` turns, oldest first."""
    if max_messages <= 0:
        return ()
    history = tuple(messages)
    return history[-max_messages:]


def build_system_content(include_journal: bool, journal_text: str) -> str:
    """Return the system message content, optionally with a consensual journal block.

    The journal is appended only when the user has consented **and** the text has
    content. The block is clearly delimited and labelled as background.
    """
    prompt = prompts.SYSTEM_PROMPT
    if not include_journal or not journal_text.strip():
        return prompt
    return f"{prompt}\n\n{prompts.JOURNAL_CONTEXT_HEADER}\n{journal_text.strip()}"


def build_api_messages(
    history: Sequence[ChatMessage],
    include_journal: bool = False,
    journal_text: str = "",
) -> list[dict[str, str]]:
    """Return the OpenRouter wire messages, with the system message always first.

    Order is a safety property: user text can never displace or edit the system
    prompt, because the system message is rebuilt as message 0 on every call.
    """
    system_message = {
        "role": Role.SYSTEM.value,
        "content": build_system_content(include_journal, journal_text),
    }
    turns = [
        {"role": Role(message.role).value, "content": message.content}
        for message in trim_history(history)
        if Role(message.role) in (Role.USER, Role.ASSISTANT)
    ]
    return [system_message, *turns]


def build_payload(
    api_messages: Sequence[Mapping[str, str]],
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> dict[str, Any]:
    """Return the JSON body for a chat-completions request.

    Conservative defaults (0.6 temperature, 400 tokens) keep replies brief and in
    character. The API key is never part of the payload.
    """
    return {
        "model": model,
        "messages": [dict(message) for message in api_messages],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }


def build_http_request(payload: Mapping[str, Any], api_key: str) -> urllib.request.Request:
    """Return a POST request with the JSON body and the bearer token in its header.

    The key lives only in the ``Authorization`` header: never in the body, never in
    a log line, never in a user-facing message.
    """
    body = json.dumps(payload).encode("utf-8")
    return urllib.request.Request(
        OPENROUTER_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": HTTP_REFERER,
            "X-Title": APP_TITLE,
        },
        method="POST",
    )


def parse_reply(body: bytes) -> str:
    """Return ``choices[0].message.content`` stripped from a response body.

    Raises ``ValueError`` for any malformed shape or empty content: the whole
    response is untrusted and only that one string is ever taken from it.
    """
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Response body is not valid JSON") from error
    if not isinstance(payload, Mapping):
        raise ValueError("Response body is not a JSON object")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("Response has no choices")
    first = choices[0]
    if not isinstance(first, Mapping):
        raise ValueError("Response choice is not an object")
    message = first.get("message")
    if not isinstance(message, Mapping):
        raise ValueError("Response choice has no message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Response message content is empty")
    return content.strip()


def error_kind_for_status(status: int) -> str:
    """Map an HTTP status to an error kind: auth, billing, rate_limit, or server."""
    if status in (401, 403):
        return "auth"
    if status == 402:
        return "billing"
    if status == 429:
        return "rate_limit"
    return "server"


def api_key_from_env(env: Mapping[str, str]) -> str | None:
    """Return the stripped ``MINDPULSE_API_KEY`` value, or ``None`` when unset."""
    value = env.get(ENV_API_KEY)
    if value is None or not value.strip():
        return None
    return value.strip()


def model_from_env(env: Mapping[str, str]) -> str:
    """Return ``MINDPULSE_MODEL`` when set, else :data:`DEFAULT_MODEL`."""
    value = env.get(ENV_MODEL)
    if value is None or not value.strip():
        return DEFAULT_MODEL
    return value.strip()


def failure_reply(error_kind: str) -> CompanionReply:
    """Return a failed :class:`CompanionReply` carrying the fixed message."""
    text = prompts.ERROR_MESSAGES.get(
        error_kind,
        prompts.ERROR_MESSAGES["server"],
    )
    return CompanionReply(ok=False, text=text, error_kind=error_kind)


def crisis_reply() -> CompanionReply:
    """Return the fixed crisis reply used instead of any API call."""
    return CompanionReply(ok=False, text=prompts.CRISIS_REPLY, error_kind="crisis")


def asks_for_screening_interpretation(text: str) -> bool:
    """Return True when a message asks what a screening score means.

    Deterministic word matching, so the app can answer locally with
    :data:`prompts.SCREENING_REFUSAL` without contacting the model.
    """
    normalized = normalize_text(text)
    if not normalized:
        return False
    mentions_score = any(word in normalized for word in _SCORE_WORDS)
    asks_meaning = any(word in normalized for word in _INTERPRET_WORDS)
    return mentions_score and asks_meaning


def assistant_message(text: str, created_at: str = "") -> ChatMessage:
    """Return a :class:`ChatMessage` for an assistant turn."""
    return ChatMessage(role=Role.ASSISTANT, content=text, created_at=created_at)


def user_message(text: str, created_at: str = "") -> ChatMessage:
    """Return a :class:`ChatMessage` for a user turn."""
    return ChatMessage(role=Role.USER, content=text, created_at=created_at)


# ---------------------------------------------------------------------------
# The single I/O function
# ---------------------------------------------------------------------------


def request_companion_reply(
    history: Sequence[ChatMessage],
    user_text: str,
    *,
    api_key: str | None,
    include_journal: bool = False,
    journal_text: str = "",
    model: str = DEFAULT_MODEL,
    open_url: OpenUrl | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> CompanionReply:
    """Return the companion's reply to ``user_text``, or a fixed failure reply.

    Order of operations, which must not change:

    1. Crisis gate first: if self-harm or crisis language appears in the message
       (or in journal text that would be shared), return :data:`prompts.CRISIS_REPLY`
       with ``error_kind="crisis"``. No request is built and no network call happens.
    2. Key check: a missing key returns ``no_key`` without contacting anything.
    3. Build and send through the injected transport.
    4. Classify the outcome: success, HTTP status, offline, or bad response. No
       exception ever escapes to the UI layer.
    """
    if is_crisis_response_required((), journal_text if include_journal else "", user_text):
        return crisis_reply()
    if api_key is None or not api_key.strip():
        return failure_reply("no_key")
    transport = open_url or urllib.request.urlopen
    outgoing = (*trim_history(history), user_message(user_text))
    request = build_http_request(
        build_payload(
            build_api_messages(outgoing, include_journal, journal_text),
            model=model,
        ),
        api_key.strip(),
    )
    try:
        body = _read_response(transport, request, timeout)
    except urllib.error.HTTPError as error:
        return failure_reply(error_kind_for_status(int(error.code)))
    except (urllib.error.URLError, TimeoutError, OSError):
        return failure_reply("offline")
    try:
        return CompanionReply(ok=True, text=parse_reply(body), error_kind=None)
    except ValueError:
        return failure_reply("bad_response")


def _read_response(transport: OpenUrl, request: urllib.request.Request, timeout: float) -> bytes:
    """Perform the request through ``transport`` and return the response body."""
    with closing(transport(request, timeout=timeout)) as response:
        return response.read()


# ---------------------------------------------------------------------------
# Environment wrappers (thin)
# ---------------------------------------------------------------------------


def load_api_key() -> str | None:
    """Return the API key from the process environment, or ``None``."""
    return api_key_from_env(os.environ)


def load_model() -> str:
    """Return the configured model name from the process environment."""
    return model_from_env(os.environ)
