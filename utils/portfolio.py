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
        A new DataFrame with ``ret_col`` replaced by the forward-shifted
        values per stock. Rows where the shift produces NaN (i.e. the
        last ``n_lags`` periods of each stock's history) are dropped.

        **The shifted return is written back into the SAME column
        (``ret_col``) — NOT into a new column named e.g.
        ``ret_fwd1``.** After calling this, ``df["ret"]`` is the
        next-period return paired with the current-period signal.

        The per-stock grouping key is auto-detected in this priority
        order: ``permno``, ``ticker``, ``stock_id``, ``id``. If none of
        those columns exist, raises :class:`PortfolioError`.

    Raises:
        PortfolioError: if ``date_col``, ``signal_col``, or ``ret_col``
            are missing, or if no recognized stock-id column is found.
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


def forward_returns_h(
    panel: pd.DataFrame,
    signal_col: str,
    date_col: str,
    ret_col: str = "ret",
    n_lags: int = 6,
    out_col=None,
    cumulative: bool = False,
) -> pd.DataFrame:
    """Add a forward H-month return column.

    Overlapping-cohort (Jegadeesh-Titman) convention: for each (stock, t),
    the output column is the forward return realized over months t+1 ... t+H.

    For H=1, equivalent to forward_returns (single-period shift). For H>1,
    standard momentum-overlapping-cohort return.

    The output column is ADDED (ret_col is preserved). Different from
    forward_returns which REPLACES the column.

    Per-stock grouping auto-detected from {permno, ticker, stock_id, id}.

    Args:
        panel: per-(stock, date) DataFrame.
        signal_col: signal column (sanity check only).
        date_col: date column.
        ret_col: per-period return column. Default "ret".
        n_lags: how many periods to forward-aggregate. Default 6.
        out_col: output column name. Default f"{ret_col}_fwd{n_lags}".
        cumulative: if False (default), output the per-month geometric
            mean: ``exp(mean(log(1+ret))) - 1``. If True, output the
            H-month cumulative return: ``prod(1+ret) - 1``. Use
            ``cumulative=True`` when the paper reports cumulative
            holding-period returns (e.g. FIP Table 2: "6-month return").

    Returns:
        New DataFrame with out_col added. Last n_lags periods per stock
        dropped.

    Example::

        # FIP: 6-month cumulative forward return
        monthly = forward_returns_h(
            monthly, signal_col="pret", date_col="month",
            ret_col="ret", n_lags=6, cumulative=True,
        )
    """
    required = [date_col, signal_col, ret_col]
    missing = [c for c in required if c not in panel.columns]
    if missing:
        raise PortfolioError(f"forward_returns_h: missing columns {missing}")
    if n_lags < 1:
        raise PortfolioError(f"forward_returns_h: n_lags must be >= 1, got {n_lags}")

    stock_col = None
    for candidate in ("permno", "ticker", "stock_id", "id"):
        if candidate in panel.columns:
            stock_col = candidate
            break
    if stock_col is None:
        raise PortfolioError(
            "forward_returns_h: no per-stock grouping column found. "
            "Need one of: permno, ticker, stock_id, id."
        )

    if out_col is None:
        out_col = f"{ret_col}_fwd{n_lags}"

    df = panel.sort_values([stock_col, date_col]).copy()
    # Vectorized rolling-sum per stock via NumPy strided views.
    # The previous implementation used groupby().transform(lambda s: s.rolling(...))
    # which is O(n_stocks) Python-level apply calls — the bottleneck on
    # large panels (30M+ rows). This version does the same math with
    # one cumulative-sum pass and one strided window view, fully in C.
    #
    # Algorithm:
    #   1. log_ret = log1p(ret) (per row)
    #   2. group-starts: find index where each stock begins (after sort).
    #   3. cumsum of log_ret, but reset to 0 at each group boundary so
    #      cumsum within a group is independent.
    #   4. rolling-H sum at position i = cumsum[i] - cumsum[i-H] (if i>=H else NaN)
    #      -- this gives sum over [i-H+1, i].
    #   5. shift the result by -H within each group to get sum over [i+1, i+H]
    #      (the forward window the caller wants).
    #   6. exp(sum/H) - 1 = per-month equivalent.
    log_ret = np.log1p(df[ret_col].to_numpy())
    n = len(df)
    # Group boundaries: positions where stock_col changes.
    stock_vals = df[stock_col].to_numpy()
    is_group_start = np.empty(n, dtype=bool)
    is_group_start[0] = True
    is_group_start[1:] = stock_vals[1:] != stock_vals[:-1]
    group_ids = np.cumsum(is_group_start)  # 1..n_groups
    n_groups = int(group_ids[-1])

    # Reset cumulative sum at each group boundary.
    raw_cumsum = np.cumsum(log_ret)
    group_start_cumsum = np.zeros(n_groups + 1)
    # At each group's first index, subtract the running cumsum so the
    # group-local cumsum starts at 0.
    group_start_indices = np.where(is_group_start)[0]
    # The "offset" at group g is raw_cumsum at the LAST index before the
    # group's first row (i.e. raw_cumsum[group_start_indices[g] - 1] or 0).
    offsets = np.empty(n_groups)
    offsets[0] = 0.0
    offsets[1:] = raw_cumsum[group_start_indices[1:] - 1]
    # Local cumsum = raw_cumsum - offsets[group_id - 1]
    local_cumsum = raw_cumsum - offsets[group_ids - 1]

    # Rolling H sum at position i: sum over [i-H+1, i] within the group.
    # local_cumsum[i] - local_cumsum[i-H] (for i >= H AND group_ids[i] == group_ids[i-H]).
    # NaN where i < H or the group boundary falls within the window.
    rolling_log = np.full(n, np.nan)
    if n >= n_lags:
        rolling_log[n_lags:] = local_cumsum[n_lags:] - local_cumsum[:-n_lags]
        # Mask windows that cross a group boundary.
        same_group = group_ids[n_lags:] == group_ids[:-n_lags]
        # (Within a group, positions [i-H+1, i] are guaranteed contiguous
        # because the data was sorted by (stock_col, date_col). So this
        # check is sufficient.)
        rolling_log[n_lags:] = np.where(same_group, rolling_log[n_lags:], np.nan)

    # Forward-shift by H within each group: rolling_log[i] becomes the
    # sum over [i+1, i+H]. Build a per-group offset array.
    fwd_log_sum = np.full(n, np.nan)
    if n > n_lags:
        # For each i, fwd_log_sum[i] = rolling_log[i+n_lags] IF they're in
        # the same group; NaN otherwise (or if i+n_lags >= n).
        same_group = group_ids[: n - n_lags] == group_ids[n_lags:]
        fwd_log_sum[: n - n_lags] = np.where(same_group, rolling_log[n_lags:], np.nan)

    if cumulative:
        # H-month cumulative return: prod(1+ret) - 1 = exp(sum(log(1+ret))) - 1
        df[out_col] = np.expm1(fwd_log_sum)
    else:
        # Per-month geometric mean: exp(mean(log(1+ret))) - 1
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
    """Rolling cumulative return: ``prod(1+ret)`` over the past ``window``
    months, skipping the most recent ``skip`` months.

    **Use this for momentum signal formation** — it encodes the
    Jegadeesh-Titman skip convention correctly so the agent doesn't
    have to reason about ``shift(skip+1)`` manually.

    For JT 12-2 momentum: ``window=11, skip=1`` → formation period is
    months t-12 to t-2 (11 months, skipping the most recent month t-1).

    The current month t is always excluded (it hasn't ended yet).
    ``skip`` controls how many *additional* months to exclude:

    ====== ========== =========================
    skip   shift      formation window
    ====== ========== =========================
    0      1          t-window to t-1
    1      2          t-(window+1) to t-2  (JT 12-2)
    2      3          t-(window+2) to t-3
    ====== ========== =========================

    Args:
        panel: per-(stock, date) DataFrame. Must contain ``date_col``,
            ``ret_col``, and a per-stock grouping column.
        date_col: name of the date column.
        ret_col: name of the return column (e.g. ``"ret"``).
        window: number of months in the formation period.
        skip: months to skip between the current month and the most
            recent formation month. Default 1 (JT 12-2 convention).
        min_periods: minimum non-NaN months required. Default
            ``window`` (require full window).

    Returns:
        pandas Series aligned to ``panel`` — the rolling cumulative
        return ``prod(1+ret) - 1``. NaN where insufficient data.

    Raises:
        PortfolioError: if columns are missing or no stock-id column
            is found.

    Example::

        # JT 12-2 momentum: 11-month formation, skip 1
        monthly["pret"] = rolling_cumret(
            monthly, date_col="month", ret_col="ret",
            window=11, skip=1,
        )
        # At month t: prod(1+ret[t-12..t-2]) - 1
    """
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
    # Compute prod(1+r) - 1 = exp(sum(log(1+r))) - 1 in two stages:
    #   1. log1p + shift within each stock
    #   2. rolling SUM (built-in, respects min_periods) within each stock
    #   3. expm1 of the rolling sum
    # Note: ``rolling.apply(raw=True)`` ignores min_periods in pandas, so we
    # cannot use it here. Built-in ``.sum()`` is required for min_periods.
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
    "forward_returns_h",
    "rolling_cumret",
    "PortfolioError",
]
