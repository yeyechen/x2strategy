---
name: quant-paper-reader
description: >
  Extract structured, executable strategy specifications from quantitative
  finance research papers (PDF). Multi-strategy detection, 5-layer LLM
  extraction, dual-format output (JSON + Markdown). Use this skill whenever
  the user mentions analyzing a quant paper, extracting trading strategies
  from a PDF, understanding what strategies a paper describes, parsing
  academic finance research, or preparing a paper for code generation.
  Also use when the user has a PDF of a trading/investment paper and wants
  to know what's in it, compare strategies across papers, or build a
  library of strategy specifications. Even if they just say "look at this
  paper" or "what strategies does this use" — this skill handles it.
version: 0.3.0
author: ALAGENT AI (alagent-ai)
tags: [quantitative-finance, paper-parsing, strategy-extraction, research, multi-strategy]
---

# paper2spec

Convert quantitative finance research papers into structured, machine-readable
strategy specifications — with automatic multi-strategy detection.

## What This Skill Does

Given a **PDF** of a quantitative finance paper, this skill:

1. **Parses** the paper into structured sections (methodology, signal logic,
   data requirements) via dual-mode extraction (direct LLM or FAISS RAG).
2. **Detects** if the paper contains multiple independent strategies (Layer 0).
3. **Extracts** a complete specification per strategy through 4 focused LLM
   calls (metadata → indicators → logic pipeline → execution plan).
4. **Renders** all outputs in dual format: machine-readable JSON +
   human-readable Markdown.

The output is designed to be directly consumable by code generation agents
(e.g., for Backtrader, Zipline, or other backtesting frameworks).

## First-Run Setup

On first use, walk the user through these three steps. Skip any step
that's already configured. Save choices to `.paper2spec.json` in the
project root so future runs remember them.

### Step 1: Workspace Location

Ask the user where they want to store PDFs and analysis results.
Default: `./library/` in the current working directory.

```
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
No LLM API key detected. paper2spec needs one to extract strategies.

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
PAPER2SPEC_MODEL=deepseek/deepseek-chat
DEEPSEEK_API_KEY=sk-actualKeyFromUser
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

paper2spec uses **uv** for dependency management. The project contains a
`.python-version` (3.11) and `pyproject.toml` — uv handles everything.

```bash
cd <skill-path>

# Check if already set up
.venv/bin/python -c "import paper2spec; print(paper2spec.__version__)" 2>/dev/null

# If not set up: create venv + install deps (one command)
uv sync                    # Core only (Mode A)
uv sync --extra agent      # + FAISS/embeddings (Mode B)
uv sync --extra dev        # + pytest (for testing)
```

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
pip install -e .                    # Core (Mode A)
pip install -e ".[agent]"           # + Mode B deps
pip install -e ".[dev]"             # + test deps
```

### Config File (`.paper2spec.json`)

After setup, write this to the project root:
```json
{
  "library_path": "./library",
  "model": "deepseek/deepseek-chat",
  "default_parser_mode": "auto"
}
```

On subsequent runs, read this file first and skip setup.

## Quick Start

### One-Shot Analysis (recommended)

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

## Agent Workflow

When using this skill as an AI agent, follow this workflow:

### Standard Analysis

```
1. Run: uv run python scripts/analyze.py <pdf_path> -o library/<slug>/
2. Read the generated spec.md for a quick summary
3. Read spec.json for machine-readable details
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
- When the user wants to proceed to code generation (Spec2Code), point them
  to the specific `spec.json` path and strategy index.
- To re-analyze a paper with different settings, the PDF is already in the
  directory — no need to locate the original file again.

### Handing Off to Spec2Code

The `spec.json` output is designed for downstream code generation. To pass a
specific strategy to a Spec2Code agent:

```python
import json
result = json.load(open("library/pairs_trading/spec.json"))
strategy = result["strategies"][0]  # Pick strategy by index
# Pass `strategy` dict to Spec2Code agent
```

## Scripts Reference

### `scripts/analyze.py` — Full Pipeline (recommended)

```
uv run python scripts/analyze.py <pdf> [-o DIR] [--parser-mode builtin|agent] [--model MODEL]
```

| Flag | Default | Description |
|------|---------|-------------|
| `-o, --output-dir` | `./<slug>/` | Output directory |
| `--parser-mode` | `builtin` | `builtin` (fast, <40 pages) or `agent` (FAISS semantic retrieval, for long/dense papers). See **Parser Mode Selection** below. |
| `--extractor-mode` | `multilayer` | `multilayer` (recommended) or `single` (legacy) |
| `--model` | env `PAPER2SPEC_MODEL` | Override LLM model |

**Outputs**: `content.json`, `content.md`, `spec.json`, `spec.md`, `metadata.json`

### `scripts/parse.py` — PDF → PaperContent

```
uv run python scripts/parse.py <pdf> [--mode builtin|agent] [--model MODEL] [-o FILE]
```

### `scripts/extract.py` — PaperContent → ExtractionResult

```
uv run python scripts/extract.py <content.json> [--mode multilayer|single] [--model MODEL] [-o FILE]
```

### `scripts/search.py` — Academic Paper Search

```
uv run python scripts/search.py <query> [--sources arxiv ssrn] [-n 10] [-o FILE]
```

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
| PDF > 100 pages, or user reports missing content | `agent` (Mode B) | FAISS semantic retrieval. Chunks text (1500/200), embeds with bge-small-en, retrieves top-k per query. Requires `pip install paper2spec[agent]`. |

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
| `PAPER2SPEC_MODEL` | `openai/gpt-4o-mini` | Default LLM model |
| `OPENAI_API_KEY` | — | For OpenAI / OpenRouter models |
| `DEEPSEEK_API_KEY` | — | For DeepSeek models |
| `ANTHROPIC_API_KEY` | — | For Anthropic models |

Any [litellm-supported model](https://docs.litellm.ai/docs/providers) works.
The `--model` flag on any script overrides `PAPER2SPEC_MODEL`.

## Project Structure

```
paper2spec/
├── __init__.py        # v0.3.0
├── models.py          # PaperContent, StrategySpec, ExtractionResult, StrategyBrief
├── parser.py          # PDF → PaperContent (Mode A: builtin, Mode B: FAISS)
├── extractor.py       # PaperContent → ExtractionResult (Layer 0-4)
├── render.py          # JSON → Markdown renderers
├── pdf_utils.py       # Hybrid PDF extraction (pymupdf4llm + fitz)
├── llm.py             # litellm wrapper
├── prompts.py         # Layer 0-4 prompt templates
└── search.py          # arXiv + SSRN search
scripts/
├── analyze.py         # Full pipeline: PDF → all outputs
├── parse.py           # CLI: parse PDF
├── extract.py         # CLI: extract spec
├── search.py          # CLI: search papers
└── generate_schemas.py
schemas/
├── paper_content.schema.json
└── strategy_spec.schema.json
examples/               # Pre-generated outputs for reference
```

## Limitations

- **Mode A** (builtin): Truncates to first 90K + last 10K chars when text exceeds 100K.
  For very long papers (>100 pages), use `--parser-mode agent`.
- **SSRN search**: Best-effort HTML scraping — may break if SSRN changes layout.
- **Tables/formulas**: Not yet extracted (reserved fields in PaperContent).
- **Multi-strategy**: Conservative detector — may merge borderline-distinct strategies.
