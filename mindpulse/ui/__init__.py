"""Tkinter views for MindPulse.

Functional style: no classes anywhere in the UI. Each view is a module of
functions that build widgets into a parent frame and close over an application
state dictionary (see :func:`mindpulse.ui.app.new_app_state`).
"""

from __future__ import annotations
