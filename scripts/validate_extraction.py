#!/usr/bin/env python3
"""validate_extraction.py — Check that the LLM-extracted spec is complete.

The L8 extractor is supposed to fill in `signals` and `weightings_reported`
based on the paper's described trading rule. Small models (e.g.
deepseek-v4-flash) sometimes return empty arrays for these fields,
which silently bypasses the structural guard. This script reads the
extracted spec and rejects it on any obvious incompleteness.

The fip_v4 run produced `signals: []` and `weightings_reported: []`.
The agent's own diagnostic at line 84 of fip_v4.txt noted the
emptiness but moved on. This script would have caught the bug
at the spec-validation step before the agent wrote strategy.py.

What it checks (for cross-sectional strategies):
  - `replication_targets` is non-empty
  - `indicators` is non-empty (the paper's signal definitions)
  - `signals` is non-empty (per-signal long-leg direction)
  - `weightings_reported` is non-empty
  - `time_period` is set
  - `n_bins` is in [1, 20]

Exit codes:
  0  — all checks pass
  1  — spec is incomplete (one or more required fields are missing)
  2  — error reading the spec file (not found, malformed JSON)

Usage:
    python scripts/validate_extraction.py <spec.json>
    python scripts/validate_extraction.py replications/<slug>/inputs/spec.json

The script is best-effort: a missing field produces a clear warning
but does not block the run unless it's a structural requirement
(like empty `signals` for a cross-sectional strategy).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _is_cross_sectional(spec: dict) -> bool:
    """Heuristic: a strategy is cross-sectional if it bins stocks by a signal.

    The LLM-extracted spec carries `strategy_type`. Most academic
    cross-sectional equity strategies have strategy_type like
    `equity_long_short` or `cross_sectional`. We err on the side
    of "treat as cross-sectional" so an empty `signals: []` is caught
    even when the strategy_type label is unclear.
    """
    if not spec.get("strategies"):
        return False
    strat = spec["strategies"][0]
    st = (strat.get("strategy_type") or "").lower()
    asset = strat.get("asset_class") or []
    if "equity" in asset and "long_short" in st:
        return True
    if "cross_sectional" in st:
        return True
    # Default: if the strategy has replication_targets, treat as
    # cross-sectional. This is the most common case for the papers
    # this skill is designed to handle.
    if strat.get("replication_targets"):
        return True
    return False


def _check_spec(spec_path: Path) -> list[str]:
    """Return a list of error messages (empty if spec is complete)."""
    errors: list[str] = []
    if not spec_path.is_file():
        return [f"spec file not found: {spec_path}"]

    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)

    if "strategies" not in spec:
        return ["spec.json missing 'strategies' key"]
    if not spec["strategies"]:
        return ["spec.json 'strategies' is empty"]

    strat = spec["strategies"][0]
    cross_sectional = _is_cross_sectional(spec)

    # Universal checks (apply to any strategy)
    if not strat.get("replication_targets"):
        errors.append("replication_targets is empty — no targets to validate against")
    if not strat.get("indicators"):
        errors.append("indicators is empty — no signals extracted from the paper")

    tp = strat.get("time_period")
    if tp is not None:
        if isinstance(tp, str):
            # Free-text form like "1976-01-01 to 2007-12-31" — check it
            # parses to a year range. Heuristic: contains two 4-digit
            # years.
            import re
            years = re.findall(r"\b\d{4}\b", tp)
            if len(years) < 2:
                errors.append(
                    f"time_period is a string but doesn't contain a year "
                    f"range: {tp!r}. Expected 'YYYY-MM-DD to YYYY-MM-DD' or "
                    f"a dict with 'start_date' / 'end_date'."
                )
        elif isinstance(tp, dict):
            if not (tp.get("start_date") and tp.get("end_date")):
                errors.append(
                    "time_period is a dict but missing start_date or end_date"
                )
        else:
            errors.append(
                f"time_period must be a dict or string, got {type(tp).__name__}"
            )

    n_bins = strat.get("n_bins") or 5
    if not isinstance(n_bins, int) or not (1 <= n_bins <= 20):
        errors.append(f"n_bins={n_bins!r} is out of expected range [1, 20]")

    # Cross-sectional-only checks (the ones fip_v4 missed)
    if cross_sectional:
        signals = strat.get("signals")
        if not signals:
            errors.append(
                "signals is empty or missing — for cross-sectional strategies, "
                "each L/S signal must declare its long-leg direction. "
                "Re-run analyze.py or grep content.md for the paper's described "
                "L/S rule, then add e.g. {\"name\": \"pret\", \"long_leg\": \"high\"}."
            )
        else:
            for i, s in enumerate(signals):
                if not isinstance(s, dict):
                    errors.append(f"signals[{i}] is not a dict: {s!r}")
                    continue
                if "name" not in s or "long_leg" not in s:
                    errors.append(
                        f"signals[{i}] is missing 'name' or 'long_leg': {s!r}"
                    )
                elif s["long_leg"] not in ("high", "low"):
                    errors.append(
                        f"signals[{i}].long_leg must be 'high' or 'low', "
                        f"got {s['long_leg']!r}"
                    )

        weightings = strat.get("weightings_reported")
        if not weightings:
            errors.append(
                "weightings_reported is empty or missing — for cross-sectional "
                "academic papers, default to [\"EW\", \"VW\"] (the paper reports "
                "both side-by-side). Re-run analyze.py."
            )
        else:
            for w in weightings:
                if w not in ("EW", "VW"):
                    errors.append(
                        f"weightings_reported contains invalid value {w!r}; "
                        f"only 'EW' and 'VW' are supported"
                    )

    return errors


def main():
    parser = argparse.ArgumentParser(
        description="Validate that the LLM-extracted spec is complete."
    )
    parser.add_argument(
        "spec_json",
        help="Path to spec.json (or a path containing it)",
    )
    args = parser.parse_args()

    spec_path = Path(args.spec_json)
    # Allow passing a directory containing inputs/spec.json
    if spec_path.is_dir():
        spec_path = spec_path / "inputs" / "spec.json"

    try:
        errors = _check_spec(spec_path)
    except json.JSONDecodeError as e:
        print(f"ERROR: spec.json is not valid JSON: {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"ERROR: failed to read spec: {e}", file=sys.stderr)
        sys.exit(2)

    if not errors:
        print(f"✓ spec is complete: {spec_path}")
        sys.exit(0)

    print(f"⛔ spec is INCOMPLETE: {spec_path}", file=sys.stderr)
    print("", file=sys.stderr)
    for i, err in enumerate(errors, 1):
        print(f"  {i}. {err}", file=sys.stderr)
    print("", file=sys.stderr)
    print(
        "Re-run scripts/analyze.py to re-extract. If the LLM still "
        "returns empty fields, grep inputs/content.md for the paper's "
        "described L/S rule and add manually.",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
