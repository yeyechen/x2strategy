"""Fama-MacBeth regressions — ported from RA-2025-summer/utils/regressions.py.

This is the primitive that makes cross-sectional controls (size, BM,
momentum) reproducible across runs. Every cross-sectional regression
paper needs this — the MAX paper's headline alpha is "the coefficient
on MAX in a monthly cross-section of future returns on MAX, controls,
and a constant, time-series averaged with Newey-West t-stats".

Adaptations:
- Type hints throughout
- Time column name is parameterized (default ``"month"``)
- Winsorize percentile is parameterized (default 1% / 99%)
- ``n_jobs`` is parameterized (default -2, matches user's source)
- Removed monkey-patched ``coef_df._rsquared_values`` (those go in
  an explicit metadata dict returned alongside the coef DataFrame)

Key reference: Fama & MacBeth (1973), "Risk, Return, and Equilibrium".
Newey-West (1987) HAC standard errors with 2 lags per the user's source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


class RegressionError(Exception):
    """Raised when a regression cannot be computed."""
    pass


@dataclass
class FamaMacBethResult:
    """Result of :func:`fama_macbeth`.

    ``coefficients`` is a DataFrame indexed by time period with one column
    per independent variable. Time-series averages and Newey-West t-stats
    are in ``summary``.

    Attributes:
        coefficients: time-series of cross-sectional OLS coefficients.
            One row per period, one column per regressor.
        summary: dict with keys ``mean``, ``std_error``, ``t_stat``,
            ``p_value``, ``n_periods``, ``n_valid_periods``, ``avg_rsquared``,
            ``total_nobs``.
        winsorize_pct: percentile used for winsorization (e.g. 0.01).
        time_col: name of the time column used to group periods.
    """

    coefficients: pd.DataFrame
    summary: Dict[str, object]
    winsorize_pct: float
    time_col: str


# Local helper — OLS is small enough to inline; we don't need a
# public utility since callers will always go through fama_macbeth().
def _run_ols(reg_data: pd.DataFrame, dependent_var: str, independent_vars: List[str],
             min_obs: int = 5) -> Optional[Dict[str, object]]:
    """Single OLS with intercept. Returns dict or None if too few obs."""
    try:
        import statsmodels.api as sm
    except ImportError as e:
        raise RegressionError(
            "statsmodels is required for regressions — "
            "install with `uv pip install statsmodels`"
        ) from e

    if len(reg_data) < len(independent_vars) + min_obs:
        return None

    y = reg_data[dependent_var]
    X = sm.add_constant(reg_data[independent_vars])
    model = sm.OLS(y, X).fit()
    return {
        "params": model.params,
        "rsquared": model.rsquared,
        "nobs": model.nobs,
    }


def run_ols(
    df: pd.DataFrame,
    dependent_var: str,
    independent_vars: List[str],
    min_obs: int = 5,
) -> Dict[str, object]:
    """Convenience wrapper around a single OLS.

    Args:
        df: input DataFrame.
        dependent_var: dependent variable column name.
        independent_vars: list of independent variable column names.
        min_obs: minimum number of observations to fit (default 5).

    Returns:
        Dict with the following keys (keys are LITERALLY these names,
        not e.g. "coef" or "coefficients"):

            - ``"params"``   (pd.Series, indexed by variable name including
              ``"const"``) — the OLS coefficients
            - ``"rsquared"`` (float) — R² of the fit
            - ``"nobs"``     (int) — number of observations used

        To access a coefficient: ``result["params"]["const"]`` or
        ``result["params"]["MAX"]`` (NOT ``result["coef"]``).

        If you need bse / pvalues / tvalues, run :func:`statsmodels.api.OLS`
        directly — :func:`run_ols` returns only what most agents need.

    Raises:
        RegressionError: if fit fails or insufficient observations.
    """
    result = _run_ols(df, dependent_var, independent_vars, min_obs=min_obs)
    if result is None:
        raise RegressionError(
            f"run_ols: insufficient observations "
            f"(have {len(df)}, need {len(independent_vars) + min_obs})"
        )
    return result


def fama_macbeth(
    df: pd.DataFrame,
    dependent_var: Optional[str] = None,
    independent_vars: Optional[List[str]] = None,
    time_col: str = "month",
    winsorize_pct: float = 0.01,
    n_lags: int = 2,
    n_jobs: int = -2,
    min_obs: int = 5,
    *,
    y_col: Optional[str] = None,
    x_cols: Optional[List[str]] = None,
) -> FamaMacBethResult:
    """Run the Fama-MacBeth (1973) two-pass procedure with Newey-West t-stats.

    Pipeline:
      1. Drop inf / NaN rows.
      2. Winsorize each independent variable to (pct, 1-pct) within each
         time period — controls for outliers.
      3. Per time period, fit cross-sectional OLS of
         ``dependent_var ~ const + independent_vars`` on RAW (unstandardized)
         variables. Coefficients are directly comparable to paper-reported
         raw coefficients — do NOT z-score.
      4. Time-series average the coefficients.
      5. Newey-West HAC standard errors (default 2 lags) on the
         coefficient time series.

    Args:
        df: input DataFrame. Must contain the dependent variable, the
            independent variables, and ``time_col``.
        dependent_var: column name of the dependent variable
            (e.g. ``"ret"``). Use this OR ``y_col``.
        independent_vars: list of column names for the regressors
            (e.g. ``["MAX", "log_mcap", "log_bm", "ret_11_2", "ret_1"]``).
            Use this OR ``x_cols``.
        y_col: DEPRECATED sklearn-style alias for ``dependent_var``.
            If both are given, ``dependent_var`` wins. Emits a
            :class:`DeprecationWarning`.
        x_cols: DEPRECATED sklearn-style alias for
            ``independent_vars``. If both are given,
            ``independent_vars`` wins. Emits a
            :class:`DeprecationWarning`.
        time_col: name of the time column. Default ``"month"``.
        winsorize_pct: percentile for winsorization. Default 0.01
            (clip to 1st and 99th percentile within each period).
        n_lags: Newey-West HAC lags. Default 2 (per user's source).
        n_jobs: parallel jobs for the per-period OLS. Default -2
            (all but one core). Set to 1 to disable parallelism.
        min_obs: minimum observations per period to fit. Default 5.

    Returns:
        :class:`FamaMacBethResult` with the time-series of coefficients
        and the summary dict.

    Raises:
        RegressionError: if statsmodels is not installed, if neither
            ``dependent_var`` nor ``y_col`` is given, or if no period
            has enough observations.
    """
    # Resolve dependent_var / y_col
    if dependent_var is None and y_col is None:
        raise RegressionError(
            "fama_macbeth: must provide either dependent_var= or y_col="
        )
    if y_col is not None:
        import warnings
        warnings.warn(
            "fama_macbeth(y_col=...) is deprecated; use dependent_var= instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        if dependent_var is None:
            dependent_var = y_col

    # Resolve independent_vars / x_cols
    if independent_vars is None and x_cols is None:
        raise RegressionError(
            "fama_macbeth: must provide either independent_vars= or x_cols="
        )
    if x_cols is not None:
        import warnings
        warnings.warn(
            "fama_macbeth(x_cols=...) is deprecated; use independent_vars= instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        if independent_vars is None:
            independent_vars = list(x_cols)

    try:
        from joblib import Parallel, delayed
        from scipy import stats
        import statsmodels.api as sm
        from statsmodels.stats.sandwich_covariance import cov_hac
    except ImportError as e:
        raise RegressionError(
            f"fama_macbeth requires statsmodels, scipy, joblib — install with "
            f"`uv pip install statsmodels scipy joblib`. Got: {e}"
        ) from e

    # 1. Clean
    all_vars = [dependent_var] + list(independent_vars) + [time_col]
    clean_df = df[all_vars].copy().replace([np.inf, -np.inf], np.nan).dropna()

    if clean_df.empty:
        raise RegressionError("fama_macbeth: no rows after dropping inf/NaN")

    # 2. Winsorize independent variables within each time period.
    # We use `transform` instead of `apply` because apply drops the group
    # key column from the result, which breaks subsequent groupbys.
    def _winsorize_col(s: pd.Series) -> pd.Series:
        lo, hi = s.quantile([winsorize_pct, 1 - winsorize_pct])
        return s.clip(lower=lo, upper=hi)

    reg_df = clean_df.copy()
    for var in independent_vars:
        reg_df[var] = (
            clean_df.groupby(time_col)[var].transform(_winsorize_col)
        )

    # 3. Per-period OLS on RAW (unstandardized) variables (parallelized)
    grouped = list(reg_df.groupby(time_col))

    def _fit_one(time_val: object, group: pd.DataFrame):
        return time_val, _run_ols(
            group, dependent_var, independent_vars, min_obs=min_obs
        )

    raw = Parallel(n_jobs=n_jobs)(
        delayed(_fit_one)(t, g) for t, g in grouped
    )

    # Filter periods that didn't fit
    valid = [(t, r) for t, r in raw if r is not None]

    if not valid:
        raise RegressionError(
            "fama_macbeth: no time period had enough observations "
            f"(need {len(independent_vars) + min_obs} per period)"
        )

    periods, results = zip(*valid)
    coef_df = pd.DataFrame([r["params"] for r in results])
    coef_df.index = pd.Index(periods, name=time_col)
    rsquared_values = [r["rsquared"] for r in results]
    nobs_values = [r["nobs"] for r in results]

    # 5 + 6. Time-series average + Newey-West HAC SE
    valid_coef = coef_df.dropna()
    if valid_coef.empty:
        raise RegressionError("fama_macbeth: all periods returned NaN coefficients")

    mean_coefs = valid_coef.mean()
    n_periods_valid = len(valid_coef)

    # Newey-West HAC needs at least 2 valid periods (1 period gives
    # n_obs - k_params = 0 → division by zero in cov_hac). Fall back to
    # plain OLS std errors when only one period survives.
    nw_se: Dict[str, float] = {}
    use_hac = n_periods_valid >= 2
    if not use_hac:
        # Single-period case: just report the coefficient as a scalar,
        # no time-series SE. The caller should treat this as
        # "descriptive, not inferential".
        for var in valid_coef.columns:
            nw_se[var] = 0.0  # placeholder; t-stats/p-values will be NaN
    else:
        for var in valid_coef.columns:
            y = valid_coef[var].values
            X = np.ones((n_periods_valid, 1))
            model = sm.OLS(y, X).fit()
            cov = cov_hac(model, nlags=n_lags)
            nw_se[var] = float(np.sqrt(cov[0, 0]))

    se_series = pd.Series(nw_se)
    t_stats = mean_coefs / se_series.replace(0, np.nan)
    # Two-sided p-value from Student-t with (n-1) dof. NaN if single-period.
    if n_periods_valid >= 2:
        p_values = pd.Series(
            2 * (1 - stats.t.cdf(np.abs(t_stats), df=n_periods_valid - 1)),
            index=t_stats.index,
        )
    else:
        p_values = pd.Series(np.nan, index=t_stats.index)

    summary: Dict[str, object] = {
        "mean": mean_coefs,
        "std_error": se_series,
        "t_stat": t_stats,
        "p_value": p_values,
        "n_periods": len(grouped),
        "n_valid_periods": n_periods_valid,
        "avg_rsquared": float(np.mean(rsquared_values)),
        "total_nobs": int(np.sum(nobs_values)),
    }

    return FamaMacBethResult(
        coefficients=coef_df,
        summary=summary,
        winsorize_pct=winsorize_pct,
        time_col=time_col,
    )


def summarize_fama_macbeth(result: FamaMacBethResult) -> str:
    """Format a :class:`FamaMacBethResult` as a human-readable table.

    Mirrors the user's ``analyze_fama_macbeth_results`` printer.
    Returns a string instead of printing, so the agent can choose where
    it goes (stdout, ``results/diagnosis.md``, etc.).

    Args:
        result: a :class:`FamaMacBethResult`.

    Returns:
        Multi-line string with the coefficient table.
    """
    summary = result.summary
    mean = summary["mean"]
    se = summary["std_error"]
    t = summary["t_stat"]
    p = summary["p_value"]

    lines = []
    sep = "=" * 80
    lines.append(sep)
    lines.append("FAMA-MACBETH REGRESSION RESULTS")
    lines.append(sep)
    lines.append(
        f"Number of time periods: {summary['n_valid_periods']}/"
        f"{summary['n_periods']}"
    )
    lines.append(f"Average R-squared: {summary['avg_rsquared']:.4f}")
    lines.append(f"Total # Obs:       {summary['total_nobs']}")
    lines.append("-" * 80)
    lines.append(f"{'Variable':<35} {'Coef (t-stat)':<25} {'p-value':<15}")
    lines.append("-" * 80)

    for var in mean.index:
        coef_str = f"{mean[var]:.6f} ({t[var]:.3f})"
        pval = p[var]
        if pval < 0.001:
            sig = "***"
        elif pval < 0.01:
            sig = "**"
        elif pval < 0.05:
            sig = "*"
        else:
            sig = ""
        lines.append(f"{var:<35} {coef_str:<25} {pval:.6f}{sig}")

    lines.append("-" * 80)
    lines.append("Significance levels: *** p<0.001, ** p<0.01, * p<0.05")
    lines.append(sep)
    return "\n".join(lines)


def factor_alpha(
    portfolio_returns: pd.Series | pd.DataFrame,
    factor_returns: pd.DataFrame,
    factors: list[str],
    rf_col: str = "rf",
    ret_col: str = "ret",
    n_lags: int = 0,
    freq: str = "M",
) -> dict[str, object]:
    """Time-series regression of portfolio excess returns on factor returns.

    This is the **time-series complement** to :func:`fama_macbeth`:
    ``fama_macbeth`` runs cross-sectional regressions per period and
    averages the coefficients; ``factor_alpha`` runs a single
    time-series regression of the portfolio's excess returns on the
    factor returns and reports the intercept (alpha) + factor loadings.

    Used for any paper that reports a factor-model alpha (Carhart
    4-factor, Fama-French 3-factor, 5-factor) on a long-short portfolio.

    Args:
        portfolio_returns: Portfolio return series. If a DataFrame, must
            contain ``ret_col``; the index (or a ``date``/``month``
            column) is used to align with ``factor_returns``. If a
            Series, its index is used directly.
        factor_returns: Factor returns DataFrame. Must contain all names
            in ``factors`` plus ``rf_col``. Index must be alignable with
            ``portfolio_returns`` (both PeriodIndex or both DatetimeIndex).
        factors: List of factor column names in ``factor_returns``
            (e.g. ``["mkt_rf", "smb", "hml", "mom"]`` for Carhart 4-factor).
        rf_col: Risk-free rate column name in ``factor_returns``.
        ret_col: Portfolio return column name if ``portfolio_returns``
            is a DataFrame.
        n_lags: Newey-West HAC lags for the alpha t-stat. Default 0
            (= iid t-stat, appropriate for non-overlapping monthly
            returns). Set to ``H-1`` for H-month overlapping cohorts.
        freq: Return frequency for annualization (``"M"`` -> x12,
            ``"D"`` -> x252, ``"Q"`` -> x4).

    Returns:
        Dict with keys (LITERALLY these names):

            - ``"alpha_monthly"`` (float) -- regression intercept
              (per-period, not annualized)
            - ``"alpha_annualized_pct"`` (float) -- intercept x
              annualization factor x 100
            - ``"t_alpha_newey_west"`` (float) -- HAC t-stat on the
              intercept
            - ``"p_alpha"`` (float) -- two-sided p-value
            - ``"betas"`` (pd.Series) -- factor loadings, indexed by
              factor name
            - ``"r_squared"`` (float) -- regression R-squared
            - ``"n_obs"`` (int) -- number of observations used

    Raises:
        RegressionError: if statsmodels is not installed, if the merged
            data is empty, or if there are insufficient observations.
    """
    try:
        import statsmodels.api as sm
        from statsmodels.stats.sandwich_covariance import cov_hac
    except ImportError as e:
        raise RegressionError(
            "factor_alpha requires statsmodels -- "
            "install with `uv pip install statsmodels`"
        ) from e

    # 1. Extract portfolio return as a Series
    if isinstance(portfolio_returns, pd.DataFrame):
        if ret_col not in portfolio_returns.columns:
            raise RegressionError(
                f"factor_alpha: '{ret_col}' not in portfolio_returns columns "
                f"{list(portfolio_returns.columns)}"
            )
        port_ret = portfolio_returns[ret_col].copy()
    else:
        port_ret = portfolio_returns.copy()

    # 2. Align portfolio returns with factor returns
    if not isinstance(port_ret.index, type(factor_returns.index)):
        try:
            if not isinstance(port_ret.index, pd.PeriodIndex):
                port_ret.index = pd.PeriodIndex(port_ret.index, freq=freq)
            if not isinstance(factor_returns.index, pd.PeriodIndex):
                factor_returns = factor_returns.copy()
                factor_returns.index = pd.PeriodIndex(
                    factor_returns.index, freq=freq
                )
        except Exception as e:
            raise RegressionError(
                f"factor_alpha: cannot align portfolio and factor indices "
                f"({type(port_ret.index).__name__} vs "
                f"{type(factor_returns.index).__name__}): {e}"
            )

    merged = port_ret.to_frame(name="__ret").join(factor_returns, how="inner").dropna()

    if merged.empty:
        raise RegressionError(
            "factor_alpha: no overlapping observations after merging "
            "portfolio and factor returns"
        )

    missing_factors = [f for f in factors if f not in merged.columns]
    if missing_factors:
        raise RegressionError(
            f"factor_alpha: factors not in factor_returns: {missing_factors}"
        )
    if rf_col not in merged.columns:
        raise RegressionError(
            f"factor_alpha: risk-free column '{rf_col}' not in factor_returns"
        )

    # 3. OLS: excess return ~ const + factors
    y = merged["__ret"].astype(float) - merged[rf_col].astype(float)
    X = merged[factors].astype(float)
    X = sm.add_constant(X)
    model = sm.OLS(y, X).fit()

    alpha = float(model.params["const"])
    betas = model.params.drop("const")

    # 4. Newey-West HAC t-stat on the intercept
    n_obs = int(model.nobs)
    if n_lags > 0 and n_obs > 2:
        try:
            cov = cov_hac(model, nlags=n_lags)
            se_alpha = float(np.sqrt(cov[0, 0]))
        except Exception:
            se_alpha = float(model.bse["const"])
    else:
        se_alpha = float(model.bse["const"])

    t_alpha = alpha / se_alpha if se_alpha > 0 else float("nan")

    from scipy import stats as sp_stats
    p_alpha = float(
        2 * (1 - sp_stats.t.cdf(abs(t_alpha), df=n_obs - len(factors) - 1))
    )

    ann_factor = {"M": 12, "D": 252, "Q": 4, "W": 52, "A": 1}.get(freq, 12)
    alpha_annualized_pct = alpha * ann_factor * 100

    return {
        "alpha_monthly": alpha,
        "alpha_annualized_pct": alpha_annualized_pct,
        "t_alpha_newey_west": t_alpha,
        "p_alpha": p_alpha,
        "betas": betas,
        "r_squared": float(model.rsquared),
        "n_obs": n_obs,
    }


def summarize_factor_alpha(
    result: dict[str, object], model_name: str = "Factor"
) -> str:
    """Format a :func:`factor_alpha` result as a human-readable table.

    Args:
        result: dict returned by :func:`factor_alpha`.
        model_name: header label (e.g. ``"Carhart 4-Factor"``).

    Returns:
        Multi-line string with the alpha, t-stat, betas, and R-squared.
    """
    lines = []
    sep = "=" * 60
    lines.append(sep)
    lines.append(f"{model_name.upper()} TIME-SERIES REGRESSION")
    lines.append(sep)
    lines.append(f"N observations: {result['n_obs']}")
    lines.append(f"R-squared:       {result['r_squared']:.4f}")
    lines.append("-" * 60)
    lines.append(f"Alpha (monthly):     {result['alpha_monthly']:.6f}")
    lines.append(f"Alpha (annualized):  {result['alpha_annualized_pct']:.4f}%")
    lines.append(f"t-stat (Newey-West): {result['t_alpha_newey_west']:.3f}")
    p = result["p_alpha"]
    if p < 0.001:
        sig = "***"
    elif p < 0.01:
        sig = "**"
    elif p < 0.05:
        sig = "*"
    else:
        sig = ""
    lines.append(f"p-value:             {p:.6f}{sig}")
    lines.append("-" * 60)
    lines.append(f"{'Factor':<20} {'Beta':<15}")
    lines.append("-" * 60)
    for factor, beta in result["betas"].items():
        lines.append(f"{factor:<20} {beta:.6f}")
    lines.append("-" * 60)
    lines.append("Significance: *** p<0.001, ** p<0.01, * p<0.05")
    lines.append(sep)
    return "\n".join(lines)


__all__ = ["run_ols", "fama_macbeth", "summarize_fama_macbeth",
           "factor_alpha", "summarize_factor_alpha",
           "FamaMacBethResult", "RegressionError"]