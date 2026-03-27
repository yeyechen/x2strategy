---
name: quant-paper2code
description: >
  End-to-end pipeline: quantitative finance research paper (PDF) →
  structured strategy specification → executable Backtrader code →
  backtest → diagnosis report. Two capabilities: (1) paper2spec extracts
  multi-strategy specs from PDFs via 5-layer LLM extraction, and
  (2) spec2code generates validated, runnable backtest code from specs, 
  executes it locally, and compares results against paper-reported metrics.
  Use this skill when the user wants to analyze a quant paper, extract
  trading strategies from a PDF, generate executable strategy code,
  run a backtest, or go end-to-end from paper to results. Covers any
  request about parsing finance research, building strategy specifications,
  implementing strategies as code, or validating backtest performance.
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
| **spec2code** | Specification → validated Backtrader code → local backtest → diagnosis report | [references/spec2code.md](references/spec2code.md) |

## First-Run Setup

On first use, walk the user through these steps. Skip any already configured.
Persist choices in `.env`.

### Step 1: Workspace Location

Ask where to store PDFs and results. Default: `./library/`.

```
PAPER2SPEC_LIBRARY_PATH=/absolute/path/to/library
```

### Step 2: LLM API Key

Check for existing keys (`DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`).
If none found, ask the user:

```
No LLM API key detected. This skill needs one for extraction and code generation.

Recommended: DeepSeek (~$0.01 per paper)
Alternatives: OpenAI GPT-4o, Anthropic Claude, any litellm-supported model.

Please paste your API key and tell me which provider:
```

Write to `.env` (gitignored). Verify with:

```bash
uv run python -c "from paper2spec.llm import chat; print(chat('Say OK'))" 2>&1 | head -1
```

### Step 3: Python Environment

```bash
cd <skill-path>

# Install all dependencies
uv sync --extra codegen     # Core + backtrader/yfinance/akshare
uv sync --extra agent       # + FAISS/embeddings for long papers
uv sync --extra dev         # + pytest

# Or minimal (paper2spec only)
uv sync
```

Always use `uv run` to execute scripts.

### Persistent Config (.env)

```
PAPER2SPEC_LIBRARY_PATH=/absolute/path/to/library
PAPER2SPEC_MODEL=deepseek/deepseek-chat
DEEPSEEK_API_KEY=sk-...
SPEC2CODE_BACKTEST_TIMEOUT=300
PAPER2SPEC_INIT_VERSION=1
```

## Quick Start

### End-to-End: Paper → Spec → Code → Backtest

```bash
# Step 1: Analyze paper → extract specs
uv run python scripts/analyze.py paper.pdf -o library/my_paper/

# Step 2: Generate code from spec (agent-driven or CLI)
uv run python scripts/generate.py library/my_paper/spec.json --strategy-index 0

# Step 3: Validate code
uv run python scripts/validate_strategy.py library/my_paper/strategy.py

# Step 4: Run backtest
uv run python scripts/backtest.py library/my_paper/strategy.py -o library/my_paper/results/
```

### Paper2Spec Only

```bash
uv run python scripts/analyze.py paper.pdf -o library/my_paper/
# → content.json, content.md, spec.json, spec.md, metadata.json
```

### Spec2Code Only

```bash
uv run python scripts/generate.py library/my_paper/spec.json --strategy-index 0
# → strategy.py, validation report, backtest results, diagnosis report
```

## Agent Workflow

### User-Facing Interaction Policy

- Commands and scripts are internal implementation details.
- Present capabilities to users as agent actions, not raw CLI commands.
- Run tools internally, report outcomes and findings.
- Show exact commands only when the user asks for reproducibility.

### Routing Logic

When the user's request arrives, route to the appropriate capability:

| User Intent | Route To | Action |
|-------------|----------|--------|
| "Analyze this paper" / "What strategies does this use" | **paper2spec** | Run `scripts/analyze.py`, read spec.md |
| "Search for papers about X" | **paper2spec** | Run `scripts/search.py` |
| "Generate code for this strategy" / "Implement this" | **spec2code** | Generate code using LLM + validate + execute |
| "Run a backtest" / "Test this strategy" | **spec2code** | Run `scripts/backtest.py` |
| "Take this paper end to end" | **both** | paper2spec → spec2code pipeline |
| "Compare results with the paper" | **spec2code** | Run analyzer/diagnosis |

### Full Pipeline Agent Flow

```
1. Receive PDF from user
2. [paper2spec] Parse and extract specs
   → Read references/paper2spec.md for details
3. Present extracted strategies to user for review
4. User selects strategy (or all)
5. [spec2code] For each selected strategy:
   a. Generate data module → signal module → backtest module
   b. Integrate into single script
   c. Validate (AST + structural checks)
   d. Execute backtest (subprocess, timeout-guarded)
   e. Diagnose: compare metrics vs paper
   → Read references/spec2code.md for details
6. Present diagnosis report to user
```

### Library Management

```
library/
├── pairs_trading/
│   ├── paper.pdf, content.json, spec.json, spec.md
│   ├── strategy_0.py          # Generated code
│   ├── results/               # Backtest outputs
│   └── metadata.json
├── momentum_crashes/
│   └── ...
```

Before analyzing a new paper, check for existing entries in `library/`.
Use descriptive slugs for directories.

## Configuration

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `PAPER2SPEC_LIBRARY_PATH` | `./library` | Default output root |
| `PAPER2SPEC_MODEL` | `openai/gpt-4o-mini` | Default LLM model |
| `PAPER2SPEC_INIT_VERSION` | — | Setup completion marker |
| `SPEC2CODE_BACKTEST_TIMEOUT` | `300` | Backtest timeout (seconds) |
| `SPEC2CODE_DATA_CACHE` | `<library>/data_cache` | Data download cache |
| `OPENAI_API_KEY` | — | OpenAI / OpenRouter models |
| `DEEPSEEK_API_KEY` | — | DeepSeek models |
| `ANTHROPIC_API_KEY` | — | Anthropic models |
| `PAPER2SPEC_ARXIV_MIN_INTERVAL` | `3.0` | arXiv rate limiting (seconds) |

## Project Structure

```
paper2spec/          # PDF → structured spec
├── models.py        #   PaperContent, StrategySpec, ExtractionResult
├── parser.py        #   PDF → PaperContent
├── extractor.py     #   PaperContent → ExtractionResult (Layer 0-4)
├── render.py, llm.py, prompts.py, search.py, pdf_utils.py

spec2code/           # Spec → executable code → backtest → diagnosis
├── models.py        #   CodeModules, BacktestResult, DiagnosisReport
├── prompts.py       #   Data/Signal/Backtest/Integration templates
├── validator.py     #   AST + structural validation
├── executor.py      #   Subprocess-based backtest execution
├── analyzer.py      #   Result comparison + report

scripts/             # CLI entry points
├── analyze.py       #   Full paper2spec pipeline
├── parse.py         #   PDF → PaperContent
├── extract.py       #   PaperContent → ExtractionResult
├── search.py        #   Academic paper search
├── generate.py      #   Full spec2code pipeline
├── validate_strategy.py  # Code validation
├── backtest.py      #   Backtest execution

references/          # Deep-dive documentation (read on demand)
├── paper2spec.md    #   Paper2spec detailed guide
├── spec2code.md     #   Spec2code detailed guide
├── backtrader_patterns.md   # Common Backtrader code patterns
├── indicator_cookbook.md     # Indicator implementations
├── data_sources.md          # yfinance/akshare API reference
```

## Technical References

For detailed implementation guidance, read on demand:

- [references/paper2spec.md](references/paper2spec.md) — Paper2spec internals, parser modes, multi-strategy detection
- [references/spec2code.md](references/spec2code.md) — Spec2code agent workflow, output formats, diagnosis
- [references/backtrader_patterns.md](references/backtrader_patterns.md) — Strategy class, data loading, position sizing, cerebro runner
- [references/indicator_cookbook.md](references/indicator_cookbook.md) — Built-in indicators, custom indicators, signal patterns
- [references/data_sources.md](references/data_sources.md) — yfinance, akshare, FRED API reference
