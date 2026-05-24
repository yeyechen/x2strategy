#!/usr/bin/env python3
"""operator_pitfalls.py — Retrieve operator-pitfall context for a draft spec.

This is a deterministic retrieval helper for repair/audit. It performs semantic
similarity over paper2spec/resources/operator_pitfall_index.md and writes matched entries
as Markdown. The LLM should read the output; it should not self-select pitfalls.
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from paper2spec.operator_pitfall import (  # noqa: E402
    DEFAULT_THRESHOLD,
    DEFAULT_TOP_K,
    render_operator_pitfall_matches,
    retrieve_operator_pitfalls,
)


def _load_strategy_spec(path: Path, strategy_index: int | None) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "strategies" in data:
        strategies = data.get("strategies") or []
        if not strategies:
            raise SystemExit("Error: spec file contains no strategies")
        idx = strategy_index if strategy_index is not None else 0
        if idx < 0 or idx >= len(strategies):
            raise SystemExit(f"Error: --strategy-index {idx} out of range (0..{len(strategies)-1})")
        return strategies[idx]
    return data


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Retrieve operator-pitfall matches for a draft StrategySpec via semantic similarity."
    )
    parser.add_argument("spec_json", help="Path to StrategySpec JSON or ExtractionResult spec.json")
    parser.add_argument(
        "--strategy-index",
        type=int,
        help="Strategy index when spec_json is an ExtractionResult with a strategies array (default: 0)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"Minimum relevance score (default: {DEFAULT_THRESHOLD})",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help=f"Top-k operator entries per component query (default: {DEFAULT_TOP_K})",
    )
    parser.add_argument(
        "--corpus",
        help="Optional operator-pitfall corpus path (default: paper2spec/resources/operator_pitfall_index.md)",
    )
    parser.add_argument(
        "-o", "--output",
        help="Optional Markdown output path. If omitted, prints to stdout.",
    )
    args = parser.parse_args()

    spec_path = Path(args.spec_json)
    if not spec_path.is_file():
        raise SystemExit(f"Error: file not found: {spec_path}")

    spec = _load_strategy_spec(spec_path, args.strategy_index)
    corpus_path = Path(args.corpus).expanduser().resolve() if args.corpus else None
    matches = retrieve_operator_pitfalls(spec, threshold=args.threshold, top_k=args.top_k, corpus_path=corpus_path)
    rendered = render_operator_pitfall_matches(matches)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered, encoding="utf-8")
        print(f"✅ Wrote {out} ({len(matches)} matched operator entries)")
    else:
        print(rendered or "(no operator-pitfall matches above threshold)")


if __name__ == "__main__":
    main()
