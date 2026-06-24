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
        Dict with keys ``params`` (pd.Series), ``rsquared``, ``nobs``.
        Raises ``RegressionError`` if fit fails or insufficient observations.
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
      3. Standardize each independent variable to z-score within each
         time period — so coefficients are comparable across periods.
      4. Per time period, fit cross-sectional OLS of
         ``dependent_var ~ const + independent_vars``.
      5. Time-series average the coefficients.
      6. Newey-West HAC standard errors (default 2 lags) on the
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

    # 2 + 3. Winsorize then standardize within each time period.
    # We use `transform` instead of `apply` because apply drops the group
    # key column from the result, which breaks subsequent groupbys.
    def _winsorize_col(s: pd.Series) -> pd.Series:
        lo, hi = s.quantile([winsorize_pct, 1 - winsorize_pct])
        return s.clip(lower=lo, upper=hi)

    def _standardize_col(s: pd.Series) -> pd.Series:
        std = s.std()
        if std > 0:
            return (s - s.mean()) / std
        # Zero-variance regressor within this period — keep at 0 so the
        # OLS doesn't blow up. The corresponding coefficient will be
        # NaN or zero and gets filtered below.
        return pd.Series(0.0, index=s.index)

    winsorized = clean_df.copy()
    for var in independent_vars:
        winsorized[var] = (
            clean_df.groupby(time_col)[var].transform(_winsorize_col)
        )

    standardized = winsorized.copy()
    for var in independent_vars:
        standardized[var] = (
            winsorized.groupby(time_col)[var].transform(_standardize_col)
        )

    # 4. Per-period OLS (parallelized)
    grouped = list(standardized.groupby(time_col))

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


__all__ = ["run_ols", "fama_macbeth", "summarize_fama_macbeth",
           "FamaMacBethResult", "RegressionError"]