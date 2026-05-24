# Universal Portfolio Shrinkage Review And Diagnosis

## Scope

- Target paper: P10 Kelly, Malamud, Pourmohammadi, Trojani (2025, NBER)
- Selected implementation target: `plan_1` from `sample_instruction.md`
- Input data: `jkp_factors_wide.csv`, `jkp_factors_long.csv`
- Reference artifact: `upsa_weights.csv`

## Extraction Review

The extracted `spec.json` was directionally useful but mixed two different shrinkage objects:

- Portfolio-construction precision shrinkage in principal-component space:
  `sum_l W_l / (lambda_i + z_l)`
- Trace-preserving normalization target for the implied shrunk second moment:
  `sum_l W_l * lambda_i / (lambda_i + z_l)`

The implementation uses the first object for raw UPSA weights and the second object only for variance normalization, consistent with `sample_instruction.md`.

## HITL Decisions Applied

- Gross exposure / leverage cap: not added as a separate optimizer constraint.
- User execution override: after the paper-implied direct weights are computed, the live path scales them by `0.19`.
- Transaction costs / turnover constraints: not added.
- Reporting path: a separate ex-post `10%` annual-volatility return path is retained in intermediates.

## Outputs

- Code module: `/data/zqyuan/osskill/universal_portfolio_shrinkage.py`
- Main entry point: `run_pipeline(jkp_factors_wide)`
- Paper UPSA weights: `intermediates['upsa_weights_df']`
- Live scaled UPSA weights: `intermediates['live_upsa_weights_df']`
- Paper return path: `intermediates['paper_strategy_ret_df']`
- 10% annual-vol reporting path: `intermediates['reporting_10pct_vol_df']`
- Live-path performance metrics: `intermediates['performance_metrics_df']`
- Paper-path performance metrics: `intermediates['paper_performance_metrics_df']`
- 10% annual-vol reporting metrics: `intermediates['reporting_10pct_vol_performance_metrics_df']`
- Returned strategy path: `strategy_ret_df` from `run_pipeline`, which uses the user-confirmed `0.19` live scaling

## Validation Summary

Comparison against `upsa_weights.csv` on the shared fit-date span `1981-10-31` to `2022-11-30`:

- rows compared: `494`
- factor columns compared: `153`
- flat correlation: `0.9995703282910543`
- mean cross-sectional correlation by month: `0.999650953824981`
- mean absolute error: `0.001747177092355655`
- root mean squared error: `0.026464352366594567`

Additional checks:

- `run_pipeline` produces `494` realized monthly return observations from `1981-11-30` to `2022-12-31`
- the reporting path is scaled to `10%` annualized volatility by construction
- the extra `0.19` live-path scaling reduces monthly volatility proportionally relative to the raw paper path

## Performance Metrics

All metrics below are computed from the realized monthly return paths produced by `run_pipeline`. `sharpe_ratio` is annualized with `sqrt(12)`, `init_value` starts at `1.0`, and `max_drawdown` is reported as a positive fraction.

### Live Path (`strategy_ret_df`)

- start_date: `1981-11-30`
- end_date: `2022-12-31`
- init_value: `1.0`
- final_value: `1983.414763`
- sharpe_ratio: `1.918437`
- max_drawdown: `0.145931`

### Paper Path (`intermediates['paper_strategy_ret_df']`)

- start_date: `1981-11-30`
- end_date: `2022-12-31`
- init_value: `1.0`
- final_value: `1.662833e+15`
- sharpe_ratio: `1.918437`
- max_drawdown: `0.615857`

### 10% Annual-Vol Reporting Path (`intermediates['reporting_10pct_vol_df']`)

- start_date: `1981-11-30`
- end_date: `2022-12-31`
- init_value: `1.0`
- final_value: `2092.967529`
- sharpe_ratio: `1.918437`
- max_drawdown: `0.146950`

## Residual Gap

The implementation matches the supplied reference weights extremely closely overall, but not perfectly for every month. The largest residual discrepancies are concentrated in a small number of fit dates, which likely reflects numerical or convention differences in the upstream reference pipeline rather than a timing mismatch.