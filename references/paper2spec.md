# Paper2Spec — PDF → Strategy Specification

Convert quantitative finance research papers into structured, machine-readable
strategy specifications — with automatic multi-strategy detection.

## What This Does

Given a **PDF** of a quantitative finance paper, paper2spec:

1. **Parses** the paper into structured sections (methodology, signal logic,
  data requirements) via dual-mode extraction (direct LLM or FAISS semantic retrieval).
2. **Detects** if the paper contains multiple independent strategies (Layer 0).
3. **Extracts** a complete specification per strategy through 4 focused LLM
   calls (metadata → indicators → logic pipeline → execution plan).
4. **Grounds** extraction with optional instruction, clarification, or  customization files. Operator-pitfall retrieval is a repair/audit step, not an automatic `extract.py` step.
5. **Renders** all outputs in dual format: machine-readable JSON +
   human-readable Markdown.

## Quick Start

### One-Shot Analysis (recommended)

```bash
uv run python scripts/analyze.py paper.pdf -o library/my_paper/

# Optional: use repair notes / clarifications as authoritative fallback
uv run python scripts/analyze.py paper.pdf -o library/my_paper/ --instructions-dir uploads/
```

This command parses and extracts in one shot, but it does not automatically run
a separate repair CLI. Before any code generation, you should still run the
required review/repair pass against [extraction_quality.md](extraction_quality.md).

Produces:
```
library/my_paper/
├── paper.pdf       # Original PDF (auto-copied)
├── content.json    # PaperContent (machine-readable)
├── content.md      # PaperContent (human-readable)
├── spec.json       # Extracted spec; review/repair before code generation
├── spec.md         # Human-readable extracted spec summary
└── metadata.json   # Analysis metadata
```

### Step-by-Step Pipeline

```bash
# 1. Search for papers (optional)
uv run python scripts/search.py "momentum trading strategy" -n 5

# 2. Parse PDF → PaperContent
uv run python scripts/parse.py paper.pdf -o content.json

# 3. Extract PaperContent → ExtractionResult (multi-strategy)
uv run python scripts/extract.py content.json -o spec.json
uv run python scripts/extract.py content.json -o spec.json --instruction notes.md
```

## Scripts Reference

### `scripts/analyze.py` — Full Pipeline (recommended)

```
uv run python scripts/analyze.py <pdf> [-o DIR] [--parser-mode builtin|agent] [--model MODEL] [--instruction FILE] [--instructions-dir DIR]
```

| Flag | Default | Description |
|------|---------|-------------|
| `-o, --output-dir` | `<PAPER2SPEC_LIBRARY_PATH>/<slug>/` | Output directory |
| `--parser-mode` | `builtin` | `builtin` (fast, <40 pages) or `agent` (FAISS semantic retrieval) |
| `--extractor-mode` | `multilayer` | `multilayer` (recommended) or `single` (legacy) |
| `--instruction` | — | Extra instruction/clarification Markdown file; can be repeated |
| `--instructions-dir` | — | Directory scanned for `*instruction*.md`, `*clarification*.md`, and `*reference*.md` |
| `--model` | env `PAPER2SPEC_MODEL` | Override LLM model |

### `scripts/parse.py` — PDF → PaperContent

```
uv run python scripts/parse.py <pdf> [--mode builtin|agent] [--model MODEL] [-o FILE]
```

### `scripts/extract.py` — PaperContent → ExtractionResult

```
uv run python scripts/extract.py <content.json> [--mode multilayer|single] [--model MODEL] [-o FILE] [--instruction FILE] [--instructions-dir DIR]
```

Before extraction, ask whether the user wants to add clarifications, selected-plan preferences, constraints, or instruction/reference files. Pass any such files through `--instruction` or `--instructions-dir` so extraction is grounded in that context.

If extraction returns multiple strategies/plans, ask which one should continue before repair or code generation. Before any code generation, always review and repair the selected spec against [extraction_quality.md](extraction_quality.md). It is the required quality contract for selected-plan fidelity, `portfolio_weights`, direct-weight sizing, formula grounding, reported/evaluation scaling, and `needs_human_review`. For operator-pitfall checks, run `scripts/operator_pitfalls.py` against [../paper2spec/resources/operator_pitfall_index.md](../paper2spec/resources/operator_pitfall_index.md); do not let the model pick pitfalls from the full index on its own. If the user knows repeated formula, timing, or sizing pitfalls, add concise `## operator:` entries before retrieval.

After extraction, select the target plan, run the repair/review pass for that plan, then check `needs_human_review`. If anything remains unresolved, ask through the interactive dialog before code generation, or let the user provide another instruction file for another repair or re-extraction pass. Do not send raw extraction output straight to code generation.

### `scripts/search.py` — Academic Paper Search

```
uv run python scripts/search.py <query> [--sources arxiv ssrn] [-n 10] [-o FILE]
```

## Output Formats

### ExtractionResult (spec.json)

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

The example above is abbreviated. Current `StrategySpec` objects are expected to carry codegen-facing fields such as `data_semantics`, `executable_explanation`, `position_sizing.steps`, and `needs_human_review`; see [extraction_quality.md](extraction_quality.md) and the generated JSON schema.

### PaperContent (content.json)

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

## Parser Mode Selection

Pick automatically based on paper length — do not ask the user:

| Condition | Mode | Reason |
|-----------|------|--------|
| PDF ≤ 60 pages | `builtin` (Mode A) | Fast. 100K char threshold covers ~33 pages. |
| PDF 60-100 pages | `builtin` (Mode A) | Truncation keeps first 90K + last 10K chars. |
| PDF > 100 pages | `agent` (Mode B) | FAISS semantic retrieval. Requires `[agent]` extra. |

## Multi-Strategy Detection

| Paper | Strategies Detected |
|-------|-------------------|
| Tactical Asset Allocation (Faber) | 1: GTAA with SMA timing |
| Pairs Trading (Goncalves-Pinto et al.) | 3: Distance, Stationarity, Cointegration |
| Value and Momentum Everywhere (Asness et al.) | 2: Value Factor, Momentum Factor |

**Detection rules** (conservative):
- Parameter variations → same strategy
- Long-only vs long-short variants → same strategy, different execution plans
- Fundamentally different signal logic → separate strategies

## Module Structure

```
paper2spec/
├── __init__.py        # v0.3.0
├── models.py          # PaperContent, StrategySpec, ExtractionResult
├── parser.py          # PDF → PaperContent (builtin or FAISS)
├── extractor.py       # PaperContent → ExtractionResult (Layer 0-4)
├── render.py          # JSON → Markdown renderers
├── pdf_utils.py       # Hybrid PDF extraction
├── llm.py             # litellm wrapper
├── prompts.py         # Layer 0-4 prompt templates
└── search.py          # arXiv + SSRN search
```

## Limitations

- **Mode A**: Truncates to first 90K + last 10K chars for >100K text.
- **SSRN search**: Best-effort HTML scraping — may break if SSRN changes layout.
- **Tables/formulas**: Not yet extracted (reserved fields in PaperContent).
- **Multi-strategy**: Conservative detector — may merge borderline-distinct strategies.
