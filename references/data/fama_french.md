# Fama-French Factors

> **Status:** verified live in ClickHouse. Verified by direct queries
> against `100.77.34.92:9000` on 2026-06-23. Always cross-check
> before depending on a specific schema — FF tables can be re-ingested
> under different vintages.

## What this is

The Fama-French factor data published by Kenneth French's data
library. Used for risk-adjusted return measurement in cross-sectional
asset pricing tests — the standard way to compute "alpha" (excess
return after controlling for market, size, value, momentum). For
the MAX paper, FF factors give the **-1.18% 4-factor Carhart
alpha** that's the headline result.

## Available tables (verified live)

The current (`ff.*`) catalog:

| Table | Rows | Date range | Factors |
|-------|-----:|-------------|---------|
| `ff.four_factor_monthly` | 1,192 | (see below) | Mkt-RF, SMB, HML, RF, MOM |
| `ff.five_factor_monthly` | 748 | 1963-07-31 → 2025-10-31 | + RMW, CMA |
| `ff.four_factor` | 26,110 | daily | same 5 columns |
| `ff.five_factor` | 15,690 | daily | + RMW, CMA |
| `ff.three_factor` | 26,110 | daily | Mkt-RF, SMB, HML, RF (no MOM) |
| `ff.global_factors` | 61,230 | daily | global region factors |
| `ff.factors_na_2025` | 9,045 | daily | North America region |
| `ff.factors_developed_2025` | 9,045 | daily | Developed markets |
| `ff.factors_japan_2025` | 9,045 | daily | Japan |
| `ff.factors_asia_ex_japan_2025` | 9,045 | daily | Asia ex-Japan |

Archive vintages (kept for reproducibility):
- `ff_202401_archive.*` — same tables, 2024-01 snapshot
- `ff_archive_202410.*` — same tables, 2024-10 snapshot

## Schemas (verified)

### `ff.four_factor_monthly` (Carhart — what the MAX paper uses)

```
dt        Nullable(String)   -- date as YYYY-MM-DD
mkt_rf    Nullable(Float64) -- market excess return (value-weighted)
smb       Nullable(Float64) -- small-minus-big
hml       Nullable(Float64) -- high-minus-low (book-to-market)
rf        Nullable(Float64) -- risk-free rate (one-month T-bill)
mom       Nullable(Float64) -- momentum (winners-minus-losers)
```

### `ff.five_factor_monthly` (Fama-French 5-factor)

```
dt        Nullable(String)
mkt_rf    Nullable(Float64)
smb       Nullable(Float64)
hml       Nullable(Float64)
rmw       Nullable(Float64) -- robust-minus-weak (profitability)
cma       Nullable(Float64) -- conservative-minus-aggressive (investment)
rf        Nullable(Float64)
```

## Important gotchas

### 1. Date column is `dt`, not `date`

All FF tables use `dt` for the date column. Most other ClickHouse
tables in this repo use `date` (CRSP, Compustat). If you're joining
FF factors to a CRSP panel keyed on `date`, **rename first**:

```python
ff = c.execute("SELECT dt AS date, mkt_rf, smb, hml, rf, mom FROM ff.four_factor_monthly")
ff_df = pd.DataFrame(ff, columns=["date", "mkt_rf", "smb", "hml", "rf", "mom"])
panel = panel.merge(ff_df, on="date", how="left")
```

### 2. Returns are decimal, not percent

`mkt_rf = 0.02` means 2%, not 0.02%. This matches the convention
in `crsp_202601.dsf.ret` (also decimal), so no conversion needed
before subtracting.

### 3. Monthly file uses STRING dates

The `dt` column is `Nullable(String)`, not `Date`. Parse it:

```python
ff_df["date"] = pd.to_datetime(ff_df["date"])
```

### 4. Four-factor monthly starts 1926, daily starts later

`ff.four_factor_monthly` covers 1926-07 → present (1,192 rows).
`ff.four_factor` (daily) starts 1926-07 too. For the MAX paper
(1962-2005 monthly), `ff.four_factor_monthly` is what you want.

### 5. RF rate vs CRSP risk-free

The `rf` in FF is the **one-month T-bill rate** (already decimal,
e.g. 0.0035 for 35 bps/month). CRSP also has a `risk_free` rate in
`crsp_202601.dsi` (the daily risk-free index). Use FF's — it's what
the paper uses.

## Recipes

### Compute the MAX paper's 4-factor alpha

```python
import pandas as pd
from clickhouse_driver import Client

c = Client(host="100.77.34.92", port=9000, user="...", password="...")

# 1. Pull FF factors
ff = c.execute("""
    SELECT dt AS date, mkt_rf, smb, hml, rf, mom
    FROM ff.four_factor_monthly
    WHERE dt BETWEEN '1962-07-01' AND '2005-12-31'
""")
ff_df = pd.DataFrame(ff, columns=["date", "mkt_rf", "smb", "hml", "rf", "mom"])
ff_df["date"] = pd.to_datetime(ff_df["date"])

# 2. Pull CRSP long-short portfolio returns from the existing replication
ls = pd.read_csv("replications/ssrn_1262416/results/portfolio_vs_assets.csv")
ls["date"] = pd.to_datetime(ls["date"])
ls = ls.rename(columns={"Portfolio @ 0.000% comm": "ret"})
# Excess return
ls["ret_excess"] = ls["ret"] - ff_df.set_index("date").loc[ls["date"], "rf"].values

# 3. Run the 4-factor regression (alpha = intercept)
import statsmodels.api as sm
merged = ls.merge(ff_df, on="date", how="inner")
X = sm.add_constant(merged[["mkt_rf", "smb", "hml", "mom"]])
y = merged["ret_excess"]
model = sm.OLS(y, X).fit()
print(f"4-factor alpha: {model.params['const']*100:.2f}% per month")
# Paper: -1.18% per month
```

The regression should reproduce the paper's headline -1.18%/month
alpha. If it doesn't, check:
- Date range (1962-07 to 2005-12, monthly)
- Universe (NYSE/AMEX/NASDAQ with `shrcd IN (10, 11)`)
- Lag (bin formed at end of month t, return at month t+1 — see
  `utils.forward_returns`)
- Weighting (VW)

### Fama-MacBeth with FF controls

`utils.fama_macbeth(df, dependent_var, independent_vars, time_col)`
already accepts arbitrary independent variables. To add FF controls:

```python
from utils import fama_macbeth, summarize_fama_macbeth

panel = monthly.merge(ff_df, on="date", how="inner")
panel["ret_excess"] = panel["ret"] - panel["rf"]

result = fama_macbeth(
    panel,
    dependent_var="ret_excess",
    independent_vars=["max_signal", "log_mcap", "log_bm", "ret_11_2"],
    time_col="date",
)
print(summarize_fama_macbeth(result))
```

## What `utils.forward_returns` is for (cross-sectional basics)

If you're computing a signal at end of month t (e.g. MAX of daily
returns in month t), the return you measure at month t+1 is the
**right** return to evaluate it against. The shift convention is
universal for cross-sectional strategies with monthly rebalancing —
see `references/spec2code.md` for the canonical pipeline pattern.

## See also

- `references/data/crsp.md` — CRSP data layer (the FF joins to this)
- `references/data/compustat.md` — Compustat for book-to-market (B/M is one
  of the FF control variables' inputs, but B/M itself is computed from
  CRSP × Compustat, not from FF directly)
- `references/spec2code.md` — how the agent uses FF factors in a replication