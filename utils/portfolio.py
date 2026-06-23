"""Portfolio construction from bins — ported from RA-2025-summer/utils/portfolio_analysis.py.

These are the two functions that turn a binned DataFrame into per-bin
returns and a long-short portfolio. They sit downstream of
:func:`utils.quantile.assign_quantiles` and upstream of
:func:`utils.metrics.performance_metrics`.

Pipeline::

    df              (raw stock-level data)
    │ assign_quantiles(date_col, signal_col, n_bins=10)
    ▼
    df["bin"]       (1..10)
    │ bin_returns(date_col, bin_col, ret_col, mcap_col)
    ▼
    bin_returns_df  (date × bin with EW and VW columns)
    │ long_short(date_col, ret_col, long_bin=10, short_bin=1)
    ▼
    ls_df           (date × 1 with ret column — the LS portfolio)

Both functions are pure: no plotting, no I/O, no LLM calls.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd


class PortfolioError(Exception):
    """Raised when portfolio construction fails."""
    pass


def bin_returns(
    df: pd.DataFrame,
    date_col: str,
    bin_col: str,
    ret_col: str,
    mcap_col: str = "mcap_lag1",
) -> pd.DataFrame:
    """Calculate per-bin returns, both equal-weighted (EW) and value-weighted (VW).

    Args:
        df: input DataFrame containing one row per (stock, date) with a
            pre-computed ``bin_col``. Must contain ``date_col``, ``bin_col``,
            ``ret_col``, and ``mcap_col``.
        date_col: column to group by (e.g. ``"month"``).
        bin_col: 1-indexed bin label column (output of
            :func:`utils.quantile.assign_quantiles`).
        ret_col: stock return column.
        mcap_col: market-cap column for value-weighting. Default
            ``"mcap_lag1"`` matches the MAX paper convention.

    Returns:
        DataFrame with one row per (date, bin) and columns:
            - ``date_col`` (renamed via the ``date_col`` arg)
            - ``bin_col``
            - ``EW`` (equal-weighted mean return within the bin)
            - ``VW`` (value-weighted mean return within the bin)

    Raises:
        PortfolioError: if required columns are missing or aggregation fails.

    Example::

        bin_returns_df = bin_returns(df, "month", "decile", "ret", "mcap_lag1")
        # bin_returns_df columns: ["month", "decile", "EW", "VW"]
    """
    required = [date_col, bin_col, ret_col, mcap_col]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise PortfolioError(f"bin_returns: missing columns {missing}")

    try:
        return df.groupby([date_col, bin_col], as_index=False).apply(
            lambda g: pd.Series({
                "EW": g[ret_col].mean(),
                "VW": (g[ret_col] * g[mcap_col]).sum() / g[mcap_col].sum(),
            }),
            include_groups=False,
        ).reset_index(drop=True)
    except Exception as e:
        raise PortfolioError(f"bin_returns: aggregation failed: {e}")


def long_short(
    bins_df: pd.DataFrame,
    date_col: str,
    ret_col: str,
    long_bin: Optional[int] = None,
    short_bin: Optional[int] = None,
) -> pd.DataFrame:
    """Construct a long-short portfolio by subtracting two bins.

    Args:
        bins_df: output of :func:`bin_returns`. Must contain ``date_col``,
            a ``"bin"`` column, and ``ret_col``.
        date_col: date column (used for the merge).
        ret_col: which weighted-return column to use (typically ``"EW"`` or
            ``"VW"``).
        long_bin: bin to go long. Default: the highest bin (computed from
            the data).
        short_bin: bin to go short. Default: the lowest bin.

    Returns:
        DataFrame with one row per date, columns ``date_col`` and ``"ret"``
        where ``ret`` is ``long_minus_short`` of ``ret_col``.

    Raises:
        PortfolioError: if columns are missing, if either bin is empty, or
            if both bins refer to the same value.

    Example::

        ls = long_short(bins_df, "month", "VW", long_bin=10, short_bin=1)
        # ls.columns: ["month", "ret"]
    """
    required = [date_col, "bin", ret_col]
    missing = [c for c in required if c not in bins_df.columns]
    if missing:
        raise PortfolioError(f"long_short: missing columns {missing}")

    # Default to extreme bins
    if long_bin is None:
        long_bin = int(bins_df["bin"].max())
    if short_bin is None:
        short_bin = int(bins_df["bin"].min())

    if long_bin == short_bin:
        raise PortfolioError(
            f"long_short: long_bin ({long_bin}) and short_bin "
            f"({short_bin}) must differ"
        )

    long_data = bins_df.loc[bins_df["bin"] == long_bin, [date_col, ret_col]].rename(
        columns={ret_col: f"{ret_col}_long"}
    )
    short_data = bins_df.loc[bins_df["bin"] == short_bin, [date_col, ret_col]].rename(
        columns={ret_col: f"{ret_col}_short"}
    )

    if long_data.empty:
        raise PortfolioError(f"long_short: no data for long_bin={long_bin}")
    if short_data.empty:
        raise PortfolioError(f"long_short: no data for short_bin={short_bin}")

    merged = pd.merge(long_data, short_data, on=date_col, how="inner")
    merged["ret"] = merged[f"{ret_col}_long"] - merged[f"{ret_col}_short"]
    return merged[[date_col, "ret"]].reset_index(drop=True)


__all__ = ["bin_returns", "long_short", "PortfolioError"]