# Interface Contract: Universal Portfolio Shrinkage (Kelly, Malamud, Pourmohammadi, Trojani, 2025) — plan_1

## Required Functions

All required functions must be importable as top-level module functions.
Parameter names should match the Input column names (or append `_df` suffix).

| # | Function | Key Output Columns |
|---|----------|--------------------|
| 1 | `compute_sample_second_moment(jkp_factors_wide)` | `second_moment, sample_mean` |
| 2 | `compute_eigendecomposition(second_moment_df)` | `eigenvalues, eigenvectors` |
| 3 | `compute_ridge_portfolios(second_moment_df)` | `ridge_penalty, ridge_weights` |
| 4 | `compute_loo_moments(jkp_factors_wide)` | `mu_loo, sigma_loo` |
| 5 | `compute_ensemble_weights(loo_moments_df)` | `ensemble_weights` |
| 6 | `compute_upsa_portfolio_weights(second_moment_df, eigendecomposition_df, ensemble_weights_df)` | `upsa_weights` |
| 7 | `construct_strategy_returns(upsa_weights_df, jkp_factors_wide)` | `strategy_ret` |
| 8 | `run_pipeline(jkp_factors_wide)` | returns `(strategy_ret_df, intermediates_dict)` |

### IO Shape

#### 1. `compute_sample_second_moment(jkp_factors_wide: pd.DataFrame) -> pd.DataFrame`
- **Input:** `jkp_factors_wide` with columns `[date, ...]` (one column per factor portfolio)
- **Output:** DataFrame with columns `[date, second_moment, sample_mean, factor_ids]`
- **Temporal anchor:** The values at date t are computed from the rolling training window ending at date t (inclusive); dates without a full window (i.e. the first T−1 rows) **must be omitted** from the output — do not emit rows with `None` / `NaN` placeholders. The first emitted row is therefore dated at the T-th observation (index T−1 in a 0-based wide panel).

#### 2. `compute_eigendecomposition(second_moment_df: pd.DataFrame) -> pd.DataFrame`
- **Input:** `second_moment_df` with columns `[date, second_moment, sample_mean, factor_ids]`
- **Output:** DataFrame with columns `[date, eigenvalues, eigenvectors]`

#### 3. `compute_ridge_portfolios(second_moment_df: pd.DataFrame) -> pd.DataFrame`
- **Input:** `second_moment_df` with columns `[date, second_moment, sample_mean, factor_ids]`
- **Output:** DataFrame with columns `[date, ridge_penalty, ridge_weights]` (one row per (date, ridge_penalty) pair)

#### 4. `compute_loo_moments(jkp_factors_wide: pd.DataFrame) -> pd.DataFrame`
- **Input:** `jkp_factors_wide` with columns `[date, ...]`
- **Output:** DataFrame with columns `[date, mu_loo, sigma_loo]`
- **Temporal anchor:** `mu_loo` and `sigma_loo` at date t are the leave-one-out estimates produced inside the training window ending at date t; no observations after t are used.

#### 5. `compute_ensemble_weights(loo_moments_df: pd.DataFrame) -> pd.DataFrame`
- **Input:** `loo_moments_df` with columns `[date, mu_loo, sigma_loo]`
- **Output:** DataFrame with columns `[date, ensemble_weights]`

#### 6. `compute_upsa_portfolio_weights(second_moment_df: pd.DataFrame, eigendecomposition_df: pd.DataFrame, ensemble_weights_df: pd.DataFrame) -> pd.DataFrame`
- **Input:** `second_moment_df` with columns `[date, second_moment, sample_mean, factor_ids]`; `eigendecomposition_df` with columns `[date, eigenvalues, eigenvectors]`; `ensemble_weights_df` with columns `[date, ensemble_weights]`
- **Output:** DataFrame with columns `[date, upsa_weights, factor_ids]`

#### 7. `construct_strategy_returns(upsa_weights_df: pd.DataFrame, jkp_factors_wide: pd.DataFrame) -> pd.DataFrame`
- **Input:** `upsa_weights_df` with columns `[date, upsa_weights, factor_ids]`; `jkp_factors_wide` with columns `[date, ...]`
- **Output:** DataFrame with columns `[date, strategy_ret]`
- **Temporal anchor:** `strategy_ret` at date t is the realized return of the portfolio whose weights were fixed at the previous rebalance date (end of month t−1).

#### 8. `run_pipeline(jkp_factors_wide: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame]]`
- **Input:** `jkp_factors_wide` with columns `[date, ...]` (raw factor panel)
- **Output:** a tuple `(strategy_ret_df, intermediates)` where
  - `strategy_ret_df` is a DataFrame with columns `[date, strategy_ret]` (same schema as function 7 output, covering the full in-sample + OOS span; the harness filters to OOS ≥ 1981-11 downstream)
  - `intermediates` is a `dict` (may be empty) that may carry any intermediate artifacts (e.g. ensemble weights, UPSA weights) for inspection; it is not consumed by any grader
- **Role:** Single end-to-end orchestrator that composes functions 1–7; required entry point for the E2E/diff-fuzz harness. Must be deterministic (same input → same output across repeated calls).

## Expert Refinements

### R1: Uncentered second moment, divided by T
- **source**: paper §2 / §3 (anchor B8)
- The sample second moment is an uncentered matrix and is normalized by T, not T−1; it is not the mean-centered sample covariance produced by `numpy.cov`.
- **candidate_property**: true

### R2: Rank-deficient second moment — use spectral / pseudo-inverse arithmetic
- **source**: §3; B9
- When the training window has T < N, the sample second moment is rank-deficient (K = min(N, T) non-zero eigenvalues). All downstream operations (ridge inversion, shrinkage, portfolio formation) must be computed via the eigendecomposition / pseudo-inverse, so that the K = min(N, T) dominant eigen-directions are preserved and zero-eigenvalue directions are handled consistently.
- **candidate_property**: true

### R3: Ridge portfolios use the same rolling sample mean μ̄
- **source**: §2 (ridge estimator definition)
- Each ridge portfolio π_ridge(z) = (Σ̄ + z I)⁻¹ μ̄ uses the same in-window sample mean μ̄ that is paired with the same-window Σ̄; ridge regularization is added to Σ̄ only, never to μ̄.
- **candidate_property**: false

### R4: LOO is *within* the rolling training window
- **source**: §3 (anchor B11); §4.1
- Leave-one-out cross-validation is performed over the T training observations of the current rolling window (one fold per in-window month), producing a per-window μ̂_LOO ∈ ℝᴸ and Σ̂_LOO ∈ ℝᴸˣᴸ over the L ridge portfolios. LOO is not performed over the full 1971–2022 sample, and is not replaced by K-fold with K ≠ T.
- **Numerical detail (Lemma 7 denominator).** The closed-form LOO identity must be consistent with the T-1 refit LOO. With Σ̄ = F'F/T defined on T rows (R1), the leave-one-out inverse is `C(z)^{-1}` with eigenvalues `(α·λ_i + z)^{-1}` where **α = T/(T−1)**; the held-out prediction evaluates to `R_LOO[t, z] = (T·a_t − b_t) / ((T−1) − b_t)` with `a_t = F_t' C^{-1} μ̄`, `b_t = F_t' C^{-1} F_t`. A naive application of Lemma 7 without the α rescale agrees with T-1 direct LOO only asymptotically and drifts by O(1/T) in finite samples; graders compare to true T-1 refit.
- **candidate_property**: true

### R5: Ensemble Markowitz is solved in ridge space with a non-negativity constraint
- **source**: Definition 2, §3 (anchors B12, B13)
- The ensemble weights W* are obtained by solving max_{W ≥ 0} (W'μ̂_LOO)² / (W'Σ̂_LOO W) over the L ridge portfolios, i.e. L variables (not N variables in factor space). The non-negativity constraint is an inequality constraint on W, not an equality.
- **candidate_property**: true

### R6: Variance normalization — trace-preserving target (Ledoit–Wolf 2020, footnote 17)
- **source**: §4.1, footnote 17 (anchor B15); Ledoit and Wolf (2020)
- At each rebalance the final portfolio weights π are rescaled so that the **implied in-sample variance after shrinkage** equals the **trace of the shrunk second moment**:
  $$\pi' \, \Sigma_{\text{shrunk}} \, \pi \;=\; \mathrm{tr}(\Sigma_{\text{shrunk}}) \;=\; \sum_i f_{\text{UPSA}}(\lambda_i),$$
  where $\Sigma_{\text{shrunk}} = U \, \mathrm{diag}(f_{\text{UPSA}}(\lambda)) \, U^\top$ and the shrunk eigenvalues are $f_{\text{UPSA}}(\lambda_i) = \sum_l W_l \cdot \lambda_i / (\lambda_i + z_l)$ (with $W$ = ensemble weights from R5, $z_l$ = ridge grid). Concretely: rescale $\pi \leftarrow \pi \cdot \sqrt{\mathrm{tr}(\Sigma_{\text{shrunk}}) / (\pi' \Sigma_{\text{shrunk}} \pi)}$ each rebalance.
- The implied variance is taken under the **shrunk** second moment $\Sigma_{\text{shrunk}}$, **not** under the raw sample second moment $\bar\Sigma$. The target is the trace-preserving "Ledoit–Wolf 2020" target — **not** unit variance, **not** a fixed annualized volatility level, and **not** the statistical variance $\mathrm{Var}(\{\lambda_i\})$ of the eigenvalue spectrum.
- **candidate_property**: true

### R7: Long-short in factor space, no per-asset cap, no stop-loss
- **source**: §4.1 (anchor B16); spec `risk_management` / `notes`
- The final portfolio weights may take either sign across all factor portfolios and are not truncated, clipped, or subjected to a maximum position, gross-exposure cap, or drawdown-based rule. Non-negativity applies only to the ensemble weights W, never to the final π_UPSA.
- **candidate_property**: true

### R8: Monthly rebalance with a one-period lag between weights and realized returns
- **source**: §4.1 (anchors B5, A8, A9)
- UPSA weights computed at the end of month t are applied to the factor returns realized in month t+1; returns earned in month t must not be attributed to weights fit at the end of month t. The rolling window advances by one month between rebalances.
- **candidate_property**: true

### R9: OOS evaluation starts Nov 1981
- **source**: §4.1 (anchor B3); spec `notes.out_of_sample_period`
- The out-of-sample strategy return series begins at Nov 1981 (the first month for which a full T = 120 training window ending in Oct 1981 is available); months before Nov 1981 are treated as training-only and must not enter any downstream performance metric.
- **candidate_property**: true

## Difficulty Rating
Estimated T2 (Claude Code / Cursor) Type B pass rate: **55%** (target range 40-65%)
