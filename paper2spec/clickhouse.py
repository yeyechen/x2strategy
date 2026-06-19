"""ClickHouse schema discovery and catalog management.

Mirrors the pattern in ``paper2spec/parser.py``: a core function that
connects to an external system, extracts structured information, and
writes a resource file for downstream LLM consumption.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from paper2spec.config import get_clickhouse_config

logger = logging.getLogger(__name__)

CATALOG_PATH = Path(__file__).resolve().parent / "resources" / "clickhouse_catalog.yaml"


def discover_schema(output_path: str | None = None) -> dict[str, Any]:
    """Connect to ClickHouse, enumerate **all databases and tables**, and build a catalog.

    Discovers every database the user has access to, then enumerates all
    tables within each.  For each table we record column names / types,
    row count, and date range (when a ``date`` column exists).

    The result is written to *output_path* (default:
    ``resources/clickhouse_catalog.yaml``) and also returned as a dict.
    """
    cfg = get_clickhouse_config()
    base_url = f"http://{cfg['host']}:8123/"
    # Build auth WITHOUT locking to a single database
    auth = _build_auth(cfg, include_database=False)

    # 1. Discover all databases
    databases = _query_json(base_url, auth, "SHOW DATABASES FORMAT JSONEachRow")
    if not databases:
        raise RuntimeError("No databases found — check permissions")
    db_names = [
        row["name"] for row in databases
        if row.get("name") not in ("system", "INFORMATION_SCHEMA", "information_schema")
    ]
    logger.info("Found %d database(s): %s", len(db_names), ", ".join(db_names))

    # 2. Enumerate tables per database
    catalog: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(),
        "host": cfg["host"],
        "databases": {},
    }

    for db_name in sorted(db_names):
        db_auth = _build_auth(cfg, database=db_name)
        tables = _query_json(
            base_url, db_auth, f"SHOW TABLES FROM {db_name} FORMAT JSONEachRow"
        )
        if not tables:
            continue

        db_entry: dict[str, Any] = {}
        for row in tables:
            name = row.get("name", "")
            if not name:
                continue
            fq_name = f"{db_name}.{name}"

            # Column schema
            cols = _query_json(
                base_url, db_auth, f"DESCRIBE TABLE {db_name}.{name} FORMAT JSONEachRow"
            )

            # Row count
            count_result = _query_json(
                base_url, db_auth, f"SELECT count() AS cnt FROM {db_name}.{name} FORMAT JSONEachRow"
            )
            row_count = count_result[0]["cnt"] if count_result else 0

            # Date range (if the table has a 'date' column)
            date_range = None
            if any(c.get("name") == "date" for c in cols):
                dr = _query_json(
                    base_url, db_auth,
                    f"SELECT min(date) AS d0, max(date) AS d1 FROM {db_name}.{name} FORMAT JSONEachRow",
                )
                if dr:
                    date_range = [str(dr[0].get("d0", "")), str(dr[0].get("d1", ""))]

            db_entry[name] = {
                "columns": [{"name": c["name"], "type": c["type"]} for c in cols],
                "row_count": row_count,
                "date_range": date_range,
            }
            logger.info("  %s: %d cols, %s rows", fq_name, len(cols), f"{row_count:,}")

        if db_entry:
            catalog["databases"][db_name] = db_entry

    # Write
    dest = Path(output_path) if output_path else CATALOG_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)

    content = _to_yaml(catalog)
    dest.write_text(content, encoding="utf-8")
    logger.info("Catalog written to %s (%d bytes)", dest, len(content))

    return catalog


def load_catalog(path: str | None = None) -> dict[str, Any] | None:
    """Read an existing catalog file, returning ``None`` if it doesn't exist."""
    p = Path(path) if path else CATALOG_PATH
    if not p.is_file():
        return None
    import yaml
    return yaml.safe_load(p.read_text(encoding="utf-8"))


# ── helpers ──────────────────────────────────────────────────────


def _build_auth(cfg: dict, *, include_database: bool = True, database: str | None = None) -> str:
    """Build HTTP query-string auth params."""
    params = [f"user={cfg['user']}"]
    if cfg["password"]:
        params.append(f"password={cfg['password']}")
    db = database or cfg.get("database", "")
    if include_database and db:
        params.append(f"database={db}")
    return "&".join(params)


def _query_json(base_url: str, auth: str, query: str) -> list[dict]:
    """Run a ClickHouse query via HTTP and return JSON rows.

    Handles both ``JSONEachRow`` (NDJSON — one object per line) and
    single JSON array responses.
    """
    url = f"{base_url}?{auth}&query={urllib.request.quote(query)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            raw = resp.read().decode("utf-8").strip()
    except Exception as exc:
        logger.warning("Query failed: %s — %s", query[:80], exc)
        return []

    if not raw:
        return []

    # NDJSON (JSONEachRow): one JSON object per line
    if raw.startswith("{"):
        rows = []
        for line in raw.split("\n"):
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows

    # Single JSON array
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Could not parse JSON: %s", raw[:200])
        return []


def _to_yaml(catalog: dict) -> str:
    """Serialize catalog to YAML without external dependencies."""
    lines = [
        f"# ClickHouse catalog — auto-generated {catalog['generated_at']}",
        f"# Host: {catalog['host']}",
        "",
    ]
    for db_name, tables in catalog.get("databases", {}).items():
        lines.append(f"{db_name}:")
        for table_name, info in tables.items():
            lines.append(f"  {table_name}:")
            lines.append(f"    row_count: {info['row_count']}")
            if info["date_range"]:
                lines.append(f"    date_range: {info['date_range']}")
            lines.append("    columns:")
            for col in info["columns"]:
                lines.append(f"      - {{name: {col['name']}, type: {col['type']}}}")
            lines.append("")
    return "\n".join(lines)
