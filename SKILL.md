---
name: x2strategy
description: >
  ALAGENT X2Strategy: any research input (PDF paper, Markdown draft,
  DOCX report, text notes, or keyword search) → structured strategy
  specification → executable Backtrader code → backtest → diagnosis report.
  Two core capabilities: (1) paper2spec extracts multi-strategy specs from
  any document via 5-layer LLM extraction, and (2) spec2code generates
  validated Backtrader code, runs backtests, and compares against paper
  metrics. Use this skill whenever the user wants to analyze a quant paper,
  extract trading strategies, generate strategy code, run a backtest, search
  for papers, or go end-to-end from any input to executable results. Also
  triggers on: "look at this paper", "what strategies does this use",
  "implement this strategy", "search for momentum papers", "turn this into
  code", or any request about quantitative finance research → implementation.
  Even if the user doesn't mention "strategy" explicitly — if they provide a
  finance paper or research document, use this skill.
argument-hint: "[paper.pdf | strategy.md | report.docx | search query]"
metadata:
  version: 0.6.1
  author: ALAGENT AI (alagent-ai)
  tags: [quantitative-finance, paper-parsing, strategy-extraction, code-generation, backtesting]
---

# X2Strategy

Any finance-related input → Strategy spec → Executable code → Backtest → Diagnosis.

## Capabilities

| Capability | What it does | Deep dive |
|-----------|-------------|-----------|
| **paper2spec** | Any document (PDF/MD/DOCX/TXT) → structured strategy specification | [references/paper2spec.md](references/paper2spec.md) |
| **spec2code** | Strategy spec → Backtrader code → validate → backtest → diagnosis | [references/spec2code.md](references/spec2code.md) |

Input format auto-detected from extension:

| Format | Extension | Notes |
|--------|-----------|-------|
| PDF (papers) | `.pdf` | LightOnOCR-2 → markdown with tables + equations |
| Markdown (drafts) | `.md`, `.markdown` | Direct text read |
| DOCX (reports) | `.docx` | python-docx (requires `uv sync --extra docx`) |
| Plain text | `.txt` | Direct read |

---

## Interaction Principles

**You are the executor. The user is the requester.**

- Run tools silently, present results and insights in natural language.
- Never show CLI commands (`uv run python scripts/...`) unless user asks.
- Offer next actions conversationally: "Would you like me to implement the second strategy as well?"

When reporting results, focus on **what you found**, not how:

```
❌ Bad:  "I ran `uv run python scripts/analyze.py paper.pdf` and got 3 strategies."
✅ Good: "This paper contains 3 independent strategies: [1] minimum distance method, [2] ADF stationarity, and [3] Johansen cointegration. Which one should I implement?"
```

**Use interactive tools aggressively.** When your platform provides
interactive question tools — `vscode_askQuestions` (VS Code Copilot),
`AskUserQuestion` (Claude Code), or equivalent — use them for ALL
user-facing choices. Interactive tools present clickable options,
which is faster and less error-prone than asking the user to type.

Apply interactive tools to:
- First-Run Setup choices (workspace path, API provider, key input)
- Input confirmation (proceed / add clarification / adjust settings)
- Review checkpoints and implementation approval
- `needs_human_review` resolution after extraction or repair
- Search result selection (pick papers from a numbered list)
- Any scenario where the user picks from options

If no interactive tool is available, fall back to numbered text menus.

### Progress Marker Protocol

Run tools silently, but make long pipelines **traceable**. While working through
the eight-step workflow, prefix status lines with one of three structured
markers so the user (and any outer parser) can follow phase progress without
reading raw command output. The markers carry the discipline; the surrounding
prose stays natural-language.

| Marker | When to emit | Format |
|--------|-------------|--------|
| `[PROGRESS]` | Entering or finishing a workflow step | `[PROGRESS] <step> — <one-line status>` |
| `[ARTIFACT]` | A concrete file was written | `[ARTIFACT] <workspace-relative-path> — <what it is>` |
| `[ERROR]` | A step failed or a check did not pass | `[ERROR] <step> — <what failed> — <next action>` |

Rules:
- One marker per line, at the start of the line, then plain language.
- Every `[ARTIFACT]` must name a concrete workspace-relative path that was
  actually written (this satisfies the Output Paths contract below).
- `[ERROR]` must always be followed by what you will do next (retry once,
  stop and report, ask the user) — never a bare failure.
- Markers supplement natural-language reporting; they do not replace it. Still
  explain *what you found*, not *how you ran it*. Never show the CLI command.

Example:

```
[PROGRESS] paper2spec/extract — extracting strategy specs from inputs/content.json
[ARTIFACT] replications/upsa/inputs/spec.json — 1 strategy, 4 indicators, 3 logic steps
[PROGRESS] HITL review — 1 open needs_human_review item, asking for resolution
```

### Iteration & Retry Discipline

Generation and repair must be bounded. Translate the backend's hard turn gate
(`--max-turns`) into agent discipline:

- **Generate once, then at most one smoke-test repair round.** Write the code,
  validate, run. If it fails, apply one targeted fix round (see the triage flow
  in [references/spec2code.md](references/spec2code.md)) and re-run.
- **If it still fails after that one repair round, stop and report.** Emit an
  `[ERROR]` line, summarize what failed and the most likely root cause, and ask
  the user how to proceed. Do not keep patching incrementally.
- **A single runtime-error category gets at most 3 fix attempts.** If the same
  error class persists, the strategy logic likely needs a fundamentally
  different approach — say so rather than tweaking further.
- Never silently loop. Each retry must be visible via a `[PROGRESS]` or
  `[ERROR]` marker so the user can see the gate working.

### First Response Contract

For any paper2code, research-to-code, or “use this skill” request, the first response must not promise immediate implementation. First identify the visible inputs, then use an interactive dialog to confirm setup status, input files, extra instructions/clarifications, and intended workflow scope. Only proceed after that confirmation.

---

## First-Run Setup

On first use, walk through three steps. If a step is already configured, report the detected value and ask the user to confirm or change it. Always confirm task scope before extraction or implementation. Persist all choices to `.env` (gitignored) for session stability.

### Step 1 — Workspace Location

Present choice via interactive tool:
- `./replications/` (default, recommended)
- Custom path

Write `PAPER2SPEC_REPLICATIONS_PATH=/absolute/path` to `.env`.
Scan the directory for existing `inputs/metadata.json` to detect prior analyses.

### Step 2 — LLM API Key

Check env for `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY`, `OPENAI_API_KEY`,
or `ANTHROPIC_API_KEY`.
If none found, present via interactive tool:

```
An LLM API key is required for strategy extraction and code generation. Recommended options:
  1. DeepSeek (best cost-performance, about ¥0.7 per paper) → https://platform.deepseek.com
  2. OpenRouter (one key for access to multiple models) → https://openrouter.ai/keys
Please provide your API key and tell me which provider it belongs to.
```

Once received, write key + matching model to `.env`, then verify:
`uv run python -c "from paper2spec.llm import chat; print(chat('Say OK'))"`.

See [references/skill-internals.md](references/skill-internals.md) for
`.env` format examples per provider.

### Step 3 — Python Environment

```bash
cd <skill-path>
uv sync --all-extras    # Recommended: installs everything
```

If `uv` unavailable: `pip install -e ".[codegen,agent,dev]"`.
Always use `uv run` to execute scripts (auto-activates correct venv).

See [references/skill-internals.md](references/skill-internals.md) for
selective install options and non-uv alternatives.

### Completion

Once configured, confirm naturally with examples:

```
✅ Setup complete. You can now ask me for tasks directly, for example:

  • "Analyze this paper" + attach a PDF file
  • "Search for papers about momentum trading"
  • "Implement this strategy based on this paper" + provide the file path
  • "I wrote a strategy draft in Markdown; extract the spec and generate code"
  • "Compare the strategy differences between these two papers"

Just tell me what you want to do, and I will handle the rest.
```

---

## Single Workflow

Use one workflow for all tasks. Do not choose between competing routers.

**Default: start fresh.** Do not read prior `replications/<slug>` iterations (e.g. `max_v7`, `fip_v3`) unless the user explicitly asks you to. Each replication runs the pipeline from scratch — prior runs bias the agent toward inherited (possibly buggy) choices and waste turns on exploration the user didn't request.

**Self-cap on iterations.** `scripts/run_iteration_agent.sh` refuses to spawn a 6th agent for the same slug (5 max). If you are in agent #5 and the strategy is still failing, **stop patching runtime errors and report to the user**. The next iteration is the maintainer's job — they will inspect `replications/<slug>/results/metrics.json` and `logs/run.log`, then fix the skill (primitive, reference doc, or SKILL.md). Whack-a-mole iteration on a single broken strategy does not produce new information.

**Read the per-signal direction from the spec, do not guess.** The spec's `signals` field (populated by the L8 extractor from the paper) gives each signal's long-leg direction as `high` or `low`. For FIP, ID has `long_leg: low` (continuous info is the long leg); for momentum, PRET has `long_leg: high` (winners). The renderer emits these to `run_config.yaml` under `signals:`. The strategy code reads `cfg["signals"]` and builds the L/S portfolio from the declared direction. **Do not** infer the direction from the paper's prose — v3 guessed and produced a sign-flipped spread.

**Always compute both EW and VW unless the paper only reports one.** Most academic cross-sectional papers report BOTH equal-weighted and value-weighted spreads in the same table (typically Table 2 / 3 / 6). The spec's `weightings_reported: ["EW", "VW"]` (also from the L8 extractor) tells the strategy code which weightings to compute. The spec's single `weighting` field is the primary used for the headline hit-rate; the alternative is for robustness. Write `metrics.json` with the bare key for the primary (e.g. `fip_spread_6m_pct`) and suffixed keys for the alternative (e.g. `fip_spread_6m_pct_ew` / `_vw`). `SUMMARY.md` shows both rows. The validator uses the bare key for hit-rate. **Do not** pick just one weighting — v2 picked EW and missed the spec's VW, producing a low t-stat.

1. **Setup** — verify `.env`, replications path, API key if needed, Python environment, and user-selected scope.
2. **Input confirmation** — identify the paper/spec/data/instruction files or search results; ask whether to add clarification, constraints, selected-plan preferences, known pitfalls, or reference files.
3. **paper2spec: PDF/text to content** — parse the selected document into grounded content artifacts.
 4. **paper2spec: extract** — extract candidate strategy specs/plans from the content plus user instructions. Uses a 9-layer pipeline: L0 (detection) → L1 (metadata) → L2 (table scan) → L3 (target selection: top 3 replication targets) → L4 (data) → L5 (universe) → L6 (signal) → L7 (portfolio) → L8 (execution).
5. **paper2spec: repair/review** — read `references/extraction_quality.md`, retrieve relevant operator pitfalls when high-risk formulas are present, and repair only the selected plan/spec with grounded evidence.
 6. **HITL review** — after repair, inspect `needs_human_review`. **Convention decisions** (price filter, weighting, breakpoints, delisting adjustment, factor model) are resolved autonomously from `references/paper_conventions.md` — do NOT ask the user about these. Apply the default, emit a `[CONVENTION-APPLIED]` log line, and document in `results/SUMMARY.md`. Ask the user **only** for genuinely ambiguous decisions that the paper does not resolve and that have no standard default (e.g. which strategy to extract from a multi-strategy paper, or a methodology with two materially different interpretations). If the user is not reachable, apply the most common interpretation and emit `[HITL-AUTO-RESOLVED]`. After resolving each item, append it to the spec's `convention_resolutions` list (fields: `field_path`, `resolved_value`, `source` = "paper_conventions" | "user" | "auto_resolved") so the resolutions are auditable in `spec.json`.
 7. **Data verification** — read `inputs/spec.json` + `content.md` + `paper2spec/resources/clickhouse_catalog.json`. The catalog is a **20 MB JSON file** — too large to Read directly. Use the **Grep tool** to search it (e.g. grep for `four_factor` or `dsfhdr`); use a `python -c` one-liner only to list database/table names matching a pattern. Its top-level keys are `generated_at`, `host`, `databases`, `database_families`. Use `database_families` to pick the default vintage (e.g. `crsp` → `crsp_202601`, `comp` → `comp_202601`) unless the paper specifies otherwise. **Catalog structure:** `catalog["databases"]` is a **dict** keyed by db name (e.g. `"crsp_202601"`), NOT a list. Each `catalog["databases"][db]["tables"]` is a **dict** keyed by table name (e.g. `"dsf"`), NOT a list. Columns are `catalog["databases"][db]["tables"][tbl]["columns"]` — also a **dict** keyed by column name (e.g. `"ret"`), where each value is a type string (e.g. `"Nullable(Float64)"`). Do NOT iterate with integer indices — use `.keys()` or `.items()`. Map the spec's abstract data needs to concrete ClickHouse columns (e.g. "Book-to-Market" → `bkvlps, ceq, seq, at` from `comp.funda`; daily CRSP → `permno, date, prc, ret, vol, shrout` from `crsp.dsf`). Write `diagnostics/data_requirements.json` with **exactly** this shape (validated by `schemas/data_requirements.schema.json`):

     ```json
     {
       "paper": "Bali, Cakici & Whitelaw (2011) — MAX Effect",
       "requirements": [
         {
           "id": "daily_stock_returns",
           "description": "CRSP daily stock file: returns, price, shares for MAX signal",
           "fields": ["date", "permno", "ret", "prc", "shrout"],
           "date_range": ["1962-01-01", "2006-01-01"],
           "frequency": "daily"
         }
       ]
     }
     ```

     The top-level key MUST be `requirements` (a list); each entry needs `id` + `fields`. Other keys (`paper`, `slug`) are optional metadata. Then run `scripts/extract_requirements.py <slug>/diagnostics/data_requirements.json` to verify those fields exist in the catalog and produce `diagnostics/data_match_report.json` — the script fails loudly (exit 2) if the shape is wrong. This report is the single source of truth for code generation — never fall back to yfinance or hardcoded ticker lists. **Do not attempt to connect to ClickHouse during code generation** — the host is on a private network. Use the catalog JSON and match report for schema info; the generated code connects at runtime via ``os.getenv()``.

     **BLOCKED on insufficient data.** If `extract_requirements.py` writes `diagnostics/BLOCKED.md` and exits non-zero, the data is missing or only partially available. The replication cannot proceed — stop here. Do NOT write `src/strategy.py`. Instead:
     1. Read `diagnostics/BLOCKED.md` to see which requirements are unmatched and which columns are missing.
     2. Write `results/SUMMARY.md` with `Status: ⛔ BLOCKED — insufficient data: <one-line summary from BLOCKED.md>` and a copy of the BLOCKED.md contents. This makes the block visible at the top level where the user looks for results.
     3. Report the block to the user and stop. The user will either add the missing data to ClickHouse, choose a different paper, or adjust the spec to drop the missing fields.
     The block is structural: `BLOCKED.md` is the canonical signal, and `results/SUMMARY.md` makes it visible. The maintainer checking the run dir sees the block immediately, no parsing of `data_match_report.json` required.
 8. **spec2code** — after data verification, read `data_match_report.json` and generate code that queries ClickHouse via HTTP for all data. See `references/spec2code.md` §Data Source for the required pattern. Do not use yfinance or any other external API for data. **For CRSP universe filtering** (share codes / exchange codes), use `utils.apply_universe_filter(daily, fetch_data_cached, ...)` instead of calling `fetch_data_cached` directly on `dsenames` or `dsfhdr` — the primitive does a point-in-time merge so a stock is included only for dates when it was actually a common stock (see `utils/INDEX.md`).

    **Pre-generation checklist** (do this BEFORE writing `strategy.py`):
    1. Read `references/data/crsp.md` §Gotchas (dsenames date-filter, `prc` abs(), `ret` sentinels, `dsfhdr` vs `dsenames`)
    2. Read `utils/INDEX.md` — find the canonical pipeline for your strategy type and the primitives you'll call
    3. Confirm `data_match_report.json` has ≥75% coverage; resolve gaps before coding
 9. **Validation/backtest/diagnosis** — validate generated code, run available checks/backtests, then run `scripts/validate_replication.py <slug>` to compare the backtest output against the paper-claimed replication targets (from L3). The validator searches `metrics.json` recursively for keys matching each target's `id` — but the generated code should also write each `id` as a top-level key in `metrics.json` for reliability. The validator produces `results/validation.json` with a per-target diff + hit-rate. **Before blaming extraction for a mismatch:** grep `inputs/content.md` for the paper-claimed value to verify it was extracted correctly. If the value matches the paper text, the problem is in the code or the primitives — investigate the implementation, not the extraction. Compare against expected or reference outputs, summarize mismatches, then ask what to do next.

No bypass: never silently chain extraction → repair → implementation. User-provided papers, instructions, data files, existing specs, or reference outputs are evidence, not permission to skip review or HITL. Never generate code that uses yfinance or hardcoded ticker lists — always read `data_match_report.json` and query ClickHouse.

When previous Copilot, VS Code, or agent logs are mentioned, verify that the referenced path exists and contains the needed files before using them. If the path is missing, empty, or incomplete, regenerate the required artifacts from the original paper/instructions/data instead of relying on the log summary.

## Output Paths

Default generated artifacts go under `PAPER2SPEC_REPLICATIONS_PATH/<slug>/`, where `<slug>` is the paper or task slug confirmed with the user. If a custom output path is requested, confirm it before writing files.

### Directory layout (the per-paper contract)

Every paper replication has the same nested structure. **All scripts and
LLM-generated code MUST use `paper_layout(slug)` from
`paper2spec/paths.py`** rather than constructing paths by hand — that's
the single source of truth for this layout.

```
<slug>/
├── paper/                     # source PDF (large; usually gitignored per-paper)
│   └── original.pdf           # REQUIRED: agents that fail to copy the PDF here are broken
├── inputs/                    # paper2spec artifacts (parse + extract + metadata)
│   ├── content.json
│   ├── content.md
│   ├── spec.json
│   ├── spec.md
│   └── metadata.json
├── diagnostics/               # mid-pipeline ONLY: data matching, conventions
│   ├── data_requirements.json
│   ├── data_match_report.json
│   └── operator_pitfall_context.md
├── src/                       # generated strategy code
│   └── strategy.py
├── data/                      # parquet caches (gitignored per-paper)
│   └── *.parquet
├── results/                   # spec2code outputs
│   ├── SUMMARY.md             # READ FIRST: hit-rate, per-target table, evidence links
│   ├── validation.json        # machine-readable: per-target diff + hit-rate
│   ├── metrics.json           # all raw metrics
│   ├── pnl_curve.png          # cumulative P&L (fundamental evidence)
│   ├── drawdown.png           # drawdown (fundamental evidence)
│   ├── decile_spread.png      # per-decile bar chart
│   ├── decile_spread.csv      # per-decile returns table
│   ├── fama_macbeth.json      # FM regression output (when applicable)
│   └── key_pred/              # one CSV + PNG per key observable factor
│       ├── <factor>.csv
│       └── <factor>.png
├── config/                    # optional run config (run_config.yaml, etc.)
└── logs/                      # runtime logs (per-paper, not at slug root)
    ├── agent_run.log
    └── run.log
```

### File responsibilities

| Path | Owner | Notes |
|------|-------|-------|
| `inputs/content.{json,md}` | `scripts/parse.py`, `scripts/analyze.py` | `PaperContent` — the parsed paper |
| `inputs/spec.{json,md}` | `scripts/extract.py`, `scripts/analyze.py` | `ExtractionResult` (one or more `StrategySpec`) |
| `inputs/metadata.json` | `scripts/analyze.py` | Pipeline run metadata (model, parser mode, instruction files) |
| `diagnostics/data_requirements.json` | agent (spec2code stage) | What data the spec needs — agent maps abstract spec fields to concrete ClickHouse columns |
| `diagnostics/data_match_report.json` | `scripts/extract_requirements.py` | What ClickHouse actually has — deterministic verification of the agent's field choices |
| `diagnostics/operator_pitfall_context.md` | `scripts/operator_pitfalls.py` | Retrieved operator-pitfall context for the spec |
| `src/strategy.py` | spec2code LLM | Generated code. One file per paper — no `_1` suffix |
| `data/*.parquet` | spec2code runtime | Local cache, see `assets/backtrader_template.py` |
| `results/SUMMARY.md` | spec2code runtime | THE VERDICT: hit-rate table, per-target paper-vs-ours comparison, P&L description, evidence links |
| `results/validation.json` | `scripts/validate_replication.py` | Machine-readable: per-target diff + hit-rate |
| `results/metrics.json` | spec2code runtime | Sharpe, max DD, total return, all raw metrics |
| `results/pnl_curve.png` | spec2code runtime | Cumulative P&L — fundamental evidence |
| `results/drawdown.png` | spec2code runtime | Drawdown — fundamental evidence |
| `results/decile_spread.{png,csv}` | spec2code runtime | Per-decile VW/EW returns bar chart + raw data |
| `results/fama_macbeth.json` | spec2code runtime | FM cross-sectional regression output (when applicable) |
| `results/key_pred/<factor>.{csv,png}` | spec2code runtime | One per key observable factor |
| `paper/original.pdf` | `scripts/analyze.py` | REQUIRED: copy of the source PDF for self-contained replication |
| `logs/agent_run.log`, `logs/run.log` | `scripts/run_iteration_agent.sh` | Runtime logs of the agent invocation |

### Why this layout (vs the previous flat layout)

The previous flat layout put `content.json`, `spec.json`, `strategy_1.py`,
`data_match_report.json`, and `ssrn-1262416.pdf` all siblings at the
per-paper root. That was hard to navigate, made standalone-repo
publication awkward, and gave no visual distinction between inputs,
diagnostics, and outputs. The nested layout fixes all three, and
`paper_layout(slug)` makes it enforceable.

### Constructor reference

```python
from paper2spec.paths import paper_layout

layout = paper_layout("ssrn_1262416")
layout.ensure()                              # mkdir -p every subdir

layout.input_path("spec.json")               # <root>/inputs/spec.json
layout.diagnostic_path("data_match_report.json")
layout.src_path("strategy.py")               # <root>/src/strategy.py
layout.data_path("crsp_202601_dsf.parquet")
layout.result_path("metrics.json")           # <root>/results/metrics.json
layout.key_pred_path("max_daily_return.png")
layout.config_path("run_config.yaml")
layout.paper_pdf_path()                      # <root>/paper/original.pdf
```

Every status update after file generation should name the concrete
workspace-relative path that was written.

## Deterministic Primitives (the `x2strategy/utils/` contract)

**The agent MUST NOT reimplement** the following operations. They live in
`x2strategy/utils/` as deterministic primitives — same input → same
output, every time. The agent writes only the **paper-specific signal**.
Primitives handle everything downstream.

**Before writing strategy.py, READ `utils/INDEX.md`** — it's the
one-page reference listing every primitive, the canonical call
pattern, and three worked end-to-end patterns (cross-sectional L-S,
single-asset trend-following, FM-with-controls). Pair that with
`tests/test_utils_canonical_usage.py`, which exercises every
primitive on a 2-stock × 3-date fixture in ~7 seconds.

**Between edits to strategy.py, RUN** the canonical-usage test as a
smoke check — if any utility call is wrong, you'll know in seconds
instead of after a 5-minute backtest:

```bash
uv run pytest tests/test_utils_canonical_usage.py -x
```

```python
from utils import (
    assign_quantiles,             # within-date quantile binning
    bin_returns,                  # EW + VW per-bin returns
    long_short,                   # long-short portfolio from bins
    performance_metrics,          # Sharpe / CAGR / max DD / annual vol
    format_metrics,               # pretty-print metrics dict
    plot_cumulative_returns,      # P&L curve (the "every strategy needs this" plot)
    plot_drawdown,                # drawdown over time
    plot_decile_spread,           # per-bin EW + VW bar charts
    plot_performance_comparison,  # multiple portfolios side-by-side
    fama_macbeth,                 # monthly cross-section OLS + Newey-West HAC
    summarize_fama_macbeth,       # formatted table output
)
```

**Use primitives, don't reimplement.** If you find yourself writing
`groupby().apply(pd.qcut)` or `(1 + r).cumprod()` or
`np.sqrt(252) * mean / std`, **stop** and call the primitive instead.
The primitive is unit-tested, deterministic, and used by every other
replication. Reinventing it adds variance to the output across runs.

### Canonical pipeline (cross-sectional / portfolio papers)

For the bulk of academic finance papers (MAX effect, momentum, value,
B/M, etc.) — cross-sectional signals over many stocks, monthly
rebalancing, long-short by bin — the pipeline is always the same:

```python
# 1. Load data from ClickHouse (paper-specific)
df = load_paper_data(...)

# 2. Compute the signal (paper-specific — agent writes this)
df["my_signal"] = compute_signal(df)

# 3. Primitives do the rest:
df["bin"]      = assign_quantiles(df, "month", "my_signal", n_bins=10)
bin_rets      = bin_returns(df, "month", "bin", "ret", "mcap_lag1")
ls            = long_short(bin_rets, "month", "VW", long_bin=10, short_bin=1)
metrics       = performance_metrics(ls["ret"], freq="M")
plot_cumulative_returns(ls, "month", "ret", save_to=layout.result_path("pnl_curve.png"))
plot_drawdown(ls, "month", "ret", save_to=layout.result_path("drawdown.png"))
plot_decile_spread(bin_rets, save_to=layout.result_path("decile_spread.png"))
fm = fama_macbeth(panel, "ret", ["my_signal", "log_mcap", "ret_11_2"], time_col="month")
```

**Skip backtrader entirely** for cross-sectional papers. Backtrader is
only useful for single-asset, event-driven strategies (SMA crossovers,
RSI thresholds). If the spec's `strategy_type` is `equity_long_short`
or similar, do not import `backtrader`.

### When you need Fama-French factors

**Fama-French factors are NOT currently in ClickHouse** (verified by
full catalog scan). If a paper's spec calls for FF factors (Mkt-RF,
SMB, HML, MOM, RMW, CMA) in a Fama-MacBeth regression or 4-factor
alpha:

1. **First**, query `crsp_202601.dsi` for the market return and
   `ea_oneoff.rf` for the risk-free rate. You can compute `Mkt-RF` from
   these.
2. **Then**, attempt to query `ff.factors_monthly` for SMB / HML /
   MOM. If it doesn't exist (`UNKNOWN_TABLE`), **do not fail the run**:
   - Continue with the partial regression (signal + size + momentum,
     no FF controls)
   - Emit a `[WARNING]` noting that FF factors were unavailable
   - Write the limitation into `results/SUMMARY.md`
3. The full FF-factor gap is tracked as TODO #3 in `TODOs.md`. A paper
   that needs FF factors but can't get them is a known-partial
   replication, not a bug.

### Headless plotting — required

Generated code MUST run on a headless server (no GUI). Set
`matplotlib.use("Agg")` as the **first** matplotlib import in any
generated file. All plot calls must use `save_to=Path(...)` — never
`plt.show()`. The primitives in `utils/plot.py` already follow this.

### Per-paper run config — `replications/<slug>/config/run_config.yaml`

Paper-specific settings (date range, universe filter, binning
parameters, FF control table, output list) live in
`config/run_config.yaml`. **This file is auto-generated by
`scripts/analyze.py`** as part of the spec-extraction step — after
`analyze.py` writes `inputs/spec.json`, it also writes
`config/run_config.yaml` in the same run. The agent does not need
to call `scripts/render_run_config.py` separately.

```python
from paper2spec.paths import paper_layout
from utils import load_run_config

layout = paper_layout("<slug>")
cfg = load_run_config("<slug>")            # reads config/run_config.yaml

start = cfg["start_date"]                  # "1976-01-01"
end   = cfg["end_date"]                    # "2007-12-31"
n_bins = cfg["n_bins"]                      # 10
weighting = cfg["weighting"]                # "VW"
forward_lag = cfg["forward_returns_lag"]    # 1
table = cfg["data_sources"]["daily_returns"] # "crsp_202601.dsf"
where = cfg["universe"]["where_clause"]     # "exchcd IN (1,2,3) AND shrcd IN (10,11)"
```

**The generated `strategy.py` MUST load the config instead of
hard-coding paper-specific constants.** Constants like
`N_BINS = 5`, `FORMATION_MONTHS = 12`, `HOLDING_MONTHS = 6`,
`PRICE_FILTER = 5.0`, `SAMPLE_START` / `SAMPLE_END` belong in
`config/run_config.yaml`, not in `strategy.py`. This is a
single source of truth per replication, and the config can be
diffed across paper runs to see exactly what changed.

`scripts/validate_replication.py` warns (non-fatal) if
`config/run_config.yaml` is missing or if `strategy.py` hardcodes
any of the canonical run constants. Both warnings usually mean
the agent forgot to use `load_run_config(slug)` and should
re-generate the strategy.

If the paper is non-standard and needs settings not in the spec,
edit the YAML directly and re-run `analyze.py` (or run
`scripts/render_run_config.py <spec> --force` to refresh).

## Spec2Code Metrics

For every runnable strategy, spec2code should compute and report at least: Sharpe ratio, maximum drawdown, total return, and return value/final portfolio value. If a strategy is not runnable as a broker-connected strategy, report why and still compute the metrics that are meaningful for the confirmed research/backtest contract.

Spec2Code-generated code must cache all network data locally, save headless-safe visual diagnostics, and plot the strategy's own P&L curve plus one CSV + PNG per key observable factor (under `results/key_pred/`).

For US equity strategies, SPY must be included as the market baseline in any asset overlay. See [references/spec2code.md](references/spec2code.md) and [references/data_sources.md](references/data_sources.md) for the required data cache and visualization contract.

---

## Agent Pipeline Flow

```
1. Setup: confirm environment, replications path, keys if needed, and task scope
2. Confirm inputs: paper/spec/data/instructions/search result + clarifications
3. paper2spec: parse PDF/text/doc to content artifacts
4. paper2spec: extract candidate specs/plans
5. paper2spec: select target plan/spec and repair with extraction_quality + matched pitfalls
6. HITL: resolve convention decisions autonomously from paper_conventions.md; ask user only for genuinely ambiguous selections
7. Data verification: Grep the 20MB clickhouse_catalog.json (not Read). Map abstract spec fields to concrete ClickHouse columns, write data_requirements.json with the {requirements: [{id, fields, ...}]} shape, run extract_requirements.py to verify and produce data_match_report.json
8. spec2code: generate code using matched tables, validate, run backtest
9. Diagnose: run backtest, then validate_replication.py for per-target hit-rate. Before blaming extraction, grep content.md to verify paper values.
```

For code generation patterns: [references/spec2code.md](references/spec2code.md)
For Backtrader patterns: [references/backtrader_patterns.md](references/backtrader_patterns.md)

---

## Internal Toolchain

Agent-only. Run silently; present results in natural language.

```bash
# Document → spec
uv run python scripts/analyze.py <file> -o replications/<slug>/

# Step-by-step paper2spec
uv run python scripts/parse.py <file> -o content.json
uv run python scripts/extract.py content.json -o spec.json

# Matched operator-pitfall context for repair/review
uv run python scripts/operator_pitfalls.py inputs/spec.json -o diagnostics/operator_pitfall_context.md

# Extract data requirements and match against ClickHouse catalog
uv run python scripts/extract_requirements.py replications/<slug>/diagnostics/data_requirements.json

# Validate generated code
uv run python scripts/validate_strategy.py replications/<slug>/src/strategy.py

# Run backtest
uv run python replications/<slug>/src/strategy.py
```

For full flags, output formats, and library management:
[references/skill-internals.md](references/skill-internals.md)

---

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `PAPER2SPEC_REPLICATIONS_PATH` | `./replications` | Output root |
| `PAPER2SPEC_MODEL` | `openai/gpt-4o-mini` | Default LLM ([litellm-supported](https://docs.litellm.ai/docs/providers)) |
| `DEEPSEEK_API_KEY` | — | DeepSeek (recommended) |
| `OPENROUTER_API_KEY` | — | OpenRouter (multi-model) |
| `OPENAI_API_KEY` | — | OpenAI direct |
| `PAPER2SPEC_ARXIV_MIN_INTERVAL` | `3.0` | Seconds between arXiv requests |
| `PAPER2SPEC_SEARCH_MAX_RETRIES` | `3` | Retry on HTTP 429/5xx |

Any [litellm-supported model](https://docs.litellm.ai/docs/providers) works.
The `--model` flag on any script overrides `PAPER2SPEC_MODEL`.
Full config + .env examples: [references/skill-internals.md](references/skill-internals.md)

---

## References

Read on demand for implementation details:

- [references/paper2spec.md](references/paper2spec.md) — Parser modes, multi-strategy detection, output schemas
- [references/extraction_quality.md](references/extraction_quality.md) — Mandatory review/repair and `needs_human_review` rules
- [paper2spec/resources/operator_pitfall_index.md](paper2spec/resources/operator_pitfall_index.md) — Retrieval corpus for high-risk formula pitfalls
- [references/spec2code.md](references/spec2code.md) — Code generation workflow, Backtrader patterns
- [references/skill-internals.md](references/skill-internals.md) — Script flags, output formats, .env examples, replication management, project structure
- [references/backtrader_patterns.md](references/backtrader_patterns.md) — Strategy class, data loading, position sizing
- [references/clickhouse.md](references/clickhouse.md) — ClickHouse query patterns, schema discovery, data extraction rules
- [references/indicator_cookbook.md](references/indicator_cookbook.md) — Built-in and custom indicators
- [references/data_sources.md](references/data_sources.md) — ClickHouse data connection and catalog
- [references/paper_conventions.md](references/paper_conventions.md) — Standard academic-finance defaults the agent applies autonomously (universe filter, weighting, breakpoints, factor model)

## Limitations

- **OCR quality**: LightOnOCR-2 output is markdown with HTML tables and LaTeX equations; quality depends on PDF clarity. Rotated pages or dense multi-column layouts may need preprocessing.
- **Multi-strategy**: conservative — may merge borderline-distinct strategies.
- **DOCX**: paragraph text only (tables, images not preserved — use PDF for rich docs).
- **SSRN search**: best-effort HTML scraping, may break on layout changes.
