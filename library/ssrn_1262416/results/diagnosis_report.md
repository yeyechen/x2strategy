# Diagnosis Report — MAX Factor Strategy

**Strategy**: MAX Factor — Stocks as Lotteries (SSRN 1262416)
**Data period**: 2015-01-01 → 2024-12-31
**Universe**: 25 US large-cap stocks + SPY benchmark
**Rebalancing**: Monthly, at month-boundary open
**Position sizing**: Equal-weight within deciles, dollar-neutral
**Risk management**: None (matches paper design)

## Backtest Results (0% commission)

| Metric | Value |
|--------|-------|
| Final value | \$2,016.67 |
| Total return | -97.98% |
| Sharpe ratio | -0.5588 |
| Max drawdown | 98.31% |
| SQN | -2.2294 |
| Number of trades | 345 |
| Win rate | 46.96% |
| Profit factor | 0.64 |

## Paper Expected Performance (reference only)

| Metric | Paper Value | Notes |
|--------|-------------|-------|
| Value-weighted raw return (L−H MAX) | −1.03% / month | July 1962 – Dec 2005 |
| Four-factor alpha (L−H MAX) | −1.18% / month | Fama-French + momentum |
| Fama-MacBeth slope on MAX | −0.0637 (t=−6.16) | Cross-sectional regression |

## Deviation Analysis

- **Different universe**: Paper uses full CRSP (NYSE/AMEX/NASDAQ); this
  backtest uses 25 S&P 500 large-cap stocks — MAX spreads are narrower in
  large caps.
- **Different period**: Paper: 1962–2005; backtest: 2015–2024. The MAX
  premium may have decayed post-publication.
- **No short-constituent costs**: Paper reports academic portfolio returns
  without short-selling fees, borrow costs, or execution slippage.
- **Survivorship bias**: Current S&P 500 constituents have survived; CRSP
  includes delisted stocks.

## Generated files

- `strategy_1.py` — self-contained strategy code
- `spec.json` — strategy specification (with HITL resolutions)
- `results/metrics.json` — backtest metrics for all commission rates
- `results/portfolio_vs_assets.png` / `.csv` — portfolio vs B&H comparison
- `results/key_pred/` — MAX factor time-series plots
- `data/` — local cached price data