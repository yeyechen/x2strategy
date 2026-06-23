"""Deterministic primitives for paper replication.

This package provides pure-Python building blocks that the LLM agent
calls into when generating ``strategy.py``. Every primitive:

- takes a pandas DataFrame in, returns a DataFrame (or metrics dict) out
- has no backtrader coupling — works for any strategy type
- has no side effects beyond an optional ``save_to=...`` for plots
- is deterministic — same input → same output, every time

This is the **deterministic primitives** layer the agent pipeline was
designed around. The agent writes only the **signal** (paper-specific);
primitives handle binning, portfolio construction, performance metrics,
plots, and Fama-MacBeth regressions.

Usage::

    from utils import (
        assign_quantiles,
        bin_returns,
        long_short,
        performance_metrics,
        plot_cumulative_returns,
    )

Quick reference (see each module's docstring for full details):

- :func:`utils.quantile.assign_quantiles` — within-date quantile binning
- :func:`utils.quantile.assign_ranks` — within-date ranking
- :func:`utils.portfolio.bin_returns` — EW + VW returns per bin
- :func:`utils.portfolio.long_short` — long-short portfolio from bins
- :func:`utils.metrics.performance_metrics` — Sharpe / CAGR / max DD / vol
- :func:`utils.plot.plot_cumulative_returns` — P&L curve
- :func:`utils.plot.plot_drawdown` — drawdown over time
- :func:`utils.plot.plot_decile_spread` — decile-level EW + VW bar chart
- :func:`utils.regressions.fama_macbeth` — monthly cross-section OLS with
  Newey-West t-stats

These primitives are ported and adapted from the user's
``RA-2025-summer/utils/`` codebase. See ``TODOs.md`` item #5 and
``references/spec2code.md`` for the integration plan.
"""

from __future__ import annotations

__version__ = "0.1.0"

# Re-export the public API at the package level for `from utils import X`.
# This matches the `RA-2025-summer/utils/__init__.py` convention.
from .quantile import (
    assign_quantiles,
    assign_ranks,
    QuantileError,
)

from .portfolio import (
    bin_returns,
    long_short,
    forward_returns,
    PortfolioError,
)

from .metrics import (
    performance_metrics,
    format_metrics,
    MetricsError,
)

from .plot import (
    plot_cumulative_returns,
    plot_drawdown,
    plot_decile_spread,
    plot_performance_comparison,
    PlotError,
)

from .plot_config import plot_config

from .regressions import (
    run_ols,
    fama_macbeth,
    summarize_fama_macbeth,
    RegressionError,
)


__all__ = [
    # quantile
    "assign_quantiles",
    "assign_ranks",
    "QuantileError",
    # portfolio
    "bin_returns",
    "long_short",
    "forward_returns",
    "PortfolioError",
    # metrics
    "performance_metrics",
    "format_metrics",
    "MetricsError",
    # plot
    "plot_cumulative_returns",
    "plot_drawdown",
    "plot_decile_spread",
    "plot_performance_comparison",
    "PlotError",
    # plot config
    "plot_config",
    # regressions
    "run_ols",
    "fama_macbeth",
    "summarize_fama_macbeth",
    "RegressionError",
]