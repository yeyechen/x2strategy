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

import numpy as np
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
    flip_sign: bool = False,
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
        flip_sign: If True, multiply the return by -1. Use this when
            the paper reports the spread as "high minus low" (e.g.,
            D10-D1) but you are long the low bin (long_bin=1,
            short_bin=10). Default False (ret = long - short).

    Returns:
        DataFrame with one row per date, columns ``date_col`` and ``"ret"``
        where ``ret`` is ``long_minus_short`` of the chosen return column
        (or the negation if ``flip_sign=True``).

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
    if flip_sign:
        merged["ret"] = -merged["ret"]
    return merged[[date_col, "ret"]].reset_index(drop=True)


def forward_returns(
    panel: pd.DataFrame,
    signal_col: str,
    date_col: str,
    ret_col: str = "ret",
    n_lags: int = 1,
    *,
    aggregate: str = "raw",
    out_col: Optional[str] = None,
) -> pd.DataFrame:
    """Shift the return window forward by ``n_lags`` periods, with optional aggregation.

    **Unified function for all forward-return patterns.** Replaces the
    older ``forward_returns`` (raw shift) and ``forward_returns_h``
    (H-period aggregation) — they were two functions doing the same
    thing, with the only real difference being whether to aggregate
    across periods.

    **Use this to avoid look-ahead bias in cross-sectional strategies.**
    The signal at time ``t`` is paired with the return realized over
    months ``t+1 ... t+n_lags``. The signal is observed at end of ``t``;
    the paired return is realized strictly after. There is no
    look-ahead — the signal could not have used the future return
    because the return has not happened yet at the time the signal
    is observed.

    Three ``aggregate`` modes cover the cross-sectional literature:

    - ``"raw"`` — no aggregation, just shift by ``n_lags`` periods.
      The output is the per-period return at month ``t+n_lags``.
      Best for 1-month holding (MAX, value, B/M): ``ret[t+1]`` is
      exactly the next-month return. Replaces ``ret_col`` in place.

    - ``"per_month"`` (default) — per-month geometric mean of the
      H-month compounded return: ``exp(mean(log(1+ret))) - 1``. This
      is the per-month equivalent used in academic momentum papers
      (Jegadeesh-Titman 1993): 6-month return ÷ 6, in log space.
      Adds a new column (default ``f"{ret_col}_fwd{n_lags}"``);
      ``ret_col`` is preserved for cohort computation.

    - ``"cumulative"`` — H-month cumulative return: ``prod(1+ret) - 1``.
      Use when the paper reports H-month holding-period returns
      directly (e.g. FIP Table 2 "6-month return"). Same column
      handling as ``"per_month"``.

    Args:
        panel: per-(stock, date) DataFrame. Must contain
            ``signal_col``, ``date_col``, ``ret_col``, and a per-stock
            grouping column (``permno`` / ``ticker`` / ``stock_id`` / ``id``).
        signal_col: name of the signal column. Sanity check only —
            its values are not shifted.
        date_col: name of the date column.
        ret_col: name of the per-period return column. Default ``"ret"``.
        n_lags: how many periods to forward-shift (default 1).
            1 for bin-and-evaluate (MAX / value / B/M); 6 for momentum.
        aggregate: one of ``"raw"``, ``"per_month"``, ``"cumulative"``.
            See the docstring above for the per-mode behavior.
        out_col: name of the output column. If ``None`` (default):
            for ``aggregate="raw"`` the output is written back into
            ``ret_col`` (replaces in place); for ``"per_month"`` or
            ``"cumulative"`` the output is added as
            ``f"{ret_col}_fwd{n_lags}"`` and ``ret_col`` is preserved.

    Returns:
        A new DataFrame with the output column written. The last
        ``n_lags`` periods per stock are dropped (their forward
        window is incomplete).

    Raises:
        PortfolioError: if required columns are missing, ``n_lags < 1``,
            ``aggregate`` is not one of the three allowed values, or no
            per-stock grouping column is found.

    Examples::

        # MAX / value / B/M: 1-month holding, raw shift, replace ret
        df = forward_returns(df, signal_col="max_signal", date_col="month")
        # df["ret"] is now ret[t+1] — next-month return

        # FIP / momentum: 6-month cumulative, add new column
        df = forward_returns(
            df, signal_col="pret", date_col="month",
            n_lags=6, aggregate="cumulative",
        )
        # df["ret_fwd6"] = prod(1+ret[t+1..t+6]) - 1
        # df["ret"] is preserved for cohort computation

        # 6-month per-month equivalent (also Jegadeesh-Titman style)
        df = forward_returns(
            df, signal_col="pret", date_col="month",
            n_lags=6, aggregate="per_month",
        )
        # df["ret_fwd6"] = exp(mean(log(1+ret[t+1..t+6]))) - 1
    """
    required = [date_col, signal_col, ret_col]
    missing = [c for c in required if c not in panel.columns]
    if missing:
        raise PortfolioError(f"forward_returns: missing columns {missing}")
    if n_lags < 1:
        raise PortfolioError(
            f"forward_returns: n_lags must be >= 1, got {n_lags}"
        )
    valid_aggregates = ("raw", "per_month", "cumulative")
    if aggregate not in valid_aggregates:
        raise PortfolioError(
            f"forward_returns: aggregate must be one of {valid_aggregates}, "
            f"got {aggregate!r}"
        )

    # Per-stock grouping key — prefer permno, fall back to other names.
    stock_col = None
    for candidate in ("permno", "ticker", "stock_id", "id"):
        if candidate in panel.columns:
            stock_col = candidate
            break
    if stock_col is None:
        raise PortfolioError(
            "forward_returns: no per-stock grouping column found. "
            "Need one of: permno, ticker, stock_id, id."
        )

    df = panel.sort_values([stock_col, date_col]).copy()

    if aggregate == "raw":
        # Pure shift: ret[t] becomes ret[t+n_lags]. Replace in place.
        df[ret_col] = df.groupby(stock_col)[ret_col].shift(-n_lags)
        df = df.dropna(subset=[ret_col])
        return df.reset_index(drop=True)

    # aggregate == "per_month" or "cumulative": aggregate H periods,
    # then exp() back to return space. ADDS a new column; ret_col preserved.
    if out_col is None:
        out_col = f"{ret_col}_fwd{n_lags}"

    # Vectorized rolling-sum per stock via NumPy strided views:
    #   1. log_ret = log1p(ret) (per row)
    #   2. reset cumulative sum at each group boundary
    #   3. rolling-H sum at position i = cumsum[i] - cumsum[i-H]
    #      (sum over [i-H+1, i] within the stock)
    #   4. shift by -H to get sum over [i+1, i+H] (the forward window)
    #   5. exp(sum/H) - 1  (per-month equivalent)
    #   OR exp(sum) - 1    (H-month cumulative)
    log_ret = np.log1p(df[ret_col].to_numpy())
    n = len(df)
    stock_vals = df[stock_col].to_numpy()
    is_group_start = np.empty(n, dtype=bool)
    is_group_start[0] = True
    is_group_start[1:] = stock_vals[1:] != stock_vals[:-1]
    group_ids = np.cumsum(is_group_start)
    n_groups = int(group_ids[-1])

    raw_cumsum = np.cumsum(log_ret)
    group_start_indices = np.where(is_group_start)[0]
    offsets = np.empty(n_groups)
    offsets[0] = 0.0
    offsets[1:] = raw_cumsum[group_start_indices[1:] - 1]
    local_cumsum = raw_cumsum - offsets[group_ids - 1]

    rolling_log = np.full(n, np.nan)
    if n >= n_lags:
        rolling_log[n_lags:] = local_cumsum[n_lags:] - local_cumsum[:-n_lags]
        same_group = group_ids[n_lags:] == group_ids[:-n_lags]
        rolling_log[n_lags:] = np.where(same_group, rolling_log[n_lags:], np.nan)

    fwd_log_sum = np.full(n, np.nan)
    if n > n_lags:
        same_group = group_ids[: n - n_lags] == group_ids[n_lags:]
        fwd_log_sum[: n - n_lags] = np.where(same_group, rolling_log[n_lags:], np.nan)

    if aggregate == "cumulative":
        # H-month cumulative: prod(1+ret) - 1 = exp(sum) - 1
        df[out_col] = np.expm1(fwd_log_sum)
    else:
        # Per-month equivalent: exp(mean(log(1+ret))) - 1
        df[out_col] = np.expm1(fwd_log_sum / n_lags)
    df = df.dropna(subset=[out_col])
    df = df[np.isfinite(df[out_col])]
    return df.reset_index(drop=True)



def rolling_cumret(
    panel: pd.DataFrame,
    date_col: str,
    ret_col: str,
    window: int,
    skip: int = 1,
    min_periods: int = None,
) -> pd.Series:
    """Rolling cumulative return: prod(1+ret) over the past window
    months, skipping the most recent skip months. See the canonical
    JT 12-2 momentum signal-formation pattern."""
    required = [date_col, ret_col]
    missing = [c for c in required if c not in panel.columns]
    if missing:
        raise PortfolioError(f"rolling_cumret: missing columns {missing}")
    if window < 1:
        raise PortfolioError(f"rolling_cumret: window must be >= 1, got {window}")
    if skip < 0:
        raise PortfolioError(f"rolling_cumret: skip must be >= 0, got {skip}")
    if min_periods is None:
        min_periods = window

    stock_col = None
    for candidate in ("permno", "ticker", "stock_id", "id"):
        if candidate in panel.columns:
            stock_col = candidate
            break
    if stock_col is None:
        raise PortfolioError(
            "rolling_cumret: no per-stock grouping column found. "
            "Need one of: permno, ticker, stock_id, id."
        )

    shift_amt = skip + 1
    df = panel.sort_values([stock_col, date_col]).copy()
    df["_logret"] = np.log1p(df[ret_col])
    df["_logret_shifted"] = df.groupby(stock_col)["_logret"].shift(shift_amt)
    df["_logcum"] = (
        df.groupby(stock_col)["_logret_shifted"]
        .rolling(window, min_periods=min_periods)
        .sum()
        .reset_index(level=0, drop=True)
    )
    return np.expm1(df["_logcum"])



__all__ = [
    "bin_returns",
    "long_short",
    "forward_returns",

    "rolling_cumret",
    "PortfolioError",
]
