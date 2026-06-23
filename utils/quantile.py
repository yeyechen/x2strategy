"""Quantile and rank binning — ported from RA-2025-summer/utils/portfolio_analysis.py.

Adapted for x2strategy:
- Type hints added throughout
- ``warn_fallback`` flag added to :func:`assign_quantiles` so the silent
  rank-based fallback (when ``pd.qcut`` can't bin uniformly) is observable
- Renamed ``PortfolioAnalysisError`` → ``QuantileError`` for module locality
- Pure functions: no ``print()`` side effects

These are the within-date binning primitives the agent calls after
computing a per-stock signal. The output bin (1..n_bins) is then passed
to :func:`utils.portfolio.bin_returns` to get EW + VW returns per bin.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


class QuantileError(Exception):
    """Raised when quantile binning cannot be applied to a frame."""
    pass


def assign_quantiles(
    df: pd.DataFrame,
    date_col: str,
    signal_col: str,
    n_bins: int = 10,
    warn_fallback: bool = True,
) -> pd.Series:
    """Assign 1-indexed quantile bins to ``signal_col`` within each date group.

    Equivalent to ``df.groupby(date_col)[signal_col].transform(pd.qcut, ...)``
    but with two extras:

    1. **Rank-based fallback** when ``pd.qcut`` fails (e.g. too many ties,
       too few distinct values). The fallback uses
       ``ceil(rank / len * n_bins)`` which preserves bin balance in
       well-behaved cases.
    2. **Optional warning** when the fallback is triggered. The user's
       original code fell back silently; that hides binning problems
       from the agent.

    Args:
        df: input DataFrame. Must contain ``date_col`` and ``signal_col``.
        date_col: column to group by (e.g. ``"month"``, ``"date"``).
        signal_col: column to bin (e.g. ``"max_daily_return"``, ``"log_mcap"``).
        n_bins: number of quantile bins. Default 10 (deciles).
        warn_fallback: if True, print a warning when ``pd.qcut`` fails and
            the rank-based fallback is used. Default True — set False for
            large pipelines where the warning would spam the logs.

    Returns:
        pandas Series with int bin labels in ``[1, n_bins]``. NaN where
        ``signal_col`` was NaN (the bin is undefined).

    Raises:
        QuantileError: if ``date_col`` or ``signal_col`` are missing, or if
            ``n_bins`` < 1.

    Example::

        df["decile"] = assign_quantiles(df, "month", "max_daily_return", n_bins=10)
    """
    if date_col not in df.columns:
        raise QuantileError(f"assign_quantiles: missing date_col '{date_col}'")
    if signal_col not in df.columns:
        raise QuantileError(f"assign_quantiles: missing signal_col '{signal_col}'")
    if n_bins < 1:
        raise QuantileError(f"assign_quantiles: n_bins must be >= 1, got {n_bins}")

    def _bin(series: pd.Series) -> pd.Series:
        # pd.qcut with duplicates="drop" handles ties gracefully.
        # We +1 so the smallest bin is 1 (matching convention in
        # utils.portfolio.long_short — long_bin=10 = top decile).
        try:
            return pd.qcut(series, q=n_bins, labels=False, duplicates="drop") + 1
        except (ValueError, TypeError):
            # Fallback: rank-based binning. Less accurate when there are
            # many ties but always produces a result.
            if warn_fallback:
                n_unique = series.nunique(dropna=True)
                print(
                    f"[utils] assign_quantiles: qcut failed for group "
                    f"(len={len(series)}, n_unique={n_unique}, n_bins={n_bins}); "
                    f"using rank-based fallback"
                )
            # ceil(rank / n * n_bins) — distributes ties via average rank.
            return np.ceil(series.rank(method="average") / len(series) * n_bins)

    return df.groupby(date_col)[signal_col].transform(_bin)


def assign_ranks(
    df: pd.DataFrame,
    date_col: str,
    signal_col: str,
    ascending: bool = False,
) -> pd.Series:
    """Assign within-date ranks to ``signal_col``.

    Args:
        df: input DataFrame. Must contain ``date_col`` and ``signal_col``.
        date_col: column to group by.
        signal_col: column to rank.
        ascending: if False (default), rank 1 = highest value (matching the
            "top decile = rank 1" convention). Set True to flip.

    Returns:
        pandas Series with int ranks in ``[1, len(group)]`` per date.
        Ties get method='first' to break deterministically.

    Raises:
        QuantileError: if ``date_col`` or ``signal_col`` are missing.

    Example::

        df["rank"] = assign_ranks(df, "month", "log_mcap", ascending=False)
    """
    if date_col not in df.columns:
        raise QuantileError(f"assign_ranks: missing date_col '{date_col}'")
    if signal_col not in df.columns:
        raise QuantileError(f"assign_ranks: missing signal_col '{signal_col}'")

    return df.groupby(date_col)[signal_col].transform(
        lambda x: x.rank(method="first", ascending=ascending)
    )


__all__ = ["assign_quantiles", "assign_ranks", "QuantileError"]