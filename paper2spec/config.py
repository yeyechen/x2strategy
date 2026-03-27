"""Shared configuration helpers for paper2spec.

This module centralizes project-level environment loading and stable path
resolution so all scripts behave consistently across sessions.
"""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"


def load_project_env() -> None:
    """Best-effort load of project `.env` file without overriding shell vars."""
    try:
        from dotenv import load_dotenv

        load_dotenv(ENV_PATH, override=False)
    except ImportError:
        # Keep working even when python-dotenv is unavailable.
        pass


def get_library_path(default: str = "./library") -> str:
    """Return library path from env, with a deterministic fallback.

    Priority:
      1) PAPER2SPEC_LIBRARY_PATH
      2) provided default
    """
    load_project_env()
    raw = os.getenv("PAPER2SPEC_LIBRARY_PATH", default).strip()
    return str(Path(raw).expanduser())