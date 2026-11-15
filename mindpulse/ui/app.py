"""Window shell, navigation, and the always-visible help affordances (Prompt A).

Functional style, no classes: the shell is a module of functions plus one mutable
``state`` dictionary that views close over. Widgets live in that dictionary so
callbacks never need a global and never need ``self``.
"""

from __future__ import annotations

import logging
import sqlite3
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import ttk
from typing import Any

from .. import config, storage
from . import dialogs
from .brain_facts_view import build as build_brain_facts_view
from .check_in_view import build as build_check_in_view
from .companion_view import build as build_companion_view
from .companion_view import load_api_key as load_chat_api_key
from .companion_view import load_model as load_chat_model
from .dashboard_view import build as build_dashboard_view
from .screens_view import build as build_screeners_view

LOGGER = logging.getLogger(__name__)

#: View name -> builder function. Adding a screen means adding one entry here.
VIEW_BUILDERS: dict[str, Callable[[tk.Misc, dict[str, Any]], ttk.Frame]] = {
    "check_in": build_check_in_view,
    "screeners": build_screeners_view,
    "dashboard": build_dashboard_view,
    "brain_facts": build_brain_facts_view,
    "companion": build_companion_view,
}


def run() -> int:
    """Start the application. Returns a process exit code."""
    root = tk.Tk()
    root.title(f"{config.APP_NAME} — {config.APP_TAGLINE}")
    root.minsize(config.WINDOW_MIN_WIDTH, config.WINDOW_MIN_HEIGHT)
    root.configure(background=config.COLOR_APP_BG)
    database_path = config.default_database_path()
    try:
        conn = storage.connect(database_path)
        storage.run_migrations(conn)
    except (sqlite3.Error, OSError) as error:
        LOGGER.error("Could not open the MindPulse database: %s", error)
        root.withdraw()
        dialogs.show_error_dialog(
            root,
            "Couldn't start MindPulse",
            "MindPulse couldn't open its local database. Nothing was changed. "
            f"The expected location is {database_path}.",
        )
        root.destroy()
        return 1
    state = new_app_state(root, conn, database_path)
    build_shell(state)
    root.mainloop()
    return 0


def new_app_state(
    root: tk.Tk,
    conn: sqlite3.Connection,
    database_path: Path,
) -> dict[str, Any]:
    """Return the application state shared by every view and callback."""
    state: dict[str, Any] = {
        "root": root,
        "conn": conn,
        "database_path": database_path,
        "current_view": "",
        "view_frame": None,
        "banner_frame": None,
        "banner_shown": False,
        "nav_buttons": {},
        "status_var": tk.StringVar(master=root, value=""),
        "api_key": load_chat_api_key(),
        "model": load_chat_model(),
    }
    state["show_view"] = lambda name: show_view(state, name)
    state["open_help"] = lambda: open_help(state)
    state["enable_help_banner"] = lambda: enable_help_banner(state)
    state["set_status"] = lambda text: set_status(state, text)
    return state


def build_shell(state: dict[str, Any]) -> None:
    """Build the window chrome: menu, banner slot, sidebar, content area, footer."""
    root = state["root"]
    root.columnconfigure(0, weight=1)
    root.rowconfigure(1, weight=1)
    _build_menu(state)
    state["banner_slot"] = ttk.Frame(root)
    body = ttk.Frame(root, padding=(config.PAD, 0, config.PAD, 0))
    body.grid(row=1, column=0, sticky="nsew")
    body.columnconfigure(1, weight=1)
    body.rowconfigure(0, weight=1)
    _build_sidebar(state, body)
    content = ttk.Frame(body)
    content.grid(row=0, column=1, sticky="nsew", padx=(config.PAD, 0))
    content.rowconfigure(0, weight=1)
    content.columnconfigure(0, weight=1)
    state["content_frame"] = content
    _build_footer(state, root)
    show_view(state, "check_in")


def _build_menu(state: dict[str, Any]) -> None:
    """Build the menu bar. Help is never only here - the sidebar always shows it."""
    root = state["root"]
    menu = tk.Menu(root)
    file_menu = tk.Menu(menu, tearoff=False)
    file_menu.add_command(
        label="About MindPulse",
        command=lambda: dialogs.show_about_dialog(
            root, state["conn"], lambda: show_view(state, state["current_view"])
        ),
    )
    file_menu.add_command(
        label="Export my data",
        command=lambda: dialogs.export_data_to_file(root, state["conn"]),
    )
    file_menu.add_command(
        label="Erase all my data",
        command=lambda: dialogs.erase_data(
            root, state["conn"], lambda: show_view(state, state["current_view"])
        ),
    )
    file_menu.add_separator()
    file_menu.add_command(label="Quit", command=lambda: quit_app(state))
    menu.add_cascade(label="MindPulse", menu=file_menu)
    root.configure(menu=menu)


def _build_sidebar(state: dict[str, Any], body: ttk.Frame) -> None:
    """Build the navigation column, with "Get help now" pinned to the bottom."""
    sidebar = ttk.Frame(body, padding=(0, config.PAD, 0, config.PAD))
    sidebar.grid(row=0, column=0, sticky="nsw")
    ttk.Label(sidebar, text=config.APP_NAME, font=config.FONT_TITLE).pack(
        anchor="w", pady=(0, config.PAD)
    )
    for view_name, label in config.NAV_ITEMS:
        button = ttk.Button(
            sidebar,
            text=label,
            width=24,
            command=lambda name=view_name: show_view(state, name),
        )
        button.pack(anchor="w", pady=2)
        state["nav_buttons"][view_name] = button
    ttk.Frame(sidebar, height=config.PAD).pack(fill="y", expand=True)
    ttk.Button(
        sidebar,
        text=config.HELP_BUTTON_TEXT,
        command=lambda: open_help(state),
        width=24,
    ).pack(anchor="w", pady=(config.PAD, 2))
    ttk.Button(
        sidebar,
        text=dialogs.ABOUT_TITLE,
        command=lambda: dialogs.show_about_dialog(
            state["root"], state["conn"], lambda: show_view(state, state["current_view"])
        ),
        width=24,
    ).pack(anchor="w")


def _build_footer(state: dict[str, Any], root: tk.Tk) -> None:
    """Build the footer: the standing disclaimer plus a transient status line."""
    footer = ttk.Frame(root, padding=(config.PAD, config.PAD_SMALL))
    footer.grid(row=2, column=0, sticky="ew")
    footer.columnconfigure(0, weight=1)
    ttk.Label(
        footer,
        text=config.APP_DISCLAIMER_SHORT,
        font=config.FONT_SMALL,
        foreground=config.COLOR_TEXT_MUTED,
        wraplength=760,
        justify="left",
    ).grid(row=0, column=0, sticky="w")
    ttk.Label(
        footer,
        textvariable=state["status_var"],
        font=config.FONT_SMALL,
        foreground=config.COLOR_TEXT_MUTED,
    ).grid(row=0, column=1, sticky="e")


def show_view(state: dict[str, Any], view_name: str) -> None:
    """Build (or rebuild) the named view inside the content area."""
    builder = VIEW_BUILDERS.get(view_name)
    if builder is None:
        LOGGER.error("Unknown view %r", view_name)
        return
    previous = state.get("view_frame")
    if previous is not None:
        previous.destroy()
    frame = builder(state["content_frame"], state)
    frame.grid(row=0, column=0, sticky="nsew")
    state["view_frame"] = frame
    state["current_view"] = view_name
    for name, button in state["nav_buttons"].items():
        button.state(["disabled"] if name == view_name else ["!disabled"])
    set_status(state, "")


def set_status(state: dict[str, Any], text: str) -> None:
    """Set the footer status line."""
    state["status_var"].set(text)


def enable_help_banner(state: dict[str, Any]) -> None:
    """Show the persistent support banner above every screen (Prompt D §4.1)."""
    if state["banner_shown"]:
        return
    root = state["root"]
    banner = ttk.Frame(root, padding=(config.PAD, config.PAD_SMALL))
    banner.configure(style="Banner.TFrame")
    banner.columnconfigure(0, weight=1)
    ttk.Label(
        banner,
        text=config.HELP_BANNER_TEXT,
        font=config.FONT_BODY,
        foreground=config.COLOR_HELP_ACCENT,
    ).grid(row=0, column=0, sticky="w")
    ttk.Button(banner, text=config.HELP_BUTTON_TEXT, command=lambda: open_help(state)).grid(
        row=0, column=1, sticky="e"
    )
    banner.grid(row=0, column=0, sticky="ew")
    state["banner_frame"] = banner
    state["banner_shown"] = True


def open_help(state: dict[str, Any]) -> None:
    """Open the crisis dialog with no risk sources; dismissal leaves the banner."""
    dialogs.show_crisis_dialog(state["root"], (), on_acknowledge=lambda: enable_help_banner(state))


def quit_app(state: dict[str, Any]) -> None:
    """Close the database cleanly and destroy the window."""
    try:
        state["conn"].close()
    except sqlite3.Error as error:  # pragma: no cover - shutdown best effort
        LOGGER.warning("Could not close the database cleanly: %s", error)
    state["root"].destroy()
