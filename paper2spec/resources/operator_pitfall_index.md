# Operator Pitfall Index

This is an editable pitfall corpus for semantic retrieval during spec repair/audit.
Each `## operator:` entry has a short description for matching and concise
pitfalls that become mandatory checks for the matched spec component.

You can manually add new operator entries here when you discover a repeated
formula, timing, sizing, or implementation pitfall. Keep entries short and
specific so semantic similarity can retrieve the right pitfall without asking
the model to scan the full corpus by itself.

The repair workflow builds queries from draft `indicators`, `logic_pipeline`,
`expected_performance.metric_definitions[*].steps`, and
`execution_plan[*].position_sizing.steps` description-like fields. Only matched
operator entries should be applied, and only to the component path reported by
retrieval.

## Always-Available High-Frequency Pitfalls (no retrieval needed)

Apply these to **every** spec review, even when semantic retrieval is disabled,
returns nothing, or the matched-entry threshold is not met. They are the
highest-frequency "runs but wrong" causes and are cheap to check by hand. The
operator-specific entries below add depth; this list is the always-on floor.

- **Centered vs uncentered moments.** Confirm whether the source uses raw `R.T @ R / T` (uncentered second moment) or demeaned `(R-mean).T @ (R-mean)/T` (covariance), and preserve the exact denominator (`T` vs `T-1`). Picking the wrong one silently changes every downstream weight.
- **Estimate-at-t, apply-at-t+1 timing.** If weights/signals estimated at *t* are applied to returns at *t+1*, the estimation window must exclude the evaluated return. Advance by **one index step in the data array** (`iloc[i+1]`), never by `DateOffset`/calendar arithmetic. This is the most common look-ahead leak.
- **Warm-up / OOS exclusion.** Paper-style Sharpe / Calmar / hit-rate use the OOS return series only; training/warm-up periods must not enter the reported metrics.
- **Direct-weight pass-through.** Raw `portfolio_weights` may be negative and need not sum to 1 or to gross 1. Do not normalize, clip, or de-leverage unless the spec has non-null sizing constraints.
- **Ensemble weights ≠ asset weights.** Weights over strategies/models/predictors are intermediate; if they are not implementation-ready asset weights, the downstream mapping to asset-level `portfolio_weights` must be explicit.
- **Preserve shrinkage target and intensity.** Keep the exact shrinkage/ridge target (identity, diagonal, grand mean, market factor) and the exact intensity/denominator. Do not turn statistical normalization into live order sizing.
- **Near-zero denominator sign trap.** Never stabilize with `max(denom, eps)` / `np.maximum(denom, eps)` — it flips a legitimately negative denominator to `+eps` and reverses the position's sign. Mask with `abs(denom) > eps` and zero out invalid entries instead.
- **Broker Sharpe ≠ paper Sharpe.** `bt.analyzers.SharpeRatio` reflects cash/fill/margin effects; for replication, compute the paper metric from `strategy_ret[t] = weights[t-1] @ returns[t]`, and configure the analyzer by return frequency (monthly→factor 12, weekly→52, daily→252), not by rebalance frequency.
- **Zero costs unless stated.** Commission and slippage default to `0.0` when the paper does not specify them. Do not invent transaction costs.

When in doubt and no operator entry matches a high-risk formula, do not guess a
default — write a structured `needs_human_review` item (see
[extraction_quality.md](../../references/extraction_quality.md)).

## operator: second_moment

description: Compute a return cross-product matrix used in portfolio optimization, quadratic utility, or base-portfolio evaluation. The matrix may be an uncentered second moment such as `R.T @ R / T`, or a centered covariance matrix such as `(R - mean).T @ (R - mean) / T`.

pitfalls:
- Identify whether the source uses raw returns or demeaned returns.
- If source uses `R.T @ R / T`, keep uncentered second moment.
- If source uses `(R - mean)`, keep centered covariance.
- Preserve the source denominator: `T`, `T-1`, or another value.
- For LOO/base-portfolio moments, copy the estimator exactly because it feeds the optimizer.

## operator: ensemble_weight_optimization

description: Optimize convex or constrained ensemble weights across base portfolios, predictors, model variants, or strategy sleeves. Common forms maximize expected utility, Sharpe ratio, or minimize variance with constraints such as nonnegative weights and sum-to-one normalization.

pitfalls:
- Distinguish ensemble weights over strategies/models from final tradable asset weights.
- Preserve all constraints from the paper, including nonnegativity, sum-to-one, leverage, turnover, and box constraints.
- If the optimizer returns implementation-ready asset weights, canonicalize the final output to `portfolio_weights`.
- If ensemble weights are intermediate, explicitly add the downstream mapping from ensemble weights to asset-level `portfolio_weights`.
- Do not replace an optimization with equal weighting unless the paper says so.

## operator: shrinkage_normalization

description: Apply shrinkage, ridge stabilization, regularization, diagonal loading, or normalization to covariance/second-moment matrices, signals, scores, or portfolio weights.

pitfalls:
- Preserve the shrinkage target exactly: identity, diagonal covariance, grand mean, market factor, or paper-specific target.
- Preserve the shrinkage intensity, ridge coefficient, or normalization denominator exactly.
- Do not convert score normalization into portfolio exposure sizing unless the paper does that explicitly.
- Separate statistical normalization used for estimates from live order sizing or evaluation volatility scaling.
- If the paper reports annualized or target-volatility metrics, do not apply those scalars to live `order_weights` unless stated.

## operator: loo_closed_form

description: Use leave-one-out, cross-validation, jackknife, or Sherman-Morrison/Woodbury closed-form updates for portfolio construction, prediction, or performance estimation.

pitfalls:
- Keep train/test timing exact: leave-one-out outputs must not use the held-out target in the fitted quantity for that observation.
- Preserve closed-form denominators, eigenvalue transforms, and matrix dimensions exactly.
- Do not replace an analytic LOO formula with a full refit loop unless equivalent and documented.
- State whether the output is per-observation returns, model scores, base portfolio weights, or final `portfolio_weights`.
- If LOO estimates feed a later optimizer, keep them as intermediate logic outputs until the final allocation step.
