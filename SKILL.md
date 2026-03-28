---
name: anything2strategy
description: >
  ALAGENT Anything2Strategy: any research input (PDF paper, Markdown draft,
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
  version: 0.5.0
  author: ALAGENT AI (alagent-ai)
  tags: [quantitative-finance, paper-parsing, strategy-extraction, code-generation, backtesting]
---

# Anything2Strategy

Any research input → Strategy spec → Executable code → Backtest → Diagnosis.
End-to-end quantitative strategy implementation from papers, drafts, or ideas.

## Capabilities

| Capability | Description | Reference |
|-----------|-------------|-----------|
| **paper2spec** | Any document (PDF/MD/DOCX/TXT) → structured strategy specification (multi-strategy detection, JSON + Markdown) | [references/paper2spec.md](references/paper2spec.md) |
| **spec2code** | Agent generates Backtrader code from spec → validates → runs backtest → diagnoses results | [references/spec2code.md](references/spec2code.md) |

### Supported Input Formats

| Format | Extension | How It Works |
|--------|-----------|-------------|
| **PDF** (papers) | `.pdf` | PyMuPDF extraction → Mode A (direct) or Mode B (FAISS) |
| **Markdown** (drafts, notes) | `.md`, `.markdown` | Direct text read — ideal for strategy drafts or formatted notes |
| **DOCX** (Word reports) | `.docx` | python-docx extraction (requires `uv sync --extra docx`) |
| **Plain text** | `.txt` | Direct read — for raw strategy descriptions |

The parser auto-detects format from file extension. No user action needed.

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

### End-to-End: Any Document → Spec → Code → Backtest

```bash
# Step 1: Analyze document → extract specs (auto-detects format)
uv run python scripts/analyze.py paper.pdf -o library/my_paper/
uv run python scripts/analyze.py strategy_draft.md -o library/my_draft/
uv run python scripts/analyze.py report.docx -o library/my_report/

# Step 2: Read spec.json, generate strategy code (agent-driven)
# Step 3: Validate code
uv run python scripts/validate_strategy.py library/my_paper/strategy_1.py

# Step 4: Run backtest directly
uv run python library/my_paper/strategy_1.py
```

### Paper2Spec Only

```bash
# Full pipeline: Document → content (JSON+MD) + spec (JSON+MD) + metadata
uv run python scripts/analyze.py paper.pdf -o library/my_paper/
uv run python scripts/analyze.py strategy.md -o library/my_draft/
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
| "Analyze this paper/doc" / "What strategies does this use" | **paper2spec** | Run `scripts/analyze.py`, read spec.md |
| "Search for papers about X" | **paper2spec** | Run `scripts/search.py` → **Gate 1** |
| "Here's my strategy draft" (MD/DOCX/TXT) | **paper2spec** | Auto-detect format, parse, extract |
| "Generate code for this strategy" / "Implement this" | **spec2code** | Read spec.json → generate code → validate → run |
| "Run a backtest" / "Test this strategy" | **spec2code** | Run strategy.py directly |
| "Take this paper end to end" | **both** | paper2spec → **Gate 2** → spec2code pipeline |
| "Compare results with the paper" | **spec2code** | Read backtest output + spec, compare natively |

---

## Interaction Gates (HITL Checkpoints)

Two mandatory human-in-the-loop gates ensure the user stays in control.
These are NOT optional — always pause at these gates unless the user
explicitly said "fully automatic" or "end to end without stopping".

### Gate 1: Input Confirmation

**When**: After receiving or finding the input, BEFORE running spec extraction.

This gate covers three scenarios:

**Scenario A — User provided a file (PDF/MD/DOCX):**

After receiving the file, do a quick preliminary scan (title, page count,
abstract if available) and present to the user:

```
📄 Received: "Tactical Asset Allocation" (Faber, 2007)
   Format: PDF, 18 pages
   Abstract: [first 2 sentences of abstract]

I'll extract the trading strategies from this paper.
This typically takes 30-60 seconds and costs ~$0.01.

→ Proceed with extraction?
→ Or would you like to adjust settings first?
  (parser mode, LLM model, output location)
```

If the document is straightforward, keep this gate light — one question
with a default-proceed option. The user can just say "go" or "yes".

**Scenario B — User searched for papers:**

After search results come back, present a numbered list:

```
🔍 Found 8 papers for "momentum trading strategy":

  1. ⭐ "Time Series Momentum" (Moskowitz et al., 2012) — 847 citations
  2. "Momentum Crashes" (Daniel & Moskowitz, 2016) — 523 citations
  3. "Cross-Sectional Momentum" (Jegadeesh & Titman, 1993) — 12k citations
  ...

Which paper would you like me to analyze?
  → Pick a number (or multiple: "1, 3")
  → "download 1" to just save the PDF without analysis
  → Refine search with different keywords
```

Do NOT auto-analyze. Always let the user pick.

**Scenario C — User provided raw text or a strategy idea:**

```
📝 I see you've described a strategy concept:
   "[brief summary of what you understood]"

   I'll structure this into a formal strategy specification.

   → Proceed?
   → Want to add more details first?
```

### Gate 2: Spec Review & Next Steps

**When**: After spec extraction completes, BEFORE any code generation.

This is the most important gate. Always present it as a structured
decision point, not a yes/no question.

First, show the extraction summary:

```
✅ Strategy Extraction Complete

📋 Paper: "Pairs Trading: Does Volatility Timing Matter?"
   Detected: 3 independent strategies

   [1] Minimum Distance Method
       • 4 indicators (spread, SMA, Z-score, distance)
       • Entry: spread Z-score > 2σ, Exit: mean reversion
       • Assets: equity pairs (S&P 500 universe)

   [2] Stationarity-Based (ADF Test)
       • 3 indicators (ADF statistic, half-life, spread)
       • Entry: cointegrated pair + spread deviation
       • Assets: equity pairs

   [3] Cointegration (Johansen)
       • 5 indicators (eigenvalue, trace stat, β-weights, spread, Z-score)
       • Entry: Johansen test + Z-score threshold
       • Assets: equity pairs

   Full spec: library/pairs_trading/spec.md
```

Then present the action menu:

```
What would you like to do next?

  1. 🚀 Implement → Generate executable code
     (pick strategy number, or "all" for all 3)

  2. 🔍 Deep dive → Explore a strategy in detail
     (I'll explain the logic, indicators, and assumptions)

  3. 📊 Compare → How do these strategies differ?
     (side-by-side comparison of the 3 approaches)

  4. ✏️ Adjust → Modify a strategy spec
     (change parameters, add constraints, tweak logic)

  5. 💾 Export only → Save specs and stop here
     (spec.json + spec.md already saved)

  6. 🔄 Re-extract → Try with different settings
     (different model, parser mode, or focus)

Pick a number or describe what you want:
```

Wait for the user's choice before proceeding.

**Key behaviors at Gate 2:**

- If user picks "Implement", confirm which strategy index before generating code.
- If user picks "Deep dive", read and present the relevant section of spec.json
  with explanations, then return to the same action menu.
- After code generation + backtest, present results and offer another decision point
  (diagnose, adjust, try another strategy, etc.).
- Never silently proceed from spec extraction to code generation.

### Gate Bypass

If the user explicitly indicates they want the full pipeline without stops:
- "End to end" / "fully automatic" / "don't stop" / "just do everything"

Then collapse both gates into brief inline status updates:
```
📄 Parsing paper... ✓ (3 strategies detected)
💻 Generating code for strategy 1... ✓
📊 Running backtest... ✓
📈 Results ready — see below.
```

Even in bypass mode, if something unexpected happens (0 strategies detected,
extraction errors, validation failures), stop and consult the user.

---

### Standard Analysis

```
1. Run: uv run python scripts/analyze.py <file> -o library/<slug>/
   (auto-detects PDF/MD/DOCX/TXT format)
2. Read the generated spec.md for a quick summary
3. Read spec.json for machine-readable details
```

### Full Pipeline Agent Flow

```
1. Receive input from user (file, search query, or text)
2. ── Gate 1: Input Confirmation ──
   Present what was received, confirm proceeding
3. [paper2spec] Parse and extract specs
   → Read references/paper2spec.md for details
4. ── Gate 2: Spec Review & Next Steps ──
   Present strategies, offer action menu
5. User selects strategy and action
6. [spec2code] For each selected strategy:
   a. Read spec.json + references/backtrader_patterns.md + indicator_cookbook.md
   b. Generate self-contained strategy.py (data + signal + backtest in one file)
   c. Validate with: uv run python scripts/validate_strategy.py strategy.py
   d. Run directly: uv run python strategy.py
   e. Read stdout/stderr, compare metrics vs spec's expected_performance
   → Read references/spec2code.md for details
7. Present results and diagnosis to user
8. Offer next actions (adjust, try another strategy, re-run, etc.)
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
uv run python scripts/analyze.py <file> [-o DIR] [--parser-mode builtin|agent] [--model MODEL]
```

Accepts any supported format: `.pdf`, `.md`, `.markdown`, `.docx`, `.txt`.
Auto-detects from file extension.

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
- **DOCX**: Extracts paragraph text only. Tables, images, and complex
  formatting in DOCX files are not preserved (use PDF for richly formatted papers).
