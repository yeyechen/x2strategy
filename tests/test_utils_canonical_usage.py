"""Canonical-usage smoke test for x2strategy.utils.

Purpose
-------
This test is the agent's "is my code calling utils right?" check.
It exercises every public function in :mod:`utils` end-to-end on a
tiny 2-stock × 3-date fixture, asserting no exception and that the
return value has the expected shape. Runs in under 5 seconds.

**Three roles this file plays:**

1. **Documentation** — the test bodies are the canonical usage
   examples. When an LLM is generating ``strategy.py``, the test
   bodies here are the patterns to copy. Mirror what's in
   ``utils/INDEX.md``.

2. **Smoke test for the agent** — between edits to ``strategy.py``,
   the agent can run::

       uv run pytest tests/test_utils_canonical_usage.py -x

   and get a clear failure in 2 seconds if it called a utils
   function wrong. No 5-minute backtest required.

3. **Regression suite** — if a future commit breaks the canonical
   signature, this test fails immediately.

Fixture
-------
``tiny_panel`` is a 2-stock × 3-month DataFrame with the columns
that the canonical cross-sectional pipeline needs:

    permno   date         ret      signal    mcap_lag1
    1        2020-01-31   +0.01    +0.5      1000.0
    2        2020-01-31   -0.02    -0.3      2000.0
    1        2020-02-29   +0.03    +0.7      1100.0
    2        2020-02-29   -0.01    -0.4      2100.0
    1        2020-03-31   +0.02    +0.6      1050.0
    2        2020-03-31   +0.04    -0.2      2050.0
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # headless — match SKILL.md requirement

import numpy as np
import pandas as pd
import pytest

# IMPORTANT: import via the package path ('from utils import X'), NOT
# the module path ('from utils.module import X'). This mirrors how
# agents write 'from utils import forward_returns_h' in strategy.py
# and catches re-export drift in utils/__init__.py — iter 9 added 3
# primitives to their modules but missed __init__.py, crashing the
# FIP refactor at 'from utils import double_sort'.
from utils import (
    assign_quantiles,
    assign_ranks,
    double_sort,
    bin_returns,
    long_short,
    forward_returns,
    forward_returns_h,
    performance_metrics,
    format_metrics,
    tstat_newey_west,
    plot_cumulative_returns,
    plot_drawdown,
    plot_decile_spread,
    run_ols,
    fama_macbeth,
    summarize_fama_macbeth,
)


# ── Fixture ──────────────────────────────────────────────────


@pytest.fixture
def tiny_panel() -> pd.DataFrame:
    """2 stocks × 3 months. Same shape as a real cross-sectional panel."""
    return pd.DataFrame(
        {
            "permno": [1, 2] * 3,
            "date": pd.to_datetime(
                ["2020-01-31", "2020-01-31",
                 "2020-02-29", "2020-02-29",
                 "2020-03-31", "2020-03-31"]
            ),
            "ret": [0.01, -0.02, 0.03, -0.01, 0.02, 0.04],
            "signal": [0.5, -0.3, 0.7, -0.4, 0.6, -0.2],
            "mcap_lag1": [1000.0, 2000.0, 1100.0, 2100.0, 1050.0, 2050.0],
        }
    )


# ── assign_quantiles ─────────────────────────────────────────


def test_canonical_assign_quantiles(tiny_panel: pd.DataFrame) -> None:
    """Canonical: assign 2 bins within each date group."""
    bins = assign_quantiles(tiny_panel, date_col="date",
                            signal_col="signal", n_bins=2)
    # Returns a Series; agent assigns back as a column:
    tiny_panel = tiny_panel.copy()
    tiny_panel["bin"] = bins
    # Each date has exactly 2 bins, one per stock
    assert set(tiny_panel["bin"].unique()) == {1, 2}


def test_canonical_assign_ranks(tiny_panel: pd.DataFrame) -> None:
    """Canonical: rank within each date (1=highest signal by default)."""
    ranks = assign_ranks(tiny_panel, date_col="date", signal_col="signal")
    assert set(ranks.unique()) == {1, 2}


# ── bin_returns + long_short ────────────────────────────────


def test_canonical_bin_returns(tiny_panel: pd.DataFrame) -> None:
    """Canonical: per-bin EW + VW returns. Output columns LITERALLY
    named "EW" and "VW" — see utils/portfolio.py docstring.
    """
    tiny_panel = tiny_panel.copy()
    tiny_panel["bin"] = assign_quantiles(
        tiny_panel, date_col="date", signal_col="signal", n_bins=2
    )
    bin_rets = bin_returns(
        tiny_panel,
        date_col="date",
        bin_col="bin",
        ret_col="ret",
        mcap_col="mcap_lag1",
    )
    assert set(bin_rets.columns) >= {"date", "bin", "EW", "VW"}
    # 3 dates × 2 bins = 6 rows
    assert len(bin_rets) == 6


def test_canonical_long_short_new_signature(tiny_panel: pd.DataFrame) -> None:
    """Canonical NEW signature: long_short(..., weighting='VW').

    The agent should NOT pass ret_col='VW' anymore — that's the
    pre-iteration-7 style that the max_v4 agent debug-looped on.
    """
    tiny_panel = tiny_panel.copy()
    tiny_panel["bin"] = assign_quantiles(
        tiny_panel, date_col="date", signal_col="signal", n_bins=2
    )
    bin_rets = bin_returns(
        tiny_panel, date_col="date", bin_col="bin",
        ret_col="ret", mcap_col="mcap_lag1",
    )
    ls = long_short(
        bin_rets,
        date_col="date",
        weighting="VW",       # canonical NEW style
        long_bin=2,
        short_bin=1,
    )
    assert set(ls.columns) == {"date", "ret"}
    assert len(ls) == 3


def test_canonical_long_short_legacy_emits_warning(tiny_panel: pd.DataFrame) -> None:
    """Legacy signature (positional) maps cleanly to weighting=. The
    ret_col= kwarg path emits a DeprecationWarning when used.
    """
    import warnings
    tiny_panel = tiny_panel.copy()
    tiny_panel["bin"] = assign_quantiles(
        tiny_panel, date_col="date", signal_col="signal", n_bins=2
    )
    bin_rets = bin_returns(
        tiny_panel, date_col="date", bin_col="bin",
        ret_col="ret", mcap_col="mcap_lag1",
    )
    # Positional call (the historical signature): no warning, maps to
    # weighting= under the hood.
    ls = long_short(bin_rets, "date", "VW", long_bin=2, short_bin=1)
    assert len(ls) == 3

    # Explicit ret_col= kwarg path: SHOULD warn (deprecated).
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        ls2 = long_short(
            bin_rets, date_col="date", ret_col="VW",
            long_bin=2, short_bin=1,
        )
        assert any(issubclass(x.category, DeprecationWarning) for x in w)


def test_canonical_long_short_custom_bin_col(tiny_panel: pd.DataFrame) -> None:
    """Pass bin_col='decile' when assign_quantiles chose that name."""
    tiny_panel = tiny_panel.copy()
    tiny_panel["decile"] = assign_quantiles(
        tiny_panel, date_col="date", signal_col="signal", n_bins=2
    )
    bin_rets = bin_returns(
        tiny_panel, date_col="date", bin_col="decile",
        ret_col="ret", mcap_col="mcap_lag1",
    )
    ls = long_short(
        bin_rets, date_col="date", weighting="VW",
        bin_col="decile",      # pick up the right column
        long_bin=2, short_bin=1,
    )
    assert len(ls) == 3


# ── forward_returns ──────────────────────────────────────────


def test_canonical_forward_returns(tiny_panel: pd.DataFrame) -> None:
    """Canonical: shift the return forward by 1 period per stock.

    Note: forward_returns REPLACES the ret column (does NOT create a
    new column) and auto-detects the stock-id from {permno, ticker,
    stock_id, id}.
    """
    out = forward_returns(
        tiny_panel, signal_col="signal", date_col="date",
        ret_col="ret", n_lags=1,
    )
    # The shifted return replaces the original "ret" column. The
    # 2 last rows (one per stock) are dropped because there's no
    # "next month" yet for the shift.
    assert len(out) == 4
    # Sanity: stock 1's "ret" at 2020-01-31 should now be stock 1's
    # original ret at 2020-02-29 (i.e. 0.03).
    stock1_jan = out[(out["permno"] == 1) & (out["date"] == pd.Timestamp("2020-01-31"))]
    assert len(stock1_jan) == 1
    assert np.isclose(stock1_jan["ret"].iloc[0], 0.03)


# ── performance_metrics ─────────────────────────────────────


def test_canonical_performance_metrics(tiny_panel: pd.DataFrame) -> None:
    """Canonical: Sharpe / CAGR / max DD / vol on a return series."""
    ls_ret = tiny_panel.groupby("date")["ret"].mean()  # fake LS returns
    metrics = performance_metrics(ls_ret, freq="M")
    for k in ("sharpe_ratio", "max_drawdown", "cagr"):
        assert k in metrics


# ── plot_* ───────────────────────────────────────────────────


def test_canonical_plot_cumulative_returns(tiny_panel: pd.DataFrame, tmp_path) -> None:
    """Canonical: plot a return series to a PNG.

    Note: plot_cumulative_returns uses different kwarg names than the
    other plot_* functions — ``index_col_name`` and ``ret_col_lst``
    (a LIST of column names, not a single column).
    """
    out_path = tmp_path / "pnl.png"
    ls_ret = tiny_panel.groupby("date")["ret"].mean().reset_index()
    plot_cumulative_returns(
        ls_ret, index_col_name="date", ret_col_lst=["ret"], save_to=out_path,
    )
    assert out_path.is_file()


def test_canonical_plot_drawdown(tiny_panel: pd.DataFrame, tmp_path) -> None:
    """Canonical: plot drawdown to a PNG. Uses date_col + ret_col (single)."""
    out_path = tmp_path / "dd.png"
    ls_ret = tiny_panel.groupby("date")["ret"].mean().reset_index()
    plot_drawdown(
        ls_ret, date_col="date", ret_col="ret", save_to=out_path,
    )
    assert out_path.is_file()


def test_canonical_plot_decile_spread(tiny_panel: pd.DataFrame, tmp_path) -> None:
    """Canonical: per-bin EW + VW bar chart. Auto-derives from bins_df."""
    out_path = tmp_path / "dec.png"
    tiny_panel = tiny_panel.copy()
    tiny_panel["bin"] = assign_quantiles(
        tiny_panel, date_col="date", signal_col="signal", n_bins=2
    )
    bin_rets = bin_returns(
        tiny_panel, date_col="date", bin_col="bin",
        ret_col="ret", mcap_col="mcap_lag1",
    )
    plot_decile_spread(bin_rets, save_to=out_path)
    assert out_path.is_file()


# ── regressions ─────────────────────────────────────────────


def test_canonical_run_ols(tiny_panel: pd.DataFrame) -> None:
    """Canonical: single OLS. Result dict keys: params, rsquared, nobs
    — see utils/regressions.py run_ols docstring.
    """
    res = run_ols(
        tiny_panel, dependent_var="ret",
        independent_vars=["signal", "mcap_lag1"],
        min_obs=3,
    )
    assert "params" in res
    assert "rsquared" in res
    assert "nobs" in res
    # Coefficient access (NOT result["coef"]):
    const = res["params"]["const"]
    assert np.isfinite(const)


def test_canonical_fama_macbeth(tiny_panel: pd.DataFrame) -> None:
    """Canonical: Fama-MacBeth cross-section. Use dependent_var=
    (NOT y_col= — y_col is a deprecated alias).
    """
    # Need more obs per period for the default min_obs=5 + 2 indep = 7
    # Replicate the fixture to get more rows:
    big = pd.concat([tiny_panel] * 5, ignore_index=True)
    fm = fama_macbeth(
        big, dependent_var="ret",
        independent_vars=["signal", "mcap_lag1"],
        time_col="date",
    )
    summary = summarize_fama_macbeth(fm)
    assert "Variable" in summary  # formatted table has a header


def test_canonical_fama_macbeth_y_col_alias(tiny_panel: pd.DataFrame) -> None:
    """The y_col / x_cols deprecated aliases still work (with warning)."""
    import warnings
    big = pd.concat([tiny_panel] * 5, ignore_index=True)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        fm = fama_macbeth(
            big, y_col="ret", x_cols=["signal", "mcap_lag1"],
            time_col="date",
        )
        assert any(issubclass(x.category, DeprecationWarning) for x in w)
    assert fm.summary["n_periods"] >= 1


# ── End-to-end smoke test ───────────────────────────────────


def test_canonical_pipeline_end_to_end(tiny_panel: pd.DataFrame, tmp_path) -> None:
    """The full canonical cross-sectional pipeline runs without errors.

    This is the test the agent should run after writing strategy.py
    if it wants a 2-second answer to "did I wire utils up right?".
    Steps mirror the canonical pipeline documented in utils/INDEX.md.

    Replicates the fixture 5x so we have enough obs per date group
    for the default Fama-MacBeth min_obs=5 + 1 indep = 6.
    """
    panel = pd.concat([tiny_panel] * 5, ignore_index=True)
    panel["permno"] = panel["permno"] + panel.index // 6 * 2  # unique permnos

    # 1. Forward-shift the return to avoid look-ahead bias.
    panel = forward_returns(
        panel, signal_col="signal", date_col="date",
        ret_col="ret", n_lags=1,
    )

    # 2. Cross-sectional binning (on the un-shifted signal; the signal
    # IS observed at end of month t, no shift needed).
    panel["bin"] = assign_quantiles(
        panel, date_col="date", signal_col="signal", n_bins=2,
    )

    # 3. Per-bin returns (EW + VW). Note: ret_col is just "ret" because
    # forward_returns REPLACES the ret column with the shifted values.
    bin_rets = bin_returns(
        panel, date_col="date", bin_col="bin",
        ret_col="ret", mcap_col="mcap_lag1",
    )

    # 4. Long-short portfolio (new canonical signature).
    ls = long_short(
        bin_rets, date_col="date", weighting="VW",
        long_bin=2, short_bin=1,
    )
    assert len(ls) >= 1

    # 5. Performance metrics.
    metrics = performance_metrics(ls["ret"], freq="M")
    assert "sharpe_ratio" in metrics  # may be 0/None for tiny data

    # 6. Plot the P&L (note: index_col_name + ret_col_lst kwargs).
    out_path = tmp_path / "pnl.png"
    plot_cumulative_returns(
        ls, index_col_name="date", ret_col_lst=["ret"], save_to=out_path,
    )
    assert out_path.is_file()

    # 7. Cross-sectional regression.
    fm = fama_macbeth(
        panel, dependent_var="ret",
        independent_vars=["signal"], time_col="date",
    )
    assert fm.summary["n_periods"] >= 1

# ── forward_returns_h (Jegadeesh-Titman overlapping cohorts) ─────────────────


def test_canonical_forward_returns_h(tiny_panel: pd.DataFrame) -> None:
    """Canonical: geometric-mean H-month forward return.

    Different from forward_returns: this ADDS a new column (default
    'ret_fwd{H}'), preserves the original 'ret' column, and computes
    the per-month equivalent of the compounded H-month return.
    """
    # Need enough obs per stock for n_lags=2. tiny_panel has 3 dates
    # per stock — exactly enough (last 2 rows per stock dropped).
    out = forward_returns_h(
        tiny_panel, signal_col="signal", date_col="date",
        ret_col="ret", n_lags=2,
    )
    # Output has both the original 'ret' and the new 'ret_fwd2' column.
    assert "ret" in out.columns
    assert "ret_fwd2" in out.columns
    # Last 2 dates per stock are dropped.
    assert len(out) == 2  # 1 obs per stock (the earliest date).


# ── double_sort (conditional outer x inner sort) ───────────────────────────


def test_canonical_double_sort(tiny_panel: pd.DataFrame) -> None:
    """Canonical: bin by outer signal, then within each outer-bin bin
    by inner signal. Returns frame with outer_q + inner_q columns.
    """
    # tiny_panel has 2 stocks x 3 dates. With n_bins=2, each date has
    # outer_q in {1,2} and within each outer_q, inner_q in {1,2}.
    out = double_sort(
        tiny_panel, date_col="date", outer_col="signal",
        inner_col="ret", n_bins=2,
    )
    assert "signal_q" in out.columns
    assert "ret_q" in out.columns
    assert set(out["signal_q"].unique()) <= {1, 2}


# ── tstat_newey_west (HAC t-stat for autocorrelated returns) ───────────────


def test_canonical_tstat_newey_west() -> None:
    """Canonical: HAC t-stat on a return series. For H-month overlapping
    cohorts, use n_lags = H - 1. For independent monthly returns,
    n_lags=0 (no correction) should match the iid t-stat closely.
    """
    np.random.seed(42)
    # White-noise returns — iid t and NW(0) should agree.
    r = pd.Series(np.random.normal(0.005, 0.04, 60))
    out = tstat_newey_west(r, n_lags=0)
    assert "t_stat" in out
    assert "mean_return" in out
    # For iid returns, NW(0) t-stat should be finite and close to
    # the iid t-stat (mean / (std / sqrt(n))).
    iid_t = r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))
    assert abs(out["t_stat"] - iid_t) < 0.01


# ── Re-export sanity check (TODO #14) ────────────────────────────────────────


def test_utils_package_re_exports_all_primitives() -> None:
    """utils/__init__.py must re-export every public primitive.

    The package-path import at the top of this file already exercises
    this for the primitives we use. This test additionally walks
    utils.__all__ and asserts every name is callable, which catches
    drift in either direction (added a primitive but didn't re-export,
    or renamed a primitive in __all__ but forgot to update the
    module).
    """
    import utils
    for name in utils.__all__:
        assert hasattr(utils, name), f"utils.{name} missing"
        obj = getattr(utils, name)
        # Exceptions and the plot_config singleton are valid __all__
        # entries that aren't callable. Skip the callability check
        # for those.
        if isinstance(obj, type) or name in ("plot_config",):
            continue
        assert callable(obj), f"utils.{name} is not callable"


# ── _resolve_ret_col auto-detect (TODO #16) ─────────────────────────────────


def test_resolve_ret_col_explicit_wins() -> None:
    """When ret_col is in the DataFrame, use it (don't auto-detect)."""
    from utils.metrics import _resolve_ret_col
    df = pd.DataFrame({"month": [1, 2], "fip_spread": [0.01, 0.02], "extra": [0, 0]})
    assert _resolve_ret_col(df, "fip_spread", "month") == "fip_spread"


def test_resolve_ret_col_single_column() -> None:
    """Single-column DataFrame: use that column."""
    from utils.metrics import _resolve_ret_col
    df = pd.DataFrame({"fip_spread": [0.01, 0.02]})
    assert _resolve_ret_col(df, "ret", "month") == "fip_spread"


def test_resolve_ret_col_two_columns_with_date() -> None:
    """Two-column DataFrame: pick the non-date column."""
    from utils.metrics import _resolve_ret_col
    df = pd.DataFrame({"month": [1, 2], "fip_spread": [0.01, 0.02]})
    assert _resolve_ret_col(df, "ret", "month") == "fip_spread"


def test_resolve_ret_col_ambiguous_raises() -> None:
    """Two non-date columns: raise with a helpful message."""
    import pytest as _pytest
    from utils.metrics import _resolve_ret_col, MetricsError
    df = pd.DataFrame({"mom": [0.01], "value": [0.02]})
    with _pytest.raises(MetricsError, match="Could not auto-detect"):
        _resolve_ret_col(df, "ret", "month")


def test_performance_metrics_auto_detect_custom_column() -> None:
    """End-to-end: pass a DataFrame with ret_col='fip_spread' and a
    single-return column; performance_metrics figures it out."""
    np.random.seed(0)
    df = pd.DataFrame({
        "month": pd.date_range("2020-01-31", periods=240, freq="ME"),
        "fip_spread": np.random.normal(0.005, 0.02, 240),
    })
    # No ret_col kwarg — should auto-detect "fip_spread".
    m = performance_metrics(df, freq="M")
    assert "sharpe_ratio" in m
    # 240 months of iid N(0.005, 0.02) gives annual_return ~ 0.06 +/- 0.015.
    assert abs(m["annual_return"] - 0.06) < 0.02


def test_tstat_newey_west_auto_detect_custom_column() -> None:
    """End-to-end: pass a DataFrame with a custom column name."""
    np.random.seed(0)
    df = pd.DataFrame({
        "month": pd.date_range("2020-01-31", periods=60, freq="ME"),
        "fip_spread": np.random.normal(0.005, 0.02, 60),
    })
    out = tstat_newey_west(df, n_lags=0)  # auto-detect "fip_spread"
    assert "t_stat" in out
    assert np.isfinite(out["t_stat"])


# ── forward_returns_h parity + perf (iter 11) ───────────────────────────────


def test_forward_returns_h_matches_naive_implementation() -> None:
    """Parity: vectorized forward_returns_h matches the iter-9
    groupby().transform(rolling) implementation within float tolerance.

    We inline the iter-9 implementation as the reference rather than
    re-deriving it from first principles (the latter is error-prone —
    this test was wrong once already when the hand-rolled "naive"
    reference had an off-by-one in the fwd index range).
    """
    np.random.seed(7)
    n_stocks, n_months = 5, 60
    permno = np.repeat(np.arange(1, n_stocks + 1), n_months)
    month = np.tile(pd.date_range("2018-01-31", periods=n_months, freq="ME"), n_stocks)
    ret = np.random.normal(0.01, 0.04, n_stocks * n_months)
    df = pd.DataFrame({"permno": permno, "month": month, "ret": ret, "signal": ret})

    out = forward_returns_h(df, signal_col="signal", date_col="month",
                            ret_col="ret", n_lags=6)

    # Reference: the iter-9 implementation, inlined here. If this
    # implementation is wrong, both the reference and the vectorized
    # version will agree with each other (and the canonical-usage
    # test + FIP backtest will catch the real bug).
    ref = df.sort_values(["permno", "month"]).copy()
    log_ret = np.log1p(ref["ret"])
    rolling_log = (
        ref.assign(_log=log_ret)
          .groupby("permno")["_log"]
          .transform(lambda s: s.rolling(6, min_periods=6).sum())
    )
    fwd_log_sum = rolling_log.groupby(ref["permno"]).shift(-6)
    ref["ref_ret_fwd6"] = np.expm1(fwd_log_sum / 6.0)
    ref = ref.dropna(subset=["ref_ret_fwd6"])

    # Merge on (permno, month) and compare.
    merged = out.merge(ref, on=["permno", "month"], how="inner")
    assert len(merged) > 0, "no overlap between vectorized and iter-9 reference"
    np.testing.assert_allclose(
        merged["ret_fwd6"].values,
        merged["ref_ret_fwd6"].values,
        rtol=1e-10,
        atol=1e-12,
        err_msg="vectorized forward_returns_h disagrees with iter-9 reference",
    )


def test_forward_returns_h_fast_on_large_panel() -> None:
    """Perf gate: 50k rows of 12 monthly periods must complete in <2s.

    Sanity check that the vectorized implementation is actually fast.
    Pre-iter-11 this would have been ~30s.
    """
    import time
    np.random.seed(1)
    n_stocks, n_months = 5000, 12
    permno = np.repeat(np.arange(1, n_stocks + 1), n_months)
    month = np.tile(pd.date_range("2020-01-31", periods=n_months, freq="ME"), n_stocks)
    ret = np.random.normal(0.005, 0.03, n_stocks * n_months)
    df = pd.DataFrame({
        "permno": permno, "month": month, "ret": ret,
        "signal": np.random.normal(0, 1, n_stocks * n_months),
    })
    t0 = time.time()
    out = forward_returns_h(df, signal_col="signal", date_col="month",
                            ret_col="ret", n_lags=6)
    elapsed = time.time() - t0
    # Pre-iter-11 this was ~30s for 60k rows; vectorized should be <2s.
    assert elapsed < 2.0, f"forward_returns_h too slow: {elapsed:.2f}s on 60k rows"
    assert len(out) > 0
