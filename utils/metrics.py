"""Performance metrics — ported from RA-2025-summer/utils/portfolio_analysis.py.

The single most important primitive in this package. Given a return
series, this function returns the dict the agent needs to fill in
``results/metrics.json`` and compare against paper-claimed numbers.

Output keys match ``spec2code.models.BacktestMetrics`` (so the existing
diagnosis pipeline consumes them without conversion):

    {
        "total_return":      float,   # cumulative (1 + r).prod() - 1
        "annual_return":     float,   # mean * ann_factor
        "annualized_vol":    float,   # std * sqrt(ann_factor)
        "sharpe_ratio":      float,   # ann_ret / ann_vol
        "max_drawdown":      float,   # min of cum_ret / running_max - 1
        "cagr":              float,   # (1 + total_ret) ** (1/years) - 1
    }

These names are also friendly to the agent: when it's writing
``metrics.json``, it can map them straight in.
"""

from __future__ import annotations

from typing import Dict, Literal, Union

import numpy as np
import pandas as pd


# Annualization factors — matches the user's source.
_ANN_FACTORS: Dict[str, int] = {
    "D": 252,
    "W": 52,
    "M": 12,
}

FreqLiteral = Literal["D", "W", "M"]


class MetricsError(Exception):
    """Raised when performance metrics cannot be computed."""
    pass


def performance_metrics(
    returns: Union[pd.Series, pd.DataFrame],
    freq: FreqLiteral = "M",
    date_col: str = "date",
    ret_col: str = "ret",
) -> Dict[str, float]:
    """Compute performance metrics for a return series.

    Args:
        returns: either a pandas Series indexed by date, or a DataFrame
            with columns ``date_col`` (date) and ``ret_col`` (return).
        freq: ``"D"``, ``"W"``, or ``"M"`` — drives annualization
            (252 / 52 / 12 trading periods per year).
        date_col: name of the date column when ``returns`` is a DataFrame.
            Ignored if ``returns`` is a Series.
        ret_col: name of the return column when ``returns`` is a DataFrame.
            Ignored if ``returns`` is a Series.

    Returns:
        Dict with keys ``total_return``, ``annual_return``,
        ``annualized_vol`` (also aliased as ``annualized_volatility`` for
        consistency with the user's source), ``sharpe_ratio``,
        ``max_drawdown``, ``cagr``.

    Raises:
        MetricsError: if freq is not D/W/M, or if the return series is
            empty / has zero variance.

    Example::

        metrics = performance_metrics(ls["ret"], freq="M")
        # {'total_return': 1.23, 'annual_return': 0.08, 'sharpe_ratio': 0.97, ...}
    """
    if freq not in _ANN_FACTORS:
        raise MetricsError(f"Invalid frequency '{freq}'. Must be one of D, W, M")

    # Normalize input
    if isinstance(returns, pd.DataFrame):
        if ret_col not in returns.columns:
            raise MetricsError(f"DataFrame missing ret_col '{ret_col}'")
        if date_col in returns.columns:
            returns = returns.set_index(date_col)[ret_col]
        else:
            returns = returns[ret_col]
    elif not isinstance(returns, pd.Series):
        raise MetricsError(f"returns must be Series or DataFrame, got {type(returns)}")

    if returns.empty:
        raise MetricsError("Cannot compute metrics on empty return series")

    returns = returns.dropna()
    if returns.empty:
        raise MetricsError("All returns are NaN")

    try:
        ann_factor = _ANN_FACTORS[freq]
        # Sort chronologically — pd.Series may not be sorted by index
        # if the caller merged in some non-monotonic order.
        sorted_returns = returns.sort_index()

        cum_ret = (1 + sorted_returns).cumprod()
        total_ret = float(cum_ret.iloc[-1] - 1)

        # CAGR — uses elapsed calendar days, not bar count, so partial
        # windows don't bias the figure.
        if isinstance(sorted_returns.index, pd.DatetimeIndex):
            n_days = (sorted_returns.index.max() - sorted_returns.index.min()).days
            n_years = n_days / 365.25
        else:
            n_years = len(sorted_returns) / ann_factor

        if n_years <= 0:
            raise MetricsError("Invalid date range for CAGR calculation")
        cagr = (1 + total_ret) ** (1 / n_years) - 1

        ann_ret = float(sorted_returns.mean() * ann_factor)
        ann_vol = float(sorted_returns.std(ddof=0) * np.sqrt(ann_factor))
        # Tolerance for floating-point: a perfectly constant series has
        # std = 0 mathematically, but pd.Series.std(ddof=0) on [c, c, c, ...]
        # returns ~1e-18 due to floating-point representation. Treat anything
        # below 1e-12 as effectively zero to avoid Sharpe blowups.
        sharpe = ann_ret / ann_vol if abs(ann_vol) > 1e-12 else 0.0

        # Max drawdown — running max of cum_ret, drawdown is min of
        # cum_ret / running_max - 1.
        running_max = cum_ret.expanding().max()
        drawdowns = cum_ret / running_max - 1
        max_dd = float(drawdowns.min())

        return {
            "total_return": total_ret,
            "annual_return": ann_ret,
            "annualized_vol": ann_vol,            # canonical
            "annualized_volatility": ann_vol,     # alias — matches user's source
            "sharpe_ratio": sharpe,
            "max_drawdown": max_dd,
            "cagr": cagr,
        }
    except Exception as e:
        if isinstance(e, MetricsError):
            raise
        raise MetricsError(f"performance_metrics: computation failed: {e}")


def format_metrics(metrics: Dict[str, float]) -> Dict[str, str]:
    """Format a metrics dict as human-readable strings (percent / 2-decimal).

    Useful for printing to stdout or writing to
    ``results/backtest_output.txt``. Pure function — no printing.

    Args:
        metrics: the dict returned by :func:`performance_metrics`.

    Returns:
        A new dict with the same keys but formatted string values:
        - percentages become ``"X.XX%"``
        - ratios stay as ``"X.XX"``

    Example::

        print(format_metrics(performance_metrics(returns, freq="M")))
        # ╔═══════════════════════════════╗
        # ║ Total Return      │  123.45%  ║
        # ║ Annual Return     │    8.20%  ║
        # ║ Sharpe Ratio      │    0.97   ║
        # ║ Max Drawdown      │  -34.50%  ║
        # ║ ...                          ║
        # ╚═══════════════════════════════╝
    """
    return {
        "Total Return":      f"{metrics['total_return'] * 100:.2f}%",
        "Annual Return":     f"{metrics['annual_return'] * 100:.2f}%",
        "Sharpe Ratio":      f"{metrics['sharpe_ratio']:.2f}",
        "Max Drawdown":      f"{metrics['max_drawdown'] * 100:.2f}%",
        "CAGR":              f"{metrics['cagr'] * 100:.2f}%",
        "Annualized Vol":    f"{metrics['annualized_vol'] * 100:.2f}%",
    }


__all__ = ["performance_metrics", "format_metrics", "MetricsError", "FreqLiteral"]

def tstat_newey_west(
    returns: Union[pd.Series, pd.DataFrame],
    n_lags: int = 5,
    date_col: str = "date",
    ret_col: str = "ret",
) -> Dict[str, float]:
    """Compute Newey-West (1987) HAC t-stat for the mean of a return series.

    For overlapping cohorts (Jegadeesh-Titman, H-month holding), the
    monthly portfolio returns are autocorrelated; the iid t-stat
    overstates significance. Newey-West with n_lags = H - 1 corrects
    this.

    The regression is::

        r_t = alpha + epsilon_t

    where alpha is the mean return. The t-stat on alpha is what papers
    report. Under H-month overlapping cohorts, set n_lags = H - 1.

    Args:
        returns: a pandas Series indexed by date, or a DataFrame with
            ``date_col`` and ``ret_col``.
        n_lags: number of HAC lags. Default 5. For H-month overlapping
            cohorts, use H - 1.
        date_col: name of the date column when ``returns`` is a DataFrame.
        ret_col: name of the return column when ``returns`` is a DataFrame.

    Returns:
        Dict with keys:
          - ``mean_return``: average return (per-period)
          - ``t_stat``: Newey-West HAC t-stat on the mean
          - ``n_obs``: number of observations

    Example::

        # FIP 6-month overlapping cohorts:
        nw = tstat_newey_west(fip_spread, n_lags=5)
        # Paper reports t=5.03; iid t=21.01; NW-corrected should be ~5.

        # MAX 1-month holding (no overlap):
        nw = tstat_newey_west(ls_spread, n_lags=0)
    """
    from statsmodels.regression.linear_model import OLS
    from statsmodels.tools import add_constant

    if isinstance(returns, pd.DataFrame):
        if ret_col not in returns.columns:
            raise MetricsError(f"DataFrame missing ret_col '{ret_col}'")
        if date_col in returns.columns:
            returns = returns.set_index(date_col)[ret_col]
        else:
            returns = returns[ret_col]
    elif not isinstance(returns, pd.Series):
        raise MetricsError(f"returns must be Series or DataFrame, got {type(returns)}")

    r = returns.dropna().sort_index()
    if r.empty:
        raise MetricsError("Cannot compute t-stat on empty return series")
    if n_lags < 0:
        raise MetricsError(f"n_lags must be >= 0, got {n_lags}")

    y = r.values
    X = add_constant(np.ones_like(y))  # only an intercept
    res = OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": n_lags})
    # First coef (const) is the mean; t-stat of const is what we report.
    return {
        "mean_return": float(res.params[0]),
        "t_stat": float(res.tvalues[0]),
        "n_obs": int(res.nobs),
    }


__all__ = ["performance_metrics", "format_metrics", "tstat_newey_west", "MetricsError", "FreqLiteral"]
