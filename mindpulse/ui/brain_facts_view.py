"""Brain-facts panel: one cited education card, chosen daily (Prompt A, F4).

The panel shows a single card rather than a scrollable list. Which card appears is
decided by the calendar date alone (:func:`mindpulse.brain_facts.fact_for_date`), so
it changes at midnight without any stored state. Content is read-only.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from .. import charts, config
from ..brain_facts import fact_for_date
from ..models import BrainFact

HEADING = "Brain facts"
INTRO = (
    "A short, cited explanation of how some brain and body systems are understood to "
    "work. General education, not advice about your own health."
)
FOOTNOTE = "A different fact appears here tomorrow."
CARD_WRAP = 720


def build(parent: tk.Misc, _state: dict[str, Any]) -> ttk.Frame:
    """Build the panel showing the day's card."""
    frame = ttk.Frame(parent, padding=config.PAD)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(4, weight=1)
    ttk.Label(frame, text=HEADING, font=config.FONT_TITLE).grid(row=0, column=0, sticky="w")
    ttk.Label(
        frame,
        text=INTRO,
        font=config.FONT_BODY,
        wraplength=CARD_WRAP,
        justify="left",
    ).grid(row=1, column=0, sticky="w", pady=(0, config.PAD))
    _add_card(frame, 2, fact_for_date(charts.utc_today()))
    ttk.Label(
        frame,
        text=FOOTNOTE,
        font=config.FONT_SMALL,
        foreground=config.COLOR_TEXT_MUTED,
    ).grid(row=3, column=0, sticky="w", pady=(config.PAD_SMALL, 0))
    return frame


def _add_card(parent: ttk.Frame, row: int, fact: BrainFact) -> None:
    """Add one education card: title, body, and its citation line."""
    card = ttk.Frame(parent, padding=config.PAD, relief="solid", borderwidth=1)
    card.grid(row=row, column=0, sticky="ew", padx=2)
    card.columnconfigure(0, weight=1)
    ttk.Label(card, text=fact.title, font=config.FONT_HEADING, wraplength=CARD_WRAP).grid(
        row=0, column=0, sticky="w"
    )
    ttk.Label(
        card,
        text=fact.body,
        font=config.FONT_BODY,
        wraplength=CARD_WRAP,
        justify="left",
    ).grid(row=1, column=0, sticky="w", pady=(config.PAD_SMALL, config.PAD_SMALL))
    ttk.Label(
        card,
        text=fact.source,
        font=config.FONT_SMALL,
        foreground=config.COLOR_TEXT_MUTED,
        wraplength=CARD_WRAP,
        justify="left",
    ).grid(row=2, column=0, sticky="w")
