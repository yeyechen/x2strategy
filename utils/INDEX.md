# utils — Deterministic Primitives for Paper Replication

This package is the **agent's library**. Every public function here is
the canonical way to do that step in a paper replication. The
generated `strategy.py` should be mostly **spec-to-signal glue +
calls into these primitives** — not re-implementations.

The companion `tests/test_utils_canonical_usage.py` exercises every
function on a 2-stock × 3-date fixture and runs in ~7 seconds.
**Run it between edits to `strategy.py`** — if any call is wrong,
you'll know in seconds instead of after a 5-minute backtest:

```bash
uv run pytest tests/test_utils_canonical_usage.py -x
```

---

## 1. Pick the right primitive

> **Decision aid for the two `forward_returns` variants:**
> - `forward_returns(n_lags=1)` — **bin-and-evaluate** pattern. The return at month t+1 is paired with the signal at month t before binning. Used by **MAX, value, B/M** (1-month holding).
> - `forward_returns_h(n_lags=H)` — **overlapping-cohort** pattern. The column added is the per-month equivalent of the compounded H-month forward return. Used by **FIP, momentum** (H-month holding).
> Mixing them up gives look-ahead bias (using `forward_returns` for momentum) or wrong column shape (using `forward_returns_h` and binning on the wrong column).
> - `forward_returns_h(..., cumulative=True)` — same as above but outputs the H-month **cumulative** return `prod(1+ret) - 1` instead of the per-month geometric mean. Use when the paper reports H-month holding-period returns (e.g. FIP Table 2 "6-month return").

| I need to... | Use this | Returns |
|---|---|---|
| Bin stocks cross-sectionally by a signal | `assign_quantiles(panel, date_col, signal_col, n_bins=10)` | `pd.Series` of bin labels (1..n_bins) |
| Rank stocks cross-sectionally | `assign_ranks(panel, date_col, signal_col, ascending=False)` | `pd.Series` of ranks |
| Conditional (outer × inner) double sort | `double_sort(panel, date_col, outer_col, inner_col, n_bins=5)` | DataFrame with `outer_q` + `inner_q` columns |
| Compute per-decile EW + VW returns | `bin_returns(panel, date_col, bin_col, ret_col, mcap_col)` | DataFrame with columns `[date_col, bin_col, "EW", "VW"]` |
| Form a long-short portfolio | `long_short(bin_rets, date_col, weighting="VW", long_bin, short_bin)` | DataFrame `[date_col, "ret"]` |
| Shift the return forward to avoid look-ahead (1-period) | `forward_returns(panel, signal_col, date_col, ret_col, n_lags=1)` | DataFrame with `ret_col` REPLACED (not new column) |
| Geometric-mean H-month forward return (overlapping cohorts) | `forward_returns_h(panel, signal_col, date_col, ret_col, n_lags=6)` | DataFrame with `ret_fwd{H}` ADDED (preserves `ret_col`) |
| H-month cumulative forward return (FIP-style "6-month return") | `forward_returns_h(panel, signal_col, date_col, ret_col, n_lags=6, cumulative=True)` | DataFrame with `ret_fwd{H}` = `prod(1+ret) - 1` |
| Rolling cumulative return for momentum signal (PRET) | `rolling_cumret(panel, date_col, ret_col, window=11, skip=1)` | `pd.Series` — `prod(1+ret) - 1` over the formation window |
| Compute Sharpe / CAGR / max DD / vol | `performance_metrics(returns, freq="M")` (PREFERRED: pass `pd.Series`) | dict |
| HAC t-stat for autocorrelated returns (use n_lags=H-1 for overlapping cohorts) | `tstat_newey_west(returns, n_lags=5)` (PREFERRED: pass `pd.Series`) | dict `{mean_return, t_stat, n_obs}` |
| Plot cumulative P&L | `plot_cumulative_returns(df, index_col_name, ret_col_lst, save_to=...)` | PNG at `save_to` |
| Plot drawdown | `plot_drawdown(df, date_col, ret_col, save_to=...)` | PNG at `save_to` |
| Plot per-bin EW + VW bar chart | `plot_decile_spread(bin_rets, bin_col="bin", save_to=...)` | PNG at `save_to` |
| Run monthly cross-sectional regression | `fama_macbeth(panel, dependent_var, independent_vars, time_col)` | `FamaMacBethResult` (use `summarize_fama_macbeth` for text) |
| Single OLS | `run_ols(df, dependent_var, independent_vars)` | dict with keys `params`, `rsquared`, `nobs` |
| Load per-paper runtime config | `load_run_config(slug)` | dict |
| Filter CRSP stocks by share/exchange code (point-in-time) | `apply_universe_filter(daily, fetch_data_cached, shrcd_filter=[10,11], exchcd_filter=[1,2,3])` | filtered `pd.DataFrame` (same structure as `daily`) |
| Factor-model alpha (Carhart / FF3 / FF5) on a L/S portfolio | `factor_alpha(port_rets, factor_rets, factors=["mkt_rf","smb","hml","mom"])` | dict `{alpha_monthly, alpha_annualized_pct, t_alpha_newey_west, betas, r_squared, n_obs}` |

### Watch out

- **`bin_returns` output columns are LITERALLY `"EW"` and `"VW"`** —
  don't rename them. Pass `weighting="EW"` or `weighting="VW"` to
  `long_short`, not a column name.
- **`forward_returns` REPLACES** the `ret_col` column with the
  forward-shifted values. The output is the same shape as the input,
  minus the last `n_lags` rows per stock.
- **`forward_returns_h` ADDS a new column** (default `ret_fwd{H}`)
  instead of replacing `ret_col`. Use this for overlapping-cohort
  (Jegadeesh-Titman) momentum patterns where you need both the
  original `ret` AND the per-month-equivalent H-month forward return.
  Different from `forward_returns` by intent — don't mix them up.
- **`forward_returns_h(cumulative=True)` is the FIP-style fix.** Default
  outputs the per-month geometric mean: `exp(mean(log(1+ret))) - 1`.
  `cumulative=True` outputs the H-month cumulative: `prod(1+ret) - 1`.
  Compounding the per-month mean by H (the old FIP workaround
  `(1 + mean)**H - 1`) understates the magnitude via Jensen's
  inequality. Use `cumulative=True` whenever the paper reports
  H-month holding-period returns.
- **`tstat_newey_west` is for autocorrelated returns.** For independent
  monthly returns (MAX paper), `n_lags=0` ≈ iid t-stat. For
  H-month overlapping cohorts (FIP / momentum), set `n_lags=H-1`
  to correct for autocorrelation; otherwise the t-stat is inflated
  ~2-4×.
- **`forward_returns` auto-detects the stock-id** from
  `{permno, ticker, stock_id, id}`. There's no `per_stock_col=` kwarg.
- **`plot_cumulative_returns` uses different kwarg names** than the
  other plot functions: `index_col_name` (not `date_col`) and
  `ret_col_lst` (a LIST, not a single column name).
- **`run_ols` returns only `params`, `rsquared`, `nobs`** — no
  `bse` or `pvalues`. Use statsmodels directly if you need those.
- **`apply_universe_filter` takes the daily DataFrame + a callable.** Pass
  the strategy's own `fetch_data_cached` as the second arg. It uses
  `dsfhdr` (point-in-time header records with validity windows) to do
  a proper date-range merge — a stock is included for a given date
  ONLY if its header record on that date passes the share/exchange code
  filter. Do NOT call `fetch_data_cached` directly on `dsenames` or
  `dsfhdr` for universe filtering, and do NOT filter by a set of
  "ever-valid" permnos — that includes stocks that were REITs during
  your sample period but became common stocks later.
- **`factor_alpha` is the time-series complement to `fama_macbeth`.**
  `fama_macbeth` runs cross-sectional regressions per period and
  averages; `factor_alpha` runs one time-series regression of portfolio
  excess returns on factor returns and reports the intercept (alpha) +
  betas. Use `factor_alpha` when the paper reports a factor-model
  alpha on a portfolio (Carhart 4-factor, FF3, FF5); use `fama_macbeth`
  when the paper runs cross-sectional regressions of returns on signals.
- **`fama_macbeth` returns RAW coefficients** (not z-scored / standardized).
  The coefficients are directly comparable to paper-reported values.
  Access them via `result.summary["mean"]` and `result.summary["t_stat"]`
  — there is NO `.coefficients` or `.t_stats` attribute on the result.
- **`rolling_cumret(window=11, skip=1)` is the JT 12-2 primitive.** It
  computes `prod(1+ret[t-12..t-2]) - 1` (skip the most recent month).
  Don't write `shift(2) + rolling(11).apply((1+x).prod()-1)` by hand —
  the skip convention is easy to get wrong. Stock column auto-detected
  from {permno, ticker, stock_id, id}.
- **`factor_alpha` parameter names:** use `portfolio_returns=` (not
  `port_rets=`), `factor_returns=`, `factors=`, `rf_col=` (not `rf=`).
- **`long_short` returns `long - short`** by default. If the paper
  reports `high - low` (e.g., D10-D1) and you're long the low bin
  (long_bin=1, short_bin=10), pass `flip_sign=True`.
- **Don't hardcode the L/S bin numbers from the paper's prose.** The
  paper says "buy winners, sell losers" — you don't know whether
  that's `Q5-Q1` or `Q1-Q5` until you check the spec's
  `signals[i].long_leg` field. Read it from `run_config.yaml` and
  build the L/S with `top_q` / `bottom_q` from the long_leg, not
  from a guessed bin number. (The fip_v3 agent got this wrong by
  guessing the ID direction without checking the spec.)
- **Always compute both EW and VW unless the paper only reports one.**
  The spec's `weightings_reported` field (typically `["EW", "VW"]`)
  tells the strategy which weightings the paper actually reports.
  The single `weighting` field is the primary used for the headline
  hit-rate; the alternative is for robustness. Write `metrics.json`
  with the bare key for the primary and suffixed `_ew` / `_vw` keys
  for the alternative. Show both rows in `SUMMARY.md`. Do not pick
  just one weighting — most academic papers report both.
- **`plot_decile_spread` has NO `title=` parameter.** Don't pass one.

---

## 2. Order of operations (cross-sectional paper — the canonical pipeline)

```
fetch_data_cached → compute_signal (paper-specific) → forward_returns
→ assign_quantiles → bin_returns → long_short
→ performance_metrics → plot_*
                                 ↓
                            (in parallel:)
                            fama_macbeth → summarize_fama_macbeth
```

**`forward_returns` MUST run before `assign_quantiles`** — otherwise
you get look-ahead bias. The MAX paper bug we hit twice (iterations 2
and 3) was a missing `forward_returns` step.

---

## 3. Four worked patterns

### Pattern A: cross-sectional long-short (MAX, momentum, value, B/M)

This is the MAX paper pattern. ~30 lines of agent code.

```python
import pandas as pd
from utils import (
    assign_quantiles, bin_returns, long_short, forward_returns,
    performance_metrics, plot_cumulative_returns, plot_drawdown,
    plot_decile_spread, fama_macbeth, summarize_fama_macbeth,
    load_run_config,
)

# 1. Per-paper runtime settings (replications/<slug>/config/run_config.yaml)
cfg = load_run_config("max_paper")
N_BINS   = cfg["n_bins"]                       # 10
WEIGHTING = cfg["weighting"]                   # "VW"

# 2. Fetch + compute signal (paper-specific code — varies per paper)
daily = fetch_data_cached(cfg["data_sources"]["daily_returns"],
                          cfg["start_date"], cfg["end_date"])
monthly = compute_max_signal(daily)            # paper-specific
monthly["max_signal"] = monthly["max_daily_return"]

# 3. forward_returns (avoid look-ahead bias!)
monthly = forward_returns(
    monthly, signal_col="max_signal", date_col="month",
    ret_col="ret", n_lags=1,                   # default 1
)

# 4. Bin stocks cross-sectionally by the signal
monthly["bin"] = assign_quantiles(
    monthly, date_col="month", signal_col="max_signal", n_bins=N_BINS,
)

# 5. Per-bin returns (EW + VW)
bin_rets = bin_returns(
    monthly, date_col="month", bin_col="bin",
    ret_col="ret", mcap_col="mcap_lag1",
)

# 6. Long-short portfolio (NEW canonical signature)
ls = long_short(
    bin_rets, date_col="month", weighting=WEIGHTING,
    long_bin=1, short_bin=N_BINS,
)

# 7. Performance metrics + plots
metrics = performance_metrics(ls["ret"], freq="M")
plot_cumulative_returns(ls, index_col_name="month",
                        ret_col_lst=["ret"], save_to="results/pnl_curve.png")
plot_drawdown(ls, date_col="month", ret_col="ret", save_to="results/drawdown.png")
plot_decile_spread(bin_rets, save_to="results/decile_spread.png")

# 8. Fama-MacBeth cross-sectional regression
fm = fama_macbeth(
    monthly, dependent_var="ret",
    independent_vars=["max_signal", "log_mcap"], time_col="month",
)
print(summarize_fama_macbeth(fm))
```

### Pattern B: single-asset trend-following (200-day MA crossover)

Simpler — no binning, no long_short, just signal + position sizing +
metrics. ~15 lines.

```python
from utils import performance_metrics, plot_cumulative_returns

# 1. Fetch single ticker
prices = fetch_data_cached("crsp_202601.dsi", ["date", "vwretd"],
                           "2015-01-01", "2024-01-02")
prices["ma_200"] = prices["vwretd"].rolling(200).mean()
prices["signal"] = (prices["vwretd"] > prices["ma_200"]).astype(int)
prices["ret"] = prices["signal"].shift(1) * prices["vwretd"]

# 2. Metrics + plot
metrics = performance_metrics(prices["ret"], freq="D")
plot_cumulative_returns(prices, index_col_name="date",
                        ret_col_lst=["ret"], save_to="results/pnl_curve.png")
```

### Pattern C: cross-sectional with controls (Table VII-style FM)

The MAX paper's Table VII runs a Fama-MacBeth with MAX + 6 control
variables. Use this when the paper claims the anomaly survives
controlling for known factors.

```python
from utils import fama_macbeth, summarize_fama_macbeth

fm = fama_macbeth(
    monthly,
    dependent_var="ret",
    independent_vars=[
        "max_signal",   # the anomaly
        "log_mcap",     # size
        "log_bm",       # book-to-market
        "mom_11_2",     # momentum
        "rev_1",        # short-term reversal
        "beta",         # CAPM beta
        "illiq",        # Amihud illiquidity
    ],
    time_col="month",
    winsorize_pct=0.01,  # winsorize at 1st/99th percentile per period
    n_lags=2,             # Newey-West HAC lags
)
summary = summarize_fama_macbeth(fm)
# summary is a formatted text table. Write it to results/key_pred/fama_macbeth.txt.
```

---

## 4. If you write code that re-implements one of these primitives

**Don't.** Add it to the canonical-usage test instead. The agent's
debug-loop pattern is:

1. Agent writes re-implementation in `strategy.py`
2. Agent runs 5-minute backtest
3. Result is subtly wrong (different bin convention, different
   weighting convention, different look-ahead handling)
4. Agent doesn't notice the divergence

vs. the canonical-usage test pattern:

1. Agent copies a pattern from here
2. Agent runs `uv run pytest tests/test_utils_canonical_usage.py -x`
3. Test passes (or fails immediately with a clear error)
4. Agent moves on

If a paper genuinely needs behavior the primitives don't provide,
**add the primitive to `utils/` first**, then use it.

### Pattern D: overlapping-cohort momentum (FIP, Jegadeesh-Titman)

Use when the paper holds cohorts for H months and forms a new cohort
every month. Two flavors depending on how the paper reports returns:

**Flavor D1: H-month cumulative returns (e.g. FIP Table 2 reports
"6-month return").** Use `cumulative=True` so the per-stock column is
the actual 6-month cumulative return, not a per-month equivalent.

```python
from utils import (
    double_sort, forward_returns_h, rolling_cumret,
    performance_metrics, tstat_newey_west,
    plot_cumulative_returns,
)

# 1. PRET (Jegadeesh-Titman 12-2): 11-month formation, skip 1.
#    At month t: prod(1+ret[t-12..t-2]) - 1
monthly["pret"] = rolling_cumret(
    monthly, date_col="month", ret_col="ret",
    window=11, skip=1, min_periods=8,
)

# 2. H-month CUMULATIVE forward return (FIP-style). Per-stock column
#    is prod(1+ret[t+1..t+H]) - 1.
monthly = forward_returns_h(
    monthly, signal_col="pret", date_col="month",
    ret_col="ret", n_lags=6, cumulative=True,
)
# monthly now has 'ret_fwd6' = 6-month cumulative return per stock.
# The original 'ret' is preserved.

# 3. Conditional double sort on PRET (outer) x ID (inner).
monthly = double_sort(
    monthly, date_col="month", outer_col="pret",
    inner_col="id", n_bins=5,
)

# 4. Pick the L/S cells: PRET Q5 x ID Q1 (long) vs PRET Q1 x ID Q1 (short).
long = monthly[(monthly["pret_q"] == 5) & (monthly["id_q"] == 1)]
short = monthly[(monthly["pret_q"] == 1) & (monthly["id_q"] == 1)]

# 5. Build EW portfolios (per-cell mean of 6-month cumulative returns).
ls = (
    long.groupby("month")["ret_fwd6"].mean()
    - short.groupby("month")["ret_fwd6"].mean()
).rename("ret").reset_index()
# ls["ret"] is the 6-month cumulative spread per cohort month.
spread_6m_pct = ls["ret"].mean() * 100

# 6. NW-corrected t-stat. Convert to per-month equivalent first
#    (since the spread is 6-month cumulative, we inverse-compound),
#    then use n_lags=H-1=5 for the autocorrelation correction.
ls_monthly = (1 + ls["ret"]) ** (1.0 / 6) - 1
nw = tstat_newey_west(ls_monthly, n_lags=5)
print(f"FIP 6m spread: {spread_6m_pct:.2f}%, t_NW = {nw['t_stat']:.2f}")

# 6. P&L plot.
plot_cumulative_returns(
    ls, index_col_name="month", ret_col_lst=["ret"],
    save_to="results/fip_pnl.png",
)
```
