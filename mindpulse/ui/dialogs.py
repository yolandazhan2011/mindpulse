"""Dialogs: the crisis dialog, the About dialog, results, errors (Prompt D §4).

The crisis dialog is fixed human text plus helplines. It never contains anything
AI-generated, any coping advice, any score, or any question. Its copy is defined
once here and tested by literal equality.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import tkinter as tk
import webbrowser
from collections.abc import Callable, Sequence
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .. import config
from ..config import QUIT_PROMPT
from ..instruments import ATTRIBUTIONS, CITATIONS
from ..prompts import SCREENING_REFUSAL
from ..resources import (
    PRIMARY_LIFELINE_ID,
    WEB_HELPLINE_ID,
    resource_by_id,
    resource_line,
    resources_in_display_order,
    tel_uri,
)
from ..safety import SELF_HARM_INDICATOR
from ..scoring import RESULT_DISCLAIMER, RESULT_NEXT_STEP, RISK_RESULT_BANNER
from ..storage import erase_all_data, export_all_data

LOGGER = logging.getLogger(__name__)

#: Crisis dialog copy - single source of truth, fixed, never generated.
CRISIS_TITLE = "You matter, and help is available right now"
CRISIS_BODY = (
    "Whatever you're feeling right now, you don't have to face it alone. People are "
    "ready to listen and help — right now, any time of day or night."
)
CRISIS_ITEMS9_NOTE = (
    "Your questionnaire answers included thoughts of self-harm or of being better off "
    "dead. You deserve support from a real person right now."
)
CRISIS_SAFE_BUTTON = "I'm safe right now"
CRISIS_CALL_BUTTON = "Call or text 988"
CRISIS_FIND_HELP_BUTTON = "Find help in my country"
CRISIS_CALL_FALLBACK = "Please call or text 988 now."

ABOUT_TITLE = "About MindPulse"
EXPORT_BUTTON = "Export my data"
ERASE_BUTTON = "Erase all my data"
CLOSE_BUTTON = "Close"
EXPORT_TITLE = "Export my data"
EXPORT_DONE = "Your data was written to the file you chose."
EXPORT_FAILED = "Couldn't write that file. Your data in MindPulse is unchanged."
ERASE_CONFIRM_TITLE = "Erase all my data?"
ERASE_CONFIRM_BODY = (
    "This deletes every check-in, questionnaire result, and chat message from this "
    "computer. It cannot be undone."
)
ERASE_DONE = "All MindPulse data was erased from this computer."
RESULT_HELP_BUTTON = "Get help now"
RESULT_EXPLAIN_BUTTON = "Explain my result with AI"


def open_external(uri: str) -> bool:
    """Open ``uri`` with the platform handler. Returns False if it could not open."""
    try:
        return bool(webbrowser.open(uri))
    except (webbrowser.Error, OSError) as error:
        LOGGER.warning("Could not open the %s link: %s", uri.partition(":")[0], error)
        return False


def _center_on_parent(dialog: tk.Toplevel, parent: tk.Misc) -> None:
    """Place ``dialog`` near the centre of ``parent`` without exceeding the screen."""
    dialog.update_idletasks()
    width = max(dialog.winfo_reqwidth(), 520)
    height = max(dialog.winfo_reqheight(), 360)
    parent_x = parent.winfo_rootx() if parent is not None else 0
    parent_y = parent.winfo_rooty() if parent is not None else 0
    offset_x = max(parent_x + (parent.winfo_width() - width) // 2, 20)
    offset_y = max(parent_y + (parent.winfo_height() - height) // 3, 20)
    dialog.geometry(f"{width}x{height}+{offset_x}+{offset_y}")


def _make_modal(dialog: tk.Toplevel, parent: tk.Misc) -> None:
    """Raise and modalise ``dialog``, taking focus from the parent window."""
    # tk stubs type wm_transient as Wm | Tcl_Obj; every caller passes the root window.
    dialog.transient(parent)  # pyright: ignore[reportArgumentType, reportCallIssue]
    dialog.grab_set()
    dialog.focus_force()
    _center_on_parent(dialog, parent)


def show_crisis_dialog(
    parent: tk.Misc,
    risk_sources: Sequence[str] = (),
    on_acknowledge: Callable[[], None] | None = None,
) -> tk.Toplevel:
    """Show the modal crisis dialog (Prompt D §4).

    Content is fixed copy plus the resources from :mod:`mindpulse.resources`.
    ``risk_sources`` containing ``phq9_item9`` appends the questionnaire sentence.
    Closing the dialog always leaves a way back to help: ``on_acknowledge`` is
    called on dismissal so the caller can show the persistent banner.
    """
    dialog = tk.Toplevel(parent)
    dialog.title("Help is available right now")
    dialog.configure(background=config.COLOR_APP_BG)
    dialog.resizable(True, True)

    def acknowledge(_event: tk.Event[tk.Misc] | None = None) -> None:
        try:
            dialog.grab_release()
        finally:
            dialog.destroy()
            if on_acknowledge is not None:
                on_acknowledge()

    frame = ttk.Frame(dialog, padding=config.PAD * 2)
    frame.pack(fill="both", expand=True)
    frame.columnconfigure(0, weight=1)

    ttk.Label(
        frame,
        text=CRISIS_TITLE,
        font=config.FONT_CRISIS_TITLE,
        wraplength=560,
        justify="left",
        foreground=config.COLOR_HELP_ACCENT,
    ).grid(row=0, column=0, sticky="w")
    ttk.Label(
        frame,
        text=CRISIS_BODY,
        font=config.FONT_CRISIS_BODY,
        wraplength=560,
        justify="left",
    ).grid(row=1, column=0, sticky="w", pady=(config.PAD_SMALL, config.PAD))

    row = 2
    if SELF_HARM_INDICATOR in tuple(risk_sources):
        ttk.Label(
            frame,
            text=CRISIS_ITEMS9_NOTE,
            font=config.FONT_CRISIS_BODY,
            wraplength=560,
            justify="left",
        ).grid(row=row, column=0, sticky="w", pady=(0, config.PAD))
        row += 1

    resources = ttk.Frame(frame)
    resources.grid(row=row, column=0, sticky="ew")
    for index, resource in enumerate(resources_in_display_order()):
        ttk.Label(
            resources,
            text=f"• {resource_line(resource)}",
            font=config.FONT_CRISIS_BODY,
            wraplength=560,
            justify="left",
        ).grid(row=index, column=0, sticky="w", pady=2)
    row += 1

    fallback = ttk.Label(
        frame, text="", font=config.FONT_CRISIS_TITLE, foreground=config.COLOR_HELP_ACCENT
    )
    fallback.grid(row=row, column=0, sticky="w", pady=(config.PAD_SMALL, 0))
    row += 1

    buttons = ttk.Frame(frame)
    buttons.grid(row=row, column=0, sticky="ew", pady=(config.PAD, 0))

    def call_lifeline() -> None:
        uri = tel_uri(resource_by_id(PRIMARY_LIFELINE_ID)) or "tel:988"
        if open_external(uri):
            return
        fallback.configure(text=CRISIS_CALL_FALLBACK)

    def find_help() -> None:
        resource = resource_by_id(WEB_HELPLINE_ID)
        if resource.url:
            open_external(resource.url)

    safe_button = ttk.Button(buttons, text=CRISIS_SAFE_BUTTON, command=acknowledge)
    safe_button.pack(side="left")
    call_button = ttk.Button(buttons, text=CRISIS_CALL_BUTTON, command=call_lifeline)
    call_button.pack(side="left", padx=(config.PAD_SMALL, 0))
    find_button = ttk.Button(buttons, text=CRISIS_FIND_HELP_BUTTON, command=find_help)
    find_button.pack(side="left", padx=(config.PAD_SMALL, 0))

    # Acknowledge-able only through the buttons: the window manager's close and Esc
    # both map to "I'm safe right now", which still leaves the persistent banner.
    dialog.protocol("WM_DELETE_WINDOW", acknowledge)
    dialog.bind("<Escape>", acknowledge)
    _make_modal(dialog, parent)
    safe_button.focus_set()
    return dialog


def show_info_dialog(parent: tk.Misc, title: str, message: str) -> None:
    """Show a small modal information dialog."""
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.configure(background=config.COLOR_APP_BG)
    frame = ttk.Frame(dialog, padding=config.PAD)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text=message, font=config.FONT_BODY, wraplength=460, justify="left").pack(
        anchor="w"
    )
    ttk.Button(frame, text=CLOSE_BUTTON, command=dialog.destroy).pack(
        anchor="e", pady=(config.PAD, 0)
    )
    dialog.bind("<Escape>", lambda _event: dialog.destroy())
    _make_modal(dialog, parent)


def show_error_dialog(parent: tk.Misc, title: str, message: str) -> None:
    """Show a non-destructive error dialog (never a stack trace)."""
    show_info_dialog(parent, title, message)


def ask_yes_no(parent: tk.Misc, title: str, message: str) -> bool:
    """Ask a yes/no question with the platform dialog; returns the answer."""
    return bool(messagebox.askyesno(title=title, message=message, parent=parent))


def export_data_to_file(parent: tk.Misc, conn: sqlite3.Connection) -> None:
    """Ask for a path and write the whole database as JSON (Prompt A, F6)."""
    destination = filedialog.asksaveasfilename(
        parent=parent,
        title=EXPORT_TITLE,
        defaultextension=".json",
        initialfile="mindpulse-export.json",
        filetypes=[("JSON", "*.json")],
    )
    if not destination:
        return
    try:
        payload = export_all_data(conn)
        Path(destination).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except (OSError, TypeError, ValueError) as error:
        LOGGER.warning("Export failed: %s", error)
        show_error_dialog(parent, "Couldn't export", EXPORT_FAILED)
        return
    show_info_dialog(parent, "Export complete", EXPORT_DONE)


def erase_data(parent: tk.Misc, conn: sqlite3.Connection, on_erased: Callable[[], None]) -> None:
    """Confirm and then erase every stored row, then notify the caller."""
    if not ask_yes_no(parent, ERASE_CONFIRM_TITLE, ERASE_CONFIRM_BODY):
        return
    try:
        erase_all_data(conn)
    except sqlite3.Error as error:
        LOGGER.error("Erase failed: %s", error)
        show_error_dialog(
            parent, "Couldn't erase", "Something went wrong and your data is unchanged."
        )
        return
    on_erased()
    show_info_dialog(parent, "Data erased", ERASE_DONE)


def show_result_dialog(
    parent: tk.Misc,
    lines: Sequence[str],
    *,
    show_help_button: bool,
    on_help: Callable[[], None],
    on_explain: Callable[[], None],
    on_close: Callable[[], None] | None = None,
) -> tk.Toplevel:
    """Show a screening result with its mandatory disclaimer (Prompt B §5, §7.4).

    Order is fixed: optional "Get help now" above the fold (risk flag), then the
    result lines (which include the banner, title, score, band and disclaimer).
    """
    dialog = tk.Toplevel(parent)
    dialog.title("Your result")
    dialog.configure(background=config.COLOR_APP_BG)

    def close(_event: tk.Event[tk.Misc] | None = None) -> None:
        try:
            dialog.grab_release()
        finally:
            dialog.destroy()
            if on_close is not None:
                on_close()

    frame = ttk.Frame(dialog, padding=config.PAD)
    frame.pack(fill="both", expand=True)
    row = 0
    if show_help_button:
        ttk.Button(frame, text=RESULT_HELP_BUTTON, command=on_help).grid(
            row=row, column=0, sticky="w", pady=(0, config.PAD)
        )
        row += 1
    for index, line in enumerate(lines):
        is_disclaimer = line in (RESULT_DISCLAIMER, RESULT_NEXT_STEP, RISK_RESULT_BANNER)
        ttk.Label(
            frame,
            text=line,
            font=config.FONT_BODY if is_disclaimer else config.FONT_HEADING,
            wraplength=520,
            justify="left",
            foreground=config.COLOR_HELP_ACCENT if line == RISK_RESULT_BANNER else "",
        ).grid(row=row + index, column=0, sticky="w", pady=(0, config.PAD_SMALL))
    row += len(lines)
    ttk.Label(
        frame,
        text=SCREENING_REFUSAL,
        font=config.FONT_SMALL,
        wraplength=520,
        justify="left",
        foreground=config.COLOR_TEXT_MUTED,
    ).grid(row=row, column=0, sticky="w", pady=(config.PAD_SMALL, config.PAD))
    row += 1
    buttons = ttk.Frame(frame)
    buttons.grid(row=row, column=0, sticky="ew")
    ttk.Button(buttons, text=CLOSE_BUTTON, command=close).pack(side="right")
    ttk.Button(buttons, text=RESULT_EXPLAIN_BUTTON, command=on_explain).pack(
        side="right", padx=(0, config.PAD_SMALL)
    )
    dialog.bind("<Escape>", close)
    dialog.protocol("WM_DELETE_WINDOW", close)
    _make_modal(dialog, parent)
    return dialog


def show_about_dialog(
    parent: tk.Misc,
    conn: sqlite3.Connection,
    on_erased: Callable[[], None],
) -> None:
    """Show version, disclaimers, privacy statement, attributions, and data controls."""
    dialog = tk.Toplevel(parent)
    dialog.title(ABOUT_TITLE)
    dialog.configure(background=config.COLOR_APP_BG)
    frame = ttk.Frame(dialog, padding=config.PAD)
    frame.pack(fill="both", expand=True)

    body = tk.Text(frame, wrap="word", height=22, width=64, font=config.FONT_BODY, relief="flat")
    body.insert(
        "1.0",
        "\n".join(
            (
                f"{config.APP_NAME} {config.APP_VERSION}",
                config.APP_TAGLINE,
                "",
                config.APP_DISCLAIMER_SHORT,
                "",
                "Privacy",
                config.PRIVACY_STATEMENT,
                "",
                "Attribution",
                *ATTRIBUTIONS,
                "",
                "Citations",
                *CITATIONS,
            )
        ),
    )
    body.configure(state="disabled")
    body.pack(fill="both", expand=True)

    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", pady=(config.PAD, 0))
    ttk.Button(buttons, text=CLOSE_BUTTON, command=dialog.destroy).pack(side="right")
    ttk.Button(
        buttons,
        text=ERASE_BUTTON,
        command=lambda: erase_data(dialog, conn, on_erased),
    ).pack(side="right", padx=(0, config.PAD_SMALL))
    ttk.Button(buttons, text=EXPORT_BUTTON, command=lambda: export_data_to_file(dialog, conn)).pack(
        side="right", padx=(0, config.PAD_SMALL)
    )
    dialog.bind("<Escape>", lambda _event: dialog.destroy())
    _make_modal(dialog, parent)


def confirm_leave_questionnaire(parent: tk.Misc) -> bool:
    """Ask "Leave this questionnaire?" with Keep going / Leave.

    Returns True when the user chooses to leave. Leaving writes nothing to the
    database and sets no risk flag (Prompt B §9.3).
    """
    dialog = tk.Toplevel(parent)
    dialog.title(QUIT_PROMPT)
    dialog.configure(background=config.COLOR_APP_BG)
    answer = {"leave": False}

    def choose(leave: bool) -> None:
        answer["leave"] = leave
        dialog.grab_release()
        dialog.destroy()

    frame = ttk.Frame(dialog, padding=config.PAD)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text=QUIT_PROMPT, font=config.FONT_HEADING).pack(anchor="w")
    buttons = ttk.Frame(frame)
    buttons.pack(anchor="e", pady=(config.PAD, 0))
    ttk.Button(buttons, text="Keep going", command=lambda: choose(False)).pack(side="left")
    ttk.Button(buttons, text="Leave", command=lambda: choose(True)).pack(
        side="left", padx=(config.PAD_SMALL, 0)
    )
    dialog.bind("<Escape>", lambda _event: choose(False))
    dialog.protocol("WM_DELETE_WINDOW", lambda: choose(False))
    _make_modal(dialog, parent)
    dialog.wait_window()
    return answer["leave"]
