"""Daily check-in form (Prompt A, F1).

Validation happens at this UI edge; the crisis gate runs on the journal text
before anything is persisted, and the row is written only after the user has been
shown help.
"""

from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import ttk
from typing import Any

from .. import config
from ..models import CheckIn
from ..safety import is_crisis_response_required
from ..storage import save_check_in, utc_now_iso, validate_check_in
from . import dialogs

VALUE_KEYS: tuple[tuple[str, str], ...] = (
    ("mood", "Mood"),
    ("stress", "Stress"),
    ("energy", "Energy"),
)

HEADING = "Daily check-in"
INTRO = (
    "A quick snapshot of today. There are no wrong answers, and nothing here leaves "
    "this computer unless you choose to share it with the companion."
)
JOURNAL_LABEL = "Journal (optional)"
SAVE_BUTTON = "Save check-in"
CLEAR_BUTTON = "Clear"
SAVE_FAILED = "Couldn't save — your data is still safe."
SAVE_FAILED_TITLE = "Couldn't save"


def build(parent: tk.Misc, state: dict[str, Any]) -> ttk.Frame:
    """Build the check-in form and wire its save/clear actions."""
    frame = ttk.Frame(parent, padding=config.PAD)
    frame.columnconfigure(1, weight=1)
    ttk.Label(frame, text=HEADING, font=config.FONT_TITLE).grid(
        row=0, column=0, columnspan=3, sticky="w"
    )
    ttk.Label(frame, text=INTRO, font=config.FONT_BODY, wraplength=680, justify="left").grid(
        row=1, column=0, columnspan=3, sticky="w", pady=(0, config.PAD)
    )

    variables: dict[str, tk.DoubleVar] = {
        "mood": tk.DoubleVar(master=frame, value=5.0),
        "stress": tk.DoubleVar(master=frame, value=5.0),
        "energy": tk.DoubleVar(master=frame, value=5.0),
        "sleep_hours": tk.DoubleVar(master=frame, value=7.0),
    }
    row = 2
    for key, label in VALUE_KEYS:
        row = _add_scale_row(frame, row, key, label, variables)
    row = _add_sleep_row(frame, row, variables)
    journal, counter = _add_journal_row(frame, row)
    buttons = _add_buttons(frame, row + 2)

    def on_clear() -> None:
        for key, _label in VALUE_KEYS:
            variables[key].set(5.0)
        variables["sleep_hours"].set(7.0)
        journal.delete("1.0", "end")
        _update_counter(counter, journal)
        state["set_status"]("")

    def on_save() -> None:
        check_in = _collect(variables, journal)
        crisis = is_crisis_response_required((), check_in.journal, "")
        if crisis:
            # Help first, storage second: nothing cheerful is shown for risky text.
            dialogs.show_crisis_dialog(
                state["root"], (), on_acknowledge=state["enable_help_banner"]
            )
        try:
            save_check_in(state["conn"], check_in)
        except (sqlite3.Error, ValueError) as error:
            dialogs.show_error_dialog(state["root"], SAVE_FAILED_TITLE, f"{SAVE_FAILED} {error}")
            return
        on_clear()
        state["set_status"](config.CONFIRM_SAVE_MESSAGE)

    clear_button = ttk.Button(buttons, text=CLEAR_BUTTON, command=on_clear)
    clear_button.pack(side="left")
    save_button = ttk.Button(buttons, text=SAVE_BUTTON, command=on_save)
    save_button.pack(side="left", padx=(config.PAD_SMALL, 0))
    save_button.bind("<Return>", lambda _event: on_save())
    frame.bind("<Control-Return>", lambda _event: on_save())
    _update_counter(counter, journal)
    return frame


def _collect(
    variables: dict[str, tk.DoubleVar],
    journal: tk.Text,
) -> CheckIn:
    """Read the widgets into a validated check-in record.

    Raises ``ValueError`` (via :func:`validate_check_in`) for invalid input; the
    caller turns that into a dialog.
    """
    text = journal.get("1.0", "end-1c")
    if len(text) > config.JOURNAL_MAX_CHARS:
        raise ValueError(
            f"Journal entries are limited to {config.JOURNAL_MAX_CHARS} characters "
            f"(this one is {len(text)})."
        )
    return validate_check_in(
        CheckIn(
            created_at=utc_now_iso(),
            mood=int(round(float(variables["mood"].get()))),
            stress=int(round(float(variables["stress"].get()))),
            energy=int(round(float(variables["energy"].get()))),
            sleep_hours=float(variables["sleep_hours"].get()),
            journal=text,
        )
    )


def _add_scale_row(
    frame: ttk.Frame,
    row: int,
    key: str,
    label: str,
    variables: dict[str, tk.DoubleVar],
) -> int:
    """Add one 1-10 scale row with a live numeric readout."""
    ttk.Label(frame, text=label, font=config.FONT_BODY, width=10).grid(
        row=row, column=0, sticky="w", pady=config.PAD_SMALL
    )
    readout = ttk.Label(frame, text="5", font=config.FONT_HEADING, width=3)
    scale = ttk.Scale(
        frame,
        from_=config.SCALE_MIN,
        to=config.SCALE_MAX,
        orient="horizontal",
        length=config.SCALE_WIDGET_LENGTH,
        variable=variables[key],
        command=lambda value, target=readout: target.configure(text=f"{round(float(value))}"),
    )
    scale.grid(row=row, column=1, sticky="w", pady=config.PAD_SMALL)
    readout.grid(row=row, column=2, sticky="w")
    return row + 1


def _add_sleep_row(frame: ttk.Frame, row: int, variables: dict[str, tk.DoubleVar]) -> int:
    """Add the sleep-hours spinbox (0-24 in half-hour steps)."""
    ttk.Label(frame, text="Sleep (hours)", font=config.FONT_BODY, width=10).grid(
        row=row, column=0, sticky="w", pady=config.PAD_SMALL
    )
    ttk.Spinbox(
        frame,
        from_=config.SLEEP_MIN_HOURS,
        to=config.SLEEP_MAX_HOURS,
        increment=config.SLEEP_STEP_HOURS,
        textvariable=variables["sleep_hours"],
        width=6,
        font=config.FONT_BODY,
    ).grid(row=row, column=1, sticky="w", pady=config.PAD_SMALL)
    return row + 1


def _add_journal_row(frame: ttk.Frame, row: int) -> tuple[tk.Text, ttk.Label]:
    """Add the journal box and its character counter."""
    ttk.Label(frame, text=JOURNAL_LABEL, font=config.FONT_BODY).grid(
        row=row, column=0, columnspan=3, sticky="w", pady=(config.PAD, config.PAD_SMALL)
    )
    journal = tk.Text(
        frame,
        height=config.JOURNAL_TEXT_HEIGHT,
        wrap="word",
        font=config.FONT_BODY,
        relief="solid",
        borderwidth=1,
    )
    journal.grid(row=row + 1, column=0, columnspan=2, sticky="nsew")
    frame.rowconfigure(row + 1, weight=1)
    counter = ttk.Label(frame, text="", font=config.FONT_SMALL, foreground=config.COLOR_TEXT_MUTED)
    counter.grid(row=row + 2, column=0, columnspan=2, sticky="e")
    journal.bind("<KeyRelease>", lambda _event: _update_counter(counter, journal))
    return journal, counter


def _update_counter(counter: ttk.Label, journal: tk.Text) -> None:
    """Refresh the ``used / limit`` character counter."""
    used = len(journal.get("1.0", "end-1c"))
    counter.configure(text=f"{used} / {config.JOURNAL_MAX_CHARS}")


def _add_buttons(frame: ttk.Frame, row: int) -> ttk.Frame:
    """Add the button row and return it."""
    buttons = ttk.Frame(frame)
    buttons.grid(row=row, column=0, columnspan=3, sticky="w", pady=(config.PAD, 0))
    return buttons
