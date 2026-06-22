#!/usr/bin/env python3
"""extract_requirements.py — Extract data requirements from a spec and match against ClickHouse.

Usage (CLI):
    python scripts/extract_requirements.py <slug>/inputs/spec.json
    python scripts/extract_requirements.py spec.json -o output_dir/

Usage (agent):
    The agent runs this after extraction to produce data_requirements.json
    and a match report, then uses the report during code generation.

By default, both artifacts are written under ``<slug>/diagnostics/`` when
the spec path looks like ``<slug>/inputs/spec.json``. Pass ``-o`` to
override the destination.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from paper2spec.clickhouse import (
    extract_data_requirements,
    load_catalog,
    match_requirements,
)
from paper2spec.paths import paper_layout


def _infer_layout_from_spec(spec_path: str):
    """Best-effort: infer per-paper layout from spec path.

    Returns a :class:`PaperLayout` if ``spec_path`` is at
    ``<slug>/inputs/spec.json``, else ``None``.
    """
    p = Path(spec_path).resolve()
    if p.parent.name == "inputs" and p.parent.parent.name:
        return paper_layout(slug=p.parent.parent.name)
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Extract data requirements from a strategy spec and match to ClickHouse."
    )
    parser.add_argument("spec_json", help="Path to spec.json")
    parser.add_argument(
        "-o", "--output-dir",
        help="Output directory (default: <slug>/diagnostics/, inferred from spec path)",
    )
    parser.add_argument(
        "--model", help="Override LLM model",
    )
    parser.add_argument(
        "--catalog", help="Path to catalog YAML (default: auto-detect)",
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
        layout = _infer_layout_from_spec(args.spec_json)
        if layout is not None:
            layout.ensure()
            out_dir = layout.diagnostics_dir
        else:
            out_dir = Path(os.path.dirname(args.spec_json) or ".")
            print(
                f"⚠️  Could not infer per-paper layout from {args.spec_json}; "
                f"writing diagnostics to {out_dir}",
                file=sys.stderr,
            )
            out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Extract requirements (LLM call)
    print("🔍 Extracting data requirements from spec...")
    req_path = out_dir / "data_requirements.json"
    requirements = extract_data_requirements(
        args.spec_json, model=args.model, output_path=str(req_path)
    )
    reqs = requirements.get("requirements", [])
    print(f"   Found {len(reqs)} data requirement(s)")
    for r in reqs:
        print(f"     [{r['id']}] {r['description'][:80]}...")
        print(f"       Fields: {', '.join(r['fields'])}")
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

    # 3. Write report
    report_path = out_dir / "data_match_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n📄 Requirements: {req_path}")
    print(f"📄 Report:       {report_path}")


if __name__ == "__main__":
    main()
