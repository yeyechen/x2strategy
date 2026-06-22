# Compustat — Standard & Poor's Fundamentals

> **Status:** first pass. Covers the core US/Canada fundamentals
> tables in `comp_202601` (`funda`, `fundq`), the identifier/link
> layer (`security`, `company`, `names`, `ccmxpf_*` in CRSP), and the
> derived-field recipes (book equity, market equity, B/M) that every
> fundamentals-based paper needs. Recipes marked `[verify]` were
> **not** present in the 2003 User's Guide I worked from — they are
> standard Compustat conventions from the academic literature
> (Fama-French data library, Davis et al. CRSP/Compustat Merged
> documentation) and should be re-checked against a current
> Compustat variable reference (post-2014) before depending on them
> for anything load-bearing. Everything else has been cross-checked
> against the PDF listed at the bottom.

## What Compustat is

Compustat is the standard US (and Canadian, and global) fundamentals
database maintained by S&P Global Market Intelligence. It supplies
balance sheet, income statement, cash flow statement, and
supplementary disclosure items at annual and quarterly frequency,
indexed by a stable company identifier (`gvkey`) and a stable
security identifier (`iid`). It's the **other** half of almost every
US equity paper in academic finance, paired with CRSP for prices.

The default data files for industrial US firms are **`funda`**
(annual) and **`fundq`** (quarterly). Banks and utilities have
separate `comp_bank` and `comp_utility` files in old S&P conventions;
in modern Compustat (and in our `comp_202601` instance) they live in
the same `funda`/`fundq` tables with a `fic` (foreign-incorporation
code) and `datafmt` / `indfmt` that distinguishes them.

In this repo, Compustat data lives in ClickHouse. The auto-generated
schema catalog (`paper2spec/resources/clickhouse_catalog.json`) lists
every table and column. **This file adds the semantic layer the
catalog doesn't**: what each table is for, how the four core filter
flags work, how to construct book equity / market equity / B/M the way
academic papers do, and where the gotchas are.

This file is **read by the agent that generates strategy code**. The
catalog alone is not enough — agents routinely pick the wrong book
equity field (`bkvlps` vs `ceq` vs `seq`), skip the standard
`indfmt`/`consol`/`popsrc`/`datafmt` filters, or align book equity to
the wrong fiscal year unless told. The recipes and gotchas below are
the durable fix.

## Available Compustat databases in this ClickHouse instance

| Database | Rows (funda) | Notes |
|----------|------------:|-------|
| `comp` | (older condensed) | Older mirror. Don't use for new work. |
| `comp_202401` | (older vintage) | Don't use for new work. |
| `comp_202408` | (older vintage) | Don't use for new work. |
| `comp_202501` | (older vintage) | Don't use for new work. |
| `comp_202508` | (older vintage) | Don't use for new work. |
| `comp_202509` | (older vintage) | Don't use for new work. |
| **`comp_202601`** | **929,418** | **Default — use this.** Latest extract. Six full quarters of `fundq` (2,113,095 rows) plus the full annual file. |
| `comp_pit` | (point-in-time) | **Use this for any backtest that needs to avoid look-ahead bias.** Contains `pithistdataus` (32.5M rows, 287 cols — the as-restated PIT version of Compustat) and `pithistdatacdn` (Canada). Key PIT tables: `pithistdataus`, `pitidhistus`, `pitnamesus`, `pitqtrdataus`. |
| `comp_snapshot`, `comp_snapshot_2023`, `comp_snapshot_2024`, `comp_snapshot_202601` | snapshots | Year-end point-in-time snapshots. Less granular than `comp_pit` for vintage tracking. |

**Use `comp_202601.funda` and `comp_202601.fundq` for new work.**
PIT work uses `comp_pit.pithistdataus` (annual as-restated) and
`comp_pit.pitqtrdataus` (quarterly as-restated).

## Tables

### `comp_202601.funda` — Annual fundamentals

The workhorse for paper replications. 929,418 rows, 948 columns,
covering 1950–present (depending on the variable).

| Column | Type | Description |
|--------|------|-------------|
| `gvkey` | `Nullable(String)` | Stable company identifier. **This is the join key to CRSP — never use `cusip` or `tic` as a join key, those change.** |
| `datadate` | `Nullable(String)` | Balance sheet date of the fiscal year-end (YYYY-MM-DD as a string in this extract). **Align B/M ratios to December of the prior calendar year**, not to `datadate` directly (see *Fiscal year alignment* below). |
| `fyear` | `Nullable(Int32)` | Fiscal year (4-digit year, e.g. `2024`). Equivalent to `YEAR(datadate)` for most firms but not all — firms with non-December fiscal year-ends will have `fyear` ≠ calendar year of `datadate`. |
| `indfmt` | `Nullable(String)` | Industry format. **Filter:** `IN ('FS','IN')` for industrial+financial-services. See *Filters* below. |
| `consol` | `Nullable(String)` | Consolidation code. **Filter:** `= 'C'` for consolidated statements only. |
| `popsrc` | `Nullable(String)` | Population source. **Filter:** `IN ('D','I')` for domestic (US/Canada) firms. |
| `datafmt` | `Nullable(String)` | Data format. **Filter:** `IN ('STD','SUMM')` for standardized / summary data (excludes pre-1987 raw). |
| `tic` | `Nullable(String)` | Ticker (CHANGES over time — see *Gotchas*). |
| `cusip` | `Nullable(String)` | 6-character CUSIP Issuer Number (CHANGES — use only to validate, never to join). |
| `conm` | `Nullable(String)` | Company name (current). |
| `sich` | `Nullable(Int32)` | Standard Industrial Classification (SIC) code (historical). |
| `naics` | not in `funda` (use `company.naics` or `security.naics`) | North American Industry Classification System. |
| `fic` | `Nullable(String)` | Foreign-incorporation code (`USA` for US firms). |
| `curcd` | `Nullable(String)` | Reporting currency (`USD` for US). |
| `bkvlps` | `Nullable(Float64)` | Book value per share (Compustat-calculated; fully split-adjusted). **See recipe below.** |
| `ceq` | `Nullable(Float64)` | Common equity (book). Does **not** include intangibles adjustment. |
| `ceqt` | `Nullable(Float64)` | Common equity (total) — includes treasury stock and other reclassifications. |
| `seq` | `Nullable(Float64)` | Stockholders' equity (parent). **Includes preferred stock** — for the FF B/M convention you almost always want `ceq` or `ceqt`, not `seq`. |
| `at` | `Nullable(Float64)` | Total assets. |
| `lt` | `Nullable(Float64)` | Total liabilities. |
| `txdb` | `Nullable(Float64)` | Deferred taxes (balance sheet). **Often missing in older years** — the FF convention adds it when present and treats missing as 0. |
| `csho` | `Nullable(Float64)` | Common shares outstanding (in **millions** — different unit than CRSP `shrout` which is in **thousands**). |
| `prcc_f` | `Nullable(Float64)` | Price close, fiscal year-end. In reporting currency (USD for US). |
| `revt` | `Nullable(Float64)` | Revenue (total). |
| `ib` | `Nullable(Float64)` | Income before extraordinary items. |
| `ni` | `Nullable(Float64)` | Net income. |
| `oibdp` | `Nullable(Float64)` | Operating income before depreciation (EBITDA proxy). |

The full 948 columns include every S&P line item in every statement,
plus all the supplementary disclosures (pensions, leases, segments,
R&D, etc.). Most papers use 5–20 of these.

### `comp_202601.fundq` — Quarterly fundamentals

2,113,095 rows, 648 columns. Same identifier flags (`gvkey`,
`indfmt`, `consol`, `popsrc`, `datafmt`) but with `datadate` aligned
to the quarter-end.

| Column | Type | Description |
|--------|------|-------------|
| `gvkey` | `Nullable(String)` | Stable company identifier. |
| `datadate` | `Nullable(String)` | Quarter-end date. |
| `fyearq` | `Nullable(Int32)` | Fiscal year. |
| `fqtr` | `Nullable(Int32)` | Fiscal quarter (1–4). |
| `rdq` | `Nullable(String)` | Report date — the date the company actually reported this quarter (NOT the period-end). **This is the field to use to detect restatements and to know when information became public** — for the MAX paper or any paper that needs to know "when was this information available to investors". |
| `atq` | `Nullable(Float64)` | Total assets (quarterly). |
| `ltq` | `Nullable(Float64)` | Total liabilities (quarterly). |
| `seqq` | `Nullable(Float64)` | Stockholders' equity (quarterly, parent). |
| `ceqq` | `Nullable(Float64)` | Common equity (quarterly). |
| `ibq` | `Nullable(Float64)` | Income before extraordinary items (quarterly). |
| `niq` | `Nullable(Float64)` | Net income (quarterly). |
| `cshoq` | `Nullable(Float64)` | Common shares outstanding, quarter-end. |
| `prccq` | `Nullable(Float64)` | Price close, quarter-end. |

> **Note:** `fundq` has fewer "per-share" book equity fields than
> `funda`. There is no `bkvlps` / `bkvlpq` split per se; for quarterly
> B/M work, derive book equity from `ceqq + txdbq` (if present) or
> `seqq` (less precise).

### `comp_202601.security` — Security master

75,578 rows, 16 columns. The security-level companion to
`company`. This is the table to use for **issue-level** identifiers
(CUSIP history, ticker history, share-class-level `iid`s) and
exchange listings.

### `comp_202601.company` — Company header

56,841 rows, 40 columns. One row per `gvkey`. Holds
company-descriptor fields that don't change with security: `conm`
(current name), `gsector`, `ggroup`, `gind`, `gsubind` (GICS
hierarchy), `add1`–`add4` (HQ address), `phone`, `weburl`,
`state`, `country`, `fic`, `curcd`, `sich` (SIC code, historical),
`naicsh` (NAICS code, historical), `ipodate`, `yearfounded`.

### `comp_202601.names` — Name history

47,040 rows, 11 columns. Tracks every name change a company has
gone through. Use this for historical-name lookups (e.g. when
replicating a paper that references a 1980s company name).

## Other useful tables in `comp_202601`

### `company` / `security` / `names` (identifier layer)

Already covered above. Key point: `gvkey` is the only join key you
should trust across time. `tic` and `cusip` both change.

### `comp_pit` (point-in-time)

The right choice when you need a backtest that doesn't
look-ahead. Two tables you'll use most:

- `comp_pit.pithistdataus` (32,504,895 rows, 287 cols) — the full
  Compustat annual file in PIT form. Every row carries a `pitdate`
  indicating when the data was first known.
- `comp_pit.pitqtrdataus` (quarterly PIT) — same idea for
  `fundq`.

For a replication that "just needs the latest available book equity
at portfolio formation time", PIT is overkill. For a paper that
specifically asks "what was the value of book equity at month t-1,
using only information available at month t-1?", PIT is required.

### `comp_202601.funda_fncd` and `fundq_fncd`

`funda_fncd` carries the **footnote codes** for every line item in
`funda`. Useful for filtering out data points with bad audit opinions
or restatement issues. Each `funda` column has a paired footnote
column in `funda_fncd` (e.g. `at` ↔ `at_.fn`).

### `comp_202601.seg_*` (segment data)

Segment-level revenue, operating income, and assets by
business/geography. Not relevant for the MAX paper; relevant for
papers that use HHI, segment-based concentration measures, or
geographic exposures.

## CRSP-Compustat link (CCM)

Compustat doesn't ship with a CRSP link. The link lives in **CRSP**,
in the `ccmxpf_*` family of tables. This is the standard
"CRSP/Compustat Merged" link maintained by CRSP.

### `crsp_202601.ccmxpf_linktable` — the standard FF link

92,711 rows. Columns: `gvkey, lpermno, lpermco, linktype, linkprim,
usedflag, linkdt, linkenddt, liid`.

| Column | What it is |
|--------|-----------|
| `gvkey` | Compustat company identifier (join key to `comp_202601.*`) |
| `lpermno` | CRSP permanent security identifier (join key to `crsp_202601.dsf`/`msf`) |
| `lpermco` | CRSP permanent **company** identifier (groups all share classes of one company together) |
| `linktype` | `LC` = link confirmed by Compustat; `LU` = link unconfirmed; `LX` / `LD` / `LS` / `LR` = inactive forms |
| `linkprim` | `P` = primary link (the "best" link for that `gvkey-lpermno` pair); `C` = Compustat-confirmed secondary; `J` = join-only secondary |
| `usedflag` | `1` = recommended for academic use; `0` = not recommended |
| `linkdt` | First date the link is valid (often `1900-01-01` for permanent links) |
| `linkenddt` | Last date the link is valid (`2099-12-31` if still active) |
| `liid` | Compustat-issue-id (links to `comp_202601.security.iid`) |

**Standard FF filter** (the one to use unless the paper says
otherwise):

```sql
WHERE linktype IN ('LC', 'LU')
  AND linkprim IN ('P', 'C')
  AND usedflag = 1
```

This is what almost every academic paper that uses fundamentals does.
The exceptions (e.g. wanting only post-2000 data) are stated
explicitly.

**Temporal join** (the link is point-in-time, not static). To find
the right `gvkey` for `permno` at month t:

```sql
SELECT ccm.gvkey, ccm.lpermno
FROM crsp_202601.ccmxpf_linktable ccm
WHERE ccm.lpermno = {permno}
  AND ccm.linktype IN ('LC', 'LU')
  AND ccm.linkprim IN ('P', 'C')
  AND ccm.usedflag = 1
  AND ccm.linkdt <= {t_date}
  AND (ccm.linkenddt >= {t_date} OR ccm.linkenddt IS NULL)
```

A given `permno` can have multiple `gvkey`s over time (when S&P
reassigns the link); the temporal predicate picks the right one.

### Other CCM tables in `crsp_202601`

- `ccm_qvards` — quarterly PIT lookup, **currently empty in this
  ClickHouse instance.** Use `ccmxpf_linktable` instead.
- `ccm_lookup` — header-level lookup, useful for joining at the
  `permco` level (groups share classes).
- `ccmxpf_lnkhist` / `ccmxpf_lnkrng` / `ccmxpf_lnkused` — alternate
  history/range forms of the link; usually `ccmxpf_linktable` is all
  you need.

## Derived fields

### Book equity (Fama-French convention)

For a US industrial firm with fiscal year ending in calendar year
`Y`, **book equity at the end of fiscal year `Y`** is:

```
book_equity_Y = ceq_Y + txdb_Y                # primary formula
book_equity_Y = ceqt_Y + txdb_Y               # if ceq is missing
book_equity_Y = seq_Y  - pstk_Y + txdb_Y      # if ceq and ceqt both missing
```

Where `pstk` is preferred stock (redemption value).

> **From the 2003 User's Guide (p. 209-210):** S&P's own
> "Common Equity – Liquidation Value" (`bkvlps` is per-share;
> `ceq`/`ceqt`/`seq` are the aggregate fields) is defined as common
> stock + capital surplus + retained earnings + self-insurance
> reserves + capital stock premium, *less* treasury stock +
> accumulated unpaid preferred dividends + excess liquidating value
> of preferred over carrying value. This is roughly `ceq` + `txdb`
> in modern data. The "Common Equity – Tangible" (item 11) subtracts
> intangibles on top; FF do not subtract intangibles in the canonical
> B/M definition.

**The deferred-tax-add-back** (`+ txdb`) is what Davis, Fama and
French explicitly recommend in the B/M construction memo. It adjusts
for the fact that `ceq` already nets out deferred tax liabilities;
the standard B/M wants the gross-of-deferred-tax book equity. If
`txdb` is missing for an older firm-year, use 0.

**The `bkvlps` shortcut** (book value per share) avoids the
formula: just multiply by shares:

```
book_equity = bkvlps * csho
```

This is S&P's own calculation and is correct for most firms
post-1987. Watch for split-adjustment issues (see *Gotchas*).

### Market equity (mkt cap)

The MAX paper convention (and the convention in most US equity
papers) uses **CRSP for market equity**, not Compustat:

```
market_equity_t = abs(prc_t) * shrout_t * 1000   # CRSP dsf, in dollars
```

CRSP `prc` is in dollars (with sign convention — see the CRSP doc),
`shrout` is in thousands of shares, so the product is in dollars.

> **Why CRSP, not Compustat:** CRSP has the most up-to-date price
> and share count for the security (Compustat's `prcc_f` is fiscal
> year-end, and `csho` is fiscal year-end; both are stale for
> month-t formation). The MAX paper explicitly says: "we use share
> prices and shares outstanding [from CRSP] to calculate market
> capitalization." (page 4, §II.A)

### Book-to-market ratio (B/M)

The B/M used in cross-sectional regressions in the MAX paper, and
in the FF data library:

```
B/M_t = book_equity_(Y-1) / market_equity_t
```

where `Y-1` is the prior calendar year's fiscal year-end book
equity, and `t` is the portfolio formation month.

**Fiscal year alignment** — this is the gotcha most agents get
wrong. The book equity value from `funda` is for fiscal year ending
in calendar year `Y`. For a portfolio formed in June of year `T`, the
paper uses **the book equity from fiscal year `T-1`** (or more
precisely, the most recent fiscal year-end that is at least 6 months
prior to the formation date). The standard implementation is:

- Map each month `t` to "prior December": `Y-1 = YEAR(t) - 1` if
  `MONTH(t) >= 6`, else `Y-1 = YEAR(t) - 2`.
- Take `book_equity` for fiscal year `Y-1`.

For the MAX paper (sample 1962–2005, monthly portfolios), the
convention is even simpler: the B/M uses **December of the prior
year** (the "December-of-Y-1" convention, where Y-1 is the prior
calendar year). For most firms with December fiscal year-ends, this
is just `funda` for fiscal year `Y-1`.

For firms with **non-December fiscal year-ends** (e.g. a June
fiscal year company), the December-of-Y-1 rule effectively means
"the most recent fiscal year-end on or before June of year Y",
which is the **June of year Y-1** fiscal year-end for those firms.
The 2003 User's Guide (p. 209) explicitly notes this:

> "All annual data reported on a January through May (01-05) fiscal
> year basis is considered to be in the prior calendar year since the
> majority of the months fall in the prior calendar year. Thus, Book
> Value per Share for 1995 for a May fiscal year company will be in
> the 1996 calendar year."

Use `fyear` (not `YEAR(datadate)`) to map between calendar year and
fiscal year for B/M. The 2003 guide's rule ("Jan–May fiscal year →
prior calendar year") is the same rule the FF data library applies.

### Operating profitability / earnings

The MAX paper's `illiquidity` and earnings variables come from
CRSP, not Compustat. But for papers that need fundamentals-based
profitability (ROE, ROA, gross profitability):

```
ROE_t = ib_t / seq_(t-1)                       # return on equity
ROA_t = ib_t / at_(t-1)                        # return on assets
GP/AT_t = (revt_t - cogs_t) / at_(t-1)         # gross profitability / assets
```

`cogs` is `cogs` (cost of goods sold) in `funda`. The
Novy-Marx profitability measure uses the gross-profit / assets
ratio.

## Filters (typical for academic replications)

### Standard Compustat quality filter (the "Fama-French filter")

Applied to `funda` (or `fundq` with the analogous columns) before
any cross-sectional work:

```sql
WHERE indfmt IN ('FS', 'IN')    -- industrial + financial services
  AND consol = 'C'              -- consolidated statements only
  AND popsrc IN ('D', 'I')      -- domestic firms (US/Canada)
  AND datafmt IN ('STD', 'SUMM')  -- post-1987 standardized data
```

| Flag | What it does |
|------|-------------|
| `indfmt = 'FS'` or `'IN'` | Restricts to the standardized Industrial/Financial-Services format. `'FS'` covers banks, insurance, etc. (post-2008 split into separate format). `'IN'` is the pre-2008 industrial-only format. Excludes 'RA' (Research Annual — inactive firms only). |
| `consol = 'C'` | Consolidated statements (eliminates `P` = parent-only and `S' = subsidiary-only). |
| `popsrc IN ('D', 'I')` | Domestic (US/Canada) firms. Excludes `'F'` (foreign) and `'A'` (additional — overlapping securities). |
| `datafmt IN ('STD', 'SUMM')` | Standardized post-1987 data. Excludes `'HIST'` (pre-1987 raw format) and `'SFNDS'` (S&P's pre-1998 Standard & Poor's format — overlapping with HIST). |

**These codes are conventions from post-2014 Compustat
documentation, not from the 2003 User's Guide I worked from. The
2003 guide documents the values `indfmt`, `consol`, `popsrc`,
`datafmt` only as database fields, not as coded value lists.**
[verify] against a current Compustat variable reference before
relying on the exact code lists in a paper that does cross-sector
work.

The filter is a 4-way AND. Skipping any one will over-count firms
(typically by 5–15%).

### Active-firm filter (avoid look-ahead from inactive firms)

```sql
-- A firm is "active" in fiscal year Y if it appears in BOTH
--   - comp_202601.funda with datadate in (Y, Y+1)
--   - crsp_202601.dsf/msf with permno valid in (Y, Y+1)
```

A firm that appears in Compustat for fiscal year Y but has no
CRSP observation in the year following Y is typically a recently
delisted firm; using it for the B/M denominator in month T with T ≤
Y+1 creates a look-ahead bias. The FF data library applies this
filter via the CCM `usedflag = 1` filter plus a CRSP coverage
check.

### Fiscal-year-uniqueness filter (one observation per firm per fiscal year)

```sql
-- comp_202601.funda can have multiple rows for the same gvkey-fyear
-- (interim restatements). Take the row with the most recent filing
-- date.
ROW_NUMBER() OVER (PARTITION BY gvkey, fyear ORDER BY filing_date DESC) = 1
```

The `filing_date` is not directly in `funda`; it's in
`co_filedate`. Join to get it.

## Gotchas

- **`ceq` vs `seq` vs `ceqt` vs `bkvlps` — pick one and stick with
  it.** They differ:
  - `ceq` (item 60) = common equity, the standard FF choice
  - `seq` (item 216) = total stockholders' equity (includes preferred
    stock) — wrong for FF B/M
  - `ceqt` (item 226) = total common equity (with reclassifications) —
    used by some post-2000 papers
  - `bkvlps` (item 38, per share) = S&P's calculated book value per
    share — adjusted for splits, so the implied book equity is
    `bkvlps × csho` and may differ from `ceq + txdb` by ~1% for
    firms with frequent splits
  For B/M replications, use the same definition the paper used.
  The MAX paper (and FF) uses `ceq + txdb` (with `seq` for older
  years when `ceq` is missing).

- **Bank and utility firms** are in `funda` but their income
  statement and balance sheet structure is fundamentally different
  (interest income, deposits, etc.). The `fic = 'USA'` filter is not
  enough — you also want to exclude SIC codes 6000-6999 (banks) and
  4900-4999 (utilities) for non-bank/utility-only replications. (Or
  keep them and use a different `fic` / `sich` band; the paper
  matters.)

- **`tic` and `cusip` are NOT stable identifiers.** Both change over
  the life of a firm (CUSIP at every major corporate action;
  tickers recycled). The `tic` in `funda` is the **current** ticker.
  To get historical tickers, use `comp_202601.security` (issue
  history) or join via `gvkey` to CRSP and use the CRSP ticker from
  the matching date.

- **`bkvlps` is split-adjusted.** This is a feature for PDE-style
  comparisons across time, but a trap for B/M: if you do
  `bkvlps × csho` to get book equity, you're getting
  fully-split-adjusted book equity, but `csho` is also
  split-adjusted. The product is consistent. **But** if you ever
  mix `bkvlps` (split-adjusted) with a non-adjusted share count,
  you get garbage. Always pair `bkvlps` with `csho` (both
  split-adjusted) or use `ceq` (which is not split-adjusted) with
  `csho` (which is split-adjusted, so you'd need to undo the
  adjustment). The safe path is `bkvlps × csho` or `ceq + txdb`.

- **Negative equity** is real and common (distressed firms, recent
  IPOs, M&A). FF winsorize B/M at the 0.5/99.5 percentiles (and
  the MAX paper follows the convention). Don't drop negative
  equity — drop firms with `at <= 0` (broken balance sheet) only.

- **`popsrc` and `indfmt` interact with restated data.** A
  restatement can change the `consol` flag (e.g. a previously
  unconsolidated subsidiary now consolidated) and you can end up
  with two rows for one (gvkey, fyear) that both pass the filter.
  Use the row-numbering trick in *Filters* above.

- **Compustat fiscal year ≠ calendar year.** A firm with a June
  fiscal year-end has `fyear = Y` for the year ending June Y. The
  MAX paper's B/M uses the December-of-Y-1 rule, which means
  June-fiscal-year firms effectively use `fyear = Y-1` (the
  June-of-(Y-1) fiscal year-end). Use `fyear` for the alignment,
  not `YEAR(datadate)`.

- **`fic` and `curcd` are different.** `fic` = country of
  incorporation (e.g. `USA` for a US firm incorporated in
  Delaware). `curcd` = reporting currency. A Canadian firm
  incorporated in Canada reports in CAD; a Canadian firm
  incorporated in the US reports in USD.

- **`datadate` is a string, not a date.** In this ClickHouse
  extract, `datadate` is a `Nullable(String)`, not a `Date`. Cast
  it explicitly when comparing.

- **`fundq` is a moving target** — companies restate, mergers
  happen, and Compustat's `fundq` reflects the restated version.
  If your paper needs **point-in-time** quarterly data (the value
  as it was known on date d), use `comp_pit.pitqtrdataus` with
  `pitdate <= d`.

## Cross-references

- **CRSP data (prices, returns, market cap, identifiers)** — see
  `references/data/crsp.md`. CRSP `dsf.prc × dsf.shrout × 1000`
  is the canonical market equity for US papers. The MAX paper
  uses CRSP-only for prices; the CRSP doc covers the `prc` sign
  convention, `shrout` units, and the `ccmxpf_linktable` CCM
  cross-reference.

- **Kenneth French's data library** (Fama-French factors: Mkt-RF,
  SMB, HML, MOM, RF) — see `references/data/fama_french.md` (to
  be written). The MAX paper's 4-factor alpha calculation uses
  the FF factors. **Note: FF factors are not currently in
  ClickHouse** — they need to be ingested from
  `mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html`.

- **Deterministic primitives** — the agent should not re-implement
  B/M, ROE, market equity, or any of the derived fields above.
  These should be one-line calls to a shared library (to be
  written). The recipes in this file are the spec for what those
  primitives should compute.

## Primary source

The 2003 Compustat North America User's Guide (PDF, 735 pages) is
the primary source for the variable definitions documented here. It
lives at:

```
/home/ra_yeye/2026_projects/rep-it-up/comp_manual_pdf/compustat_users_guide-2003.pdf
```

Repo root, gitignored, fetched on demand. **Caveat:** this is a
2003 document. Compustat has added variables and conventions since
then (notably the PIT service, the post-2008 GICS reclassification,
and the modern indfmt/consol/popsrc/datafmt code lists). The
**conceptual** definitions (what `bkvlps` is, what B/M means, the
FF filter rationale) are stable; the **code lists** in
*Filters → Standard Compustat quality filter* above come from
post-2014 conventions and should be re-verified against a current
Compustat variable reference before being treated as authoritative.

Read with the project venv:

```bash
uv run python -c "
import pymupdf
doc = pymupdf.open('/home/ra_yeye/2026_projects/rep-it-up/comp_manual_pdf/compustat_users_guide-2003.pdf')
print(doc[N].get_text())
"
```

Key page index (from the User's Guide TOC):

| Item | Page |
|------|-----:|
| Perm Number / CUSIP Cross Reference (description) | 7 (PDF p. 32) |
| Calendar Year / Fiscal Year terminology | 3 (PDF p. 43) |
| Accessing Annual Data, Calendar Year vs Fiscal Year | 6 (PDF p. 46) |
| Restated Quarterly Data (4Q, 3Q, 2Q, 1Q examples) | 9–11 (PDF p. 49–51) |
| Compustat Industrial vs Utility vs Bank item mapping | 21–47 (PDF p. 63–89) |
| Book Value per Share (full definition) | 28 (PDF p. 209–210) |
| Common Equity – Liquidation Value (item 235) | 40 (PDF p. 221) |
| Common Equity – Total (item 60) | 41 (PDF p. 222) |
| Active/Inactive Flag (item) | 12 (PDF p. ~193) |
| Assets – Total (item 6) | 24 (PDF p. 205) |
| PDE File data items (mnemonic ↔ item) | 35 (PDF p. 563) |
