"""PHQ-9 / GAD-7 questionnaire flow (Prompt A F2, Prompt B §9).

One item per screen, no default selection, Back/Next/Skip, a progress label, the
optional impairment follow-up, and the crisis gate running before the result is
shown. The flow is a plain dictionary, not an object.
"""

from __future__ import annotations

import contextlib
import sqlite3
import tkinter as tk
from tkinter import ttk
from typing import Any

from .. import config
from ..instruments import (
    FREE_TEXT_PLACEHOLDER,
    IMPAIRMENT_OPTIONS,
    IMPAIRMENT_UNANSWERED,
    IMPAIRMENT_UNANSWERED_LABEL,
    any_item_answered,
    get_instrument,
    instrument_ids,
)
from ..models import Instrument
from ..safety import is_crisis_response_required, risk_sources
from ..scoring import build_screening, result_lines
from ..storage import save_screening, utc_now_iso
from . import dialogs

HEADING = "Questionnaires"
INTRO = (
    "Two short, validated screening questionnaires. Each is answered one question at "
    "a time, and you can leave at any point without saving anything."
)
PICKER_NOTE = (
    "These screen and educate. They are not a diagnosis, and MindPulse never "
    "interprets a score for you."
)
BACK_BUTTON = "Back"
NEXT_BUTTON = "Next"
SKIP_BUTTON = "Skip this survey"
FINISH_BUTTON = "Finish"
KEEP_GOING = "Keep going"
LEAVE = "Leave"
SAVE_FAILED_TITLE = "Couldn't save this result"
SAVE_FAILED = "Something went wrong saving your answers. Nothing was changed."


def build(parent: tk.Misc, state: dict[str, Any]) -> ttk.Frame:
    """Build the questionnaire screen and start on the instrument picker."""
    frame = ttk.Frame(parent, padding=config.PAD)
    frame.pack_propagate(False)
    container = ttk.Frame(frame)
    container.pack(fill="both", expand=True)
    flow: dict[str, Any] = {
        "stage": "picker",
        "instrument": None,
        "index": 0,
        "answers": [],
        "impairment": None,
        "free_text": "",
    }
    root = state["root"]
    key_handler = root.bind("<KeyPress>", lambda event: _handle_key(event, container, state, flow))
    frame.bind(
        "<Destroy>",
        lambda event: _unbind_key_handler(root, event, frame, key_handler),
    )
    _render(container, state, flow)
    return frame


def _unbind_key_handler(
    root: tk.Misc,
    event: tk.Event[tk.Misc],
    frame: ttk.Frame,
    key_handler: str | None,
) -> None:
    """Remove the view's key handler when the view frame itself is destroyed."""
    if event.widget is not frame or not key_handler:
        return
    with contextlib.suppress(tk.TclError):  # already unbound
        root.unbind("<KeyPress>", key_handler)


def _render(container: ttk.Frame, state: dict[str, Any], flow: dict[str, Any]) -> None:
    """Rebuild the current step of the flow."""
    for child in container.winfo_children():
        child.destroy()
    match flow["stage"]:
        case "item":
            _render_item(container, state, flow)
        case "impairment":
            _render_impairment(container, state, flow)
        case _:
            _render_picker(container, state, flow)


def _render_picker(container: ttk.Frame, state: dict[str, Any], flow: dict[str, Any]) -> None:
    """Show the two questionnaires to choose from."""
    ttk.Label(container, text=HEADING, font=config.FONT_TITLE).pack(anchor="w")
    ttk.Label(container, text=INTRO, font=config.FONT_BODY, wraplength=680, justify="left").pack(
        anchor="w", pady=(0, config.PAD)
    )
    for instrument_id in instrument_ids():
        spec = get_instrument(instrument_id)
        card = ttk.Frame(container, padding=config.PAD)
        card.pack(fill="x", pady=config.PAD_SMALL)
        ttk.Label(
            card, text=f"{spec.display_name} — {spec.full_name}", font=config.FONT_HEADING
        ).pack(anchor="w")
        ttk.Label(
            card,
            text=f"{spec.item_count} questions about the past 2 weeks. {spec.attribution}",
            font=config.FONT_SMALL,
            foreground=config.COLOR_TEXT_MUTED,
            wraplength=640,
            justify="left",
        ).pack(anchor="w", pady=(2, config.PAD_SMALL))
        ttk.Button(
            card,
            text=f"Start {spec.display_name}",
            command=lambda chosen=instrument_id: _start(container, state, flow, chosen),
        ).pack(anchor="w")
    ttk.Label(
        container,
        text=PICKER_NOTE,
        font=config.FONT_SMALL,
        foreground=config.COLOR_TEXT_MUTED,
        wraplength=640,
        justify="left",
    ).pack(anchor="w", pady=(config.PAD, 0))


def _start(
    container: ttk.Frame,
    state: dict[str, Any],
    flow: dict[str, Any],
    instrument_id: Instrument,
) -> None:
    """Begin a questionnaire: reset answers and show item 1."""
    spec = get_instrument(instrument_id)
    flow.update(
        stage="item",
        instrument=Instrument(instrument_id),
        index=0,
        answers=[None] * spec.item_count,
        impairment=None,
        free_text="",
    )
    state["set_status"]("")
    _render(container, state, flow)


def _render_item(container: ttk.Frame, state: dict[str, Any], flow: dict[str, Any]) -> None:
    """Show one item: stem, verbatim text, four answer buttons, Back/Next/Skip."""
    spec = get_instrument(flow["instrument"])
    index: int = flow["index"]
    item = spec.items[index]
    chosen = flow["answers"][index]

    ttk.Label(
        container,
        text=f"{spec.display_name} · Question {index + 1} of {spec.item_count}",
        font=config.FONT_HEADING,
    ).pack(anchor="w")
    ttk.Label(
        container,
        text=spec.instruction_stem,
        font=config.FONT_SMALL,
        foreground=config.COLOR_TEXT_MUTED,
        wraplength=680,
        justify="left",
    ).pack(anchor="w", pady=(config.PAD_SMALL, config.PAD))
    ttk.Label(
        container,
        text=f"{item.item_number}. {item.text}",
        font=config.FONT_ITEM,
        wraplength=680,
        justify="left",
    ).pack(anchor="w", pady=(0, config.PAD))

    options = ttk.Frame(container)
    options.pack(fill="x")
    for weight, label in spec.response_options:
        marker = "● " if chosen == weight else "○ "
        ttk.Button(
            options,
            text=f"{marker}{label}",
            width=42,
            command=lambda value=weight: _choose(container, state, flow, value),
        ).pack(anchor="w", pady=2)

    buttons = ttk.Frame(container)
    buttons.pack(fill="x", pady=(config.PAD, 0))
    back_button = ttk.Button(
        buttons,
        text=BACK_BUTTON,
        command=lambda: _back(container, state, flow),
        state="normal" if index > 0 else "disabled",
    )
    back_button.pack(side="left")
    ttk.Button(
        buttons,
        text=SKIP_BUTTON,
        command=lambda: _leave(container, state, flow),
    ).pack(side="right")
    next_button = ttk.Button(
        buttons,
        text=NEXT_BUTTON,
        command=lambda: _next(container, state, flow),
        state="normal" if chosen is not None else "disabled",
    )
    next_button.pack(side="right", padx=(0, config.PAD_SMALL))
    if chosen is not None:
        next_button.focus_set()


def _choose(
    container: ttk.Frame,
    state: dict[str, Any],
    flow: dict[str, Any],
    weight: int,
) -> None:
    """Record an answer for the current item and refresh the step."""
    flow["answers"][flow["index"]] = weight
    _render(container, state, flow)


def _back(container: ttk.Frame, state: dict[str, Any], flow: dict[str, Any]) -> None:
    """Go to the previous item, keeping the answers already given."""
    if flow["index"] > 0:
        flow["index"] -= 1
        _render(container, state, flow)


def _next(container: ttk.Frame, state: dict[str, Any], flow: dict[str, Any]) -> None:
    """Advance to the next item, the impairment follow-up, or submission."""
    spec = get_instrument(flow["instrument"])
    if flow["index"] + 1 < spec.item_count:
        flow["index"] += 1
        _render(container, state, flow)
        return
    if any_item_answered(flow["instrument"], tuple(flow["answers"])):
        flow["stage"] = "impairment"
        _render(container, state, flow)
        return
    _submit(state, flow, container)


def _render_impairment(
    container: ttk.Frame,
    state: dict[str, Any],
    flow: dict[str, Any],
) -> None:
    """Show the impairment follow-up (unscored) and the optional free-text box."""
    spec = get_instrument(flow["instrument"])
    ttk.Label(
        container, text=f"{spec.display_name} · One last thing", font=config.FONT_HEADING
    ).pack(anchor="w")
    ttk.Label(
        container,
        text=spec.impairment_question,
        font=config.FONT_BODY,
        wraplength=680,
        justify="left",
    ).pack(anchor="w", pady=(config.PAD_SMALL, config.PAD))

    for stored_value, label in IMPAIRMENT_OPTIONS:
        marker = "● " if flow["impairment"] == stored_value else "○ "
        ttk.Button(
            container,
            text=f"{marker}{label}",
            width=42,
            command=lambda value=stored_value: _set_impairment(container, state, flow, value),
        ).pack(anchor="w", pady=2)
    unanswered_marker = "● " if flow["impairment"] == IMPAIRMENT_UNANSWERED else "○ "
    ttk.Button(
        container,
        text=f"{unanswered_marker}{IMPAIRMENT_UNANSWERED_LABEL}",
        width=42,
        command=lambda: _set_impairment(container, state, flow, IMPAIRMENT_UNANSWERED),
    ).pack(anchor="w", pady=(2, config.PAD))

    ttk.Label(container, text=FREE_TEXT_PLACEHOLDER, font=config.FONT_BODY).pack(anchor="w")
    free_text = tk.Text(
        container, height=4, wrap="word", font=config.FONT_BODY, relief="solid", borderwidth=1
    )
    free_text.pack(fill="x", pady=(2, config.PAD))
    if flow["free_text"]:
        free_text.insert("1.0", flow["free_text"])

    buttons = ttk.Frame(container)
    buttons.pack(fill="x")
    ttk.Button(
        buttons, text=BACK_BUTTON, command=lambda: _back_from_impairment(container, state, flow)
    ).pack(side="left")
    ttk.Button(
        buttons,
        text=FINISH_BUTTON,
        command=lambda: _submit(state, flow, container, free_text.get("1.0", "end-1c")),
    ).pack(side="right")


def _set_impairment(
    container: ttk.Frame,
    state: dict[str, Any],
    flow: dict[str, Any],
    value: str,
) -> None:
    """Record the impairment answer (never scored) and refresh."""
    flow["impairment"] = value
    _render(container, state, flow)


def _back_from_impairment(
    container: ttk.Frame,
    state: dict[str, Any],
    flow: dict[str, Any],
) -> None:
    """Return from the follow-up to the last scored item."""
    flow["stage"] = "item"
    flow["index"] = get_instrument(flow["instrument"]).item_count - 1
    _render(container, state, flow)


def _submit(
    state: dict[str, Any],
    flow: dict[str, Any],
    container: ttk.Frame,
    free_text: str = "",
) -> None:
    """Score, gate, persist, and show the result - in that order (Prompt D §3.3)."""
    instrument: Instrument = flow["instrument"]
    answers = tuple(-1 if answer is None else int(answer) for answer in flow["answers"])
    flow["free_text"] = free_text
    screening_answers = answers if instrument is Instrument.PHQ9 else ()
    gate_open = is_crisis_response_required(screening_answers, free_text, "")
    try:
        screening = build_screening(
            instrument,
            answers,
            utc_now_iso(),
            impairment=flow["impairment"],
            free_text=free_text,
        )
    except ValueError as error:
        dialogs.show_error_dialog(state["root"], SAVE_FAILED_TITLE, f"{SAVE_FAILED} {error}")
        return
    try:
        save_screening(state["conn"], screening)
    except (sqlite3.Error, ValueError) as error:
        dialogs.show_error_dialog(state["root"], SAVE_FAILED_TITLE, f"{SAVE_FAILED} {error}")
        return
    if gate_open:
        # Nothing renders between the risky answers and the resources panel.
        dialogs.show_crisis_dialog(
            state["root"],
            risk_sources(screening_answers, free_text, ""),
            on_acknowledge=state["enable_help_banner"],
        )
    dialogs.show_result_dialog(
        state["root"],
        result_lines(instrument, screening),
        show_help_button=screening.risk_flag,
        on_help=lambda: _open_help(state),
        on_explain=lambda: _explain_with_ai(state, instrument),
    )
    flow.update(stage="picker", instrument=None, index=0, answers=[], impairment=None)
    _render(container, state, flow)


def _open_help(state: dict[str, Any]) -> None:
    """Open the crisis dialog from the result screen (dismissal keeps a banner)."""
    dialogs.show_crisis_dialog(state["root"], (), on_acknowledge=state["enable_help_banner"])


def _explain_with_ai(state: dict[str, Any], instrument: Instrument) -> None:
    """Send the user to the companion, which answers locally with its refusal.

    The companion never interprets a score, so this makes no API call (Prompt B §7.5).
    """
    state["screening_explanation_request"] = get_instrument(instrument).display_name
    state["show_view"]("companion")


def _leave(container: ttk.Frame, state: dict[str, Any], flow: dict[str, Any]) -> None:
    """Leave the questionnaire without writing anything, discarding partial answers."""
    flow.update(stage="picker", instrument=None, index=0, answers=[], impairment=None)
    state["set_status"]("")
    _render(container, state, flow)


def _handle_key(
    event: tk.Event[tk.Misc],
    container: ttk.Frame,
    state: dict[str, Any],
    flow: dict[str, Any],
) -> None:
    """Keyboard shortcuts: 1-4 choose, Enter advances, BackSpace goes back, Esc exits."""
    if flow["stage"] not in ("item", "impairment"):
        return
    if event.keysym == "Escape":
        if dialogs.confirm_leave_questionnaire(state["root"]):
            _leave(container, state, flow)
        return
    if flow["stage"] != "item":
        return
    if event.char in {"1", "2", "3", "4"}:
        _choose(container, state, flow, int(event.char) - 1)
        return
    if event.keysym == "Return" and flow["answers"][flow["index"]] is not None:
        _next(container, state, flow)
        return
    if event.keysym == "BackSpace":
        _back(container, state, flow)
