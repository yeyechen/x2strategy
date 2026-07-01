# Paper Conventions — Standard Academic-Finance Defaults

This document is the **single source of truth** for decisions the agent
makes autonomously when the paper is silent. The agent reads this before
generating `strategy.py` and applies these defaults, emitting
`[CONVENTION-APPLIED]` log lines so the user can audit them in
`results/SUMMARY.md`.

**When to deviate:** if the paper explicitly states a different value
(e.g. "we exclude stocks priced below $10"), use the paper's value, not
the default. Document the deviation in `SUMMARY.md`.

---

## Universe selection

| Decision | Default | Rationale | CRSP implementation |
|----------|---------|-----------|---------------------|
| Share codes | `shrcd IN (10, 11)` | Ordinary common shares — excludes ADRs, REITs, closed-end funds, units, preferred shares. The standard filter in virtually every cross-sectional equity paper. | `dsfhdr.hshrcd` via `utils.apply_universe_filter()` |
| Exchange codes | `exchcd IN (1, 2, 3)` | NYSE (1), NYSE MKT/AMEX (2), NASDAQ (3). Excludes Arca (4) and Bats (5). Some papers restrict to NYSE-only for breakpoint calculation. | `dsfhdr.hexcd` via `utils.apply_universe_filter()` |
| Price filter | `$5` minimum | Penny stocks have bid-ask bounce, illiquidity, and microstructure effects that distort signal construction. Most papers that mention a price floor use $5 (e.g. Fama-French, Hou-Xue-Zhang). **Apply only if the paper's sample period is post-1962** (CRSP data quality before 1962 is lower; the $5 filter is less meaningful). If the paper is silent, apply the $5 filter and document it. | `dsf.prc >= 5.0` after `prc = abs(prc)` |
| Delisting returns | Adjust | CRSP delisting returns (`dsf.ret` on the delisting date may be missing or `-0.30` placeholder). The standard approach is to use `dsedelist.dlret` when available, falling back to `-0.30` for performance-driven delistings (codes 500+). If the paper says "after adjusting for delistings," this is mandatory. | Merge `dsf` with `dsedelist` on `permno` |
| Breakpoint universe | NYSE only | When forming size-based quantiles (deciles, quintiles), breakpoints are computed from NYSE stocks only (per Fama-French 1993). This prevents NASDAQ's many small firms from skewing the size distribution. **Applies only to size-based sorting** (market cap, size quintiles). For signal-based sorting (MAX, momentum), use all stocks in the universe. | Filter `exchcd = 1` for breakpoint computation |

## Portfolio construction

| Decision | Default | Rationale |
|----------|---------|-----------|
| Weighting | VW (value-weighted) | Standard for decile/quintile portfolios. EW is used only when the paper explicitly says "equal-weighted" or when the paper's tables show EW results. |
| Number of bins | 10 (deciles) | Standard for cross-sectional sorting. Some papers use 5 (quintiles) — use what the paper specifies. |
| Rebalancing frequency | Monthly | Standard for cross-sectional equity. Weekly/daily only if the paper specifies. |
| Holding period | 1 month | Default for non-overlapping strategies. For momentum (Jegadeesh-Titman), use the paper's J-month holding period with overlapping cohorts (`forward_returns_h`). |
| Signal timing | Month-end signal → next-month return | Signal computed at month-end t, paired with return at t+1. Use `utils.forward_returns(n_lags=1)` for 1-month, `utils.forward_returns_h(n_lags=H)` for H-month. |

## Risk adjustment

| Decision | Default | Rationale |
|----------|---------|-----------|
| Factor model | Carhart 4-factor (Mkt-RF, SMB, HML, MOM) | The 4-factor model is the standard for papers published 2010-2020. Use 3-factor (FF3) for pre-Carhart (1997) papers. Use 5-factor (FF5) if the paper explicitly uses it. |
| Factor table | `ff.four_factor_monthly` | The ClickHouse `ff` database. See `references/data/fama_french.md`. |
| Alpha computation | `utils.factor_alpha(port_ret, factor_ret, factors=[...])` | Time-series regression of excess portfolio returns on factor returns, with Newey-West HAC t-stat on the intercept. |
| FM regression | `utils.fama_macbeth(panel, dependent_var, independent_vars, time_col="month")` | Cross-sectional regression per period, averaged with NW t-stats. Use when the paper runs a cross-section of returns on signals. |

## Data sources

| Decision | Default | Rationale |
|----------|---------|-----------|
| CRSP vintage | `crsp_202601` (latest) | See `references/data/crsp.md`. Use `database_families` in the catalog to pick the latest. |
| Compustat vintage | `comp_202601` (latest) | Same logic. |
| FF vintage | `ff` (no vintage suffix) | FF tables are not versioned by snapshot. |
| Market index | `crsp_202601.dsi.vwretd` | CRSP value-weighted with dividends. Use `ewretd` for equal-weighted. |
| Risk-free rate | `ff.four_factor_monthly.rf` | From the FF table, not a separate source. |

---

## When to ask the user

The agent should **not** ask the user for any of the decisions above —
they are convention defaults. The agent applies them, documents them in
`results/SUMMARY.md`, and the user reviews after the run.

**Ask the user only for genuinely ambiguous decisions that the paper
does not resolve and that have no standard default:**

- Which strategy to extract from a multi-strategy paper
- Whether to use a non-standard data source the paper mentions but
  doesn't fully specify
- Whether the paper's methodology is unclear enough that two reasonable
  interpretations give materially different results

If the user is not reachable (background run), apply the most common
interpretation and document it with a `[HITL-AUTO-RESOLVED]` log line.
