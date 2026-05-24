### Matched operator entry: second_moment
- match_score: 0.797
- matched_from: logic_pipeline[7]:step8
- threshold: 0.650

## operator: second_moment
description: Compute a return cross-product matrix used in portfolio optimization, quadratic utility, or base-portfolio evaluation. The matrix may be an uncentered second moment such as `R.T @ R / T`, or a centered covariance matrix such as `(R - mean).T @ (R - mean) / T`.

pitfalls:
- Identify whether the source uses raw returns or demeaned returns.
- If source uses `R.T @ R / T`, keep uncentered second moment.
- If source uses `(R - mean)`, keep centered covariance.
- Preserve the source denominator: `T`, `T-1`, or another value.
- For LOO/base-portfolio moments, copy the estimator exactly because it feeds the optimizer.

---

### Matched operator entry: loo_closed_form
- match_score: 0.794
- matched_from: logic_pipeline[6]:step7
- threshold: 0.650

## operator: loo_closed_form
description: Use leave-one-out, cross-validation, jackknife, or Sherman-Morrison/Woodbury closed-form updates for portfolio construction, prediction, or performance estimation.

pitfalls:
- Keep train/test timing exact: leave-one-out outputs must not use the held-out target in the fitted quantity for that observation.
- Preserve closed-form denominators, eigenvalue transforms, and matrix dimensions exactly.
- Do not replace an analytic LOO formula with a full refit loop unless equivalent and documented.
- State whether the output is per-observation returns, model scores, base portfolio weights, or final `portfolio_weights`.
- If LOO estimates feed a later optimizer, keep them as intermediate logic outputs until the final allocation step.

---

### Matched operator entry: ensemble_weight_optimization
- match_score: 0.790
- matched_from: logic_pipeline[8]:step9
- threshold: 0.650

## operator: ensemble_weight_optimization
description: Optimize convex or constrained ensemble weights across base portfolios, predictors, model variants, or strategy sleeves. Common forms maximize expected utility, Sharpe ratio, or minimize variance with constraints such as nonnegative weights and sum-to-one normalization.

pitfalls:
- Distinguish ensemble weights over strategies/models from final tradable asset weights.
- Preserve all constraints from the paper, including nonnegativity, sum-to-one, leverage, turnover, and box constraints.
- If the optimizer returns implementation-ready asset weights, canonicalize the final output to `portfolio_weights`.
- If ensemble weights are intermediate, explicitly add the downstream mapping from ensemble weights to asset-level `portfolio_weights`.
- Do not replace an optimization with equal weighting unless the paper says so.

---

### Matched operator entry: shrinkage_normalization
- match_score: 0.737
- matched_from: indicators[15]:upsa_portfolio_weights_normalized
- threshold: 0.650

## operator: shrinkage_normalization
description: Apply shrinkage, ridge stabilization, regularization, diagonal loading, or normalization to covariance/second-moment matrices, signals, scores, or portfolio weights.

pitfalls:
- Preserve the shrinkage target exactly: identity, diagonal covariance, grand mean, market factor, or paper-specific target.
- Preserve the shrinkage intensity, ridge coefficient, or normalization denominator exactly.
- Do not convert score normalization into portfolio exposure sizing unless the paper does that explicitly.
- Separate statistical normalization used for estimates from live order sizing or evaluation volatility scaling.
- If the paper reports annualized or target-volatility metrics, do not apply those scalars to live `order_weights` unless stated.