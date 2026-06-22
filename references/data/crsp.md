# CRSP — Center for Research in Security Prices

> **Status:** second-pass. Covers the 4 core tables (`dsf`, `dsi`,
> `dsfhdr`, `dsenames`) plus a curated set of commonly-needed related
> tables (`erdport*`, `mport*`, `ccmxpf_*`, `dsedelist`) and the
> methodology layer (formulas, breakpoints, eligibility, investability
> screens). Recipes marked `[verify]` have **not** been confirmed
> against the CRSP primary sources; the rest have been cross-checked
> against the three source PDFs listed at the bottom. When in doubt,
> re-read the primary source rather than re-deriving.

## What CRSP is

CRSP is the standard US-equity daily/monthly price-and-return database
maintained by the Booth School of Business (U. Chicago). It's the
default data source for almost every US equity paper in academic
finance, so most paper replications will touch at least one of the
tables below.

In this repo, CRSP data lives in ClickHouse. The auto-generated schema
catalog (`paper2spec/resources/clickhouse_catalog.json`) lists every
table and column. This file adds the **semantic** layer the catalog
doesn't: what each table is for, how columns relate to each other,
what derived fields look like, and where the gotchas are.

This file is **read by the agent that generates strategy code**. The
catalog alone is not enough — agents routinely pick the wrong vintage,
guess market-cap units, drop the `abs()` on `prc`, or skip share-code
filtering unless told. The recipes and gotchas below are the durable
fix; do not let generated code re-litigate them.

## Available CRSP databases in this ClickHouse instance

| Database | Tables | Notes |
|----------|-------:|-------|
| `crsp_202301` | 62 | Older CRSP vintage, smaller schema |
| `crsp_202401` | 247 | Full schema |
| `crsp_202501` | 250 | Older full-schema extract. Stock-file data is **bit-identical to `crsp_202601`** — kept only for compatibility with already-generated runs in `library/`. Do **not** use for new agent-generated code. |
| `crsp_202601` | 253 | **Default vintage — use this.** Strictly ≥ `crsp_202501` on every dimension: same stock-file rows (0 differences on `dsf`/`msf`/`dsi`/`msi`/`dsfhdr`/`dsenames` and the rest), ~3% more recent rows in `ccmxpf_linktable`, plus 3 extra tables. |
| `crsp` | 33 | Older condensed mirror; has mutual-fund-style tables |
| `crsp_mutual_202511` | 29 | Mutual fund data (NAV, returns, TNA) — not equity stock data |

**Use `crsp_202601.*` for all new work.** Vintage-by-vintage
comparison (verified by direct ClickHouse queries, not inferred from
the catalog):

- **Stock files** (`dsf`, `msf`, `dsi`, `msi`, `dsfhdr`, `dsenames`,
  `dseall`, `dsedelist`, `dsenasdin`, `mseall`, `msedelist`): **0 rows
  differ** between `crsp_202501` and `crsp_202601`. Row hashes of
  `dsf` by `(permno, date, ret)` are also identical. So a paper
  replication that uses stock-file data will get bit-identical
  results on either vintage.
- **Compustat link tables** (`ccmxpf_linktable`, `ccmxpf_lnkhist`,
  `ccmxpf_lnkrng`, `ccmxpf_lnkused`): `crsp_202601` has ~3% more
  recent rows. `ccmxpf_linktable` specifically: 89,677 → 92,711
  (+2,972). Matters for fundamentals-based signals (B/M, ROE,
  profitability) — use the 2026 link tables for those.
- **Tables only in `crsp_202601`** (3 new): `ccm_qvards`
  (point-in-time Compustat-CRSP merged lookup; **empty in this
  instance** — use `ccmxpf_linktable` instead), `holdings` (mutual
  fund holdings, 438M rows — different domain, ignore for equity
  stock work), `stock_qvards` (currently empty placeholder, not yet
  populated).

`crsp_202501.*` should appear only in already-generated artifacts in
`library/<slug>/strategy_*.py` and `library/<slug>/data_match_report.json`.
New agent-generated code must use `crsp_202601.*`. If you find yourself
editing an existing `strategy_*.py` to point at `crsp_202601`, don't —
the file is generated, and the next regeneration will use the right
vintage automatically once this doc is the source of truth.

## Tables

### `crsp_202601.dsf` — Daily Stock File

The workhorse. One row per `permno` per trading day. 107,663,470 rows
in this instance, covering 1925-12-31 → 2024-12-31.

| Column | Type | Description |
|--------|------|-------------|
| `date` | `Nullable(String)` | Trading date. ISO 8601 string (cast to `DATE` for filtering). |
| `permno` | `Nullable(Int32)` | CRSP's permanent security identifier. **Stable across name changes**, not across share-class changes. 5-digit integer for common securities; range `-999989` to `-100` and `100` to `999989` is reserved for CRSP (negative values exist, e.g. for some foreign securities). |
| `permco` | `Nullable(Int32)` | CRSP's permanent company identifier. Stable across all of a company's securities; use for company-level joins. |
| `issuno` | `Nullable(Int32)` | Issue number; distinguishes share classes within a permco. A company with multiple common-share classes (e.g. GM's A, E, H series) has multiple `permno`s — all sharing the same `permco` but with distinct `issuno`. |
| `cusip` | `Nullable(String)` | 9-char CUSIP (the standard uses 9 chars, though only 8 are stored in the `dsf` `cusip` column — the check digit is the 9th). Structure: first 6 chars = company (CRSP calls this `CNUM`), next 2 chars = asset class (CRSP calls this `CIC`), last char = check digit. **CUSIPs can change over a security's life** (mergers, reclassifications); use `ncusip` from `dsenames` to track a company through CUSIP changes. Joins to Compustat go through the `ccmxpf_*` link tables — see `crsp_202601.ccmxpf_linktable`. |
| `hexcd` | `Nullable(Int32)` | Exchange code: 1=NYSE, 2=NYSE MKT (formerly AMEX, renamed Oct 2008), 3=NASDAQ, 4=Arca, 5=Bats. |
| `hsiccd` | `Nullable(Int32)` | Historical SIC code (CRSP's assignment). |
| `ret` | `Nullable(Float64)` | Holding-period return **with** dividends. Missing-return sentinels (`-66.0`, `-77.0`, `-88.0`, `-99.0`, `-55.0`) appear as non-NULL negative floats — see Gotchas. |
| `retx` | `Nullable(Float64)` | Return **excluding** dividends. |
| `prc` | `Nullable(Float64)` | Closing price. **Negative when the close is a bid/ask average** (no transaction occurred at the close) — take `abs(prc)` for any price-based calculation. |
| `bidlo` / `askhi` | `Nullable(Float64)` | Daily bid low / ask high. |
| `bid` / `ask` | `Nullable(Float64)` | Closing bid / ask. |
| `openprc` | `Nullable(Float64)` | Open price. |
| `vol` | `Nullable(Float64)` | Share volume. |
| `shrout` | `Nullable(Float64)` | Shares outstanding, **in thousands**. See Derived Fields. |
| `cfacpr` | `Nullable(Float64)` | Cumulative price adjustment factor (for splits/dividends). 0 for cash dividends, -1 for total liquidations. |
| `cfacshr` | `Nullable(Float64)` | Cumulative share adjustment factor. |
| `numtrd` | `Nullable(Int32)` | Number of trades (post-1993 era). |

**Sort key** (per `system.tables` for this instance): `date, permno`.
The guide confirms "The Stock Data are sorted and indexed by this
field [PERMNO]." Always filter `WHERE date >= ...` first to use the
index.

### `crsp_202601.dsi` — Daily Stock Index

Aggregate market indices, one row per trading day. 26,051 rows, same
date range as `dsf`.

| Column | Type | Description |
|--------|------|-------------|
| `date` | `Nullable(String)` | Trading date. |
| `vwretd` | `Nullable(Float64)` | **Value-weighted return, with dividends** — the canonical "market return" series for US equity papers. Use this as the SPY proxy pre-1993 (SPY ETF started 1993). |
| `vwretx` | `Nullable(Float64)` | Value-weighted, ex-dividends. |
| `ewretd` | `Nullable(Float64)` | Equal-weighted, with dividends. |
| `ewretx` | `Nullable(Float64)` | Equal-weighted, ex-dividends. |
| `sprtrn` | `Nullable(Float64)` | S&P 500 composite return. |
| `spindx` | `Nullable(Float64)` | S&P 500 index level. |
| `totval` / `totcnt` | `Nullable(Float64)` / `Nullable(Int32)` | Total market cap / count of stocks in the index. |
| `usdval` / `usdcnt` | `Nullable(Float64)` / `Nullable(Int32)` | USD-denominated subset (post-1970s). |

For a paper that says "we use the CRSP value-weighted market return" or
"market beta estimated against the CRSP index", this is the table.

### `crsp_202601.dsfhdr` — Daily Stock File Header

One row per `permno` (not per day) — the **header record** containing
identification and lifecycle info. 38,872 rows.

| Key column | Description |
|------------|-------------|
| `permno` | FK to `dsf.permno`. |
| `hshrcd` | **Share code** (10/11 = common shares; see Filters). |
| `hexcd` | Exchange code (matches `dsf`). |
| `dlstcd` | **Delisting code** (e.g. 500 = merger, 400 = liquidation). Critical for handling delisting returns. |
| `hcusip` / `htick` / `hcomnam` / `htsymbol` | Header CUSIP, ticker, company name, ticker-symbol at the header snapshot. |
| `begdat` / `enddat` | Validity window of this header record. |
| `hsecstat` / `htrdstat` | Security/trading status flags. |

Join to `dsf` on `permno` when you need share code, exchange code, or
delisting status in a single per-permno lookup (cheaper than joining
`dsenames` per day).

### `crsp_202601.dsenames` — Names history

Detailed per-permno names history with explicit date ranges. 117,859
rows. Use this when you need to track ticker/name changes over time
(permno is stable; ticker is not).

| Column | Description |
|--------|-------------|
| `permno` | FK to `dsf.permno`. |
| `namedt` / `nameendt` | Validity window of this name record. |
| `shrcd` | Share code (same as `dsfhdr.hshrcd`). |
| `exchcd` | Exchange code. |
| `ticker` / `comnam` | Ticker / company name at this snapshot. **Caveat**: ticker symbols can be **reused** by different companies over time (after delisting, a symbol can be reassigned). Any query keyed on ticker must validate via `permno` or `permco` — never trust ticker alone for cross-company joins. |
| `ncusip` | CUSIP at this snapshot (8-char, point-in-time). CUSIP codes can change over a security's life (mergers, reclassifications); **for tracking a company across the full date range use `ncusip`**, not `cusip` from `dsf`. |
| `siccd` | SIC code (point-in-time). |
| `primexch` | Primary exchange code (post-2002 char form). |

For most academic replications, the share-code / exchange-code filter
can be done against `dsfhdr` (cheaper). Use `dsenames` when you need
point-in-time SIC codes, ticker history, or the explicit validity
windows.

## Other useful tables in `crsp_202601`

These are all in the same `crsp_202601` database — not separate
databases. They sit alongside the 4 core tables documented above
(dsf/dsi/dsfhdr/dsenames) in the same ClickHouse database, and are
included here because paper replications commonly need them even
though we don't open them on every run. Verified row counts
(queried live, not from the catalog):

| Table | Rows | Use |
|-------|-----:|-----|
| `crsp_202601.erdport1` (and `erdport2`–`erdport9`) | 97M (d1) | Daily event-ranked decile portfolios (pre-sorted by various criteria) |
| `crsp_202601.mport1` (and `mport2`–`mport5`) | 421K (m1) | Month-end ranked decile portfolios |
| `crsp_202601.ccmxpf_linktable` | 92,711 | Point-in-time CRSP-Compustat link (LC/LU, P/C/J, liid) |
| `crsp_202601.ccmxpf_lnkhist` | 123,388 | Linkage history (full audit trail of link changes) |
| `crsp_202601.ccmxpf_lnkrng` | 376,359 | Date ranges of valid links (preferred for point-in-time joins) |
| `crsp_202601.ccmxpf_lnkused` | 100,942 | WRDS-recommended link set |
| `crsp_202601.ccm_qvards` | 0 | Newer point-in-time lookup; **empty in this instance** — use `ccmxpf_linktable` instead |
| `crsp_202601.dsedelist` | 38,872 | Delisting events with `dlret` (see Delisting returns below) |

### Decile / ranked portfolios (`erdport*`, `mport*`)

CRSP ships pre-sorted decile portfolios that skip the work of running
the sort yourself. Categories include size (market cap), beta, and
standard deviation. Useful as a sanity check or a shortcut for
classics like the size premium.

| Tables | Frequency | Use |
|--------|-----------|-----|
| `crsp_202601.erdport1` … `erdport9` | Daily | Event-ranked decile portfolios (pre-sorted by various criteria) |
| `crsp_202601.mport1` … `mport5` | Monthly | Month-end ranked decile portfolios |

Verify which sort criterion corresponds to which table number before
using — the numbering convention has shifted across CRSP vintages.
These are **not** interchangeable with the `dsf`/`msf` deciles you
compute yourself unless you re-derive the sort criterion.

### Compustat-CRSP link (`ccmxpf_*`)

The CRSP/Compustat Merged (CCM) database provides the linkage
between CRSP securities and Compustat fundamentals. A row says
"this CRSP `permno` at this date corresponds to this Compustat
`gvkey`". Required for any fundamentals-based signal (B/M, ROE,
asset growth, etc.).

| Table | Use |
|-------|-----|
| `crsp_202601.ccmxpf_linktable` | Point-in-time CRSP-Compustat link with `linktype` (LC/LU), `linkprim` (P/C/J), `liid` |
| `crsp_202601.ccmxpf_lnkhist` | Linkage history (full audit trail of link changes) |
| `crsp_202601.ccmxpf_lnkrng` | Date ranges of valid links (preferred for point-in-time joins) |
| `crsp_202601.ccmxpf_lnkused` | Recommended link set (the one WRDS suggests using) |
| `crsp_202601.ccm_qvards` (2026 only) | Newer point-in-time lookup; largely overlaps `ccmxpf_linktable` |

**Standard filter**: `linktype IN ('LC', 'LU')` and `linkprim IN ('P',
'C')` per the WRDS-recommended link set. Different papers use
different subsets; check the paper's Compustat footnote.

### Delisting returns (`dsedelist`)

`crsp_202601.dsedelist` — 38,872 rows, one per delisting event.
Carries the delisting return (`dlret`) used to handle stocks that
leave CRSP coverage. Standard academic practice: substitute
`dlret` for `ret` on the delisting date (or distribute it across the
last few days of trading). See the "Returns" section of the CRSP
guide for the formula and the `-55.0` missing code.

## Index methodology

How CRSP's pre-computed series (`dsi.vwretd`, `vwretx`, `dsi.totval`,
`dsi.usdval`) are actually constructed. From the *Market Indexes
Methodology Guide*, Ch. 2 + Appendix A.

### Security total return (the basis of `dsf.ret`)

```
r(t) = (p(t) + n(t) + d(t)) / p(t') - 1
```

where `p(t)` = end-of-day price, `n(t)` = non-ordinary payments (e.g.
special dividends not adjusted into `p(t')`), `d(t)` = dividend amount,
`p(t')` = start-of-day price on day *t* (after split/dividend
adjustment). For price-return series, drop `d(t)` and `n(t)`.

**Start-of-day price** is derived from the prior close plus known
distributions:

```
p(t') = (p(t-1) - v(t)) * f(t)
```

where `v(t)` = non-ordinary split-adjusted payments (e.g. special
dividends), `f(t)` = split factor. This is why `prc` carries
adjustments for splits/dividends but **not** for cash dividends (those
appear in `ret` via `d(t)`).

### Index level and divisor (the basis of `dsi.vwretd` / `vwretx`)

```
Index_Level_t = Index_MarketValue_t / Divisor_t           # price-only
Index_Level_TR_t = Index_Level_TR_t-1 × (Index_Level_t + DivPts_t) / Index_Level_t-1   # total return
```

with `DivPts_t = Dividend_Amount_t / Divisor_t` and the divisor
updated each day to reflect corporate actions:

```
Divisor_initial = 1,000 / (Index_MarketValue_at_inception / 1,000)
Divisor_t = Divisor_t-1 × (SOD_IndexMarketValue_t / EOD_IndexMarketValue_t-1)
```

This is the standard "Laspeyres-style" value-weighted index with a
divisor that absorbs corporate actions. **The pre-computed
`dsi.vwretd` already implements this** — for most replications, use
it directly rather than rebuilding from `dsf`.

### Holdings and weights

```
Holdings_i = Effective_TSO_i × Effective_Float_Factor_i / 100
             × Size_Multiplier_i × Style_Multiplier_i
             × Concentration_Multiplier_i × Received_Stock_Multiplier_i
IndexWeight_i = (Holdings_i × Price_i) / Σ_j (Holdings_j × Price_j)
```

**Effective TSO** = TSO at the last ranking (or last corporate-action
review). **Effective Float Factor** = FSO/TSO rounded to the nearest
5/1/0.1 percent. For **value-weighted replications** of academic
papers, the convention is to use raw TSO × price (no float adjustment,
no Style/Concentration/Received multipliers). The float and
multiplier machinery only matters when you're trying to replicate the
*index*, not a paper's portfolio.

### Cap-based breakpoints (the basis of size deciles)

CRSP's standard cap-based size indexes use cumulative-market-cap
breakpoints — the canonical "NYSE size decile" methodology:

| Index | Cumulative cap range | Band |
|-------|---------------------|------|
| Mega Cap | 0–70% | 64–76% (Mega/Mid) |
| Large Cap | 0–85% | — |
| Mid Cap | 70–85% | 64–76% and 81–89% |
| Small Cap | 85–98% | 81–89% (Mid/Small) and 96–99.5% (Small/Micro) |
| Micro Cap | 98–100% | 96–99.5% |

Companies near a breakpoint are split **50/50** between adjacent
indexes ("packeting") and only fully migrate after two consecutive
rankings in the new index's core. This minimizes churn.

For paper replication, the cleaner approach is usually to compute your
own size deciles from `dsf`/`msf` using NYSE breakpoints, rather than
using `erdport*`/`mport*` directly (whose sort criteria need to be
verified per table number).

### Eligibility and investability (the basis of `dsi` inclusion)

What gets into the CRSP indexes (and therefore informs what counts as
a "real" US common stock):

- **Exchanges of interest**: NYSE, NYSE American (formerly AMEX),
  NYSE ARCA, NASDAQ (Global Select / Global / Capital), Cboe BZX.
  OTC and Pink Sheets are excluded.
- **Organization types**: Corporations, REITs, Berkshire Hathaway A/B.
  Excluded: BDCs, Closed-End Investment Companies, ETFs/ETNs, LLCs,
  LPs, Royalty Trusts, SPACs.
- **Share types**: Common Shares, SBIs (unless a fund). Excluded:
  ADRs, Preferred, Convertible Preferred, Rights, Warrants, Units.
- **US company test**: HQ + incorporation in US, **or** HQ in US plus
  EIN, **or** >5% holding by US public equity funds. Companies
  filing as Foreign Private Issuer are excluded.
- **PFIC exclusion**: Passive Foreign Investment Companies excluded
  even if they otherwise pass the US company test.

**Investability screens** (applied at quarterly ranking):

| Screen | Add | Drop |
|--------|-----|------|
| Market cap | ≥ $15M | < $10M |
| Float shares (FSO/TSO) | ≥ 12.5% (10% for fast-track IPO) | < 10% |
| Sparse trading score | ≥ 0.001 | < 0.0008 for 2 consecutive rankings |
| Trading gaps | No 10+ day zero-volume sequence | Any since last ranking |
| Seasoning | ≥ 20 trading days (≥ 5 days if fast-track) | n/a |
| Suspended | Not suspended | ≥ 40 days suspended |

For paper replication, the standard filter is much looser than the
index screen — most academic papers use `prc ≥ $5` and exclude
financials/penny stocks, not the full investability suite. But if the
paper says "replicating the CRSP US Total Market Index", these are
the exact rules.

### Rebalancing and corporate actions

- **Quarterly reconstitution** with **5-day transition window**.
- **Compliance days** (last trading day of March/June/September/
  December) check IRS RIC 25/50 concentration rules.
- **Cap-neutral actions** (no true-up needed): splits, reverse
  splits, stock dividends, stock received in spin-offs/stock mergers.
- **Non-cap-neutral actions** (require index review): secondary
  offerings ≥ 5% of holdings, mergers, IPOs, etc.

CRSP's official price adjustments (Appendix A "Price Adjustment
Table"):

| Event | Adjusted price |
|-------|---------------|
| Special dividend | `prev_close − special_div_amount` |
| Stock dividend | `prev_close / (1 + stock_div_ratio)` |
| Stock split | `prev_close / split_ratio` |
| Reverse split | `prev_close / split_ratio` |
| Spin-off (WI available) | `parent_SOD = parent_prev_close − spinoff_WI_price × spin_ratio` |

## Derived fields

### Market capitalization (per stock, per day)

**CRSP's official definition** (Data Descriptions Guide, "Capitalization,
End of Period"):

> Closing price × shares outstanding **(in 1000s)**, as of end of the
> period. If an index, capitalization is the total market value of the
> issues used in the index at the beginning of the period.

So CRSP's native `Capitalization` column is:

```python
mcap_crsp_native = prc * shrout   # in 1000s of dollars (because shrout is in 1000s)
```

TS_PRINT/TSQUERY names: `tcap` (daily), `mtcap` (monthly), `TCap`
(header). Conversions to other units:

```python
mcap_dollars  = prc * shrout * 1000    # total dollar market cap
mcap_millions = prc * shrout / 1000    # in millions of dollars
```

`prc` is signed (negative for bid/ask averages), so take `abs()` first.
A value-weighted portfolio backtest is **unit-invariant** — the scale
cancels in the weights — so any of the above forms work for VW returns.
For absolute-size work (size deciles, NYSE size breakpoints) the unit
matters.

⚠️ **The `library/ssrn_1262416_e2e/strategy_1.py` version has a
documentation bug** that confuses the units. Lines 157/173/174
disagree: the docstring says `* 1000` (dollars), the inline comment
says "in millions" with no scaling in the code, and the actual code
is `prc * shrout` with no scaling at all. The actual code matches
CRSP's native units (1000s of dollars); the inline "in millions"
comment is wrong, and the docstring's `* 1000` is correct for
dollars but contradicts the code. Fix when that file is regenerated.

### Monthly stock return (from daily)

```python
monthly_ret = (1 + daily_ret).prod() - 1
grouped_by = ["year_month", "permno"]
```

Use this when you have a daily file but want a monthly signal/return
(unlike `crsp_202601.msf`, which is the pre-aggregated monthly file).
Be careful with month-end delistings: a stock that delists mid-month
has a partial month.

### Annualised return / Sharpe

```python
sharpe_annual = mean(monthly_ret) / std(monthly_ret) * sqrt(12)
```

(rf=0 baseline; subtract risk-free rate if comparing to paper's
risk-adjusted numbers.)

## Filters (typical for academic replications)

These are the **standard** filters from US equity literature; check
the specific paper for any deviations. Exchange/share-code values are
verified against the CRSP *Data Descriptions Guide*; the broader
universe rules come from the *Market Indexes Methodology Guide*
(see Index methodology section).

| Filter | Where it applies | What it excludes |
|--------|------------------|------------------|
| `shrcd IN (10, 11)` | `dsfhdr.hshrcd` or `dsenames.shrcd` | ADRs, REITs, closed-end funds, units, etc. Keeps ordinary common shares. The `[10, 11]` filter is the *narrow* form; CRSP's broader "ordinary common shares" is all `1X` codes (10–18) per the first-digit definition (1 = Ordinary Common Shares). |
| `exchcd IN (1, 2, 3)` | `dsfhdr.hexcd` or `dsenames.exchcd` | Keeps NYSE (1), NYSE MKT (2, formerly AMEX), NASDAQ (3). Some papers restrict further to NYSE-only. Codes 4 (Arca) and 5 (Bats) are excluded by this filter. |
| `prc >= 5.0` | `dsf.prc` (after `abs()`) | Excludes penny stocks. Common robustness check, not always in the main spec. |
| `shrout > 0` | `dsf.shrout` | Excludes observations with missing shares outstanding. |
| `ret IS NOT NULL AND ret > -50` | `dsf.ret` | Excludes days with missing returns (suspensions, IPOs). The `> -50` excludes the missing-return sentinels (`-55.0`, `-66.0`, `-77.0`, `-88.0`, `-99.0`) which are non-NULL floats — see Gotchas. |
| `mcap >= 15_000_000` (in dollars) | derived from `abs(prc) * shrout * 1000` | Reproduces CRSP's index *add* threshold ($15M). Use `$10M` for the *drop* threshold. Most papers use a more permissive threshold (e.g. NYSE size breakpoints). |
| `abs(prc) > 0` | `dsf.prc` | Excludes rows where the price field is zero (rare but happens around delistings). |

### Eligibility for "real US common stock" (CRSP's own definition)

If the paper says "we replicate the CRSP US Total Market Index
universe", the full rule set is (from the *Market Indexes Methodology
Guide*, Ch. 2):

- **Exchange** in {NYSE, NYSE American, NYSE ARCA, NASDAQ (Global
  Select/Global/Capital), Cboe BZX} — corresponds to `exchcd IN
  (1, 2, 3, 4, 5)` but with the right MIC mapping. CRSP's
  "exchange of interest" is the canonical list.
- **Organization type** is Corporation, REIT, or Berkshire Hathaway
  A/B. Excludes: BDCs, Closed-End Funds, ETFs, ETNs, LLCs, LPs,
  SPACs. Not directly encoded in `dsf` — must be derived from
  `siccd` ranges or external data.
- **Share type** is common share (`shrcd` first digit = 1) or SBI
  (`shrcd = 4X`).
- **US company**: HQ + incorporation in US, or HQ in US plus EIN, or
  >5% holding by US public equity funds. Foreign Private Issuers
  excluded. Hard to encode as a single filter; `exchcd IN (1,2,3)`
  is a reasonable proxy for most replications.
- **Not a PFIC** (Passive Foreign Investment Company). Requires
  external data.
- **Investability screens** ($15M/$10M cap, float %, trading volume,
  seasoning) — see Index methodology → Eligibility and investability.

## Gotchas

- **`prc` sign**: negative for bid/ask averages. Always `abs()` before
  any price-based calculation, including market cap. (CRSP guide:
  "If the closing price is not available on any given trading day,
  the number in the price field is a bid/ask average, not an actual
  closing price.") Pre-Nov-1982 NASDAQ prices are **always** negative
  bid/ask averages; pre-Jun-1992 NASDAQ SmallCap prices are also
  always negative bid/ask averages. Pre-1982 NASDAQ data exists but
  the price field is bid/ask only.
- **Missing return codes** (sentinels, *not* NULL — they appear as
  regular negative floats). Verified from the guide:

  | Code | Meaning (Holding Period Total Return) |
  |------|---------------------------------------|
  | `-66.0` | Valid current price but no valid previous price (first price, exchange change, or >10 periods between observations) |
  | `-77.0` | Not trading on the current exchange at time *t* |
  | `-88.0` | No data available to calculate returns |
  | `-99.0` | Missing return due to missing price at *t* (suspension, trading on unknown exchange) |
  | `-55.0` | Missing **delisting** return (CRSP has no source to establish a value after delisting) |

  Filter with `ret IS NOT NULL AND ret > -50` (or a tighter bound)
  before any return-based analysis. Just checking `IS NOT NULL` is
  not enough — these are valid floats, not NULL.
- **Delisting returns**: separate from the missing-return codes. The
  guide defines a delisting return computed from the security's
  Amount After Delisting (off-exchange price, quote, or sum of
  distributions) vs. its price on the last day of trading. A
  worthless stock gets a delisting return of `-1.0` (100% loss). The
  full machinery is in `crsp_202601.dsedelist` (not in the 4 tables
  we cover here).
- **NULL encoding**: every column is `Nullable(...)` per the
  auto-discovered catalog. The native `clickhouse_driver` returns
  proper Python `None` for NULL (no `\N` workaround needed, per
  commit `0b4cf60`). Note that this is **distinct from** the
  missing-return sentinels above — sentinels are non-NULL floats.
- **PERMNO range**: 5-digit integer; the range `-999989` to `-100` and
  `100` to `999989` is reserved for CRSP PERMNO assignments. Negative
  PERMNO is valid (e.g. foreign securities); do not filter on
  `permno > 0` unless the paper specifies. A `permno BETWEEN 10000
  AND 99999` filter (5-digit positive) is sometimes used as a
  US-domestic proxy but excludes foreign securities.
- **Sample period**: catalog shows 1925-12-31 → 2024-12-31. The MAX
  paper uses 1962-2005; using the full range without a date filter
  will pull 1962-1925 garbage for older securities. Always pin the
  date range.
- **Coverage by exchange** (from the guide, Chapter 1 Background):
  NYSE / NYSE MKT — July 1962 onwards; NASDAQ — December 12, 1972
  onwards; Arca — March 8, 2006 onwards; Bats — January 24, 2012
  onwards. Any replication of a pre-1962 US equity paper cannot use
  CRSP. AMEX (now NYSE MKT, code 2) was renamed on October 1, 2008
  when NYSE Euronext completed the acquisition — historical `exchcd =
  2` rows are still AMEX securities, just labelled differently now.
- **Sort key**: `dsf` and `dsi` are sorted on `(date, permno)`.
  Confirmed by the guide: "The Stock Data are sorted and indexed by
  this field [PERMNO]." Always filter on `date` first to use the
  index. `WHERE permno = X` alone is a full scan.
- **Adjustment factors**: `cfacpr` (Factor to Adjust Price) and
  `cfacshr` (Factor to Adjust Shares Outstanding) are **cumulative**
  factors from a base date, used to adjust prices after distributions
  so that equivalent comparisons can be made across split/dividend
  events. For ordinary cash dividends, `cfacpr` is set to 0. For
  mergers/total liquidations, `cfacpr` is set to -1. For stock
  dividends and splits, `cfacpr = (s(t) - s(t')) / s(t')`. For
  total-return work using adjusted prices, divide `prc` by `cfacpr`
  and multiply `shrout` by `cfacshr` — but the *unadjusted* `prc` and
  `shrout` are correct for market-cap-as-of-the-date calculations.
  Don't mix adjusted and unadjusted in the same calc.

## Cross-references

- Catalog source: `paper2spec/resources/clickhouse_catalog.json`,
  under `databases.crsp_202601.{dsf,dsi,dsfhdr,dsenames}`.
- Connection / safety / query patterns: `references/clickhouse.md`.
- Previously used by: `library/ssrn_1262416_e2e/strategy_1.py`
  (dsf, dsi) — pre-update; queries `crsp_202501.*`. New replications
  that follow this doc will use `crsp_202601.*`.
- LLM-generated field expectations (per-paper, not durable):
  `library/ssrn_1262416_e2e/data_requirements.json`.

## Primary source

Recipes marked with **"CRSP guide"** or page citations were verified
against:

> *Data Descriptions Guide for CRSPAccess (FIZ) US Stock & Index
> Databases.* CRSP / Morningstar, Feb 2026. 126 pages.
>
> Local copy: `CRSP_US_Stock_&_Indexes_Database_Data_Descriptions_Guide.pdf`
> (repo root, gitignored — fetched on demand).

Section index used: Ch. 2 Data Definitions — `Capitalization, End of
Period` (p. 23), `Price, End of Period` (p. 71), `Returns` /
`Holding Period Total Return` (p. 41, 74), `Exchange Code - Header`
(p. 38), `Share Type Code, End of Period` (p. 78), `Factor to Adjust
Price in Period` (p. 39), `PERMNO/INDNO` (p. 67), Ch. 1 Background —
Stock Data Universe (p. 4-6).

**Supplementary source** for the practical / identifier layer
(CUSIP structure, NCUSIP rationale, ticker reuse, multi-class
PERMNO/PERMCO example, pre-sorted decile portfolios, CCM link):

> *Introduction to CRSP (WRDS).* Analytics Group, Aarhus University,
> Aug 2008. 11 pages. Mostly UI-walkthrough — only the data-identifier
> notes (Section 3.1) and the database layout (Section 1) are durable.
>
> Local copy: `Manual_WRDS_CRSP.pdf` (repo root, gitignored).

Used here for: §Other useful tables (Decile tables, CCM link), the
GM A/E/H example under `dsf.issuno`, the CUSIP-structure explanation
under `dsf.cusip`, the NCUSIP recommendation under `dsenames.ncusip`,
and the ticker-reuse caveat under `dsenames.ticker`.

**Methodology source** (the **how** — formulas, breakpoints,
eligibility, investability screens — that the two data-definition
sources don't cover):

> *CRSP Market Indexes Methodology Guide.* CRSP / Morningstar, Apr
> 2026 (last modified Jun 2, 2026). 95 pages.
>
> Local copy: `crsp_manual_pdf/CRSP_Market_Indexes_Methodology_Guide.pdf`
> (gitignored — fetched on demand).

Section index used: Ch. 2 Total Market Index (pp. 7-13) — universe
creation, eligibility, investability screens, FSO; Ch. 3 Cap-Based
Indexes (pp. 14-20) — breakpoints, bands, packeting; Appendix A
Index Formulas (pp. 72-76) — return formula, divisor, holdings,
price adjustments; Ch. 11 Glossary (pp. 67-71) — FSO/EFF/Effective
TSO definitions.

Used here for: §Index methodology (security total return, index
level/divisor, holdings/weights, cap-based breakpoints, eligibility
and investability, rebalancing and corporate actions), the
investability-screens row in §Filters, and the size-decile framing
in §Other useful tables.

Still unverified in this doc (`[verify]` markers) cover the few items
where the primary source was ambiguous or not consulted.
