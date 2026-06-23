"""Tests for utils.metrics — performance_metrics + format_metrics."""

import numpy as np
import pandas as pd
import pytest

from utils.metrics import performance_metrics, format_metrics, MetricsError


# ── Helpers ──────────────────────────────────────────────────


def _make_returns(monthly_returns: list, freq="M"):
    """Wrap a list of monthly returns as a Series indexed by month-end dates."""
    n = len(monthly_returns)
    dates = pd.date_range("2020-01-31", periods=n, freq="ME")
    return pd.Series(monthly_returns, index=dates, name="ret")


# ── performance_metrics ──────────────────────────────────────


class TestPerformanceMetrics:
    def test_known_inputs_basic(self):
        # All-zero returns → total_return = 0, sharpe = 0, max_dd = 0
        rets = _make_returns([0.0] * 12)
        m = performance_metrics(rets, freq="M")
        assert m["total_return"] == pytest.approx(0.0)
        assert m["sharpe_ratio"] == pytest.approx(0.0, abs=1e-9)
        assert m["max_drawdown"] == pytest.approx(0.0)

    def test_constant_positive_return(self):
        # Constant +1% monthly → annualized return 12%
        rets = _make_returns([0.01] * 12)
        m = performance_metrics(rets, freq="M")
        assert m["annual_return"] == pytest.approx(0.12, rel=1e-6)
        # Zero volatility → Sharpe = 0 (avoid divide-by-zero)
        assert m["annualized_vol"] == pytest.approx(0.0, abs=1e-9)
        assert m["sharpe_ratio"] == pytest.approx(0.0, abs=1e-9)

    def test_total_return_compounds(self):
        # 10% then -10% → total = -1%, not 0
        rets = _make_returns([0.10, -0.10])
        m = performance_metrics(rets, freq="M")
        # (1 + 0.10) * (1 - 0.10) - 1 = 1.1 * 0.9 - 1 = -0.01
        assert m["total_return"] == pytest.approx(-0.01, rel=1e-9)

    def test_max_drawdown_detected(self):
        # 0%, +50%, -40% → drawdown of (1.5 * 0.6) / 1.5 - 1 = -40%
        rets = _make_returns([0.0, 0.50, -0.40])
        m = performance_metrics(rets, freq="M")
        assert m["max_drawdown"] == pytest.approx(-0.40, rel=1e-6)

    def test_invalid_freq_raises(self):
        rets = _make_returns([0.01] * 12)
        with pytest.raises(MetricsError, match="Invalid frequency"):
            performance_metrics(rets, freq="X")

    def test_empty_series_raises(self):
        rets = pd.Series([], dtype=float)
        with pytest.raises(MetricsError, match="empty"):
            performance_metrics(rets, freq="M")

    def test_all_nan_raises(self):
        rets = pd.Series([np.nan] * 5, index=pd.date_range("2020-01-31", periods=5, freq="ME"))
        with pytest.raises(MetricsError, match="NaN"):
            performance_metrics(rets, freq="M")

    def test_dataframe_input(self):
        df = pd.DataFrame({
            "month": pd.date_range("2020-01-31", periods=12, freq="ME"),
            "ret": [0.01] * 12,
        })
        m = performance_metrics(df, freq="M", date_col="month", ret_col="ret")
        assert m["annual_return"] == pytest.approx(0.12, rel=1e-6)

    def test_returns_dict_keys(self):
        rets = _make_returns([0.01, -0.02, 0.03])
        m = performance_metrics(rets, freq="M")
        assert set(m.keys()) >= {
            "total_return", "annual_return", "annualized_vol",
            "annualized_volatility", "sharpe_ratio", "max_drawdown", "cagr",
        }

    def test_daily_vs_monthly_annualization(self):
        # Same mean return, different freq → different annual_return
        monthly = _make_returns([0.01] * 12)
        m_monthly = performance_metrics(monthly, freq="M")
        # Daily: 0.01 daily × 252 = 252% annual (deliberately inflated)
        daily_dates = pd.date_range("2020-01-01", periods=252, freq="B")
        daily = pd.Series([0.01] * 252, index=daily_dates)
        m_daily = performance_metrics(daily, freq="D")
        assert m_daily["annual_return"] > m_monthly["annual_return"] * 10

    def test_annualized_vol_alias_matches_canonical(self):
        rets = _make_returns([0.01, -0.01, 0.02, -0.02, 0.01])
        m = performance_metrics(rets, freq="M")
        assert m["annualized_vol"] == m["annualized_volatility"]


# ── format_metrics ───────────────────────────────────────────


class TestFormatMetrics:
    def test_format_returns_strings(self):
        rets = _make_returns([0.01, -0.02, 0.03, 0.01, -0.01, 0.02])
        m = performance_metrics(rets, freq="M")
        f = format_metrics(m)
        assert isinstance(f["Total Return"], str)
        assert f["Total Return"].endswith("%")
        assert f["Sharpe Ratio"].endswith(".2f") or "." in f["Sharpe Ratio"]  # numeric, 2 decimals

    def test_format_handles_negative(self):
        rets = _make_returns([-0.05, -0.10, 0.02])
        m = performance_metrics(rets, freq="M")
        f = format_metrics(m)
        assert "-" in f["Total Return"] or f["Total Return"].startswith("0.00")