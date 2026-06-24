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
| PDF (papers) | `.pdf` | PyMuPDF → Mode A (direct) or Mode B (FAISS) |
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

1. **Setup** — verify `.env`, replications path, API key if needed, Python environment, and user-selected scope.
2. **Input confirmation** — identify the paper/spec/data/instruction files or search results; ask whether to add clarification, constraints, selected-plan preferences, known pitfalls, or reference files.
3. **paper2spec: PDF/text to content** — parse the selected document into grounded content artifacts.
4. **paper2spec: extract** — extract candidate strategy specs/plans from the content plus user instructions.
5. **paper2spec: repair/review** — read `references/extraction_quality.md`, retrieve relevant operator pitfalls when high-risk formulas are present, and repair only the selected plan/spec with grounded evidence.
6. **HITL review** — after repair, always inspect `needs_human_review`. If any item exists, **try** to present it through the interactive dialog (`AskUserQuestion`).
   - **If the user is reachable** (interactive session, terminal is in front of them): wait for explicit answers before continuing. Standard behavior.
   - **If the user is NOT reachable** (background / batched / async run — e.g., `claude -p` in a tmux session fired by an orchestrator): the `AskUserQuestion` call will fail or block forever. **Do NOT call `AskUserQuestion` in this mode.** Instead:
     1. Pick the most common academic-finance default for each item (VW weighting, NYSE breakpoints, month-end close → next-month open, etc.)
     2. Emit a `[HITL-AUTO-RESOLVED]` log line listing what was auto-decided and why
     3. Continue with code generation
     4. Document the auto-decisions in `results/diagnosis.md` so the user can see them after the run
   - If none exists, still report that review found no open items and ask for implementation approval (only when interactive).
7. **Data bridge** — run `scripts/extract_requirements.py` to extract structured data needs from the spec and match against the ClickHouse catalog. Read `data_match_report.json` to learn which tables provide each dataset, which columns are available, and what date ranges are covered. This report is the single source of truth for code generation — never fall back to yfinance or hardcoded ticker lists. **Do not attempt to connect to ClickHouse during code generation** — the host is on a private network. Use the match report and catalog for schema info; the generated code connects at runtime via ``os.getenv()``.
8. **spec2code** — after the data bridge, read `data_match_report.json` and generate code that queries ClickHouse via HTTP for all data. See `references/spec2code.md` §Data Source for the required pattern. Do not use yfinance or any other external API for data.
9. **Validation/backtest/diagnosis** — validate generated code, run available checks/backtests, compare against expected or reference outputs, summarize mismatches, then ask what to do next.

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
├── README.md                  # what this paper replicates, expected vs actual metrics, how to re-run
├── paper/                     # source PDF (large; usually gitignored per-paper)
│   └── original.pdf
├── inputs/                    # paper2spec artifacts (parse + extract + metadata)
│   ├── content.json
│   ├── content.md
│   ├── spec.json
│   ├── spec.md
│   └── metadata.json
├── diagnostics/               # mid-pipeline debug artifacts
│   ├── data_requirements.json
│   └── data_match_report.json
├── src/                       # generated strategy code
│   ├── __init__.py
│   └── strategy.py
├── data/                      # parquet caches (gitignored per-paper)
│   └── *.parquet
├── results/                   # spec2code outputs
│   ├── metrics.json
│   ├── backtest_output.txt
│   ├── diagnosis.md
│   ├── decile_spread.csv
│   ├── decile_spread.png
│   └── key_pred/              # one CSV + PNG per key observable factor
│       ├── <factor>.csv
│       └── <factor>.png
└── config/                    # optional run config (run_config.yaml, etc.)
```

### File responsibilities

| Path | Owner | Notes |
|------|-------|-------|
| `inputs/content.{json,md}` | `scripts/parse.py`, `scripts/analyze.py` | `PaperContent` — the parsed paper |
| `inputs/spec.{json,md}` | `scripts/extract.py`, `scripts/analyze.py` | `ExtractionResult` (one or more `StrategySpec`) |
| `inputs/metadata.json` | `scripts/analyze.py` | Pipeline run metadata (model, parser mode, instruction files) |
| `diagnostics/data_requirements.json` | `scripts/extract_requirements.py` | What data the spec needs |
| `diagnostics/data_match_report.json` | `scripts/extract_requirements.py` | What ClickHouse actually has |
| `src/strategy.py` | spec2code LLM | Generated code. One file per paper — no `_1` suffix |
| `data/*.parquet` | spec2code runtime | Local cache, see `assets/backtrader_template.py` |
| `results/metrics.json` | spec2code runtime | Sharpe, max DD, total return, final value |
| `results/backtest_output.txt` | spec2code runtime | Human-readable backtest summary |
| `results/diagnosis.md` | spec2code runtime | Strategy output vs paper-claimed metrics |
| `results/key_pred/<factor>.{csv,png}` | spec2code runtime | One per key observable factor |
| `paper/original.pdf` | `scripts/analyze.py` | Copy of the source PDF for self-contained replication |
| `operator_pitfall_context.md` (legacy) | `scripts/operator_pitfalls.py` | Still emitted at the per-paper root for backward compatibility — move to `diagnostics/` if regenerating |

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
   - Write the limitation into `results/diagnosis.md`
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
parameters, FF control table) live in
`config/run_config.yaml`. The pipeline generates this from
`inputs/spec.json` via `scripts/render_run_config.py`:

```bash
python scripts/render_run_config.py replications/<slug>/inputs/spec.json --force
```

The generated `strategy.py` MUST load the config instead of hard-coding
paper-specific constants:

```python
from paper2spec.paths import paper_layout
from utils import load_run_config, paper_layout

layout = paper_layout("<slug>")
cfg = load_run_config("<slug>")            # reads config/run_config.yaml

start = cfg["start_date"]                  # "1962-01-01"
end   = cfg["end_date"]                    # "2005-12-31"
n_bins = cfg["n_bins"]                      # 10
weighting = cfg["weighting"]                # "VW"
forward_lag = cfg["forward_returns_lag"]    # 1
table = cfg["data_sources"]["daily_returns"] # "crsp_202601.dsf"
where = cfg["universe"]["where_clause"]     # "exchcd IN (1,2,3) AND shrcd IN (10,11)"
```

If the config is missing, re-run `scripts/render_run_config.py`.
If the paper is non-standard and needs settings not in the spec, edit
the YAML directly — it's a single source of truth per replication.

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
6. HITL: inspect needs_human_review and resolve through interactive dialog
7. Data bridge: extract requirements, match against ClickHouse catalog
8. spec2code: generate code using matched tables, validate, run backtest
9. Diagnose results and ask next action
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
uv run python scripts/operator_pitfalls.py inputs/spec.json -o operator_pitfall_context.md

# Extract data requirements and match against ClickHouse catalog
uv run python scripts/extract_requirements.py replications/<slug>/inputs/spec.json

# Validate generated code
uv run python scripts/validate_strategy.py replications/<slug>/src/strategy.py

# Run backtest
uv run python replications/<slug>/src/strategy.py

# Search papers
uv run python scripts/search.py "<query>" -n 5
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

## Limitations

- **Mode A** truncates at 100K chars (first 90K + last 10K). Use Mode B for >100 page papers.
- **Tables/formulas**: not yet extracted from PDFs.
- **Multi-strategy**: conservative — may merge borderline-distinct strategies.
- **DOCX**: paragraph text only (tables, images not preserved — use PDF for rich docs).
- **SSRN search**: best-effort HTML scraping, may break on layout changes.
