"""Entry point: ``python -m mindpulse``."""

from __future__ import annotations

import logging

from .ui.app import run as run_app


def main() -> int:
    """Configure logging and start the application. Returns a process exit code."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # Keeps urllib's request logging quiet: request URLs are harmless, headers are not.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    return run_app()


if __name__ == "__main__":
    raise SystemExit(main())
