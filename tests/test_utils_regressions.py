"""Tests for utils.regressions — run_ols + fama_macbeth + summarize_fama_macbeth.

These tests require statsmodels. They are deterministic given a fixed
random seed and check that the procedure recovers known coefficients.
"""

import numpy as np
import pandas as pd
import pytest

from utils.regressions import (
    run_ols, fama_macbeth, summarize_fama_macbeth,
    factor_alpha, summarize_factor_alpha, RegressionError,
)


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def synthetic_cross_section():
    """60 months × 200 stocks with known signal → return relationship.

    The true model is:
        ret = 0.02 + 0.5 * signal + 0.1 * z + noise
    so the Fama-MacBeth average coefficient on `signal` should be ~0.5
    and on `z` should be ~0.1. signal and z are N(0,1), so raw and
    standardized coefficients are similar — but the test checks RAW
    coefficients (no z-scoring in fama_macbeth).
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

    def test_raw_coefficients_not_standardized(self):
        """fama_macbeth must return RAW coefficients, not z-scored.

        If signal has std=0.1 (not 1.0), the raw coefficient is 10x
        the standardized coefficient. Verify we get the raw one.
        """
        rng = np.random.default_rng(42)
        rows = []
        for m in range(80):
            date = pd.Timestamp("2015-01-31") + pd.DateOffset(months=m)
            for s in range(100):
                # Signal with std=0.1, true raw coef = 2.0
                signal = rng.normal(0, 0.1)
                noise = rng.normal(0, 0.01)
                ret = 0.01 + 2.0 * signal + noise
                rows.append({"month": date, "permno": s,
                             "signal": signal, "ret": ret})
        df = pd.DataFrame(rows)

        result = fama_macbeth(df, "ret", ["signal"], time_col="month")
        mean = result.summary["mean"]

        # Raw coefficient should be ~2.0. If standardized, it would be ~0.2.
        assert mean["signal"] == pytest.approx(2.0, abs=0.3)
        # Explicitly check it's NOT the standardized value
        assert abs(mean["signal"]) > 1.0, (
            "fama_macbeth appears to be standardizing — coefficient "
            f"{mean['signal']:.4f} is too small for raw coef=2.0 with "
            "signal std=0.1 (standardized would be ~0.2)"
        )


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


# ── factor_alpha ──────────────────────────────────────────────


class TestFactorAlpha:
    @pytest.fixture
    def synthetic_factor_data(self):
        """120 months of portfolio + 4-factor returns with known alpha.

        True model: excess_ret = 0.005 + 1.2*mkt_rf + 0.3*smb + 0.1*hml + 0.0*mom + noise
        So alpha_monthly ~ 0.005, alpha_annualized_pct ~ 6.0.
        """
        rng = np.random.default_rng(42)
        n = 120
        months = pd.period_range("2010-01", periods=n, freq="M")
        mkt_rf = rng.normal(0.005, 0.04, n)
        smb = rng.normal(0.002, 0.02, n)
        hml = rng.normal(0.001, 0.02, n)
        mom = rng.normal(0.003, 0.03, n)
        rf = rng.normal(0.001, 0.0005, n)
        noise = rng.normal(0, 0.01, n)
        ret = rf + 0.005 + 1.2 * mkt_rf + 0.3 * smb + 0.1 * hml + 0.0 * mom + noise

        port = pd.Series(ret, index=months, name="ret")
        factors = pd.DataFrame({
            "mkt_rf": mkt_rf, "smb": smb, "hml": hml, "mom": mom, "rf": rf,
        }, index=months)
        return port, factors

    def test_recovers_known_alpha(self, synthetic_factor_data):
        port, factors = synthetic_factor_data
        result = factor_alpha(
            port, factors, factors=["mkt_rf", "smb", "hml", "mom"],
        )
        assert result["alpha_monthly"] == pytest.approx(0.005, abs=0.003)
        assert result["alpha_annualized_pct"] == pytest.approx(6.0, abs=3.6)

    def test_recovers_known_betas(self, synthetic_factor_data):
        port, factors = synthetic_factor_data
        result = factor_alpha(
            port, factors, factors=["mkt_rf", "smb", "hml", "mom"],
        )
        betas = result["betas"]
        assert betas["mkt_rf"] == pytest.approx(1.2, abs=0.15)
        assert betas["smb"] == pytest.approx(0.3, abs=0.15)
        assert betas["hml"] == pytest.approx(0.1, abs=0.15)

    def test_result_keys(self, synthetic_factor_data):
        port, factors = synthetic_factor_data
        result = factor_alpha(
            port, factors, factors=["mkt_rf", "smb", "hml", "mom"],
        )
        expected_keys = {
            "alpha_monthly", "alpha_annualized_pct",
            "t_alpha_newey_west", "p_alpha",
            "betas", "r_squared", "n_obs",
        }
        assert set(result.keys()) == expected_keys

    def test_n_obs_correct(self, synthetic_factor_data):
        port, factors = synthetic_factor_data
        result = factor_alpha(
            port, factors, factors=["mkt_rf", "smb", "hml", "mom"],
        )
        assert result["n_obs"] == 120

    def test_dataframe_input(self, synthetic_factor_data):
        """Accept DataFrame with 'ret' column, not just Series."""
        port, factors = synthetic_factor_data
        port_df = port.to_frame(name="ret")
        result = factor_alpha(
            port_df, factors, factors=["mkt_rf", "smb", "hml", "mom"],
        )
        assert result["n_obs"] == 120

    def test_newey_west_lags(self, synthetic_factor_data):
        """n_lags > 0 should still work (HAC SE on the intercept)."""
        port, factors = synthetic_factor_data
        result = factor_alpha(
            port, factors, factors=["mkt_rf", "smb", "hml", "mom"],
            n_lags=3,
        )
        assert np.isfinite(result["t_alpha_newey_west"])

    def test_empty_merge_raises(self):
        """Non-overlapping indices → RegressionError."""
        port = pd.Series([0.01, 0.02], index=pd.period_range("2020-01", periods=2, freq="M"))
        factors = pd.DataFrame(
            {"mkt_rf": [0.01], "rf": [0.001]},
            index=pd.period_range("2030-01", periods=1, freq="M"),
        )
        with pytest.raises(RegressionError, match="no overlapping"):
            factor_alpha(port, factors, factors=["mkt_rf"])

    def test_missing_factor_raises(self, synthetic_factor_data):
        port, factors = synthetic_factor_data
        with pytest.raises(RegressionError, match="factors not in"):
            factor_alpha(port, factors, factors=["nonexistent_factor"])

    def test_missing_rf_raises(self, synthetic_factor_data):
        port, factors = synthetic_factor_data
        factors_no_rf = factors.drop(columns=["rf"])
        with pytest.raises(RegressionError, match="risk-free"):
            factor_alpha(port, factors_no_rf, factors=["mkt_rf"])

    def test_three_factor_model(self, synthetic_factor_data):
        """Works with 3-factor (FF) as well as 4-factor (Carhart)."""
        port, factors = synthetic_factor_data
        result = factor_alpha(
            port, factors, factors=["mkt_rf", "smb", "hml"],
        )
        assert result["n_obs"] == 120
        assert len(result["betas"]) == 3


# ── summarize_factor_alpha ────────────────────────────────────


class TestSummarizeFactorAlpha:
    def test_returns_non_empty_string(self):
        rng = np.random.default_rng(0)
        n = 60
        months = pd.period_range("2015-01", periods=n, freq="M")
        ret = pd.Series(rng.normal(0.01, 0.05, n), index=months)
        factors = pd.DataFrame({
            "mkt_rf": rng.normal(0.005, 0.04, n),
            "rf": rng.normal(0.001, 0.0005, n),
        }, index=months)
        result = factor_alpha(ret, factors, factors=["mkt_rf"])
        s = summarize_factor_alpha(result, model_name="Carhart 4-Factor")
        assert isinstance(s, str)
        assert "TIME-SERIES REGRESSION" in s
        assert "Alpha" in s
        assert "mkt_rf" in s

    def test_significance_stars(self):
        """Strong alpha should produce significance stars."""
        rng = np.random.default_rng(0)
        n = 120
        months = pd.period_range("2010-01", periods=n, freq="M")
        # Large alpha (2%/month) with low noise
        ret = pd.Series(0.02 + rng.normal(0, 0.005, n), index=months)
        factors = pd.DataFrame({
            "mkt_rf": rng.normal(0.005, 0.04, n),
            "rf": rng.normal(0.001, 0.0005, n),
        }, index=months)
        result = factor_alpha(ret, factors, factors=["mkt_rf"])
        s = summarize_factor_alpha(result)
        assert "***" in s