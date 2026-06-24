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
        DataFrame with one row per (date, bin) and the following columns:
            - ``date_col`` (the date column, exactly as named — e.g. "month")
            - ``bin_col``  (the bin label column, exactly as named —
              whatever you passed as ``bin_col``, e.g. "decile" or "bin")
            - ``"EW"``     (equal-weighted mean return within the bin)
            - ``"VW"``     (value-weighted mean return within the bin)

        **The return columns are LITERALLY named ``"EW"`` and ``"VW"`` —
        they are NOT renamed based on the input.** Pass the column name
        you want via the ``weighting`` argument to
        :func:`long_short` (which understands both).

    Raises:
        PortfolioError: if required columns are missing or aggregation fails.

    Example::

        bin_returns_df = bin_returns(df, "month", "decile", "ret", "mcap_lag1")
        # bin_returns_df columns: ["month", "decile", "EW", "VW"]
        #                              ^        ^         ^    ^
        #                              date_col bin_col   EW  VW

        # Then form the long-short portfolio — pick EW or VW via weighting:
        ls = long_short(bin_returns_df, date_col="month", weighting="VW",
                        long_bin=1, short_bin=N_BINS)
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
    weighting: str = "VW",
    long_bin: Optional[int] = None,
    short_bin: Optional[int] = None,
    bin_col: str = "bin",
    ret_col: Optional[str] = None,
) -> pd.DataFrame:
    """Construct a long-short portfolio by subtracting two bins.

    The canonical call is::

        ls = long_short(bin_rets, date_col="month", weighting="VW",
                        long_bin=1, short_bin=N_BINS)

    The function looks up the right per-bin return column from
    ``bin_rets`` (output of :func:`bin_returns`) using ``weighting`` —
    the agent does NOT need to know that bin_returns emits columns
    literally named ``"EW"`` and ``"VW"``.

    Args:
        bins_df: output of :func:`bin_returns`. Must contain ``date_col``,
            ``bin_col``, and the column named by ``weighting`` (``"EW"``
            or ``"VW"``). For backward compatibility, an explicit
            ``ret_col`` may be supplied instead.
        date_col: date column (used for the merge).
        weighting: which weighted-return column to use. ``"EW"`` for
            equal-weighted, ``"VW"`` for value-weighted. Default ``"VW"``
            (matches the MAX paper convention). Internally translates
            to ``ret_col = weighting``.
        long_bin: bin to go long. Default: the highest bin (computed from
            the data).
        short_bin: bin to go short. Default: the lowest bin.
        bin_col: name of the bin-label column in ``bins_df``. Default
            ``"bin"`` (matches the column name produced by
            :func:`utils.quantile.assign_quantiles`).
        ret_col: DEPRECATED. Use ``weighting=`` instead. If provided,
            overrides ``weighting`` for backward compatibility. Emits a
            :class:`DeprecationWarning`.

    Returns:
        DataFrame with one row per date, columns ``date_col`` and ``"ret"``
        where ``ret`` is ``long_minus_short`` of the chosen return column.

    Raises:
        PortfolioError: if columns are missing, if either bin is empty, or
            if both bins refer to the same value.

    Example::

        # Canonical (preferred):
        ls = long_short(bin_rets, date_col="month", weighting="VW",
                        long_bin=10, short_bin=1)
        # ls.columns: ["month", "ret"]

        # Legacy (still works, with DeprecationWarning):
        ls = long_short(bin_rets, "month", "VW", long_bin=10, short_bin=1)
    """
    # Resolve the actual return-column name from weighting / ret_col.
    if ret_col is not None:
        import warnings
        warnings.warn(
            "long_short(ret_col=...) is deprecated; use weighting= "
            '("EW" or "VW") instead.',
            DeprecationWarning,
            stacklevel=2,
        )
        actual_ret_col = ret_col
    else:
        if weighting not in ("EW", "VW"):
            raise PortfolioError(
                f"long_short: weighting must be 'EW' or 'VW', got {weighting!r}"
            )
        actual_ret_col = weighting

    required = [date_col, bin_col, actual_ret_col]
    missing = [c for c in required if c not in bins_df.columns]
    if missing:
        raise PortfolioError(f"long_short: missing columns {missing}")

    # Default to extreme bins
    if long_bin is None:
        long_bin = int(bins_df[bin_col].max())
    if short_bin is None:
        short_bin = int(bins_df[bin_col].min())

    if long_bin == short_bin:
        raise PortfolioError(
            f"long_short: long_bin ({long_bin}) and short_bin "
            f"({short_bin}) must differ"
        )

    long_data = bins_df.loc[bins_df[bin_col] == long_bin, [date_col, actual_ret_col]].rename(
        columns={actual_ret_col: f"{actual_ret_col}_long"}
    )
    short_data = bins_df.loc[bins_df[bin_col] == short_bin, [date_col, actual_ret_col]].rename(
        columns={actual_ret_col: f"{actual_ret_col}_short"}
    )

    if long_data.empty:
        raise PortfolioError(f"long_short: no data for long_bin={long_bin}")
    if short_data.empty:
        raise PortfolioError(f"long_short: no data for short_bin={short_bin}")

    merged = pd.merge(long_data, short_data, on=date_col, how="inner")
    merged["ret"] = merged[f"{actual_ret_col}_long"] - merged[f"{actual_ret_col}_short"]
    return merged[[date_col, "ret"]].reset_index(drop=True)


def forward_returns(
    panel: pd.DataFrame,
    signal_col: str,
    date_col: str,
    ret_col: str = "ret",
    n_lags: int = 1,
) -> pd.DataFrame:
    """Shift the return column forward by `n_lags` periods per stock.

    **Use this to avoid look-ahead bias in cross-sectional strategies.**

    The convention for monthly-rebalanced long-short strategies:
      - Signal is computed at the *end* of month t (e.g. MAX of daily
        returns in month t).
      - Portfolio is *formed* at end of month t.
      - Portfolio is *held* during month t+1.
      - Return we measure is therefore month t+1's return, not t's.

    If you bin stocks at end of month t and then group by (month, bin)
    using month t's return, you're implicitly assuming the signal can
    be observed before the month's close — look-ahead bias. The fix is
    to shift the return forward by one period within each stock's
    history before binning.

    Example::

        # WRONG — bins at end of month t, return is also month t (look-ahead):
        df["bin"] = assign_quantiles(df, "month", "max_signal", n_bins=10)
        # ... uses month t's return to evaluate month t's bin

        # RIGHT — shift the return forward first:
        df = forward_returns(df, signal_col="max_signal", date_col="month", n_lags=1)
        # Now df["ret"] is month t+1's return, paired with month t's bin
        df["bin"] = assign_quantiles(df, "month", "max_signal", n_bins=10)
        # ... bin formed at month t, return is month t+1

    Args:
        panel: per-(stock, date) DataFrame. Must contain ``signal_col``
            (the column whose values are observed at the END of ``date_col``)
            and ``ret_col`` (the column whose values accrue DURING
            ``date_col``).
        signal_col: name of the signal column (e.g. ``"max_signal"``).
            Used only as a sanity check — its values are not shifted.
        date_col: name of the date column.
        ret_col: name of the return column to shift forward. Default ``"ret"``.
        n_lags: how many periods to shift. Default 1 (matches the
            end-of-month formation → next-month holding convention).

    Returns:
        A new DataFrame with ``ret_col`` shifted forward by ``n_lags``
        periods per stock. Rows where the shift produces NaN (i.e. the
        last ``n_lags`` periods of each stock's history) are dropped.

    Raises:
        PortfolioError: if ``date_col``, ``signal_col``, or ``ret_col``
            are missing, or if a stock-id column is missing (needed to
            group the shift per-stock).
    """
    required = [date_col, signal_col, ret_col]
    missing = [c for c in required if c not in panel.columns]
    if missing:
        raise PortfolioError(f"forward_returns: missing columns {missing}")
    if n_lags < 1:
        raise PortfolioError(f"forward_returns: n_lags must be >= 1, got {n_lags}")

    # We need a per-stock grouping key. Convention: prefer `permno`, fall back
    # to `ticker`, otherwise ask the caller to specify. Most CRSP-based
    # strategies will have `permno`.
    stock_col = None
    for candidate in ("permno", "ticker", "stock_id", "id"):
        if candidate in panel.columns:
            stock_col = candidate
            break
    if stock_col is None:
        raise PortfolioError(
            "forward_returns: no per-stock grouping column found. "
            "Need one of: permno, ticker, stock_id, id. "
            "Or pre-group via groupby + transform."
        )

    if n_lags < 1:
        raise PortfolioError(f"forward_returns: n_lags must be >= 1, got {n_lags}")

    df = panel.sort_values([stock_col, date_col]).copy()
    df[ret_col] = df.groupby(stock_col)[ret_col].shift(-n_lags)
    before = len(df)
    df = df.dropna(subset=[ret_col])
    after = len(df)
    if before != after:
        # Last `n_lags` periods per stock drop out. Expected.
        pass
    return df.reset_index(drop=True)


__all__ = ["bin_returns", "long_short", "forward_returns", "PortfolioError"]