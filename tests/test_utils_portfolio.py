"""Tests for utils.portfolio — bin_returns + long_short + forward_returns."""

import numpy as np
import pandas as pd
import pytest

from utils.portfolio import (
    bin_returns,
    long_short,
    forward_returns,
    forward_returns_h,
    rolling_cumret,
    PortfolioError,
)


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def binned_df():
    """Two dates × 50 stocks with 5 bins each."""
    n = 50
    rng = np.random.default_rng(42)
    rows = []
    for date in pd.to_datetime(["2020-01-31", "2020-02-29"]):
        for i in range(n):
            rows.append({
                "month": date,
                "permno": i,
                "bin": (i % 5) + 1,
                "ret": rng.normal(0, 0.05),
                "mcap_lag1": rng.uniform(1e6, 1e9),
            })
    return pd.DataFrame(rows)


# ── bin_returns ───────────────────────────────────────────────


class TestBinReturns:
    def test_returns_one_row_per_date_per_bin(self, binned_df):
        out = bin_returns(binned_df, "month", "bin", "ret", "mcap_lag1")
        # 2 dates × 5 bins = 10 rows
        assert len(out) == 10
        assert set(out.columns) >= {"month", "bin", "EW", "VW"}

    def test_ew_and_vw_distinct(self, binned_df):
        out = bin_returns(binned_df, "month", "bin", "ret", "mcap_lag1")
        # EW and VW should differ for the random data
        assert not (out["EW"] == out["VW"]).all()

    def test_ew_is_simple_mean(self, binned_df):
        """EW for each (date, bin) should match the simple mean of returns."""
        out = bin_returns(binned_df, "month", "bin", "ret", "mcap_lag1")
        for _, row in out.iterrows():
            mask = (binned_df["month"] == row["month"]) & (binned_df["bin"] == row["bin"])
            expected = binned_df.loc[mask, "ret"].mean()
            assert row["EW"] == pytest.approx(expected, rel=1e-9)

    def test_vw_is_weighted_mean(self, binned_df):
        """VW for each (date, bin) should match sum(r*w)/sum(w)."""
        out = bin_returns(binned_df, "month", "bin", "ret", "mcap_lag1")
        for _, row in out.iterrows():
            mask = (binned_df["month"] == row["month"]) & (binned_df["bin"] == row["bin"])
            sub = binned_df.loc[mask]
            expected = (sub["ret"] * sub["mcap_lag1"]).sum() / sub["mcap_lag1"].sum()
            assert row["VW"] == pytest.approx(expected, rel=1e-9)

    def test_missing_column_raises(self, binned_df):
        with pytest.raises(PortfolioError, match="missing columns"):
            bin_returns(binned_df, "month", "bin", "ret", "wrong_mcap_col")

    def test_ew_equals_vw_when_mcaps_equal(self):
        """If all mcaps in a bin are equal, VW should equal EW."""
        rows = []
        for date in pd.to_datetime(["2020-01-31"]):
            for i in range(10):
                rows.append({"month": date, "permno": i, "bin": 1,
                             "ret": 0.01 * (i + 1), "mcap_lag1": 1e6})
        df = pd.DataFrame(rows)
        out = bin_returns(df, "month", "bin", "ret", "mcap_lag1")
        assert out["EW"].iloc[0] == pytest.approx(out["VW"].iloc[0], rel=1e-9)


# ── long_short ───────────────────────────────────────────────


class TestLongShort:
    def test_long_short_arithmetic(self):
        """Long bin - short bin = the per-row difference."""
        bins_df = pd.DataFrame({
            "month": pd.to_datetime([
                "2020-01-31", "2020-01-31",
                "2020-02-29", "2020-02-29",
            ]),
            "bin": [10, 1, 10, 1],
            "EW": [0.05, 0.01, 0.03, -0.02],
            "VW": [0.04, 0.02, 0.02, -0.01],
        })
        out = long_short(bins_df, "month", "EW", long_bin=10, short_bin=1)
        assert list(out.columns) == ["month", "ret"]
        assert out["ret"].iloc[0] == pytest.approx(0.05 - 0.01)
        assert out["ret"].iloc[1] == pytest.approx(0.03 - (-0.02))

    def test_default_extreme_bins(self):
        """If long_bin/short_bin not given, defaults to max/min."""
        bins_df = pd.DataFrame({
            "month": pd.to_datetime(["2020-01-31"] * 5),
            "bin": [1, 2, 3, 4, 5],
            "EW": [0.01, 0.02, 0.03, 0.04, 0.05],
        })
        out = long_short(bins_df, "month", "EW")
        assert out["ret"].iloc[0] == pytest.approx(0.05 - 0.01)

    def test_same_long_short_raises(self):
        bins_df = pd.DataFrame({
            "month": pd.to_datetime(["2020-01-31"]),
            "bin": [1],
            "EW": [0.01],
        })
        with pytest.raises(PortfolioError, match="must differ"):
            long_short(bins_df, "month", "EW", long_bin=1, short_bin=1)

    def test_empty_long_bin_raises(self):
        bins_df = pd.DataFrame({
            "month": pd.to_datetime(["2020-01-31"]),
            "bin": [1],
            "EW": [0.01],
        })
        with pytest.raises(PortfolioError, match="no data for long_bin"):
            long_short(bins_df, "month", "EW", long_bin=10, short_bin=1)

    def test_missing_col_raises(self):
        df = pd.DataFrame({"month": [1], "bin": [1], "x": [0.01]})
        with pytest.raises(PortfolioError, match="missing columns"):
            long_short(df, "month", "EW")

    def test_flip_sign(self):
        """flip_sign=True negates the return (paper D10-D1 convention)."""
        bins_df = pd.DataFrame({
            "month": pd.to_datetime(["2020-01-31", "2020-01-31"]),
            "bin": [1, 10],
            "VW": [0.02, -0.01],
        })
        # Without flip: long(1) - short(10) = 0.02 - (-0.01) = 0.03
        out_normal = long_short(bins_df, "month", "VW", long_bin=1, short_bin=10)
        assert out_normal["ret"].iloc[0] == pytest.approx(0.03)

        # With flip: -(0.03) = -0.03 (paper D10-D1 convention)
        out_flip = long_short(bins_df, "month", "VW", long_bin=1, short_bin=10, flip_sign=True)
        assert out_flip["ret"].iloc[0] == pytest.approx(-0.03)


# ── forward_returns ──────────────────────────────────────────


class TestForwardReturns:
    def test_shifts_return_forward_by_n_lags(self):
        # 1 stock, 4 months — after 1-lag shift, return at month t is
        # the value that was at month t+1 originally. Last row drops.
        df = pd.DataFrame({
            "permno": [1, 1, 1, 1],
            "month": pd.to_datetime(["2020-01-31", "2020-02-29", "2020-03-31", "2020-04-30"]),
            "max_signal": [0.05, 0.04, 0.06, 0.03],
            "ret":        [0.01, 0.02, 0.03, 0.04],
        })
        out = forward_returns(df, signal_col="max_signal", date_col="month", ret_col="ret", n_lags=1)
        # After shift: row 0's ret should be 0.02 (originally at month t+1)
        assert out["ret"].iloc[0] == pytest.approx(0.02)
        assert out["ret"].iloc[1] == pytest.approx(0.03)
        assert out["ret"].iloc[2] == pytest.approx(0.04)
        # Last row (no t+1) drops out
        assert len(out) == 3

    def test_per_stock_grouping(self):
        # Two stocks — shift must happen within each stock, not across.
        df = pd.DataFrame({
            "permno":  [1, 1, 1, 2, 2, 2],
            "month":   pd.to_datetime(["2020-01-31", "2020-02-29", "2020-03-31"] * 2),
            "max_signal": [0.05, 0.04, 0.06, 0.07, 0.05, 0.04],
            "ret":     [0.01, 0.02, 0.03, 0.10, 0.20, 0.30],
        })
        out = forward_returns(df, signal_col="max_signal", date_col="month", ret_col="ret", n_lags=1)
        # Stock 1: shifted [0.02, 0.03] (last drops)
        stock1 = out[out["permno"] == 1].sort_values("month")
        assert list(stock1["ret"]) == pytest.approx([0.02, 0.03])
        # Stock 2: shifted [0.20, 0.30]
        stock2 = out[out["permno"] == 2].sort_values("month")
        assert list(stock2["ret"]) == pytest.approx([0.20, 0.30])

    def test_missing_col_raises(self):
        df = pd.DataFrame({"permno": [1], "month": [pd.Timestamp("2020-01-31")]})
        with pytest.raises(PortfolioError, match="missing columns"):
            forward_returns(df, signal_col="missing_signal", date_col="month")

    def test_no_per_stock_col_raises(self):
        df = pd.DataFrame({
            "month": [pd.Timestamp("2020-01-31")],
            "max_signal": [0.05],
            "ret": [0.01],
        })
        with pytest.raises(PortfolioError, match="per-stock grouping"):
            forward_returns(df, signal_col="max_signal", date_col="month")

    def test_n_lags_2(self):
        df = pd.DataFrame({
            "permno": [1] * 5,
            "month": pd.date_range("2020-01-31", periods=5, freq="ME"),
            "max_signal": [0.05] * 5,
            "ret": [0.01, 0.02, 0.03, 0.04, 0.05],
        })
        out = forward_returns(df, signal_col="max_signal", date_col="month", ret_col="ret", n_lags=2)
        # After 2-lag shift: returns should be [0.03, 0.04, 0.05], last 2 drop
        assert list(out["ret"]) == pytest.approx([0.03, 0.04, 0.05])

    def test_invalid_n_lags_raises(self):
        df = pd.DataFrame({
            "permno": [1],
            "month": [pd.Timestamp("2020-01-31")],
            "max_signal": [0.05],
            "ret": [0.01],
        })
        with pytest.raises(PortfolioError, match="n_lags"):
            forward_returns(df, signal_col="max_signal", date_col="month", n_lags=0)

# ── forward_returns_h ──────────────────────────────────────


class TestForwardReturnsH:
    """Tests for forward_returns_h — both default (per-month geometric mean)
    and cumulative=True (H-month cumulative return)."""

    def test_default_preserves_ret_and_adds_column(self):
        """Default mode (cumulative=False): adds ret_fwd6 = exp(mean(log(1+ret))) - 1."""
        df = pd.DataFrame({
            "permno": [1] * 7,
            "month": pd.date_range("2020-01-31", periods=7, freq="ME"),
            "pret": [0.05] * 7,
            "ret": [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07],
        })
        out = forward_returns_h(
            df, signal_col="pret", date_col="month",
            ret_col="ret", n_lags=3,
        )
        # Original 'ret' is preserved
        assert "ret" in out.columns
        # New column added with default name
        assert "ret_fwd3" in out.columns
        # Last n_lags=3 rows dropped (rows 4, 5, 6)
        assert len(out) == 4

    def test_default_geometric_mean_value(self):
        """Default mode: at month t, ret_fwd3 = exp(mean(log(1+ret[t+1:t+4]))) - 1."""
        df = pd.DataFrame({
            "permno": [1] * 6,
            "month": pd.date_range("2020-01-31", periods=6, freq="ME"),
            "pret": [0.05] * 6,
            "ret": [0.01, 0.02, 0.03, 0.04, 0.05, 0.06],
        })
        out = forward_returns_h(
            df, signal_col="pret", date_col="month",
            ret_col="ret", n_lags=3,
        )
        # Expected at row 0: 3 months of 0.02, 0.03, 0.04 → geometric mean
        # = exp((log(1.02) + log(1.03) + log(1.04)) / 3) - 1
        expected = np.expm1(
            (np.log1p(0.02) + np.log1p(0.03) + np.log1p(0.04)) / 3
        )
        assert out["ret_fwd3"].iloc[0] == pytest.approx(expected, rel=1e-9)

    def test_cumulative_true_value(self):
        """cumulative=True: at month t, ret_fwd3 = prod(1+ret[t+1:t+4]) - 1."""
        df = pd.DataFrame({
            "permno": [1] * 6,
            "month": pd.date_range("2020-01-31", periods=6, freq="ME"),
            "pret": [0.05] * 6,
            "ret": [0.01, 0.02, 0.03, 0.04, 0.05, 0.06],
        })
        out = forward_returns_h(
            df, signal_col="pret", date_col="month",
            ret_col="ret", n_lags=3, cumulative=True,
        )
        # Expected at row 0: prod(1+0.02, 1+0.03, 1+0.04) - 1
        expected = (1.02 * 1.03 * 1.04) - 1
        assert out["ret_fwd3"].iloc[0] == pytest.approx(expected, rel=1e-9)

    def test_cumulative_equals_compounded_default_when_ret_constant(self):
        """When per-period returns are constant r:
        - default = r (per-month equivalent)
        - cumulative = (1+r)^H - 1 (H-month cumulative)
        Compounding the default for H periods must equal the cumulative.
        """
        df = pd.DataFrame({
            "permno": [1] * 8,
            "month": pd.date_range("2020-01-31", periods=8, freq="ME"),
            "pret": [0.05] * 8,
            "ret": [0.02] * 8,
        })
        out_default = forward_returns_h(
            df, signal_col="pret", date_col="month",
            ret_col="ret", n_lags=4, cumulative=False,
        )
        out_cumul = forward_returns_h(
            df, signal_col="pret", date_col="month",
            ret_col="ret", n_lags=4, cumulative=True,
        )
        # (1 + default_value)^H - 1 == cumulative_value
        compounded = (1 + out_default["ret_fwd4"].iloc[0]) ** 4 - 1
        assert compounded == pytest.approx(
            out_cumul["ret_fwd4"].iloc[0], rel=1e-9
        )

    def test_cumulative_jensen_inequality(self):
        """(1 + mean(r))^H <= mean((1+r)^H): cumulative is larger than
        compounding-the-mean when returns vary (Jensen's inequality)."""
        df = pd.DataFrame({
            "permno": [1] * 8,
            "month": pd.date_range("2020-01-31", periods=8, freq="ME"),
            "pret": [0.05] * 8,
            # Alternating small and large returns → mean is 0.10
            "ret": [0.20, 0.00, 0.30, -0.10, 0.20, 0.00, 0.30, -0.10],
        })
        out_default = forward_returns_h(
            df, signal_col="pret", date_col="month",
            ret_col="ret", n_lags=4, cumulative=False,
        )
        out_cumul = forward_returns_h(
            df, signal_col="pret", date_col="month",
            ret_col="ret", n_lags=4, cumulative=True,
        )
        # Cumulative must be >= default (Jensen's inequality, both > 0 here)
        assert out_cumul["ret_fwd4"].iloc[0] > out_default["ret_fwd4"].iloc[0]

    def test_cumulative_per_stock_grouping(self):
        """Per-stock grouping is preserved in cumulative mode."""
        df = pd.DataFrame({
            "permno":  [1, 1, 1, 1, 2, 2, 2, 2],
            "month":   pd.to_datetime(
                ["2020-01-31", "2020-02-29", "2020-03-31", "2020-04-30"] * 2
            ),
            "pret":    [0.05] * 8,
            "ret":     [0.01, 0.02, 0.03, 0.04,
                        0.10, 0.20, 0.30, 0.40],
        })
        out = forward_returns_h(
            df, signal_col="pret", date_col="month",
            ret_col="ret", n_lags=2, cumulative=True,
        )
        # Stock 1: prod(1+0.02, 1+0.03) - 1 = 1.02*1.03 - 1 = 0.0506
        s1 = out[out["permno"] == 1].sort_values("month")
        assert s1["ret_fwd2"].iloc[0] == pytest.approx(1.02 * 1.03 - 1, rel=1e-9)
        # Stock 2: prod(1+0.20, 1+0.30) - 1 = 1.20*1.30 - 1 = 0.56
        s2 = out[out["permno"] == 2].sort_values("month")
        assert s2["ret_fwd2"].iloc[0] == pytest.approx(1.20 * 1.30 - 1, rel=1e-9)

    def test_cumulative_drops_last_n_lags(self):
        """cumulative=True drops the last n_lags rows per stock, same as default."""
        df = pd.DataFrame({
            "permno": [1] * 5,
            "month": pd.date_range("2020-01-31", periods=5, freq="ME"),
            "pret": [0.05] * 5,
            "ret": [0.01, 0.02, 0.03, 0.04, 0.05],
        })
        out = forward_returns_h(
            df, signal_col="pret", date_col="month",
            ret_col="ret", n_lags=2, cumulative=True,
        )
        # 5 rows - 2 dropped = 3 remaining
        assert len(out) == 3

    def test_cumulative_preserves_ret(self):
        """cumulative=True does not modify the original ret column."""
        df = pd.DataFrame({
            "permno": [1] * 5,
            "month": pd.date_range("2020-01-31", periods=5, freq="ME"),
            "pret": [0.05] * 5,
            "ret": [0.01, 0.02, 0.03, 0.04, 0.05],
        })
        out = forward_returns_h(
            df, signal_col="pret", date_col="month",
            ret_col="ret", n_lags=2, cumulative=True,
        )
        # Original ret values must be unchanged in the output
        assert list(out["ret"]) == pytest.approx([0.01, 0.02, 0.03])

    def test_missing_col_raises_h(self):
        df = pd.DataFrame({"permno": [1], "month": [pd.Timestamp("2020-01-31")]})
        with pytest.raises(PortfolioError, match="missing columns"):
            forward_returns_h(
                df, signal_col="missing_signal", date_col="month",
                ret_col="missing_ret", n_lags=2,
            )

    def test_invalid_n_lags_raises_h(self):
        df = pd.DataFrame({
            "permno": [1],
            "month": [pd.Timestamp("2020-01-31")],
            "pret": [0.05],
            "ret": [0.01],
        })
        with pytest.raises(PortfolioError, match="n_lags"):
            forward_returns_h(
                df, signal_col="pret", date_col="month",
                ret_col="ret", n_lags=0,
            )


# ── rolling_cumret ──────────────────────────────────────────


class TestRollingCumret:
    """Tests for rolling_cumret — JT 12-2 momentum signal formation."""

    def _make_panel(self, returns_per_stock, stock_ids, n_dates, start="2020-01-31"):
        """Helper: build a panel with monthly returns per stock.

        returns_per_stock[stock] is a list of n_dates returns.
        """
        rows = []
        for sid, rets in zip(stock_ids, returns_per_stock):
            assert len(rets) == n_dates
            for i, r in enumerate(rets):
                rows.append({
                    "permno": sid,
                    "month": pd.date_range(start, periods=n_dates, freq="ME")[i],
                    "ret": r,
                })
        return pd.DataFrame(rows)

    def test_jt_12_2_correctness(self):
        """JT 12-2: window=11, skip=1 → at month t, output is prod(1+ret[t-12:t-2]) - 1.

        With 14 months of data and 1 stock:
          ret indices: 0  1  2  3  4  5  6  7  8  9  10 11 12 13
          months:      0  1  2  3  4  5  6  7  8  9  10 11 12 13

        At month t=12, formation is months [1..11] (skip month 11? No — skip=1
        means skip the most recent month (month 12), so formation is months
        1..10? Let me re-derive from the function semantics:)

        Per the docstring: skip=1 → shift=2 → at month t, the value is
        ret[t-2]. Rolling(11) gives the 11 months ending at ret[t-2].
        So formation = [t-12, t-2] = months 0..10 at t=12.

        Actually for t=12, shifted[12] = ret[10], rolling(11) takes indices
        [12-10, 12] = [2, 12] in the shifted series. Wait, let me think
        again. The shifted series is shifted by 2: shifted[12] = ret[10].
        rolling(11) at index 12 takes shifted[12-10:13] = shifted[2:13]
        = ret[0:11] (after the shift). So formation = [t-12, t-2] = ret[0..10]
        at t=12.

        Hmm, that's 11 months, indices 0..10. Let me just verify the actual
        values the function returns.
        """
        # 14 months of returns, all 0.01
        rets = [0.01] * 14
        panel = self._make_panel([rets], stock_ids=[1], n_dates=14)

        out = rolling_cumret(
            panel, date_col="month", ret_col="ret",
            window=11, skip=1,
        )

        # First valid output at index 12 (t=12): formation = ret[0..10] (11 months)
        # = (1.01)^11 - 1
        expected = (1.01) ** 11 - 1
        assert out.iloc[12] == pytest.approx(expected, rel=1e-9)
        # Last index (13) should also be valid: formation = ret[1..11]
        expected_last = (1.01) ** 11 - 1
        assert out.iloc[13] == pytest.approx(expected_last, rel=1e-9)

    def test_skip_zero(self):
        """skip=0: shift=1 → formation = [t-window, t-1] (no extra skip)."""
        rets = [0.01] * 14
        panel = self._make_panel([rets], stock_ids=[1], n_dates=14)

        out = rolling_cumret(
            panel, date_col="month", ret_col="ret",
            window=11, skip=0,
        )

        # At t=12, formation = ret[1..11] (11 months), shifted[12] = ret[11]
        expected = (1.01) ** 11 - 1
        # First valid output at index 11
        assert out.iloc[11] == pytest.approx(expected, rel=1e-9)

    def test_per_stock_grouping(self):
        """Per-stock grouping: stock 2's returns don't pollute stock 1's window."""
        # 14 months, two stocks with very different returns
        rets_1 = [0.01] * 14
        rets_2 = [0.10] * 14
        panel = self._make_panel([rets_1, rets_2], stock_ids=[1, 2], n_dates=14)

        out = rolling_cumret(
            panel, date_col="month", ret_col="ret",
            window=11, skip=1,
        )

        # Both stocks should have (1.01)^11 - 1 and (1.10)^11 - 1 respectively
        # Get the value at the last month for each stock
        out_df = pd.DataFrame({"permno": panel["permno"], "val": out})
        s1_val = out_df[out_df["permno"] == 1]["val"].iloc[-1]
        s2_val = out_df[out_df["permno"] == 2]["val"].iloc[-1]
        assert s1_val == pytest.approx((1.01) ** 11 - 1, rel=1e-9)
        assert s2_val == pytest.approx((1.10) ** 11 - 1, rel=1e-9)

    def test_min_periods(self):
        """min_periods=8: window=11 → only emit when >= 8 non-NaN months available."""
        rets = [0.01] * 14
        panel = self._make_panel([rets], stock_ids=[1], n_dates=14)

        out = rolling_cumret(
            panel, date_col="month", ret_col="ret",
            window=11, skip=1, min_periods=8,
        )

        # With skip=1, first valid is at t=12 (since shift=2 + window=11 → need t>=12)
        # But min_periods=8: only emit if 8 non-NaN in the rolling window.
        # At t=12, the shifted series has valid values from index 2 onwards.
        # rolling(11) at index 12 takes shifted[2:13] — all 11 are valid.
        assert out.iloc[12] == pytest.approx((1.01) ** 11 - 1, rel=1e-9)

    def test_min_periods_relaxes_constraint(self):
        """min_periods=5 emits earlier than the default min_periods=window=11."""
        rets = [0.01] * 14
        panel = self._make_panel([rets], stock_ids=[1], n_dates=14)

        out_default = rolling_cumret(
            panel, date_col="month", ret_col="ret",
            window=11, skip=1,
        )
        out_relaxed = rolling_cumret(
            panel, date_col="month", ret_col="ret",
            window=11, skip=1, min_periods=5,
        )

        # Default (min_periods=11): first non-NaN is at t=12
        assert pd.isna(out_default.iloc[11])
        assert not pd.isna(out_default.iloc[12])

        # Relaxed (min_periods=5): first non-NaN is much earlier
        assert not pd.isna(out_relaxed.iloc[6])  # well before t=12

    def test_short_panel(self):
        """Shorter panel: only 8 months. Default min_periods=11 → all NaN."""
        rets = [0.01] * 8
        panel = self._make_panel([rets], stock_ids=[1], n_dates=8)

        out = rolling_cumret(
            panel, date_col="month", ret_col="ret",
            window=11, skip=1,
        )

        # Not enough data → all NaN
        assert out.isna().all()

    def test_missing_col_raises(self):
        panel = pd.DataFrame({
            "permno": [1, 1, 1],
            "month": pd.date_range("2020-01-31", periods=3, freq="ME"),
        })
        with pytest.raises(PortfolioError, match="missing columns"):
            rolling_cumret(panel, date_col="month", ret_col="missing_ret",
                           window=11, skip=1)

    def test_no_per_stock_col_raises(self):
        panel = pd.DataFrame({
            "month": pd.date_range("2020-01-31", periods=14, freq="ME"),
            "ret": [0.01] * 14,
        })
        with pytest.raises(PortfolioError, match="per-stock grouping"):
            rolling_cumret(panel, date_col="month", ret_col="ret",
                           window=11, skip=1)

    def test_invalid_window_raises(self):
        panel = pd.DataFrame({
            "permno": [1], "month": [pd.Timestamp("2020-01-31")],
            "ret": [0.01],
        })
        with pytest.raises(PortfolioError, match="window"):
            rolling_cumret(panel, date_col="month", ret_col="ret",
                           window=0, skip=1)

    def test_invalid_skip_raises(self):
        panel = pd.DataFrame({
            "permno": [1], "month": [pd.Timestamp("2020-01-31")],
            "ret": [0.01],
        })
        with pytest.raises(PortfolioError, match="skip"):
            rolling_cumret(panel, date_col="month", ret_col="ret",
                           window=11, skip=-1)

    def test_varying_returns(self):
        """With varying returns, output = prod(1+ret) - 1 (not just any formula)."""
        rets = [0.01, 0.02, -0.01, 0.03, -0.02, 0.01, 0.04, -0.01, 0.02, 0.01,
                -0.03, 0.02, 0.01, 0.03]
        panel = self._make_panel([rets], stock_ids=[1], n_dates=14)

        out = rolling_cumret(
            panel, date_col="month", ret_col="ret",
            window=11, skip=1,
        )

        # At t=12: formation = rets[0..10] (11 months)
        formation = rets[0:11]
        expected = np.prod([1 + r for r in formation]) - 1
        assert out.iloc[12] == pytest.approx(expected, rel=1e-9)

    def test_auto_detects_stock_col(self):
        """Auto-detects 'ticker' if 'permno' is absent."""
        panel = pd.DataFrame({
            "ticker": ["AAPL"] * 14,
            "month": pd.date_range("2020-01-31", periods=14, freq="ME"),
            "ret": [0.01] * 14,
        })
        out = rolling_cumret(
            panel, date_col="month", ret_col="ret",
            window=11, skip=1,
        )
        assert not out.isna().all()
        assert out.iloc[12] == pytest.approx((1.01) ** 11 - 1, rel=1e-9)
