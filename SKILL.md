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
[PROGRESS] paper2spec/extract — extracting strategy specs from content.json
[ARTIFACT] library/upsa/spec.json — 1 strategy, 4 indicators, 3 logic steps
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
- `./library/` (default, recommended)
- Custom path

Write `PAPER2SPEC_LIBRARY_PATH=/absolute/path` to `.env`.
Scan the directory for existing `metadata.json` to detect prior analyses.

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

1. **Setup** — verify `.env`, library path, API key if needed, Python environment, and user-selected scope.
2. **Input confirmation** — identify the paper/spec/data/instruction files or search results; ask whether to add clarification, constraints, selected-plan preferences, known pitfalls, or reference files.
3. **paper2spec: PDF/text to content** — parse the selected document into grounded content artifacts.
4. **paper2spec: extract** — extract candidate strategy specs/plans from the content plus user instructions.
5. **paper2spec: repair/review** — read `references/extraction_quality.md`, retrieve relevant operator pitfalls when high-risk formulas are present, and repair only the selected plan/spec with grounded evidence.
6. **HITL review** — after repair, always inspect `needs_human_review`. If any item exists, present it through the interactive dialog and do not continue until answered or explicitly accepted. If none exists, still report that review found no open items and ask for implementation approval.
7. **spec2code** — after HITL approval, confirm the implementation target and generate code for that target.
8. **Validation/backtest/diagnosis** — validate generated code, run available checks/backtests, compare against expected or reference outputs, summarize mismatches, then ask what to do next.

No bypass: never silently chain extraction → repair → implementation. User-provided papers, instructions, data files, existing specs, or reference outputs are evidence, not permission to skip review or HITL.

When previous Copilot, VS Code, or agent logs are mentioned, verify that the referenced path exists and contains the needed files before using them. If the path is missing, empty, or incomplete, regenerate the required artifacts from the original paper/instructions/data instead of relying on the log summary.

## Output Paths

Default generated artifacts go under `PAPER2SPEC_LIBRARY_PATH/<slug>/`, where `<slug>` is the paper or task slug confirmed with the user. If a custom output path is requested, confirm it before writing files.

Expected artifact paths:

- `content.json` and `content.md` from paper2spec parsing
- `spec.json` and `spec.md` from extraction and repair
- `operator_pitfall_context.md` when pitfall retrieval is used
- `strategy.py`, `strategy_1.py`, or the user-confirmed implementation filename from spec2code
- `data/` for any data used by generated strategy code
- `results/backtest_output.txt`, `results/metrics.json`, and `results/diagnosis_report.md` from validation/backtest/diagnosis
- `results/portfolio_vs_assets.csv` and `results/portfolio_vs_assets.png` comparing the strategy portfolio value against same-capital buy-and-hold curves for every used equity/ETF/asset in one image; asset curves must use distinguishable colors and symbol labels/legend entries, and SPY and portfolio must be boldface (comparing same-parameter portfolio curves at 0%, 0.01%, and 0.05% commission in one image)
- `results/key_pred/` with one CSV and one PNG per key observerable factors used by the strategy

Every status update after file generation should name the concrete workspace-relative path that was written.

## Spec2Code Metrics

For every runnable strategy, spec2code should compute and report at least: Sharpe ratio, maximum drawdown, total return, and return value/final portfolio value. If a strategy is not runnable as a broker-connected strategy, report why and still compute the metrics that are meaningful for the confirmed research/backtest contract.

Spec2Code-generated code must cache all network data locally, save headless-safe visual diagnostics, plot all used asset prices together, compare the strategy account value against same-capital buy-and-hold curves for all used assets, include a 0% / 0.01% / 0.05% commission equity-curve comparison for trading strategies, and include a combined portfolio-vs-assets chart where all three commission portfolio curves are plotted with all asset buy-and-hold
curves. 

For US equity strategies, SPY must be included and highlighted as the market baseline in asset and portfolio-vs-assets plots. See [references/spec2code.md](references/spec2code.md) and [references/data_sources.md](references/data_sources.md) for the required data cache and visualization contract.

---

## Agent Pipeline Flow

```
1. Setup: confirm environment, library path, keys if needed, and task scope
2. Confirm inputs: paper/spec/data/instructions/search result + clarifications
3. paper2spec: parse PDF/text/doc to content artifacts
4. paper2spec: extract candidate specs/plans
5. paper2spec: select target plan/spec and repair with extraction_quality + matched pitfalls
6. HITL: inspect needs_human_review and resolve through interactive dialog
7. spec2code: confirm output contract, generate code, validate, run checks/backtest
8. Diagnose results and ask next action
```

For code generation patterns: [references/spec2code.md](references/spec2code.md)
For Backtrader patterns: [references/backtrader_patterns.md](references/backtrader_patterns.md)

---

## Internal Toolchain

Agent-only. Run silently; present results in natural language.

```bash
# Document → spec
uv run python scripts/analyze.py <file> -o library/<slug>/

# Step-by-step paper2spec
uv run python scripts/parse.py <file> -o content.json
uv run python scripts/extract.py content.json -o spec.json

# Matched operator-pitfall context for repair/review
uv run python scripts/operator_pitfalls.py spec.json -o operator_pitfall_context.md

# Validate generated code
uv run python scripts/validate_strategy.py library/<slug>/strategy_1.py

# Run backtest
uv run python library/<slug>/strategy_1.py

# Search papers
uv run python scripts/search.py "<query>" -n 5
```

For full flags, output formats, and library management:
[references/skill-internals.md](references/skill-internals.md)

---

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `PAPER2SPEC_LIBRARY_PATH` | `./library` | Output root |
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
- [references/skill-internals.md](references/skill-internals.md) — Script flags, output formats, .env examples, library management, project structure
- [references/backtrader_patterns.md](references/backtrader_patterns.md) — Strategy class, data loading, position sizing
- [references/indicator_cookbook.md](references/indicator_cookbook.md) — Built-in and custom indicators
- [references/data_sources.md](references/data_sources.md) — yfinance, akshare, FRED API

## Limitations

- **Mode A** truncates at 100K chars (first 90K + last 10K). Use Mode B for >100 page papers.
- **Tables/formulas**: not yet extracted from PDFs.
- **Multi-strategy**: conservative — may merge borderline-distinct strategies.
- **DOCX**: paragraph text only (tables, images not preserved — use PDF for rich docs).
- **SSRN search**: best-effort HTML scraping, may break on layout changes.
