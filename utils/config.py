"""Per-paper run-config loader for deterministic replication.

A paper replication has settings that vary by paper:
- date range
- universe filter (exchange codes, share codes)
- signal / binning parameters (n_bins, weighting, forward-returns lag)
- Fama-French control table (when applicable)
- output list

These belong in `replications/<slug>/config/run_config.yaml`, generated
from `inputs/spec.json` by `scripts/render_run_config.py`. The
generated strategy.py loads it via :func:`load_run_config` instead of
hard-coding values, so different papers automatically get different
configs and there is one source of truth per replication.

Usage from generated strategy.py::

    from utils import load_run_config, paper_layout

    layout = paper_layout("<slug>")
    cfg = load_run_config("<slug>")

    daily = fetch_data_cached(
        cfg["data_sources"]["daily_returns"],
        ["permno", "date", "ret", "prc", "shrout"],
        cfg["start_date"], cfg["end_date"],
        extra_where=cfg.get("universe", {}).get("where_clause", ""),
    )
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml


class RunConfigError(Exception):
    """Raised when a paper's run_config.yaml cannot be read or is invalid."""
    pass


def load_run_config(
    slug: str,
    *,
    replications_root: str | Path | None = None,
) -> Dict[str, Any]:
    """Load ``config/run_config.yaml`` for one paper replication.

    Args:
        slug: paper slug (the directory name under the replications root).
        replications_root: override the replications root. Defaults to the
            ``PAPER2SPEC_REPLICATIONS_PATH`` env var, then ``./replications``.

    Returns:
        The parsed YAML as a nested dict. Empty sections come back as
        empty dicts / empty lists / ``None`` rather than missing keys.

    Raises:
        RunConfigError: if the file is missing or malformed YAML.
    """
    from paper2spec.paths import paper_layout

    layout = paper_layout(slug, replications_root=replications_root)
    config_path = layout.config_path("run_config.yaml")

    if not config_path.is_file():
        raise RunConfigError(
            f"run_config.yaml not found at {config_path}. "
            f"Generate it with: bash scripts/render_run_config.py "
            f"<spec.json> -o {config_path}"
        )

    try:
        with config_path.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise RunConfigError(f"Failed to parse {config_path}: {e}") from e

    if not isinstance(cfg, dict):
        raise RunConfigError(
            f"{config_path} did not parse to a mapping (got {type(cfg).__name__})"
        )

    return cfg


def render_run_config(
    spec_dict: Dict[str, Any],
    *,
    paper_layout_obj=None,
) -> str:
    """Render a YAML run_config string from a StrategySpec dict.

    Used by ``scripts/render_run_config.py`` to materialize the per-paper
    config from the extracted spec. Extracts:
      - time period (from spec.strategies[0].time_period or spec.metadata)
      - data sources (defaults to CRSP daily + index, Compustat funda)
      - universe filter (default: NYSE/AMEX/NASDAQ, share codes [10, 11],
        $5 price floor, delisting adjustment, NYSE breakpoints — per
        references/paper_conventions.md)
      - n_bins (default 10, from first numeric parameter in indicators)
      - weighting (default "VW", from spec.execution_plan[0].position_sizing)
      - forward_returns_lag (default 1 — the cross-sectional convention)
      - ff_controls (default 4-factor Carhart if the strategy is
        cross-sectional equity)

    Args:
        spec_dict: a StrategySpec dict (from ``inputs/spec.json``) or an
            ExtractionResult wrapping multiple strategies.
        paper_layout_obj: optional PaperLayout; only used to derive
            data-source defaults if not in the spec.

    Returns:
        YAML string. Caller writes to ``config/run_config.yaml``.
    """
    # Unwrap ExtractionResult if needed
    if "strategies" in spec_dict and isinstance(spec_dict["strategies"], list):
        strategies = spec_dict["strategies"]
        if not strategies:
            raise ValueError("spec_dict has empty 'strategies' list")
        spec = strategies[0]
    else:
        spec = spec_dict

    # ── Time period ─────────────────────────────────────────
    # Spec's `time_period` may be either:
    # (a) a dict {start_date, end_date}
    # (b) a free-text string like "July 1962 to December 2005"
    # (c) missing entirely
    time_period = spec.get("time_period") or {}
    if isinstance(time_period, dict):
        start_date = time_period.get("start_date") or "1962-01-01"
        end_date = time_period.get("end_date") or "2024-12-31"
    elif isinstance(time_period, str):
        # Parse "Month YYYY to Month YYYY" or "YYYY-MM-DD to YYYY-MM-DD"
        import re
        years = re.findall(r"\b(\d{4})\b", time_period)
        if len(years) >= 2:
            start_date = f"{years[0]}-01-01"
            end_date = f"{years[-1]}-12-31"
        else:
            start_date = "1962-01-01"
            end_date = "2024-12-31"
    else:
        start_date = "1962-01-01"
        end_date = "2024-12-31"

    # ── Universe filter ───────────────────────────────────────
    # Convention defaults from references/paper_conventions.md.
    # The agent may override these based on the paper's stated methodology.
    universe = {
        "exchanges": [1, 2, 3],   # NYSE, AMEX, NASDAQ
        "share_codes": [10, 11],   # ordinary common shares
        "price_filter": 5.0,       # $5 minimum (penny-stock exclusion)
        "delisting_adjustment": True,  # use dsedelist.dlret when available
        "breakpoint_universe": "NYSE",  # NYSE-only for size-based breakpoints
    }
    exch_set = ",".join(str(x) for x in universe["exchanges"])
    shr_set = ",".join(str(x) for x in universe["share_codes"])
    universe["where_clause"] = (
        f"exchcd IN ({exch_set}) AND shrcd IN ({shr_set})"
    )

    # ── Data sources ─────────────────────────────────────────
    # Default: 2026 vintage (latest in ClickHouse). Pulled from the
    # spec if the agent has flagged a different vintage.
    data_sources = {
        "daily_returns": "crsp_202601.dsf",
        "daily_index": "crsp_202601.dsi",
        "fundamentals": "comp_202601.funda",
        "ccm_link": "crsp_202601.ccmxpf_linktable",
    }

    # ── Signal & binning ─────────────────────────────────────
    indicators = spec.get("indicators") or []
    signal_column = None
    n_bins = 10
    for ind in indicators:
        if not isinstance(ind, dict):
            continue
        # The first numeric-output indicator is usually the cross-sectional
        # signal. e.g. MAX, MOM, B/M ratio.
        if ind.get("output_type") in ("scalar", "float", "int"):
            signal_column = ind.get("indicator_id") or ind.get("name")
            break
    if not signal_column:
        signal_column = "signal"

    # ── Signal directions (long_leg) ─────────────────────────
    # Each signal has a direction: "high" means top-quintile is the long
    # leg (e.g. momentum — winners), "low" means bottom-quintile is the
    # long leg (e.g. FIP ID — continuous info). The spec extraction
    # prompt asks the LLM to fill this in based on the paper. If the
    # spec has no `signals` field, leave it empty and the strategy
    # must fall back to a sensible default (e.g. high for momentum).
    raw_signals = spec.get("signals") or []
    signals_cfg: list[dict] = []
    if isinstance(raw_signals, list):
        for sig in raw_signals:
            if not isinstance(sig, dict):
                continue
            name = sig.get("name") or sig.get("indicator_id")
            long_leg = sig.get("long_leg")
            if isinstance(long_leg, str):
                long_leg = long_leg.strip().lower()
                if long_leg in ("high", "low"):
                    if name:
                        signals_cfg.append({
                            "name": str(name),
                            "long_leg": long_leg,
                        })
                # else: invalid value — silently skip; the renderer is
                # best-effort and the strategy can default.

    # ── Weightings reported by the paper ─────────────────────
    # Most academic cross-sectional papers report BOTH EW and VW spreads
    # side-by-side. The spec's `weightings_reported` lists all that the
    # paper actually reports (typically ["EW", "VW"]). The single
    # `weighting` field above is the primary used for the headline
    # hit-rate; the strategy code should still compute all of them.
    # We normalize to uppercase and validate against {"EW", "VW"}.
    raw_weightings = spec.get("weightings_reported") or []
    weightings_reported_cfg: list[str] = []
    if isinstance(raw_weightings, list):
        for w in raw_weightings:
            if isinstance(w, str):
                wn = w.strip().upper()
                if wn in ("EW", "VW") and wn not in weightings_reported_cfg:
                    weightings_reported_cfg.append(wn)

    # ── Execution plan ────────────────────────────────────────
    execution_plans = spec.get("execution_plan") or []
    weighting = "VW"
    weighting_aliases = {
        "value-weighted": "VW",
        "value_weighted": "VW",
        "equal-weighted": "EW",
        "equal_weighted": "EW",
        "vw": "VW",
        "ew": "EW",
    }
    for plan in execution_plans:
        if not isinstance(plan, dict):
            continue
        sizing = plan.get("position_sizing") or {}
        if isinstance(sizing, dict):
            steps = sizing.get("steps") or []
            for step in steps:
                if isinstance(step, dict):
                    raw_w = step.get("parameters", {}).get("weighting")
                    if raw_w:
                        weighting = weighting_aliases.get(
                            str(raw_w).strip().lower(), str(raw_w)
                        )
                        break

    # ── Fama-French controls ──────────────────────────────────
    # Default to 4-factor Carhart if this is a US equity strategy that
    # is NOT explicitly single-asset. Most academic equity papers
    # (long-short, cross-sectional, momentum, value) use FF factors.
    ff_controls = None
    asset_class = spec.get("asset_class") or []
    strategy_type = (spec.get("strategy_type") or "").lower()
    is_equity = "equity" in asset_class
    is_single_asset = "single_asset" in strategy_type
    if is_equity and not is_single_asset:
        ff_controls = {
            "table": "ff.four_factor_monthly",
            "factors": ["mkt_rf", "smb", "hml", "mom"],
            "date_column": "dt",  # CRSP/Compustat use `date`, FF uses `dt`
        }

    # ── Outputs ──────────────────────────────────────────────
    outputs = [
        "results/SUMMARY.md",
        "results/validation.json",
        "results/metrics.json",
        "results/pnl_curve.png",
        "results/drawdown.png",
        "results/decile_spread.png",
        "results/decile_spread.csv",
    ]
    if ff_controls:
        outputs.append("results/fama_macbeth.txt")

    # ── Assemble ────────────────────────────────────────────
    cfg = {
        "start_date": start_date,
        "end_date": end_date,
        "data_sources": data_sources,
        "universe": universe,
        "signal_column": signal_column,
        "n_bins": n_bins,
        "weighting": weighting,
        "forward_returns_lag": 1,
        "initial_cash": 100000.0,
        "trading_frequency": "M",
        "signals": signals_cfg,
        "weightings_reported": weightings_reported_cfg,
        "outputs": outputs,
    }
    if ff_controls is not None:
        cfg["ff_controls"] = ff_controls

    dumped = yaml.safe_dump(
        cfg,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    # PyYAML's safe_dump quotes date-like strings ("1962-07-01") so they
    # stay strings when loaded back. KEEP the quotes — stripping them
    # causes PyYAML to parse dates as datetime.date objects, which breaks
    # string operations (slicing, comparison) in generated strategy code.
    return dumped


__all__ = ["load_run_config", "render_run_config", "RunConfigError"]