"""Tests for utils.regressions — run_ols + fama_macbeth + summarize_fama_macbeth.

These tests require statsmodels. They are deterministic given a fixed
random seed and check that the procedure recovers known coefficients.
"""

import numpy as np
import pandas as pd
import pytest

from utils.regressions import (
    run_ols, fama_macbeth, summarize_fama_macbeth, RegressionError,
)


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def synthetic_cross_section():
    """60 months × 200 stocks with known signal → return relationship.

    The true model is:
        ret = 0.02 + 0.5 * signal + 0.1 * z + noise
    so the Fama-MacBeth average coefficient on `signal` should be ~0.5
    and on `z` should be ~0.1.
    """
    rng = np.random.default_rng(0)
    rows = []
    n_months = 60
    n_stocks = 200
    for m in range(n_months):
        date = pd.Timestamp("2015-01-31") + pd.DateOffset(months=m)
        for s in range(n_stocks):
            signal = rng.normal(0, 1)
            z = rng.normal(0, 1)
            noise = rng.normal(0, 0.05)
            ret = 0.02 + 0.5 * signal + 0.1 * z + noise
            rows.append({"month": date, "permno": s,
                         "signal": signal, "z": z, "ret": ret})
    return pd.DataFrame(rows)


# ── run_ols ──────────────────────────────────────────────────


class TestRunOls:
    def test_recovers_known_coefficients(self):
        rng = np.random.default_rng(0)
        x = rng.normal(0, 1, size=100)
        y = 1.5 * x + 0.3 + rng.normal(0, 0.1, size=100)
        df = pd.DataFrame({"x": x, "y": y})

        result = run_ols(df, "y", ["x"])
        params = result["params"]
        # Intercept should be ~0.3, slope should be ~1.5
        assert params["const"] == pytest.approx(0.3, abs=0.05)
        assert params["x"] == pytest.approx(1.5, abs=0.05)

    def test_insufficient_obs_raises(self):
        df = pd.DataFrame({"x": [1.0, 2.0], "y": [3.0, 4.0]})
        with pytest.raises(RegressionError, match="insufficient"):
            run_ols(df, "y", ["x"])


# ── fama_macbeth ─────────────────────────────────────────────


class TestFamaMacbeth:
    def test_recovers_known_coefficients(self, synthetic_cross_section):
        result = fama_macbeth(
            synthetic_cross_section,
            dependent_var="ret",
            independent_vars=["signal", "z"],
            time_col="month",
        )

        mean = result.summary["mean"]
        # True coefficients are 0.5 and 0.1. Allow ~0.05 std given n_months=60.
        assert mean["signal"] == pytest.approx(0.5, abs=0.1)
        assert mean["z"] == pytest.approx(0.1, abs=0.1)

    def test_returns_coefficients_dataframe(self, synthetic_cross_section):
        result = fama_macbeth(
            synthetic_cross_section, "ret", ["signal", "z"], time_col="month"
        )
        coef = result.coefficients
        # Three columns: const + signal + z (sm.add_constant adds the intercept)
        assert coef.shape[1] == 3
        assert "const" in coef.columns
        assert "signal" in coef.columns
        assert "z" in coef.columns

    def test_summary_keys_present(self, synthetic_cross_section):
        result = fama_macbeth(
            synthetic_cross_section, "ret", ["signal", "z"], time_col="month"
        )
        summary = result.summary
        for k in ("mean", "std_error", "t_stat", "p_value",
                  "n_periods", "n_valid_periods", "avg_rsquared", "total_nobs"):
            assert k in summary

    def test_insufficient_obs_per_period_raises(self):
        # Only 1 obs per period → can't fit
        df = pd.DataFrame({
            "month": pd.to_datetime(["2020-01-31", "2020-02-29"]),
            "x": [1.0, 2.0],
            "y": [0.5, 1.0],
        })
        with pytest.raises(RegressionError, match="no time period"):
            fama_macbeth(df, "y", ["x"], time_col="month", min_obs=5)

    def test_nan_dropped(self):
        """NaN/inf rows should be dropped silently."""
        df = pd.DataFrame({
            "month": pd.to_datetime(["2020-01-31"] * 10),
            "x": [1.0, np.nan, 3.0, 4.0, np.inf, 6.0, 7.0, 8.0, 9.0, 10.0],
            "y": [2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0, 18.0, 20.0],
        })
        # Should run on the 8 valid rows after dropping nan/inf
        result = fama_macbeth(df, "y", ["x"], time_col="month")
        assert result.summary["n_valid_periods"] == 1


# ── summarize_fama_macbeth ───────────────────────────────────


class TestSummarizeFamaMacbeth:
    def test_returns_non_empty_string(self, synthetic_cross_section):
        result = fama_macbeth(
            synthetic_cross_section, "ret", ["signal", "z"], time_col="month"
        )
        s = summarize_fama_macbeth(result)
        assert isinstance(s, str)
        assert "FAMA-MACBETH REGRESSION RESULTS" in s
        assert "signal" in s
        assert "z" in s
        assert "p-value" in s

    def test_significance_stars_for_strong_signals(self):
        # Build data with a STRONG signal so p-values are tiny
        rng = np.random.default_rng(0)
        rows = []
        for m in range(120):
            date = pd.Timestamp("2015-01-31") + pd.DateOffset(months=m)
            for s in range(50):
                signal = rng.normal(0, 1)
                ret = 1.0 * signal + rng.normal(0, 0.1)
                rows.append({"month": date, "permno": s,
                             "signal": signal, "ret": ret})
        df = pd.DataFrame(rows)

        result = fama_macbeth(df, "ret", ["signal"], time_col="month")
        s = summarize_fama_macbeth(result)
        # Should have at least one *** marker for a strong effect
        assert "***" in s