# Skill Internals Reference

> Agent-only reference. Contents here are for the agent's internal use —
> never present raw commands or file structures to users unless explicitly asked.

## .env Format by Provider

### DeepSeek (recommended)
```
PAPER2SPEC_REPLICATIONS_PATH=/absolute/path/to/replications
PAPER2SPEC_MODEL=deepseek/deepseek-chat
DEEPSEEK_API_KEY=sk-actualKeyFromUser
PAPER2SPEC_INIT_VERSION=1
```

### OpenRouter (multi-model gateway)
```
PAPER2SPEC_REPLICATIONS_PATH=/absolute/path/to/replications
PAPER2SPEC_MODEL=openrouter/deepseek/deepseek-chat-v3-0324
OPENROUTER_API_KEY=sk-or-actualKeyFromUser
PAPER2SPEC_INIT_VERSION=1
```

### OpenAI (direct)
```
PAPER2SPEC_REPLICATIONS_PATH=/absolute/path/to/replications
PAPER2SPEC_MODEL=openai/gpt-4o-mini
OPENAI_API_KEY=sk-actualKeyFromUser
PAPER2SPEC_INIT_VERSION=1
```

**Important**: Never write `.env` with placeholder values. Always wait for
the real key from the user, then write the file.

### Initialization Verification

```bash
# Verify key works
uv run python -c "from paper2spec.llm import chat; print(chat('Say OK'))" 2>&1 | head -1
```

Initialization completion policy:
- `PAPER2SPEC_INIT_VERSION` is a quick marker (recommended value: `1`).
- Do not trust marker alone. Always verify runtime: `PAPER2SPEC_REPLICATIONS_PATH`,
  `PAPER2SPEC_MODEL`, and at least one provider API key must all be set.

---

## Script Flags Reference

### `scripts/analyze.py` — Full Pipeline (recommended)

```
uv run python scripts/analyze.py <file> [-o DIR] [--extractor-mode multilayer|single] [--model MODEL] [--instruction FILE] [--instructions-dir DIR]
```

Accepts: `.pdf`, `.md`, `.markdown`, `.docx`, `.txt` (auto-detects from extension).

| Flag | Default | Description |
|------|---------|-------------|
| `-o, --output-dir` | `<PAPER2SPEC_REPLICATIONS_PATH>/<slug>/` | Output directory |
| `--extractor-mode` | `multilayer` | `multilayer` (recommended) or `single` (legacy) |
| `--instruction` | — | Extra instruction/clarification Markdown file to ground extraction; can be repeated |
| `--instructions-dir` | — | Directory scanned for `*instruction*.md`, `*clarification*.md`, and `*reference*.md` |
| `--model` | env `PAPER2SPEC_MODEL` | Override LLM model |

**Outputs**: `content.json`, `content.md`, `spec.json`, `spec.md`, `metadata.json`

### Additional Config Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PAPER2SPEC_INIT_VERSION` | — | Setup completion marker (set to `1`) |
| `PAPER2SPEC_ARXIV_MIN_INTERVAL` | `3.0` | Minimum seconds between arXiv API requests |
| `PAPER2SPEC_SEARCH_MAX_RETRIES` | `3` | Retry count for search HTTP 429/5xx |

### `scripts/parse.py` — Document → PaperContent

```
uv run python scripts/parse.py <file> [--force-ocr] [--model MODEL] [-o FILE]
```

Default output: `<PAPER2SPEC_REPLICATIONS_PATH>/<file_stem>/inputs/content.md`

### `scripts/extract.py` — PaperContent → ExtractionResult

```
uv run python scripts/extract.py <content.md> [--mode multilayer|single] [--model MODEL] [-o FILE] [--instruction FILE] [--instructions-dir DIR]
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

---

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
    }
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

- `spec.md` renders each strategy with tables for indicators, numbered logic
  steps, execution plans, and risk rules — for quick human review.
- `content.md` renders parsed paper sections for verifying extraction quality.

### Output Directory Structure

```
replications/<slug>/
├── paper/<original_file>   # Original document (auto-copied)
├── inputs/
│   ├── content.json      # PaperContent (machine-readable)
│   ├── content.md        # PaperContent (human-readable)
│   ├── spec.json         # ExtractionResult with all strategies
│   ├── spec.md           # Strategy summary (human-readable)
│   └── metadata.json     # Analysis metadata
├── diagnostics/
├── src/                  # generated strategy code (strategy.py)
├── data/                 # parquet caches
├── results/              # metrics, plots, key_pred/
└── config/
```

See `SKILL.md §Output Paths` for the full contract.

---

## Multi-Strategy Detection

The extractor automatically detects multiple independent strategies:

| Paper | Strategies Detected |
|-------|-------------------|
| Tactical Asset Allocation (Faber) | 1: GTAA with SMA timing |
| Pairs Trading (Goncalves-Pinto et al.) | 3: Distance, Stationarity (ADF), Cointegration (Johansen) |
| Value and Momentum Everywhere (Asness et al.) | 2: Value Factor, Momentum Factor |

**Detection rules** (conservative — false splits are worse than missing a split):
- Parameter variations (3-month vs 12-month) → same strategy
- Long-only vs long-short variants → same strategy, different execution plans
- Fundamentally different signal logic → separate strategies

---

## Library Pattern Management

Organize analyzed papers in `replications/`, each paper in its own subdirectory:

```
replications/
├── tactical_asset_allocation/
│   ├── paper/
│   │   └── faber_2007.pdf
│   ├── inputs/
│   │   ├── content.json, content.md
│   │   ├── spec.json, spec.md
│   │   └── metadata.json
│   ├── diagnostics/
│   ├── src/
│   │   └── strategy.py
│   ├── data/    # parquet caches (gitignored)
│   ├── results/
│   │   ├── metrics.json
│   │   ├── diagnosis.md
│   │   ├── portfolio_vs_assets.{csv,png}
│   │   └── key_pred/
│   └── config/
├── pairs_trading/
│   └── ...  (3 strategies)
└── value_momentum/
    └── ...  (2 strategies)
```

See `SKILL.md §Output Paths` for the full layout. Every script and
generated strategy uses `paper_layout(slug)` from `paper2spec/paths.py`
to resolve these paths — never construct them by hand.

**Agent guidelines:**
- Before analyzing, check `replications/` for existing entries (scan
  `inputs/metadata.json`).
- Use descriptive slugs (`momentum_crashes` not `paper1`).
- Cross-paper comparison: read relevant `inputs/spec.json` files and
  synthesize.
- Re-analysis: the source PDF is already in `paper/original.pdf`.

### Handing Off to Spec2Code

```python
import json
result = json.load(open("replications/pairs_trading/inputs/spec.json"))
strategy = result["strategies"][0]  # Pick by index
# Agent reads this spec dict and generates Backtrader code
```

---

## Strategy Virtual Environments

Generated strategies may need their own dependencies. When generating code,
consider creating a dedicated venv in the per-paper directory:

```bash
cd replications/<paper>/
uv venv
uv pip install backtrader yfinance akshare
uv run python src/strategy.py
```

This isolates strategy deps from the skill's own environment.

---

## Python Environment Details

### Selective Installation

```bash
uv sync                    # Core only (paper2spec basic)
uv sync --extra codegen    # + backtrader/yfinance/akshare (for spec2code)
uv sync --extra ocr        # + LightOnOCR-2 + pypdfium2 + torch (for PDF parsing)
uv sync --extra dev        # + pytest (for testing)
uv sync --all-extras       # Everything (recommended)
```

### Without uv

```bash
cd <skill-path>
python -m venv .venv && source .venv/bin/activate
pip install -e ".[codegen,ocr,dev]"
```

---

## Project Structure

```
paper2spec/          # PDF → structured spec
├── __init__.py        # v0.3.0
├── models.py          # PaperContent, StrategySpec, ExtractionResult, StrategyBrief
├── parser.py          # PDF → PaperContent (LightOnOCR-2 + fitz fallback)
├── extractor.py       # PaperContent → ExtractionResult (Layer 0-4)
├── ocr.py             # LightOnOCR-2 inference engine with disk caching
├── operator_pitfall.py # Keyword retrieval over editable pitfall corpus
├── resources/
│   └── operator_pitfall_index.md # User-extensible pitfall corpus
├── render.py          # JSON → Markdown renderers
├── pdf_utils.py       # Simple fitz text extraction (fallback)
├── llm.py             # litellm wrapper
├── prompts.py         # Layer 0-4 prompt templates
└── search.py          # arXiv + SSRN search

spec2code/           # Tools for agent-driven code generation
├── models.py        #   CodeModules, ValidationResult, BacktestMetrics, etc.
├── validator.py     #   AST + structural validation (agent tool)
├── config.py        #   Shared config (reuses paper2spec .env)

scripts/             # CLI entry points (agent-only)
├── analyze.py         # Full paper2spec pipeline
├── parse.py, extract.py, search.py
├── operator_pitfalls.py # Semantic retrieval for repair pitfall context
├── validate_strategy.py
└── generate_schemas.py

schemas/             # JSON Schema definitions
├── paper_content.schema.json
└── strategy_spec.schema.json

references/          # Deep-dive documentation (read on demand)
├── paper2spec.md
├── spec2code.md
├── extraction_quality.md
├── skill-internals.md   # This file
├── backtrader_patterns.md
├── indicator_cookbook.md
└── data_sources.md
```
