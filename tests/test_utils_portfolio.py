"""Tests for utils.portfolio — bin_returns + long_short + forward_returns."""

import numpy as np
import pandas as pd
import pytest

from utils.portfolio import bin_returns, long_short, forward_returns, PortfolioError


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