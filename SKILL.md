---
name: quant-paper2code
description: >
  End-to-end pipeline: quantitative finance research paper (PDF) →
  structured strategy specification → executable Backtrader code →
  backtest → diagnosis report. Two capabilities: (1) paper2spec extracts
  multi-strategy specs from PDFs via 5-layer LLM extraction, and
  (2) spec2code: the agent generates validated Backtrader code from specs,
  runs it directly, and compares results against paper-reported metrics.
  Use this skill when the user wants to analyze a quant paper, extract
  trading strategies from a PDF, generate executable strategy code,
  run a backtest, or go end-to-end from paper to results. Covers any
  request about parsing finance research, building strategy specifications,
  implementing strategies as code, or validating backtest performance.
  Also use when the user just says "look at this paper" or "what strategies
  does this use" — this skill handles it.
metadata:
  version: 0.4.0
  author: ALAGENT AI (alagent-ai)
  tags: [quantitative-finance, paper-parsing, strategy-extraction, code-generation, backtesting]
---

# quant-paper2code

Research paper → Strategy spec → Executable code → Backtest → Diagnosis.
End-to-end quantitative strategy implementation from academic papers.

## Capabilities

| Capability | Description | Reference |
|-----------|-------------|-----------|
| **paper2spec** | PDF → structured strategy specification (multi-strategy detection, JSON + Markdown) | [references/paper2spec.md](references/paper2spec.md) |
| **spec2code** | Agent generates Backtrader code from spec → validates → runs backtest → diagnoses results | [references/spec2code.md](references/spec2code.md) |

## First-Run Setup

On first use, walk the user through these three steps. Skip any step
that's already configured. Persist choices in the project `.env` so
future runs remain stable across sessions.

### Step 1: Workspace Location

Ask the user where they want to store PDFs and analysis results.
Default: `./library/` in the current working directory.

```

Persist this choice to `.env`:

```
PAPER2SPEC_LIBRARY_PATH=/absolute/path/to/library
```

If `.env` does not exist, create it from `.env.example` first.

On every run, scripts should read `PAPER2SPEC_LIBRARY_PATH` as the default
output root. This avoids path drift across sessions.
Prefer absolute paths so custom user directories remain stable regardless of
current working directory.
Where should I store paper analyses?
  1. ./library/  (default, recommended)
  2. Custom path
```

Scan the chosen directory for any existing `metadata.json` files to
detect previously analyzed papers. Report what's already there.

### Step 2: LLM API Key

Check if any API key is already set in the environment (`DEEPSEEK_API_KEY`,
`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`). If none found, **you must ask the
user to provide their API key** before proceeding — do not silently skip
this step or assume they will set it later. Prompt the user like this:

```
No LLM API key detected. paper2code needs one to extract strategies
and generate code.

Recommended: DeepSeek (best cost-performance ratio for this task)
  → ~$0.01 per paper, API key from https://platform.deepseek.com

Alternatives: OpenAI GPT-4o, Anthropic Claude, any litellm-supported model.

Please paste your API key now (e.g. sk-...) and tell me which provider
it belongs to (DeepSeek / OpenAI / Anthropic):
```

Wait for the user to reply with their key. Once received, **write it into
a `.env` file** at the project root so the key persists across sessions.
The project auto-loads `.env` (gitignored by default):

```bash
cp .env.example .env
# Then replace the placeholder values with the user's actual key and model
```

For example, if the user provides a DeepSeek key, the `.env` should contain:
```
PAPER2SPEC_LIBRARY_PATH=/absolute/path/to/library
PAPER2SPEC_MODEL=deepseek/deepseek-chat
DEEPSEEK_API_KEY=sk-actualKeyFromUser
PAPER2SPEC_INIT_VERSION=1
```

If the user provides an OpenAI key:
```
PAPER2SPEC_MODEL=openai/gpt-4o-mini
OPENAI_API_KEY=sk-actualKeyFromUser
```

**Important**: Never write a `.env` with placeholder values like `sk-...`.
Always wait until you have the real key from the user, then write the file.

Verify the key works by running:
```bash
uv run python -c "from paper2spec.llm import chat; print(chat('Say OK'))" 2>&1 | head -1
```

### Step 3: Python Environment

paper2code uses **uv** for dependency management. The project contains a
`.python-version` (3.11) and `pyproject.toml` — uv handles everything.

```bash
cd <skill-path>

# Check if already set up
.venv/bin/python -c "import paper2spec; print(paper2spec.__version__)" 2>/dev/null

# If not set up: create venv + install ALL deps (recommended)
uv sync --all-extras       # Install everything: core + codegen + agent + dev

# Or install selectively:
# uv sync                    # Core only (paper2spec Mode A basic)
# uv sync --extra codegen    # + backtrader/yfinance/akshare (for spec2code)
# uv sync --extra agent      # + FAISS/embeddings (Mode B: long papers)
# uv sync --extra dev        # + pytest (for testing)
```

**Note**: Mode A (direct LLM extraction) works with core deps only.
Mode B (FAISS-based chunked extraction for long papers) requires `--extra agent`.
Code generation and backtesting require `--extra codegen`.
**Recommended: always use `uv sync --all-extras` to ensure full functionality.**

**Running scripts**: Always use `uv run` so the correct venv is activated
automatically — no need to manually activate `.venv/`:

```bash
uv run python scripts/analyze.py paper.pdf -o library/my_paper/
uv run python scripts/search.py "momentum trading" -n 5
```

**Alternative (no uv)**: If `uv` is not available, use pip directly:
```bash
cd <skill-path>
python -m venv .venv && source .venv/bin/activate
pip install -e ".[codegen,agent,dev]"   # All extras (recommended)

# Or selectively:
# pip install -e .                    # Core (paper2spec)
# pip install -e ".[codegen]"         # + backtrader/yfinance/akshare
# pip install -e ".[agent]"           # + FAISS/embeddings
# pip install -e ".[dev]"             # + test deps
```

**Strategy virtual environments**: Generated strategies may need their own
dependencies (backtrader, yfinance, akshare). When generating code for a paper,
consider creating a dedicated venv in the library subdirectory:

```bash
cd library/<paper>/
uv venv
uv pip install backtrader yfinance akshare
uv run python strategy_1.py
```

This isolates strategy deps from the skill's own environment.

### Persistent Config (Environment)

Primary persistent config is `.env` (gitignored):

```
PAPER2SPEC_LIBRARY_PATH=/absolute/path/to/library
PAPER2SPEC_MODEL=deepseek/deepseek-chat
DEEPSEEK_API_KEY=sk-...
PAPER2SPEC_INIT_VERSION=1
```

On subsequent runs, read `.env` first and skip setup questions for already
configured values.

Initialization completion policy:
- `PAPER2SPEC_INIT_VERSION` is a quick marker (recommended value: `1`).
- Do not trust marker alone. Always verify runtime capability:
  `PAPER2SPEC_LIBRARY_PATH`, `PAPER2SPEC_MODEL`, and at least one provider API key.

## Quick Start

### End-to-End: Paper → Spec → Code → Backtest

```bash
# Step 1: Analyze paper → extract specs
uv run python scripts/analyze.py paper.pdf -o library/my_paper/

# Step 2: Read spec.json, generate strategy code (agent-driven)
# Step 3: Validate code
uv run python scripts/validate_strategy.py library/my_paper/strategy_1.py

# Step 4: Run backtest directly
uv run python library/my_paper/strategy_1.py
```

### Paper2Spec Only

```bash
# Full pipeline: PDF → content (JSON+MD) + spec (JSON+MD) + metadata
uv run python scripts/analyze.py paper.pdf -o library/my_paper/
```

This produces:
```
library/my_paper/
├── paper.pdf       # Original PDF (auto-copied for self-contained library)
├── content.json    # PaperContent (machine-readable)
├── content.md      # PaperContent (human-readable)
├── spec.json       # ExtractionResult with all strategies (machine-readable)
├── spec.md         # Strategy summary (human-readable)
└── metadata.json   # Analysis metadata (model, version, pdf_file, etc.)
```

### Step-by-Step Pipeline

```bash
# 1. Search for papers (optional)
uv run python scripts/search.py "momentum trading strategy" -n 5

# 2. Parse PDF → PaperContent
uv run python scripts/parse.py paper.pdf -o content.json

# 3. Extract PaperContent → ExtractionResult (multi-strategy)
uv run python scripts/extract.py content.json -o spec.json
```

### Spec2Code Only (Agent-Driven)

The agent reads `spec.json`, generates a self-contained Backtrader
strategy file, validates it, runs it directly, and analyzes the output.
See [references/spec2code.md](references/spec2code.md) for the full workflow.

## Agent Workflow

### User-Facing Interaction Policy

- Commands and scripts in this skill are internal implementation details.
- In user conversations, present these as agent capabilities (search, parse,
  extract, generate, backtest) rather than exposing raw command sequences by default.
- Run tools internally, then report outcomes, key findings, and next actions.
- Show exact commands only when the user explicitly asks for reproducibility,
  debugging, or CLI instructions.
- Combine this skill with broader agent reasoning to resolve ambiguity and
  choose sensible defaults before asking users extra questions.

### Routing Logic

When the user's request arrives, route to the appropriate capability:

| User Intent | Route To | Action |
|-------------|----------|--------|
| "Analyze this paper" / "What strategies does this use" | **paper2spec** | Run `scripts/analyze.py`, read spec.md |
| "Search for papers about X" | **paper2spec** | Run `scripts/search.py` |
| "Generate code for this strategy" / "Implement this" | **spec2code** | Read spec.json → generate code → validate → run |
| "Run a backtest" / "Test this strategy" | **spec2code** | Run strategy.py directly |
| "Take this paper end to end" | **both** | paper2spec → spec2code pipeline |
| "Compare results with the paper" | **spec2code** | Read backtest output + spec, compare natively |

### Standard Analysis

```
1. Run: uv run python scripts/analyze.py <pdf_path> -o library/<slug>/
2. Read the generated spec.md for a quick summary
3. Read spec.json for machine-readable details
```

### Full Pipeline Agent Flow

```
1. Receive PDF from user
2. [paper2spec] Parse and extract specs
   → Read references/paper2spec.md for details
3. Present extracted strategies to user for review
4. User selects strategy (or all)
5. [spec2code] For each selected strategy:
   a. Read spec.json + references/backtrader_patterns.md + indicator_cookbook.md
   b. Generate self-contained strategy.py (data + signal + backtest in one file)
   c. Validate with: uv run python scripts/validate_strategy.py strategy.py
   d. Run directly: uv run python strategy.py
   e. Read stdout/stderr, compare metrics vs spec's expected_performance
   → Read references/spec2code.md for details
6. Present results and diagnosis to user
```

### Managing Multiple Papers (Library Pattern)

Organize analyzed papers in a `library/` directory. Each paper gets its own
subdirectory with all outputs:

```
library/
├── tactical_asset_allocation/
│   ├── faber_2007.pdf            # Original PDF
│   ├── content.json, content.md  # Parsed paper
│   ├── spec.json, spec.md        # Strategy specs
│   ├── strategy_1.py             # Generated code (self-contained)
│   └── metadata.json             # Metadata (pdf_file, model, strategies, ...)
├── pairs_trading/
│   ├── goncalves_2023.pdf
│   └── ...  (3 strategies detected)
└── value_momentum/
    ├── asness_2013.pdf
    └── ...  (2 strategies detected)
```

Each directory is **self-contained**: the original PDF is copied in, so the
library can be moved or shared without losing the source paper. The
`metadata.json` field `pdf_file` records the filename within the directory.

**Agent guidelines for library management:**

- Before analyzing a new paper, check if `library/` already has an entry
  for it (scan `metadata.json` files for matching titles or `pdf_file`).
- Use descriptive slugs for directories (e.g., `momentum_crashes` not `paper1`).
- When the user asks to compare strategies across papers, read the relevant
  `spec.json` files and synthesize.
- When the user wants to proceed to code generation (spec2code), point them
  to the specific `spec.json` path and strategy index.
- To re-analyze a paper with different settings, the PDF is already in the
  directory — no need to locate the original file again.

### Handing Off to Spec2Code

The `spec.json` output is designed for downstream code generation. To pass a
specific strategy to the spec2code workflow:

```python
import json
result = json.load(open("library/pairs_trading/spec.json"))
strategy = result["strategies"][0]  # Pick strategy by index
# Agent reads this spec dict and generates Backtrader code
```

## Scripts Reference

### `scripts/analyze.py` — Full Pipeline (recommended)

```
uv run python scripts/analyze.py <pdf> [-o DIR] [--parser-mode builtin|agent] [--model MODEL]
```

| Flag | Default | Description |
|------|---------|-------------|
| `-o, --output-dir` | `<PAPER2SPEC_LIBRARY_PATH>/<slug>/` | Output directory |
| `--parser-mode` | `builtin` | `builtin` (fast, <40 pages) or `agent` (FAISS semantic retrieval, for long/dense papers). See **Parser Mode Selection** below. |
| `--extractor-mode` | `multilayer` | `multilayer` (recommended) or `single` (legacy) |
| `--model` | env `PAPER2SPEC_MODEL` | Override LLM model |

**Outputs**: `content.json`, `content.md`, `spec.json`, `spec.md`, `metadata.json`

### `scripts/parse.py` — PDF → PaperContent

```
uv run python scripts/parse.py <pdf> [--mode builtin|agent] [--model MODEL] [-o FILE]
```

If `-o` is not provided, default output is:

```
<PAPER2SPEC_LIBRARY_PATH>/<pdf_stem>/content.json
```

### `scripts/extract.py` — PaperContent → ExtractionResult

```
uv run python scripts/extract.py <content.json> [--mode multilayer|single] [--model MODEL] [-o FILE]
```

### `scripts/search.py` — Academic Paper Search

```
uv run python scripts/search.py <query> [--sources arxiv ssrn] [-n 10] [-o FILE]
```

### `scripts/validate_strategy.py` — Validate Generated Code

```
uv run python scripts/validate_strategy.py <strategy.py>
```

Checks: syntax (AST parse), backtrader import, Strategy class definition,
cerebro runner, `__main__` guard.

## Output Formats

### ExtractionResult (from extract.py / analyze.py)

```json
{
  "paper_title": "Pairs Trading: Does Volatility Timing Matter?",
  "num_detected": 3,
  "strategies": [
    {
      "strategy_name": "Minimum Distance Pairs Trading",
      "strategy_type": "technical",
      "asset_class": ["equity"],
      "description": "...",
      "indicators": [...],
      "logic_pipeline": [...],
      "execution_plan": [...],
      "risk_management": [...]
    },
    ...
  ]
}
```

### PaperContent (from parse.py / analyze.py)

```json
{
  "title": "...",
  "abstract": "...",
  "methodology": "...",
  "data_description": "...",
  "signal_logic": "...",
  "full_text": "..."
}
```

### Markdown Outputs

`spec.md` renders each strategy with tables for indicators, numbered logic
steps, execution plans, and risk rules — designed for quick human review.

`content.md` renders the parsed paper sections for verifying extraction quality.

## Parser Mode Selection

The parser has two modes. **Do not ask the user to choose** — pick
automatically based on paper length, and explain your choice:

| Condition | Mode | Reason |
|-----------|------|--------|
| PDF ≤ 60 pages | `builtin` (Mode A) | Fast. 100K char threshold covers ~33 pages of markdown-extracted text without truncation. 3 parallel LLM calls. |
| PDF 60-100 pages | `builtin` (Mode A) | Still works — truncation keeps first 90K + last 10K chars, covering methodology (front) + results (back). |
| PDF > 100 pages, or user reports missing content | `agent` (Mode B) | FAISS semantic retrieval. Chunks text (1500/200), embeds with bge-small-en, retrieves top-k per query. Requires `uv sync --extra agent`. |

**How Mode A works**: Extracts full PDF text → if >100K chars, takes first
90K + last 10K (skips middle). Sends 3 parallel LLM prompts (methodology,
data description, signal logic) each with the full context window.

**How Mode B works**: Extracts full PDF text → chunks at 1500 chars /
200 overlap → builds FAISS index with bge-small-en-v1.5 embeddings →
for each section, runs 5 semantic queries to retrieve the most relevant
chunks → sends retrieved chunks (not full text) to LLM. Better recall
for buried details in very long papers, but slower (embedding + retrieval
overhead) and requires ~500MB extra dependencies.

**Rule of thumb**: Mode A works for 95% of papers. Only switch to Mode B
if the user says "the spec is missing something I can see in the paper"
or the PDF is genuinely book-length (>100 pages).

## Multi-Strategy Detection

The extractor automatically detects when a paper contains multiple independent
strategies. For example:

| Paper | Strategies Detected |
|-------|-------------------|
| Tactical Asset Allocation (Faber) | 1: GTAA with SMA timing |
| Pairs Trading (Goncalves-Pinto et al.) | 3: Distance, Stationarity (ADF), Cointegration (Johansen) |
| Value and Momentum Everywhere (Asness et al.) | 2: Value Factor, Momentum Factor |

**Detection rules** (conservative — false splits are worse than missing a split):
- Parameter variations (3-month vs 12-month) → same strategy
- Long-only vs long-short variants → same strategy, different execution plans
- Fundamentally different signal logic → separate strategies

## Configuration

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `PAPER2SPEC_LIBRARY_PATH` | `./library` | Default output root for analyze/parse |
| `PAPER2SPEC_INIT_VERSION` | — | Optional setup marker (`1` recommended after successful setup) |
| `PAPER2SPEC_MODEL` | `openai/gpt-4o-mini` | Default LLM model |
| `OPENAI_API_KEY` | — | For OpenAI / OpenRouter models |
| `DEEPSEEK_API_KEY` | — | For DeepSeek models |
| `ANTHROPIC_API_KEY` | — | For Anthropic models |
| `PAPER2SPEC_ARXIV_MIN_INTERVAL` | `3.0` | Minimum seconds between arXiv API requests |
| `PAPER2SPEC_SEARCH_MAX_RETRIES` | `3` | Retry count for search HTTP 429/5xx |

Any [litellm-supported model](https://docs.litellm.ai/docs/providers) works.
The `--model` flag on any script overrides `PAPER2SPEC_MODEL`.

## Project Structure

```
paper2spec/          # PDF → structured spec
├── __init__.py        # v0.3.0
├── models.py          # PaperContent, StrategySpec, ExtractionResult, StrategyBrief
├── parser.py          # PDF → PaperContent (Mode A: builtin, Mode B: FAISS)
├── extractor.py       # PaperContent → ExtractionResult (Layer 0-4)
├── render.py          # JSON → Markdown renderers
├── pdf_utils.py       # Hybrid PDF extraction (pymupdf4llm + fitz)
├── llm.py             # litellm wrapper
├── prompts.py         # Layer 0-4 prompt templates
└── search.py          # arXiv + SSRN search

spec2code/           # Tools for agent-driven code generation
├── models.py        #   CodeModules, ValidationResult, BacktestMetrics, etc.
├── validator.py     #   AST + structural validation (agent tool)
├── config.py        #   Shared config (reuses paper2spec .env)

scripts/             # CLI entry points
├── analyze.py       #   Full paper2spec pipeline
├── parse.py, extract.py, search.py
├── validate_strategy.py  # Code validation CLI
└── generate_schemas.py

schemas/
├── paper_content.schema.json
└── strategy_spec.schema.json

references/          # Deep-dive documentation (read on demand)
├── paper2spec.md    #   Paper2spec detailed guide
├── spec2code.md     #   Spec2code agent workflow + code generation guidance
├── backtrader_patterns.md   # Common Backtrader code patterns
├── indicator_cookbook.md     # Indicator implementations
├── data_sources.md          # yfinance/akshare API reference

examples/            # Pre-generated outputs for reference
```

## Technical References

For detailed implementation guidance, read on demand:

- [references/paper2spec.md](references/paper2spec.md) — Paper2spec internals, parser modes, multi-strategy detection
- [references/spec2code.md](references/spec2code.md) — Spec2code agent workflow, code generation guidance, output patterns
- [references/backtrader_patterns.md](references/backtrader_patterns.md) — Strategy class, data loading, position sizing, cerebro runner
- [references/indicator_cookbook.md](references/indicator_cookbook.md) — Built-in indicators, custom indicators, signal patterns
- [references/data_sources.md](references/data_sources.md) — yfinance, akshare, FRED API reference

## Limitations

- **Mode A** (builtin): Truncates to first 90K + last 10K chars when text exceeds 100K.
  For very long papers (>100 pages), use `--parser-mode agent`.
- **SSRN search**: Best-effort HTML scraping — may break if SSRN changes layout.
- **Tables/formulas**: Not yet extracted (reserved fields in PaperContent).
- **Multi-strategy**: Conservative detector — may merge borderline-distinct strategies.
- **Spec2code**: Agent-driven only — no fully automatic CLI pipeline. The agent
  generates code, runs it, and analyzes results interactively.
