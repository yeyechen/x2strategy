"""Tests for utils.portfolio — bin_returns + long_short."""

import numpy as np
import pandas as pd
import pytest

from utils.portfolio import bin_returns, long_short, PortfolioError


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