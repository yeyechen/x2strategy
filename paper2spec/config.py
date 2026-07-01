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


def get_replications_path(default: str = "./replications") -> str:
    """Return replications root path from env, with a deterministic fallback.

    Priority:
      1) PAPER2SPEC_REPLICATIONS_PATH
      2) provided default
    """
    load_project_env()
    raw = os.getenv("PAPER2SPEC_REPLICATIONS_PATH", default).strip()
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return str(path)


def get_clickhouse_config() -> dict[str, str]:
    """Return ClickHouse connection parameters from environment.

    Two ports are returned because the project uses two protocols:
      * ``port``      — native TCP (9000), used by the generated strategy
        code via ``clickhouse_driver.Client``.
      * ``http_port`` — HTTP (8123), used by ``paper2spec.clickhouse``
        schema discovery (``urllib.request``).
    """
    load_project_env()
    return {
        "host": os.getenv("CLICKHOUSE_HOST", "localhost"),
        "port": os.getenv("CLICKHOUSE_PORT", "9000"),
        "http_port": os.getenv("CLICKHOUSE_HTTP_PORT", "8123"),
        "user": os.getenv("CLICKHOUSE_USER", "default"),
        "password": os.getenv("CLICKHOUSE_PASSWORD", ""),
        "database": os.getenv("CLICKHOUSE_DATABASE", "default"),
    }