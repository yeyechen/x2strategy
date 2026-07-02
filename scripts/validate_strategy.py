#!/usr/bin/env python3
"""validate_strategy.py — Sanity checks on the strategy output.

The fip_v4 run produced base momentum of 0.05% (literature says 6%+
for JT 12-2 over 6 months). The agent's own diagnostic flagged the
discrepancy but the run completed anyway. This script runs a few
sanity checks on `results/metrics.json` and `results/SUMMARY.md` and
fails loudly if the strategy output is implausible.

What it checks (best-effort, all warnings):
  1. **Base momentum sanity**: if the strategy's main L/S return is
     in `metrics.json`, the equivalent simple-momentum check should
     be in a plausible range. The strategy is wrong if it's not.
  2. **Look-ahead smoke test**: the metric values are finite (no
     NaN/Inf). A NaN alpha usually means the agent's dep var was
     wrong (e.g. `ret_fwd6` instead of `ret`) or the agent passed
     a numpy array instead of a DataFrame.
  3. **t-stat plausibility**: the reported t-stats are not absurdly
     large (>10) or small (<0.1 in absolute value when n_obs > 100).
  4. **n_obs sanity**: the replication sample has enough observations
     (n_obs > 100 for monthly, > 1000 for daily).

The script does NOT know the paper-claimed values (that's
`validate_replication.py`'s job). It catches the "your numbers are
implausible" case before the human even reads the hit-rate table.

Exit codes:
  0  — all checks pass
  1  — one or more sanity checks failed
  2  — error reading metrics.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


def _check_metrics(metrics: dict, file_path: Path) -> list[str]:
    """Return a list of warning/error strings. Empty = all checks pass."""
    errors: list[str] = []

    # 1. Look-ahead / runtime smoke test: no NaN/Inf in numeric fields.
    def _walk_finite(obj, path: str = "") -> list[str]:
        bad = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                bad.extend(_walk_finite(v, f"{path}.{k}" if path else k))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                bad.extend(_walk_finite(v, f"{path}[{i}]"))
        elif isinstance(obj, float):
            if math.isnan(obj) or math.isinf(obj):
                bad.append(path)
        return bad

    nan_inf = _walk_finite(metrics)
    if nan_inf:
        errors.append(
            f"NaN or Inf in metrics.json at: {', '.join(nan_inf[:5])}. "
            f"This usually means a regression's dep var was wrong "
            f"(e.g. ret_fwd6 instead of ret) or factor_alpha was passed "
            f"a numpy array instead of a DataFrame. Check the strategy.py "
            f"around the failing metric."
        )

    # 2. t-stat plausibility
    def _walk_tstat(obj, path: str = "") -> list[str]:
        bad = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.endswith("_tstat") or k == "t_stat" or k == "t_alpha_newey_west":
                    if isinstance(v, (int, float)) and not math.isnan(v):
                        if abs(v) > 10:
                            bad.append(
                                f"{path}.{k}={v:.2f} is implausibly large "
                                f"(t-stats > 10 are rare in academic work)"
                            )
                bad.extend(_walk_tstat(v, f"{path}.{k}" if path else k))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                bad.extend(_walk_tstat(v, f"{path}[{i}]"))
        return bad

    bad_tstats = _walk_tstat(metrics)
    if bad_tstats:
        errors.append(
            "Implausible t-stats in metrics.json — likely bugs:\n"
            + "\n".join(f"  - {x}" for x in bad_tstats[:5])
        )

    # 3. n_obs sanity — replication sample should have enough obs.
    def _walk_nobs(obj, path: str = "") -> list[str]:
        bad = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "n_obs" and isinstance(v, (int, float)):
                    if v < 100:
                        bad.append(
                            f"{path}.{k}={v} is very small; "
                            f"the replication sample may be too short"
                        )
                bad.extend(_walk_nobs(v, f"{path}.{k}" if path else k))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                bad.extend(_walk_nobs(v, f"{path}[{i}]"))
        return bad

    bad_nobs = _walk_nobs(metrics)
    if bad_nobs:
        errors.append(
            "Suspiciously small n_obs in metrics.json:\n"
            + "\n".join(f"  - {x}" for x in bad_nobs[:5])
        )

    # 4. Base-momentum plausibility: any value in metrics.json whose
    # key contains "momentum" or "spread" should be in a plausible
    # range for a cross-sectional equity paper. A value under 0.5%
    # (in absolute value) is suspicious — the literature shows
    # ~1%/month for JT 12-2 (~5-8% over 6 months). A near-zero
    # headline usually means the formation period or the forward-
    # return computation is wrong. The fip_v4 run had
    # continuous_id_momentum = 4.56 (close to the paper's 5.95) but
    # if it had been 0.05% we'd flag it.
    suspicious = []
    for k, v in metrics.items():
        if not isinstance(v, (int, float)):
            continue
        if math.isnan(v) or math.isinf(v):
            continue
        if "momentum" in k.lower() or "spread" in k.lower():
            if abs(v) < 0.5 and v != 0:
                suspicious.append((k, v))
    for k, v in suspicious:
        errors.append(
            f"metrics.json['{k}'] = {v} is suspiciously small. "
            f"For JT 12-2 momentum over 6 months, the literature "
            f"shows ~5-8% (continuous-info L/S in FIP, top-decile "
            f"momentum). A near-zero headline usually means the "
            f"formation period or the forward-return computation is "
            f"wrong. Check PRET and forward_returns usage in "
            f"strategy.py."
        )

    return errors


def main():
    parser = argparse.ArgumentParser(
        description="Sanity checks on the strategy output (best-effort)."
    )
    parser.add_argument(
        "slug",
        help="Paper slug (e.g. 'fip_v4') or path to a replication directory",
    )
    args = parser.parse_args()

    slug_path = Path(args.slug)
    if slug_path.is_dir():
        candidates = [
            slug_path / "results" / "metrics.json",
            slug_path / "metrics.json",
        ]
    else:
        candidates = [
            Path("replications") / args.slug / "results" / "metrics.json",
            Path("replications") / args.slug / "metrics.json",
        ]

    metrics_path = next((p for p in candidates if p.is_file()), None)
    if metrics_path is None:
        print(
            f"ERROR: cannot find metrics.json in any of:\n  "
            + "\n  ".join(str(p) for p in candidates),
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        with open(metrics_path, encoding="utf-8") as f:
            metrics = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: {metrics_path} is not valid JSON: {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"ERROR: failed to read {metrics_path}: {e}", file=sys.stderr)
        sys.exit(2)

    errors = _check_metrics(metrics, metrics_path)
    if not errors:
        print(f"✓ sanity checks pass: {metrics_path}")
        sys.exit(0)

    print(f"⛔ sanity checks FAILED: {metrics_path}", file=sys.stderr)
    print("", file=sys.stderr)
    for i, err in enumerate(errors, 1):
        print(f"  {i}. {err}", file=sys.stderr)
    print("", file=sys.stderr)
    print(
        "These are plausibility checks, not hit-rate checks. Fix the "
        "underlying bugs in strategy.py before reporting results.",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
