from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


TRAINING_WINDOW = 120
RIDGE_PENALTIES = np.power(10.0, np.arange(-10, 0, dtype=float))
USER_DIRECT_WEIGHT_SCALE = 0.19
REPORTING_TARGET_ANNUAL_VOL = 0.10
DEFAULT_INITIAL_PORTFOLIO_VALUE = 1.0
MONTHS_PER_YEAR = 12
NUMERICAL_TOL = 1e-12


def _prepare_wide_factors(jkp_factors_wide: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    if "date" not in jkp_factors_wide.columns:
        raise ValueError("jkp_factors_wide must contain a 'date' column")

    frame = jkp_factors_wide.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.sort_values("date").reset_index(drop=True)

    factor_ids = [column for column in frame.columns if column != "date"]
    numeric_values = frame[factor_ids].apply(pd.to_numeric, errors="coerce")
    if numeric_values.isna().any().any():
        raise ValueError("jkp_factors_wide contains missing or non-numeric factor returns")

    prepared = pd.concat([frame[["date"]], numeric_values], axis=1)
    return prepared, factor_ids


def _symmetrize(matrix: np.ndarray) -> np.ndarray:
    return 0.5 * (matrix + matrix.T)


def _eigendecompose(second_moment: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    eigenvalues, eigenvectors = np.linalg.eigh(_symmetrize(second_moment))
    order = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[order]
    eigenvectors = eigenvectors[:, order]
    eigenvalues[np.abs(eigenvalues) < NUMERICAL_TOL] = 0.0
    return eigenvalues, eigenvectors


def _ridge_weights_from_components(
    sample_mean: np.ndarray,
    eigenvalues: np.ndarray,
    eigenvectors: np.ndarray,
    ridge_penalty: float,
) -> np.ndarray:
    mean_pc = eigenvectors.T @ sample_mean
    precision_pc = mean_pc / (eigenvalues + ridge_penalty)
    return eigenvectors @ precision_pc


def _build_loo_returns(window_returns: np.ndarray) -> np.ndarray:
    sample_second_moment = (window_returns.T @ window_returns) / TRAINING_WINDOW
    sample_mean = window_returns.mean(axis=0)
    eigenvalues, eigenvectors = _eigendecompose(sample_second_moment)
    mean_pc = eigenvectors.T @ sample_mean
    factor_returns_pc = window_returns @ eigenvectors
    alpha = TRAINING_WINDOW / (TRAINING_WINDOW - 1)

    loo_returns = np.empty((TRAINING_WINDOW, len(RIDGE_PENALTIES)), dtype=float)
    for penalty_index, ridge_penalty in enumerate(RIDGE_PENALTIES):
        inverse_eigenvalues = 1.0 / (alpha * eigenvalues + ridge_penalty)
        a_t = factor_returns_pc @ (inverse_eigenvalues * mean_pc)
        b_t = np.sum((factor_returns_pc * factor_returns_pc) * inverse_eigenvalues, axis=1)
        denominator = (TRAINING_WINDOW - 1) - b_t
        denominator = np.where(
            np.abs(denominator) < NUMERICAL_TOL,
            np.sign(denominator) * NUMERICAL_TOL + (denominator == 0.0) * NUMERICAL_TOL,
            denominator,
        )
        loo_returns[:, penalty_index] = (TRAINING_WINDOW * a_t - b_t) / denominator

    return loo_returns


def _solve_nonnegative_direction(target: np.ndarray, second_moment: np.ndarray) -> np.ndarray | None:
    positive = np.flatnonzero(target > NUMERICAL_TOL)
    if positive.size == 0:
        return None

    active = positive.copy()
    candidate = None
    all_indices = np.arange(target.shape[0])

    for _ in range(target.shape[0] * 4):
        if active.size == 0:
            return None

        second_moment_active = second_moment[np.ix_(active, active)]
        target_active = target[active]
        inverse_active = np.linalg.pinv(second_moment_active)
        denominator = float(target_active @ inverse_active @ target_active)

        if denominator <= NUMERICAL_TOL:
            diagonal = np.clip(np.diag(second_moment_active), NUMERICAL_TOL, None)
            score = np.square(target_active) / diagonal
            chosen = active[int(np.argmax(score))]
            fallback = np.zeros_like(target)
            fallback[chosen] = 1.0 / max(target[chosen], NUMERICAL_TOL)
            return fallback

        candidate = np.zeros_like(target)
        candidate_active = (inverse_active @ target_active) / denominator
        candidate[active] = candidate_active

        if np.any(candidate_active <= NUMERICAL_TOL):
            active = active[candidate_active > NUMERICAL_TOL]
            continue

        lagrange_multiplier = 2.0 * float(candidate @ second_moment @ candidate)
        reduced_cost = 2.0 * (second_moment @ candidate) - lagrange_multiplier * target
        inactive = np.setdiff1d(all_indices, active, assume_unique=True)

        if inactive.size == 0 or np.all(reduced_cost[inactive] >= -1e-10):
            return candidate

        entering = inactive[int(np.argmin(reduced_cost[inactive]))]
        active = np.sort(np.concatenate([active, [entering]]))

    return candidate


def _solve_ensemble_weights(mu_loo: np.ndarray, sigma_loo: np.ndarray) -> np.ndarray:
    mu_loo = np.asarray(mu_loo, dtype=float)
    sigma_loo = _symmetrize(np.asarray(sigma_loo, dtype=float))
    sigma_loo += np.eye(mu_loo.shape[0]) * NUMERICAL_TOL

    weights = _solve_nonnegative_direction(mu_loo, sigma_loo)
    if weights is not None:
        return np.maximum(weights, 0.0)

    positive = np.flatnonzero(mu_loo > NUMERICAL_TOL)
    diagonal = np.clip(np.diag(sigma_loo), NUMERICAL_TOL, None)

    fallback = np.zeros_like(mu_loo)
    if positive.size > 0:
        chosen = positive[int(np.argmax(np.square(mu_loo[positive]) / diagonal[positive]))]
        fallback[chosen] = 1.0 / max(mu_loo[chosen], NUMERICAL_TOL)
        return fallback

    chosen = int(np.argmax(np.abs(mu_loo) / np.sqrt(diagonal)))
    fallback[chosen] = 1.0
    return fallback


def _paper_upsa_weights(
    sample_mean: np.ndarray,
    eigenvalues: np.ndarray,
    eigenvectors: np.ndarray,
    ensemble_weights: np.ndarray,
) -> np.ndarray:
    mean_pc = eigenvectors.T @ sample_mean
    precision_shrinkage = np.sum(
        ensemble_weights[:, None] / (eigenvalues[None, :] + RIDGE_PENALTIES[:, None]),
        axis=0,
    )
    raw_weights_pc = precision_shrinkage * mean_pc
    raw_weights = eigenvectors @ raw_weights_pc

    shrunk_second_moment_eigenvalues = np.sum(
        ensemble_weights[:, None]
        * eigenvalues[None, :]
        / (eigenvalues[None, :] + RIDGE_PENALTIES[:, None]),
        axis=0,
    )
    target_variance = float(np.sum(shrunk_second_moment_eigenvalues))
    current_variance = float(np.sum(np.square(raw_weights_pc) * shrunk_second_moment_eigenvalues))

    if target_variance <= NUMERICAL_TOL or current_variance <= NUMERICAL_TOL:
        return np.zeros_like(raw_weights)

    scale = np.sqrt(target_variance / current_variance)
    return raw_weights * scale


def _construct_strategy_returns_with_scale(
    upsa_weights_df: pd.DataFrame,
    jkp_factors_wide: pd.DataFrame,
    weight_scale: float,
) -> pd.DataFrame:
    factor_frame, default_factor_ids = _prepare_wide_factors(jkp_factors_wide)
    factor_panel = factor_frame.set_index("date")
    next_date_map = {
        pd.Timestamp(factor_frame.iloc[index]["date"]): pd.Timestamp(factor_frame.iloc[index + 1]["date"])
        for index in range(len(factor_frame) - 1)
    }

    weights_frame = upsa_weights_df.copy()
    weights_frame["date"] = pd.to_datetime(weights_frame["date"])
    weights_frame = weights_frame.sort_values("date").reset_index(drop=True)

    rows = []
    for row in weights_frame.itertuples(index=False):
        fit_date = pd.Timestamp(row.date)
        realized_date = next_date_map.get(fit_date)
        if realized_date is None:
            continue

        factor_ids = list(row.factor_ids) if hasattr(row, "factor_ids") else default_factor_ids
        factor_returns = factor_panel.loc[realized_date, factor_ids].to_numpy(dtype=float)
        scaled_weights = weight_scale * np.asarray(row.upsa_weights, dtype=float)
        strategy_ret = float(scaled_weights @ factor_returns)
        rows.append({"date": realized_date, "strategy_ret": strategy_ret})

    return pd.DataFrame(rows)


def _target_vol_report(strategy_ret_df: pd.DataFrame, target_annual_vol: float) -> pd.DataFrame:
    if strategy_ret_df.empty:
        return strategy_ret_df.copy()

    reporting = strategy_ret_df.copy()
    realized_monthly_vol = float(reporting["strategy_ret"].std(ddof=0))
    if realized_monthly_vol <= NUMERICAL_TOL:
        return reporting

    scale = target_annual_vol / (realized_monthly_vol * np.sqrt(MONTHS_PER_YEAR))
    reporting["strategy_ret"] = reporting["strategy_ret"] * scale
    return reporting


def _build_value_path(
    strategy_ret_df: pd.DataFrame,
    initial_value: float,
) -> pd.DataFrame:
    if initial_value <= 0.0:
        raise ValueError("initial_value must be strictly positive")

    if strategy_ret_df.empty:
        return pd.DataFrame(columns=["date", "portfolio_value"])

    value_path = strategy_ret_df.copy()
    value_path["date"] = pd.to_datetime(value_path["date"])
    returns = pd.to_numeric(value_path["strategy_ret"], errors="coerce")
    if returns.isna().any():
        raise ValueError("strategy_ret_df contains missing or non-numeric returns")

    value_path["portfolio_value"] = initial_value * (1.0 + returns).cumprod()
    return value_path[["date", "portfolio_value"]]


def compute_performance_metrics(
    strategy_ret_df: pd.DataFrame,
    initial_value: float = DEFAULT_INITIAL_PORTFOLIO_VALUE,
) -> pd.DataFrame:
    if initial_value <= 0.0:
        raise ValueError("initial_value must be strictly positive")

    if strategy_ret_df.empty:
        return pd.DataFrame(
            [
                {
                    "start_date": pd.NaT,
                    "end_date": pd.NaT,
                    "init_value": float(initial_value),
                    "final_value": float(initial_value),
                    "sharpe_ratio": np.nan,
                    "max_drawdown": np.nan,
                }
            ]
        )

    returns = pd.to_numeric(strategy_ret_df["strategy_ret"], errors="coerce")
    if returns.isna().any():
        raise ValueError("strategy_ret_df contains missing or non-numeric returns")

    returns = returns.astype(float)
    dates = pd.to_datetime(strategy_ret_df["date"])
    value_path = _build_value_path(strategy_ret_df, initial_value=initial_value)
    portfolio_values = value_path["portfolio_value"].to_numpy(dtype=float)
    running_peak = np.maximum.accumulate(portfolio_values)
    drawdowns = portfolio_values / running_peak - 1.0

    volatility = float(returns.std(ddof=1))
    sharpe_ratio = np.nan
    if volatility > NUMERICAL_TOL:
        sharpe_ratio = float((returns.mean() / volatility) * np.sqrt(MONTHS_PER_YEAR))

    return pd.DataFrame(
        [
            {
                "start_date": pd.Timestamp(dates.iloc[0]),
                "end_date": pd.Timestamp(dates.iloc[-1]),
                "init_value": float(initial_value),
                "final_value": float(portfolio_values[-1]),
                "sharpe_ratio": sharpe_ratio,
                "max_drawdown": float(-drawdowns.min()),
            }
        ]
    )


def compute_sample_second_moment(jkp_factors_wide: pd.DataFrame) -> pd.DataFrame:
    factor_frame, factor_ids = _prepare_wide_factors(jkp_factors_wide)
    returns_matrix = factor_frame[factor_ids].to_numpy(dtype=float)
    dates = factor_frame["date"].to_numpy()

    rows = []
    for end_index in range(TRAINING_WINDOW - 1, len(factor_frame)):
        window = returns_matrix[end_index - TRAINING_WINDOW + 1 : end_index + 1]
        rows.append(
            {
                "date": pd.Timestamp(dates[end_index]),
                "second_moment": (window.T @ window) / TRAINING_WINDOW,
                "sample_mean": window.mean(axis=0),
                "factor_ids": factor_ids.copy(),
            }
        )

    return pd.DataFrame(rows)


def compute_eigendecomposition(second_moment_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in second_moment_df.itertuples(index=False):
        eigenvalues, eigenvectors = _eigendecompose(np.asarray(row.second_moment, dtype=float))
        rows.append(
            {
                "date": pd.Timestamp(row.date),
                "eigenvalues": eigenvalues,
                "eigenvectors": eigenvectors,
            }
        )

    return pd.DataFrame(rows)


def compute_ridge_portfolios(second_moment_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in second_moment_df.itertuples(index=False):
        second_moment = np.asarray(row.second_moment, dtype=float)
        sample_mean = np.asarray(row.sample_mean, dtype=float)
        eigenvalues, eigenvectors = _eigendecompose(second_moment)

        for ridge_penalty in RIDGE_PENALTIES:
            rows.append(
                {
                    "date": pd.Timestamp(row.date),
                    "ridge_penalty": ridge_penalty,
                    "ridge_weights": _ridge_weights_from_components(
                        sample_mean=sample_mean,
                        eigenvalues=eigenvalues,
                        eigenvectors=eigenvectors,
                        ridge_penalty=ridge_penalty,
                    ),
                }
            )

    return pd.DataFrame(rows)


def compute_loo_moments(jkp_factors_wide: pd.DataFrame) -> pd.DataFrame:
    factor_frame, factor_ids = _prepare_wide_factors(jkp_factors_wide)
    returns_matrix = factor_frame[factor_ids].to_numpy(dtype=float)
    dates = factor_frame["date"].to_numpy()

    rows = []
    for end_index in range(TRAINING_WINDOW - 1, len(factor_frame)):
        window = returns_matrix[end_index - TRAINING_WINDOW + 1 : end_index + 1]
        loo_returns = _build_loo_returns(window)
        rows.append(
            {
                "date": pd.Timestamp(dates[end_index]),
                "mu_loo": loo_returns.mean(axis=0),
                "sigma_loo": (loo_returns.T @ loo_returns) / TRAINING_WINDOW,
            }
        )

    return pd.DataFrame(rows)


def compute_ensemble_weights(loo_moments_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in loo_moments_df.itertuples(index=False):
        mu_loo = np.asarray(row.mu_loo, dtype=float)
        sigma_loo = np.asarray(row.sigma_loo, dtype=float)
        rows.append(
            {
                "date": pd.Timestamp(row.date),
                "ensemble_weights": _solve_ensemble_weights(mu_loo, sigma_loo),
            }
        )

    return pd.DataFrame(rows)


def compute_upsa_portfolio_weights(
    second_moment_df: pd.DataFrame,
    eigendecomposition_df: pd.DataFrame,
    ensemble_weights_df: pd.DataFrame,
) -> pd.DataFrame:
    sample_moment_rows = {
        pd.Timestamp(row.date): row for row in second_moment_df.itertuples(index=False)
    }
    eigendecomposition_rows = {
        pd.Timestamp(row.date): row for row in eigendecomposition_df.itertuples(index=False)
    }
    ensemble_rows = {
        pd.Timestamp(row.date): row for row in ensemble_weights_df.itertuples(index=False)
    }

    shared_dates = sorted(
        set(sample_moment_rows).intersection(eigendecomposition_rows).intersection(ensemble_rows)
    )

    rows = []
    for date in shared_dates:
        sample_row = sample_moment_rows[date]
        eigen_row = eigendecomposition_rows[date]
        ensemble_row = ensemble_rows[date]
        rows.append(
            {
                "date": date,
                "upsa_weights": _paper_upsa_weights(
                    sample_mean=np.asarray(sample_row.sample_mean, dtype=float),
                    eigenvalues=np.asarray(eigen_row.eigenvalues, dtype=float),
                    eigenvectors=np.asarray(eigen_row.eigenvectors, dtype=float),
                    ensemble_weights=np.asarray(ensemble_row.ensemble_weights, dtype=float),
                ),
                "factor_ids": list(sample_row.factor_ids),
            }
        )

    return pd.DataFrame(rows)


def construct_strategy_returns(
    upsa_weights_df: pd.DataFrame,
    jkp_factors_wide: pd.DataFrame,
) -> pd.DataFrame:
    return _construct_strategy_returns_with_scale(
        upsa_weights_df=upsa_weights_df,
        jkp_factors_wide=jkp_factors_wide,
        weight_scale=USER_DIRECT_WEIGHT_SCALE,
    )


def run_pipeline(
    jkp_factors_wide: pd.DataFrame,
) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame]]:
    second_moment_df = compute_sample_second_moment(jkp_factors_wide)
    eigendecomposition_df = compute_eigendecomposition(second_moment_df)
    ridge_portfolios_df = compute_ridge_portfolios(second_moment_df)
    loo_moments_df = compute_loo_moments(jkp_factors_wide)
    ensemble_weights_df = compute_ensemble_weights(loo_moments_df)
    upsa_weights_df = compute_upsa_portfolio_weights(
        second_moment_df=second_moment_df,
        eigendecomposition_df=eigendecomposition_df,
        ensemble_weights_df=ensemble_weights_df,
    )

    strategy_ret_df = construct_strategy_returns(upsa_weights_df, jkp_factors_wide)
    paper_strategy_ret_df = _construct_strategy_returns_with_scale(
        upsa_weights_df=upsa_weights_df,
        jkp_factors_wide=jkp_factors_wide,
        weight_scale=1.0,
    )
    reporting_10pct_vol_df = _target_vol_report(
        paper_strategy_ret_df,
        target_annual_vol=REPORTING_TARGET_ANNUAL_VOL,
    )
    performance_metrics_df = compute_performance_metrics(strategy_ret_df)
    paper_performance_metrics_df = compute_performance_metrics(paper_strategy_ret_df)
    reporting_10pct_vol_performance_metrics_df = compute_performance_metrics(reporting_10pct_vol_df)
    live_upsa_weights_df = upsa_weights_df.copy()
    if not live_upsa_weights_df.empty:
        live_upsa_weights_df["upsa_weights"] = live_upsa_weights_df["upsa_weights"].apply(
            lambda weights: USER_DIRECT_WEIGHT_SCALE * np.asarray(weights, dtype=float)
        )

    metadata_df = pd.DataFrame(
        [
            {"parameter": "training_window", "value": TRAINING_WINDOW},
            {"parameter": "user_direct_weight_scale", "value": USER_DIRECT_WEIGHT_SCALE},
            {"parameter": "reporting_target_annual_vol", "value": REPORTING_TARGET_ANNUAL_VOL},
        ]
    )

    intermediates = {
        "second_moment_df": second_moment_df,
        "eigendecomposition_df": eigendecomposition_df,
        "ridge_portfolios_df": ridge_portfolios_df,
        "loo_moments_df": loo_moments_df,
        "ensemble_weights_df": ensemble_weights_df,
        "upsa_weights_df": upsa_weights_df,
        "live_upsa_weights_df": live_upsa_weights_df,
        "paper_strategy_ret_df": paper_strategy_ret_df,
        "reporting_10pct_vol_df": reporting_10pct_vol_df,
        "performance_metrics_df": performance_metrics_df,
        "paper_performance_metrics_df": paper_performance_metrics_df,
        "reporting_10pct_vol_performance_metrics_df": reporting_10pct_vol_performance_metrics_df,
        "metadata_df": metadata_df,
    }
    return strategy_ret_df, intermediates