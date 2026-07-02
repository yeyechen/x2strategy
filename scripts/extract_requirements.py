#!/usr/bin/env python3
"""extract_requirements.py — Verify agent-produced data requirements against ClickHouse.

Usage (CLI):
    python scripts/extract_requirements.py <slug>/diagnostics/data_requirements.json
    python scripts/extract_requirements.py data_requirements.json -o output_dir/

Usage (agent):
    The agent writes diagnostics/data_requirements.json itself (mapping
    abstract spec fields to concrete ClickHouse columns using the catalog),
    then runs this script to verify those fields exist and produce
    diagnostics/data_match_report.json.

This script is deterministic — no LLM calls. It reads the requirements
JSON from disk, loads the ClickHouse catalog, and runs match_requirements
to produce a coverage report.
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from paper2spec.clickhouse import load_catalog, match_requirements


def _write_blocked_md(out_dir: Path, report: dict, requirements: dict) -> Path:
    """Write diagnostics/BLOCKED.md summarizing why replication cannot proceed.

    The agent reads this file to learn the data is insufficient and
    must stop (do not write strategy.py). Greppable by the literal
    string 'BLOCKED' in the filename and the # BLOCKED heading.

    Args:
        out_dir: the per-slug diagnostics/ directory.
        report: the data_match_report dict (must have 'gaps' and 'matches').
        requirements: the data_requirements.json dict (for paper title).

    Returns:
        Path to the written file.
    """
    paper_title = requirements.get("paper") or requirements.get("paper_title") or "?"
    gaps = report.get("gaps", [])
    partial = [m for m in report.get("matches", []) if m.get("missing_columns")]
    n_gaps = len(gaps)
    n_partial = len(partial)

    lines = [
        "# BLOCKED: Insufficient Data for Replication",
        "",
        f"**Paper:** {paper_title}",
        f"**Coverage:** {report.get('coverage', '?')}",
        f"**Detected at:** {datetime.now(timezone.utc).isoformat()}",
        "",
        "**Status:** The data verification step found requirement(s) that",
        "cannot be satisfied by the available ClickHouse catalog. The",
        "replication cannot proceed until the missing data is added or the",
        "spec is adjusted to a paper we can actually replicate.",
        "",
        "## Unmatched Requirements",
        "",
    ]
    if gaps:
        for g in gaps:
            req_id = g.get("requirement", "?")
            reason = g.get("reason", "no match found in catalog")
            lines.append(f"- **[{req_id}]** {reason}")
    else:
        lines.append("- (none — all requirements matched, see partial-matches section)")

    if partial:
        lines.extend([
            "",
            "## Partial Matches (Missing Columns)",
            "",
        ])
        for m in partial:
            req_id = m.get("requirement", "?")
            fq = m.get("fq_name", "?")
            missing = ", ".join(m.get("missing_columns", []))
            lines.append(f"- **[{req_id}]** → {fq}; missing columns: {missing}")

    lines.extend([
        "",
        "## Resolution",
        "",
        "The agent MUST stop here and write `results/SUMMARY.md` with",
        "`Status: BLOCKED — insufficient data`. Do NOT write `src/strategy.py`.",
        "",
        "To unblock:",
        "1. Add the missing data to ClickHouse and re-run, OR",
        "2. Adjust the spec to drop the missing data fields, OR",
        "3. Re-run analyze.py after editing the spec to skip these requirements",
    ])

    blocked_path = out_dir / "BLOCKED.md"
    blocked_path.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
    return blocked_path


def _infer_output_dir(requirements_path: str) -> Path:
    """Best-effort: infer diagnostics/ dir from requirements path.

    Returns the parent directory of *requirements_path* if it's under
    ``<slug>/diagnostics/``, else the parent directory of the file.
    """
    return Path(requirements_path).resolve().parent


def main():
    parser = argparse.ArgumentParser(
        description="Verify agent-produced data requirements against the ClickHouse catalog."
    )
    parser.add_argument(
        "requirements_json",
        help="Path to data_requirements.json (agent-produced)",
    )
    parser.add_argument(
        "-o", "--output-dir",
        help="Output directory (default: alongside requirements_json)",
    )
    parser.add_argument(
        "--catalog", help="Path to catalog JSON (default: auto-detect)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    # Resolve output directory
    if args.output_dir:
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
    else:
        out_dir = _infer_output_dir(args.requirements_json)

    # 1. Load agent-produced requirements
    requirements_path = Path(args.requirements_json)
    if not requirements_path.is_file():
        print(f"ERROR: {requirements_path} not found", file=sys.stderr)
        sys.exit(1)

    with open(requirements_path, encoding="utf-8") as f:
        requirements = json.load(f)

    # Validate top-level shape — fail loudly instead of silently producing
    # an empty match report (the agent must use the "requirements" key).
    if "requirements" not in requirements:
        top_keys = list(requirements.keys())
        print(
            f"ERROR: {requirements_path.name} is missing the 'requirements' key.\n"
            f"  Found top-level keys: {top_keys}\n"
            f"  Expected shape:\n"
            f"    {{\n"
            f"      \"paper\": \"...\",\n"
            f"      \"requirements\": [\n"
            f"        {{\"id\": \"...\", \"description\": \"...\", "
            f"\"fields\": [\"col1\", \"col2\"], \"date_range\": [\"...\", \"...\"], "
            f"\"frequency\": \"daily|monthly\"}}\n"
            f"      ]\n"
            f"    }}\n"
            f"  Rewrite the file with this shape and re-run.",
            file=sys.stderr,
        )
        sys.exit(2)

    reqs = requirements["requirements"]
    if not reqs:
        print(
            f"ERROR: {requirements_path.name} has an empty 'requirements' list.\n"
            f"  At least one requirement entry is expected.",
            file=sys.stderr,
        )
        sys.exit(2)

    print(f"📄 Loaded {len(reqs)} data requirement(s) from {requirements_path}")
    for r in reqs:
        print(f"   [{r['id']}] {r.get('description', '')[:80]}...")
        print(f"       Fields: {', '.join(r.get('fields', []))}")
        print(f"       Date: {r.get('date_range', '?')}")
        print(f"       Frequency: {r.get('frequency', '?')}")

    # 2. Match against catalog
    catalog = load_catalog(args.catalog)
    if catalog is None:
        print("\n⚠️  No catalog found — run scripts/discover_clickhouse.py first")
        return

    print("\n🔗 Matching against ClickHouse catalog...")
    report = match_requirements(requirements, catalog)

    print(f"\n   Coverage: {report['coverage']}")

    if report["matches"]:
        print(f"\n   ✅ Matched ({len(report['matches'])}):")
        for m in report["matches"]:
            print(f"     [{m['requirement']}] → {m['fq_name']}")
            print(f"       Columns: {', '.join(m['matched_columns'])}")
            if m["missing_columns"]:
                print(f"       Missing: {', '.join(m['missing_columns'])}")
            if m["date_range"]:
                print(f"       Coverage: {m['date_range'][0]} → {m['date_range'][1]}")

    if report["gaps"]:
        print(f"\n   ❌ Gaps ({len(report['gaps'])}):")
        for g in report["gaps"]:
            print(f"     [{g['requirement']}] — {g['reason']}")

    # 3. Write report. The "matches" list may have up to 10 candidate
    #    tables per requirement — only the FIRST per requirement matters
    #    for blocking. A requirement is "fully matched" if its best
    #    candidate has no missing_columns; "partial" otherwise; "gap"
    #    if there are no candidates at all.
    gaps = report.get("gaps", [])
    seen_reqs: set[str] = set()
    partial: list[dict] = []
    for m in report.get("matches", []):
        req_id = m.get("requirement", "?")
        if req_id in seen_reqs:
            continue  # only consider the best candidate per requirement
        seen_reqs.add(req_id)
        if m.get("missing_columns"):
            partial.append(m)
    report["status"] = "blocked" if (gaps or partial) else "ok"
    report["blocked_at"] = datetime.now(timezone.utc).isoformat() if (gaps or partial) else None

    report_path = out_dir / "data_match_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n📄 Report: {report_path}")

    # 4. If there are gaps or partial matches, write BLOCKED.md and
    #    exit non-zero. The agent must check for this file and stop
    #    before writing strategy.py.
    if gaps or partial:
        blocked_path = _write_blocked_md(out_dir, report, requirements)
        print(f"\n⛔ BLOCKED: {len(gaps)} unmatched, {len(partial)} partial-mismatch")
        print(f"   See {blocked_path}")
        print(f"   The agent MUST stop here and write results/SUMMARY.md")
        print(f"   with Status: BLOCKED. Do NOT write src/strategy.py.")
        sys.exit(1)


if __name__ == "__main__":
    main()
