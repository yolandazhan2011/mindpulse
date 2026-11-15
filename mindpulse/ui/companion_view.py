"""The "Pulse" chat screen (Prompt C §6).

Chat is a required feature and is always in the navigation. Model output is
rendered as plain text only. The crisis gate and the screening refusal run before
any request, and a network failure only ever replaces the reply text.
"""

from __future__ import annotations

import contextlib
import sqlite3
import threading
import tkinter as tk
from tkinter import ttk
from typing import Any

from .. import config, storage
from ..ai_companion import (
    asks_for_screening_interpretation,
    assistant_message,
    load_api_key,
    load_model,
    request_companion_reply,
    user_message,
)
from ..models import ChatMessage, Role
from ..prompts import (
    CRISIS_REPLY,
    ERROR_MESSAGES,
    GREETING,
    PERSISTENT_CHAT_DISCLAIMER,
    SCREENING_PAUSED_NOTICE,
    SCREENING_REFUSAL,
)
from ..safety import CHAT_PHRASE_SOURCE, is_crisis_response_required
from . import dialogs

__all__ = ["build", "load_api_key", "load_model"]

HEADING = "Pulse"
INTRO = (
    "Pulse is an AI companion: it reflects, asks questions, and shares the occasional "
    "brain fact. It is not a therapist, and it never interprets questionnaire scores."
)
SEND_BUTTON = "Send"
DELETE_BUTTON = "Delete this conversation"
INPUT_HINT = "Type here, then press Enter to send (Shift+Enter for a new line)."
THINKING = "Pulse is thinking…"
DELETED = "Conversation deleted."
CONSENT_LABEL = config.JOURNAL_CONSENT_LABEL


def build(parent: tk.Misc, state: dict[str, Any]) -> ttk.Frame:
    """Build the chat screen: log, input, consent, disclaimer, and controls."""
    frame = ttk.Frame(parent, padding=config.PAD)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(2, weight=1)

    ttk.Label(frame, text=HEADING, font=config.FONT_TITLE).grid(row=0, column=0, sticky="w")
    ttk.Label(frame, text=INTRO, font=config.FONT_BODY, wraplength=720, justify="left").grid(
        row=1, column=0, sticky="w", pady=(0, config.PAD_SMALL)
    )

    # Pin the palette on the text areas. Tk 9 resolves an unstyled tk.Text to the
    # macOS system colours, which turn near-black in Dark Mode, while the tag colours
    # below stay tuned for the light palette: Pulse's replies became unreadable.
    log = tk.Text(
        frame,
        height=config.CHAT_TEXT_HEIGHT,
        wrap="word",
        state="disabled",
        font=config.FONT_BODY,
        relief="solid",
        borderwidth=1,
        background=config.COLOR_APP_BG,
        foreground=config.COLOR_TEXT,
    )
    log.grid(row=2, column=0, sticky="nsew")
    log.tag_configure("user", foreground=config.COLOR_SERIES_1, font=config.FONT_BODY)
    log.tag_configure("assistant", foreground=config.COLOR_TEXT, font=config.FONT_BODY)
    log.tag_configure(
        "note",
        foreground=config.COLOR_TEXT_MUTED,
        font=config.FONT_SMALL,
    )

    paused = storage.screening_risk_active(state["conn"])
    if paused:
        ttk.Label(
            frame,
            text=SCREENING_PAUSED_NOTICE,
            font=config.FONT_BODY,
            foreground=config.COLOR_HELP_ACCENT,
            wraplength=720,
            justify="left",
        ).grid(row=3, column=0, sticky="w", pady=(config.PAD_SMALL, 0))

    consent = tk.BooleanVar(master=frame, value=config.FEATURE_JOURNAL_SHARING_DEFAULT)
    ttk.Checkbutton(frame, text=CONSENT_LABEL, variable=consent).grid(
        row=4, column=0, sticky="w", pady=(config.PAD_SMALL, 0)
    )

    input_box = tk.Text(
        frame,
        height=3,
        wrap="word",
        font=config.FONT_BODY,
        relief="solid",
        borderwidth=1,
        background=config.COLOR_APP_BG,
        foreground=config.COLOR_TEXT,
        insertbackground=config.COLOR_TEXT,
    )
    input_box.grid(row=5, column=0, sticky="ew", pady=(config.PAD_SMALL, 0))
    ttk.Label(
        frame, text=INPUT_HINT, font=config.FONT_SMALL, foreground=config.COLOR_TEXT_MUTED
    ).grid(row=6, column=0, sticky="w")

    controls = ttk.Frame(frame)
    controls.grid(row=7, column=0, sticky="ew", pady=(config.PAD_SMALL, 0))
    send_button = ttk.Button(controls, text=SEND_BUTTON)
    send_button.pack(side="left")
    ttk.Button(controls, text=DELETE_BUTTON).pack(side="right")

    disclaimer = ttk.Label(
        frame,
        text=PERSISTENT_CHAT_DISCLAIMER,
        font=config.FONT_SMALL,
        foreground=config.COLOR_TEXT_MUTED,
        wraplength=720,
        justify="left",
    )
    disclaimer.grid(row=8, column=0, sticky="w", pady=(config.PAD_SMALL, 0))

    widgets: dict[str, Any] = {
        "log": log,
        "input": input_box,
        "consent": consent,
        "send": send_button,
        "paused": paused,
    }

    def reload_log() -> None:
        _render_log(widgets, state)

    def on_send(_event: tk.Event[tk.Misc] | None = None) -> str:
        _handle_send(widgets, state, reload_log)
        return "break"

    def on_delete() -> None:
        try:
            storage.delete_conversation(state["conn"])
        except sqlite3.Error:
            dialogs.show_error_dialog(state["root"], "Couldn't delete", "Nothing was changed.")
            return
        state["set_status"](DELETED)
        reload_log()

    send_button.configure(command=on_send)
    controls.winfo_children()[1].configure(command=on_delete)  # type: ignore[attr-defined]
    input_box.bind("<Return>", on_send)
    input_box.bind("<Shift-Return>", lambda _event: input_box.insert("insert", "\n"))

    _handle_pending_screening_request(state)
    _render_log(widgets, state)
    if paused:
        widget_state = "disabled"
        input_box.configure(state=widget_state)
        send_button.state(["disabled"])
    else:
        input_box.focus_set()
    return frame


def _handle_pending_screening_request(state: dict[str, Any]) -> None:
    """Answer a queued "explain my result" request locally, with no API call."""
    instrument_name = state.pop("screening_explanation_request", None)
    if not instrument_name:
        return
    try:
        storage.append_chat_message(
            state["conn"], assistant_message(SCREENING_REFUSAL, storage.utc_now_iso())
        )
    except (sqlite3.Error, ValueError):
        return


def _render_log(widgets: dict[str, Any], state: dict[str, Any]) -> None:
    """Redraw the conversation from storage, plus the canned greeting and notices."""
    log: tk.Text = widgets["log"]
    try:
        messages = storage.load_chat_messages(state["conn"])
    except sqlite3.Error:
        messages = ()
    log.configure(state="normal")
    log.delete("1.0", "end")
    if not state.get("api_key"):
        _append(log, ERROR_MESSAGES["no_key"] + "\n\n", "note")
    if not messages:
        _append(log, f"{GREETING}\n\n", "assistant")
    for message in messages:
        _append_message(log, message)
    log.configure(state="disabled")
    log.see("end")


def _append_message(log: tk.Text, message: ChatMessage) -> None:
    """Append one stored message with a role label."""
    if Role(message.role) is Role.USER:
        _append(log, "You: ", "user")
        _append(log, f"{message.content}\n\n", "user")
        return
    _append(log, "Pulse: ", "assistant")
    _append(log, f"{message.content}\n\n", "assistant")


def _append(log: tk.Text, text: str, tag: str) -> None:
    """Append plain text with a tag. Never interprets markup."""
    log.insert("end", text, tag)


def _handle_send(
    widgets: dict[str, Any],
    state: dict[str, Any],
    reload_log: Any,
) -> None:
    """Send one message: crisis gate, score refusal, then (only then) the network."""
    if widgets["paused"]:
        return
    input_box: tk.Text = widgets["input"]
    text = input_box.get("1.0", "end-1c").strip()
    if not text:
        return
    input_box.delete("1.0", "end")
    if _is_sending(widgets):
        return
    try:
        history = storage.load_chat_messages(state["conn"])
        storage.append_chat_message(state["conn"], user_message(text, storage.utc_now_iso()))
    except (sqlite3.Error, ValueError):
        dialogs.show_error_dialog(state["root"], "Couldn't send", "Your message was not saved.")
        return
    if is_crisis_response_required((), "", text):
        _store_reply(state, CRISIS_REPLY)
        reload_log()
        dialogs.show_crisis_dialog(
            state["root"],
            (CHAT_PHRASE_SOURCE,),
            on_acknowledge=state["enable_help_banner"],
        )
        return
    if asks_for_screening_interpretation(text):
        # Local refusal: no request is made (Prompt B §7.5).
        _store_reply(state, SCREENING_REFUSAL)
        reload_log()
        return
    reload_log()
    _request_in_background(widgets, state, history, text, reload_log)


def _is_sending(widgets: dict[str, Any]) -> bool:
    """Return True while a request is in flight."""
    return bool(widgets.get("sending"))


def _store_reply(state: dict[str, Any], text: str) -> None:
    """Persist an app-produced assistant message."""
    with contextlib.suppress(sqlite3.Error, ValueError):
        storage.append_chat_message(state["conn"], assistant_message(text, storage.utc_now_iso()))


def _request_in_background(
    widgets: dict[str, Any],
    state: dict[str, Any],
    history: tuple[ChatMessage, ...],
    text: str,
    reload_log: Any,
) -> None:
    """Run the HTTP call off the UI thread, then update widgets on the main thread."""
    widgets["sending"] = True
    widgets["send"].state(["disabled"])
    state["set_status"](THINKING)
    consent = bool(widgets["consent"].get())
    journal_text = _latest_journal(state) if consent else ""
    root = state["root"]

    def worker() -> None:
        reply = request_companion_reply(
            history,
            text,
            api_key=state["api_key"],
            include_journal=consent,
            journal_text=journal_text,
            model=state["model"],
        )
        root.after(0, lambda: _finish_reply(widgets, state, reply, reload_log))

    threading.Thread(target=worker, daemon=True).start()


def _finish_reply(
    widgets: dict[str, Any],
    state: dict[str, Any],
    reply: Any,
    reload_log: Any,
) -> None:
    """Store the reply, refresh the log, and re-enable the controls."""
    widgets["sending"] = False
    widgets["send"].state(["!disabled"])
    state["set_status"]("")
    _store_reply(state, reply.text)
    reload_log()
    if reply.error_kind == "crisis":
        dialogs.show_crisis_dialog(
            state["root"],
            (CHAT_PHRASE_SOURCE,),
            on_acknowledge=state["enable_help_banner"],
        )


def _latest_journal(state: dict[str, Any]) -> str:
    """Return the newest check-in's journal text (sent only with consent)."""
    try:
        latest = storage.latest_check_in(state["conn"])
    except sqlite3.Error:
        return ""
    return latest.journal if latest else ""
