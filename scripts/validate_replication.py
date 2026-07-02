#!/usr/bin/env python3
"""validate_replication.py — Compare backtest output to paper-claimed targets.

Reads replication_targets from inputs/spec.json and replicated values
from results/metrics.json, then reports a per-target comparison and
an overall hit-rate.

Usage:
    python scripts/validate_replication.py <slug>
    python scripts/validate_replication.py replications/max_v9/

Exit codes:
    0 — all targets matched (or no targets found)
    1 — some targets did not match
    2 — error (missing files, malformed JSON)
"""

import argparse
import json
import sys
from pathlib import Path


def _find_spec_json(slug_or_path: str) -> Path:
    """Resolve the spec.json path from a slug or path."""
    p = Path(slug_or_path)
    if p.is_dir():
        candidate = p / "inputs" / "spec.json"
        if candidate.is_file():
            return candidate
        # Maybe it's the replications root + slug
        candidate = p / "inputs" / "spec.json"
        if candidate.is_file():
            return candidate
    # Try as a slug under the default replications path
    try:
        from paper2spec.paths import paper_layout
        layout = paper_layout(slug_or_path)
        if layout.input_path("spec.json").is_file():
            return layout.input_path("spec.json")
    except Exception:
        pass
    # Direct file path
    if p.is_file():
        return p
    raise FileNotFoundError(f"Could not find spec.json for '{slug_or_path}'")


def _find_metrics_json(slug_or_path: str) -> Path:
    """Resolve the metrics.json path from a slug or path."""
    p = Path(slug_or_path)
    if p.is_dir():
        candidate = p / "results" / "metrics.json"
        if candidate.is_file():
            return candidate
    try:
        from paper2spec.paths import paper_layout
        layout = paper_layout(slug_or_path)
        if layout.result_path("metrics.json").is_file():
            return layout.result_path("metrics.json")
    except Exception:
        pass
    if p.is_file():
        return p
    raise FileNotFoundError(f"Could not find metrics.json for '{slug_or_path}'")


def _extract_replicated_value(metrics: dict, target: dict) -> float | None:
    """Find the replicated value for a target in metrics.json.

    Searches recursively through nested dicts. Tries the target's 'id'
    as a key at any level, then falls back to common naming patterns.
    """
    target_id = target.get("id", "")

    def _search_nested(obj, key):
        """Recursively search for key in nested dicts."""
        if isinstance(obj, dict):
            if key in obj:
                return _to_float(obj[key])
            for v in obj.values():
                result = _search_nested(v, key)
                if result is not None:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = _search_nested(item, key)
                if result is not None:
                    return result
        return None

    # Direct match (recursive)
    if target_id:
        result = _search_nested(metrics, target_id)
        if result is not None:
            return result
    # Try common suffixes/prefixes
    for key in _flatten_keys(metrics):
        if target_id in key or key in target_id:
            result = _search_nested(metrics, key)
            if result is not None:
                return result
    return None


def _flatten_keys(obj, prefix=""):
    """Yield all keys in a nested dict structure."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _flatten_keys(v, k)
    elif isinstance(obj, list):
        for item in obj:
            yield from _flatten_keys(item, prefix)


def _to_float(val) -> float | None:
    """Safely convert a value to float."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


# Constants the agent commonly hardcodes. These should live in
# config/run_config.yaml, not in strategy.py. Each entry is the
# assignment form we look for (e.g. ``N_BINS = 10``).
_HARDCODED_RUN_CONFIG_NAMES = (
    "N_BINS",
    "FORMATION_MONTHS",
    "SKIP_MONTHS",
    "HOLDING_MONTHS",
    "PRICE_FILTER",
    "SAMPLE_START",
    "SAMPLE_END",
    "START_DATE",
    "END_DATE",
    "FETCH_START",
    "FETCH_END",
)


def _check_run_config(replication_dir: Path) -> list[str]:
    """Return a list of warnings about config + hardcoded constants.

    Two checks:
      (a) config/run_config.yaml exists — the per-paper single source
          of truth for run parameters. If missing, the agent skipped
          the auto-generation step (or analyze.py was not run).
      (b) strategy.py does not hardcode any of the canonical
          constants listed in _HARDCODED_RUN_CONFIG_NAMES. These
          belong in run_config.yaml and should be loaded via
          ``load_run_config(slug)``.

    Returns a list of warning strings (empty if everything is clean).
    """
    warnings: list[str] = []
    if not replication_dir:
        return warnings

    run_config_path = replication_dir / "config" / "run_config.yaml"
    if not run_config_path.is_file():
        warnings.append(
            f"config/run_config.yaml missing at {run_config_path}. "
            f"This file is auto-generated by scripts/analyze.py from "
            f"spec.json — re-run analyze.py, or run "
            f"scripts/render_run_config.py manually."
        )

    strategy_path = replication_dir / "src" / "strategy.py"
    if strategy_path.is_file():
        try:
            strategy_text = strategy_path.read_text(encoding="utf-8")
        except OSError:
            return warnings
        # Only flag module-level assignments, not function args or local
        # variables. The pattern: "NAME = <value>" at line start (with
        # optional leading whitespace), not preceded by another identifier.
        import re
        # Match module-level assignments like:
        #     NAME = <value>
        # where <value> is NOT a function call. We extract the value
        # (captured group 2) and inspect it separately — a negative
        # lookahead on the RHS is fragile because of trailing-whitespace
        # consumption in the prefix.
        for name in _HARDCODED_RUN_CONFIG_NAMES:
            pattern = rf"(?m)^([ \t]*){name}\s*=\s*(.+?)\s*$"
            for match in re.finditer(pattern, strategy_text):
                value = match.group(2)
                # Strip trailing inline comment (e.g. `5  # default`) for the
                # function-call check. The value still appears in the warning.
                value_for_check = value.split("#", 1)[0].rstrip()
                if (
                    value_for_check.startswith("load_run_config")
                    or value_for_check.startswith("os.environ")
                    or value_for_check.startswith("fetch_data_cached")
                    or "(" in value_for_check
                ):
                    continue
                line_no = strategy_text[: match.start()].count(chr(10)) + 1
                warnings.append(
                    f"strategy.py line {line_no}: '{name} = ...' is hardcoded. "
                    f"Move it to config/run_config.yaml and load via "
                    f"``load_run_config(slug)['<key>']``. The config is "
                    f"auto-generated by analyze.py."
                )
    return warnings


def main():
    parser = argparse.ArgumentParser(
        description="Compare backtest output to paper-claimed replication targets."
    )
    parser.add_argument(
        "slug",
        help="Paper slug (e.g., 'max_v9') or path to the replication directory",
    )
    parser.add_argument(
        "--spec", help="Override path to spec.json",
    )
    parser.add_argument(
        "--metrics", help="Override path to metrics.json",
    )
    args = parser.parse_args()

    # Resolve paths
    try:
        spec_path = Path(args.spec) if args.spec else _find_spec_json(args.slug)
        metrics_path = Path(args.metrics) if args.metrics else _find_metrics_json(args.slug)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)

    # Derive the replication root for the config + strategy.py checks.
    # spec_path is <replication_root>/inputs/spec.json — go up two levels.
    replication_root = spec_path.parent.parent

    # Pre-flight: check that run_config.yaml exists and strategy.py
    # does not hardcode canonical run constants. These are non-fatal
    # warnings (the per-target validation below is the source of truth)
    # but they catch the most common process mistakes early.
    config_warnings = _check_run_config(replication_root)

    # Load spec.json — extract replication_targets
    with open(spec_path, encoding="utf-8") as f:
        spec_data = json.load(f)

    # Handle ExtractionResult wrapper
    if "strategies" in spec_data:
        strategies = spec_data["strategies"]
        if not strategies:
            print("ERROR: spec.json has empty 'strategies' list", file=sys.stderr)
            sys.exit(2)
        spec = strategies[0]
    else:
        spec = spec_data

    targets = spec.get("replication_targets", [])

    if not targets:
        print("No replication_targets found in spec.json — nothing to validate.")
        print("  (Add replication_targets to the spec for automatic validation.)")
        sys.exit(0)

    # Load metrics.json
    with open(metrics_path, encoding="utf-8") as f:
        raw_metrics = json.load(f)

    # metrics.json may be a list (one entry per commission rate) or a dict
    if isinstance(raw_metrics, list):
        # Use the first entry (0% commission — the academic standard)
        metrics = raw_metrics[0] if raw_metrics else {}
    elif isinstance(raw_metrics, dict):
        metrics = raw_metrics
    else:
        print(f"ERROR: metrics.json is not a dict or list (got {type(raw_metrics).__name__})", file=sys.stderr)
        sys.exit(2)

    # Compare each target
    results = []
    matched = 0
    for target in targets:
        tid = target.get("id", "?")
        paper_value = _to_float(target.get("paper_value"))
        tolerance = _to_float(target.get("tolerance"))
        replicated = _extract_replicated_value(metrics, target)
        reason = ""
        diff = None

        if paper_value is None:
            status = "SKIP"
            reason = "no paper_value in target"
        elif replicated is None:
            status = "MISSING"
            reason = f"key '{tid}' not found in metrics.json"
        elif tolerance is None:
            status = "SKIP"
            reason = "no tolerance in target"
        else:
            diff = abs(replicated - paper_value)
            if diff <= tolerance:
                status = "MATCH"
                matched += 1
            else:
                status = "FAIL"
                reason = f"diff {diff:.4f} > tolerance {tolerance:.4f}"

        results.append({
            "id": tid,
            "metric": target.get("metric", ""),
            "paper_value": paper_value,
            "replicated_value": replicated,
            "tolerance": tolerance,
            "diff": diff,
            "status": status,
            "table_ref": target.get("table_ref", ""),
            "description": target.get("description", ""),
            "reason": reason if status not in ("MATCH",) else "",
        })

    total = len(targets)
    hit_rate = matched / total if total > 0 else 0

    # Print config / hardcoded-constant warnings first (before the
    # per-target report), so the agent sees them in context.
    if config_warnings:
        print()
        print("=" * 70)
        print("CONFIG / STRATEGY HYGIENE WARNINGS")
        print("=" * 70)
        for w in config_warnings:
            print(f"  ⚠  {w}")
        print("=" * 70)

    # Print report
    print()
    print("=" * 70)
    print("REPLICATION VALIDATION REPORT")
    print("=" * 70)
    print(f"Spec:     {spec_path}")
    print(f"Metrics:  {metrics_path}")
    print(f"Targets:  {matched}/{total} matched ({hit_rate:.0%})")
    print("-" * 70)
    print(f"{'ID':<25} {'Status':<10} {'Paper':>10} {'Repl':>10} {'Diff':>10} {'Tol':>10}")
    print("-" * 70)
    for r in results:
        paper_s = f"{r['paper_value']:.4f}" if r['paper_value'] is not None else "?"
        repl_s = f"{r['replicated_value']:.4f}" if r['replicated_value'] is not None else "?"
        diff_s = f"{r['diff']:.4f}" if r['diff'] is not None else "?"
        tol_s = f"{r['tolerance']:.4f}" if r['tolerance'] is not None else "?"
        print(f"{r['id']:<25} {r['status']:<10} {paper_s:>10} {repl_s:>10} {diff_s:>10} {tol_s:>10}")
        if r['status'] not in ('MATCH',) and r['reason']:
            print(f"  -> {r['reason']}")
    print("=" * 70)

    # Write validation.json
    report = {
        "hit_rate": f"{matched}/{total} ({hit_rate:.0%})",
        "matched": matched,
        "total": total,
        "targets": results,
    }
    report_path = metrics_path.parent / "validation.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nReport written to: {report_path}")

    sys.exit(0 if matched == total else 1)


if __name__ == "__main__":
    main()
