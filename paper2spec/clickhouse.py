"""ClickHouse schema discovery, catalog management, and data requirements.

Mirrors the pattern in ``paper2spec/parser.py``: a core function that
connects to an external system, extracts structured information, and
writes a resource file for downstream LLM consumption.

Also provides the data bridge: extract structured data requirements
from a strategy spec, then match them against the catalog.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from paper2spec.config import get_clickhouse_config

logger = logging.getLogger(__name__)

CATALOG_PATH = Path(__file__).resolve().parent / "resources" / "clickhouse_catalog.json"

DATA_REQUIREMENTS_PROMPT = """You are a data engineer.  Given a strategy specification extracted
from a quantitative finance paper, produce a JSON list of the **minimum
data tables** needed to replicate the strategy.

STRATEGY SPEC:
{spec_text}

INSTRUCTIONS:
1. Identify each distinct dataset the strategy needs (daily returns,
   monthly returns, fundamental data, factor returns, etc.).
2. For each, specify the exact fields, frequency, date range, and
   any universe filters (exchange codes, share codes, price filters).
3. Be precise — use field names from the paper (e.g. "permno", "ret",
   "prc", "shrout", "gvkey", "fyear", "bkvlps").
4. If the paper underspecifies a field, use the conventional CRSP /
   Compustat field name.
5. Date range must match the paper's sample period exactly.

Return ONLY valid JSON:
{{
  "paper_title": "...",
  "requirements": [
    {{
      "id": "short_descriptive_id",
      "description": "What this dataset provides",
      "fields": ["field1", "field2", ...],
      "frequency": "daily|monthly|annual",
      "date_range": ["YYYY-MM-DD", "YYYY-MM-DD"],
      "filters": ["filter description 1", ...],
      "estimated_rows": null
    }}
  ]
}}"""


def extract_data_requirements(
    spec_path: str, *, model: str | None = None, output_path: str | None = None
) -> dict[str, Any]:
    """Run an LLM call to extract structured data requirements from a spec.

    Parameters
    ----------
    spec_path : str
        Path to ``spec.json`` produced by the extraction stage.
    model : str or None
        Override LLM model.
    output_path : str or None
        Where to write ``data_requirements.json``.  Defaults alongside *spec_path*.

    Returns
    -------
    dict
        The requirements dict, also written to disk.
    """
    return asyncio.run(
        _aextract_data_requirements(spec_path, model=model, output_path=output_path)
    )


async def _aextract_data_requirements(
    spec_path: str, *, model: str | None = None, output_path: str | None = None
) -> dict[str, Any]:
    from paper2spec.llm import achat

    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)

    # Flatten spec to text for the LLM — include strategies, data description
    spec_text = json.dumps(spec, indent=2, ensure_ascii=False)
    # Truncate if very long (strategies array can be large)
    if len(spec_text) > 40_000:
        spec_text = spec_text[:35_000] + "\n...\n" + spec_text[-5_000:]

    prompt = DATA_REQUIREMENTS_PROMPT.format(spec_text=spec_text)
    raw = await achat(prompt, model=model, temperature=0.1, max_tokens=4096)

    # Parse JSON from LLM response
    import re
    text = raw.strip()
    if text.startswith("```"):
        m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if m:
            text = m.group(1).strip()
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start : end + 1]
    requirements = json.loads(text)

    # Write
    if output_path is None:
        output_path = os.path.join(
            os.path.dirname(spec_path), "data_requirements.json"
        )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(requirements, f, indent=2, ensure_ascii=False)

    logger.info(
        "Data requirements: %d datasets → %s",
        len(requirements.get("requirements", [])),
        output_path,
    )
    return requirements


def match_requirements(
    requirements: dict[str, Any], catalog: dict[str, Any]
) -> dict[str, Any]:
    """Match extracted data requirements against the ClickHouse catalog.

    For each requirement, scans all catalog tables and scores them by
    column overlap.  Returns the best candidate per requirement, plus
    a coverage report.

    Parameters
    ----------
    requirements : dict
        Output of :func:`extract_data_requirements`.
    catalog : dict
        Output of :func:`discover_schema` or :func:`load_catalog`.

    Returns
    -------
    dict
        ``{matches: [...], gaps: [...], coverage_pct: float}``
    """
    import math

    matches: list[dict] = []
    gaps: list[dict] = []

    for req in requirements.get("requirements", []):
        needed = set(req.get("fields", []))
        if not needed:
            gaps.append({"requirement": req["id"], "reason": "no fields specified"})
            continue

        # Minimum score: must match at least half of the required fields
        min_score = max(1, math.ceil(len(needed) / 2))

        candidates: list[dict] = []
        for db_name, tables in catalog.get("databases", {}).items():
            for table_name, info in tables.items():
                cols = {c["name"].lower() for c in info.get("columns", [])}
                score = len(needed & cols)
                if score >= min_score:
                    candidates.append({
                        "database": db_name,
                        "table": table_name,
                        "fq_name": f"{db_name}.{table_name}",
                        "matched_columns": sorted(needed & cols),
                        "missing_columns": sorted(needed - cols),
                        "score": score,
                        "row_count": info.get("row_count", 0),
                        "date_range": info.get("date_range"),
                    })

        if candidates:
            # Sort by score descending, then by row count (prefer larger tables)
            candidates.sort(key=lambda c: (c["score"], c["row_count"]), reverse=True)
            # Cap at top 5 to avoid noise from snapshot databases
            for c in candidates[:5]:
                matches.append({"requirement": req["id"], **c})
        else:
            best_score = max(
                (len(needed & {c2["name"].lower() for c2 in info.get("columns", [])})
                 for db_name, tables in catalog.get("databases", {}).items()
                 for table_name, info in tables.items()),
                default=0,
            )
            gaps.append({
                "requirement": req["id"],
                "reason": (
                    f"no table found with ≥{min_score}/{len(needed)} required fields "
                    f"(best score: {best_score}). "
                    f"Required: {sorted(needed)}"
                ),
            })

    total = len(requirements.get("requirements", []))
    coverage = len({m["requirement"] for m in matches}) / total if total else 0

    return {
        "paper_title": requirements.get("paper_title", ""),
        "matches": matches,
        "gaps": gaps,
        "coverage": f"{coverage:.0%} ({len({m['requirement'] for m in matches})}/{total})",
    }


def discover_schema(output_path: str | None = None) -> dict[str, Any]:
    """Connect to ClickHouse, enumerate **all databases and tables**, and build a catalog.

    Discovers every database the user has access to, then enumerates all
    tables within each.  For each table we record column names / types,
    row count, and date range (when a ``date`` column exists).

    The result is written to *output_path* (default:
    ``resources/clickhouse_catalog.json``) and also returned as a dict.
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

    dest.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Catalog written to %s (%d bytes)", dest, dest.stat().st_size)

    return catalog


def load_catalog(path: str | None = None) -> dict[str, Any] | None:
    """Read an existing catalog file, returning ``None`` if it doesn't exist."""
    p = Path(path) if path else CATALOG_PATH
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


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


