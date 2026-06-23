"""Tests for utils.plot — verify the plots produce PNG files when given
a save_to path. Doesn't check pixel content (matplotlib behavior is
contracted enough), only that the file gets written.
"""

import tempfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # must be set before any pyplot import
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from utils.plot import (
    plot_cumulative_returns, plot_drawdown, plot_decile_spread,
    plot_performance_comparison, PlotError,
)


@pytest.fixture
def sample_returns():
    rng = np.random.default_rng(0)
    n = 24
    dates = pd.date_range("2020-01-31", periods=n, freq="ME")
    return pd.DataFrame({
        "month": dates,
        "ret_EW": rng.normal(0.005, 0.03, size=n),
        "ret_VW": rng.normal(0.004, 0.02, size=n),
    })


@pytest.fixture
def sample_bins():
    return pd.DataFrame({
        "bin": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "EW": [0.001, 0.002, 0.003, 0.004, 0.005, 0.006, 0.007, 0.008, 0.009, 0.010],
        "VW": [0.0005, 0.0015, 0.0025, 0.0035, 0.0045, 0.0055, 0.0065, 0.0075, 0.0085, 0.0095],
    })


class TestPlotCumulativeReturns:
    def test_writes_png(self, sample_returns, tmp_path):
        path = tmp_path / "pnl.png"
        plot_cumulative_returns(
            sample_returns, "month", ["ret_EW", "ret_VW"],
            title="Test", save_to=path,
        )
        assert path.exists()
        assert path.stat().st_size > 0

    def test_missing_col_raises(self, sample_returns):
        with pytest.raises(PlotError, match="missing columns"):
            plot_cumulative_returns(sample_returns, "month", ["nonexistent"])


class TestPlotDrawdown:
    def test_writes_png(self, sample_returns, tmp_path):
        path = tmp_path / "dd.png"
        plot_drawdown(sample_returns, "month", "ret_EW", save_to=path)
        assert path.exists()
        assert path.stat().st_size > 0

    def test_missing_col_raises(self, sample_returns):
        with pytest.raises(PlotError, match="missing columns"):
            plot_drawdown(sample_returns, "month", "nonexistent")


class TestPlotDecileSpread:
    def test_writes_png(self, sample_bins, tmp_path):
        path = tmp_path / "deciles.png"
        plot_decile_spread(sample_bins, save_to=path)
        assert path.exists()
        assert path.stat().st_size > 0

    def test_missing_col_raises(self, sample_bins):
        with pytest.raises(PlotError, match="missing columns"):
            plot_decile_spread(sample_bins[["bin", "EW"]])  # no VW


class TestPlotPerformanceComparison:
    def test_writes_png(self, sample_returns, tmp_path):
        path = tmp_path / "compare.png"
        portfolios = {"EW": sample_returns, "VW": sample_returns}
        plot_performance_comparison(
            portfolios, "month", "ret_EW", save_to=path
        )
        assert path.exists()
        assert path.stat().st_size > 0

    def test_empty_raises(self):
        with pytest.raises(PlotError, match="no portfolios"):
            plot_performance_comparison({}, "month", "ret")