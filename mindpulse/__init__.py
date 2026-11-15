"""MindPulse — a local-first mental fitness companion.

A wellness and education tool, not a medical device, and not a diagnostic tool.
All data stays on this computer in a single SQLite file; the optional AI companion
is the only feature that uses the network.
"""

from __future__ import annotations

from .config import APP_NAME, APP_TAGLINE, APP_VERSION

__all__ = ["APP_NAME", "APP_TAGLINE", "APP_VERSION"]
__version__ = APP_VERSION
