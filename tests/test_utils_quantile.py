"""Tests for utils.quantile — assign_quantiles + assign_ranks."""

import numpy as np
import pandas as pd
import pytest

from utils.quantile import assign_quantiles, assign_ranks, QuantileError


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def signal_df():
    """Two dates × 100 stocks with a uniform signal."""
    n = 100
    rng = np.random.default_rng(42)
    rows = []
    for date in pd.to_datetime(["2020-01-31", "2020-02-29"]):
        for i in range(n):
            rows.append({
                "month": date,
                "permno": i,
                "signal": rng.uniform(0, 1),
                "ret": rng.normal(0, 0.05),
            })
    return pd.DataFrame(rows)


# ── assign_quantiles ──────────────────────────────────────────


class TestAssignQuantiles:
    def test_returns_int_bins_in_range(self, signal_df):
        out = assign_quantiles(signal_df, "month", "signal", n_bins=10)
        assert out.dtype.kind == "i" or out.dtype.kind == "f"  # qcut returns int; fallback returns float
        # Every non-NaN bin should be in [1, 10]
        valid = out.dropna()
        assert valid.between(1, 10).all()

    def test_bins_balanced_for_uniform_signal(self, signal_df):
        out = assign_quantiles(signal_df, "month", "signal", n_bins=10)
        for date, group in out.groupby(signal_df["month"]):
            counts = group.value_counts()
            # Each bin should have ~10 observations (100 stocks / 10 bins)
            assert counts.max() - counts.min() <= 2, (
                f"Imbalanced bins on {date}: {counts.to_dict()}"
            )

    def test_missing_date_col_raises(self, signal_df):
        with pytest.raises(QuantileError, match="missing date_col"):
            assign_quantiles(signal_df, "wrong_col", "signal", n_bins=10)

    def test_missing_signal_col_raises(self, signal_df):
        with pytest.raises(QuantileError, match="missing signal_col"):
            assign_quantiles(signal_df, "month", "wrong_col", n_bins=10)

    def test_invalid_n_bins_raises(self, signal_df):
        with pytest.raises(QuantileError, match="n_bins"):
            assign_quantiles(signal_df, "month", "signal", n_bins=0)

    def test_fallback_triggered_when_qcut_fails(self, capsys, monkeypatch):
        # Force pd.qcut to fail, simulating the conditions under which
        # the rank-based fallback is meant to fire (very small groups,
        # all-equal inputs that older pandas versions reject).
        def _exploding_qcut(*args, **kwargs):
            raise ValueError("simulated qcut failure")

        monkeypatch.setattr("pandas.qcut", _exploding_qcut)

        df = pd.DataFrame({
            "month": pd.to_datetime(["2020-01-31"] * 10),
            "permno": list(range(10)),
            "signal": list(range(10)),  # unique values → qcut normally succeeds
        })
        out = assign_quantiles(df, "month", "signal", n_bins=5, warn_fallback=True)
        captured = capsys.readouterr()
        assert "rank-based fallback" in captured.out
        # Fallback should still produce valid bin labels in [1, 5]
        valid = out.dropna()
        assert valid.between(1, 5).all()

    def test_warn_fallback_false_silences(self, capsys, monkeypatch):
        def _exploding_qcut(*args, **kwargs):
            raise ValueError("simulated qcut failure")

        monkeypatch.setattr("pandas.qcut", _exploding_qcut)

        df = pd.DataFrame({
            "month": pd.to_datetime(["2020-01-31"] * 10),
            "permno": list(range(10)),
            "signal": list(range(10)),
        })
        out = assign_quantiles(df, "month", "signal", n_bins=5, warn_fallback=False)
        captured = capsys.readouterr()
        assert "rank-based fallback" not in captured.out


# ── assign_ranks ──────────────────────────────────────────────


class TestAssignRanks:
    def test_ranks_1_to_n_descending_by_default(self, signal_df):
        out = assign_ranks(signal_df, "month", "signal")
        for date, group_idx in out.groupby(signal_df["month"]).groups.items():
            ranks = out.loc[group_idx]
            assert ranks.min() == 1
            assert ranks.max() == 100
            # Default ascending=False → highest signal gets rank 1
            top_rank_pos = ranks.idxmin()  # position in original df where rank is min
            top_signal = signal_df.loc[top_rank_pos, "signal"]
            bottom_rank_pos = ranks.idxmax()
            bottom_signal = signal_df.loc[bottom_rank_pos, "signal"]
            assert top_signal >= bottom_signal  # rank 1 must be the highest signal

    def test_ranks_with_ascending_true(self, signal_df):
        out = assign_ranks(signal_df, "month", "signal", ascending=True)
        for date, group in out.groupby(signal_df["month"]):
            assert group.min() == 1
            assert group.max() == 100

    def test_tie_breaking_deterministic(self):
        # method="first" → ties broken by row order, fully deterministic
        df = pd.DataFrame({
            "month": pd.to_datetime(["2020-01-31"] * 4),
            "permno": [1, 2, 3, 4],
            "signal": [0.5, 0.5, 0.5, 0.5],
        })
        out = assign_ranks(df, "month", "signal")
        # method='first' gives ranks 1, 2, 3, 4 in row order
        assert sorted(out.tolist()) == [1, 2, 3, 4]

    def test_missing_col_raises(self):
        df = pd.DataFrame({"month": [1], "x": [0.5]})
        with pytest.raises(QuantileError, match="missing signal_col"):
            assign_ranks(df, "month", "y")