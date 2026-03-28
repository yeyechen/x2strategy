# quant-paper2code

> Any research input → Strategy spec → Executable code → Backtest → Diagnosis report.

```
PDF / Markdown / DOCX / Text → PaperContent → StrategySpec (N strategies) → Backtrader Code → Backtest → Diagnosis
```

**quant-paper2code** (skill name: `anything2strategy`) is an [Agent Skill](https://agentskills.io/) that takes quantitative finance research — papers, drafts, reports, or strategy ideas — end-to-end: from any document to executable, validated backtest code. Two integrated capabilities:

- **paper2spec** — Parse any document (PDF/MD/DOCX/TXT), detect multiple strategies, extract structured specs
- **spec2code** — Generate Backtrader code, validate, execute backtests, diagnose results

Works as an AI agent skill (VS Code Copilot / Claude Code / any [Agent Skills](https://agentskills.io/)-compatible agent) or as standalone Python CLI tools.

## Install

### Option A: As an Agent Skill (recommended)

Clone into any supported skill directory — the AI agent auto-discovers `SKILL.md` and registers `/anything2strategy` as a slash command.

**GitHub Copilot (VS Code / CLI / Coding Agent):**
```bash
git clone https://github.com/ALAGENT-HKU/quant-paper2code.git \
  ~/.copilot/skills/anything2strategy
```

**Claude Code:**
```bash
git clone https://github.com/ALAGENT-HKU/quant-paper2code.git \
  ~/.claude/skills/anything2strategy
```

**Generic (any Agent Skills-compatible tool):**
```bash
git clone https://github.com/ALAGENT-HKU/quant-paper2code.git \
  ~/.agents/skills/anything2strategy
```

**Project-scoped (shared with team via repo):**
```bash
git clone https://github.com/ALAGENT-HKU/quant-paper2code.git \
  .github/skills/anything2strategy
```

Install dependencies:
```bash
cd ~/.copilot/skills/anything2strategy   # or wherever you cloned it
uv sync --extra codegen            # core + backtrader/yfinance/akshare
```

> **Note:** The directory name (`anything2strategy`) must match the `name` field in `SKILL.md`. After install, type `/anything2strategy` in chat to invoke the skill, or the agent auto-loads it when relevant.

首次在 chat 中触发该 skill 时，agent 会自动引导完成 LLM 配置和 API key 设置。

### Option B: As a Standalone CLI Tool

```bash
git clone https://github.com/ALAGENT-HKU/quant-paper2code.git
cd quant-paper2code
uv sync --extra codegen        # core + backtrader/yfinance/akshare
uv sync --extra agent          # + FAISS semantic search (for long papers)
uv sync --extra dev            # + pytest
```

<details>
<summary>Alternative: pip instead of uv</summary>

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[codegen]"    # core + backtest deps
pip install -e ".[agent]"      # + FAISS
pip install -e ".[dev]"        # + pytest
```
</details>

## Quick Start

### End-to-End: Any Input → Spec → Code → Backtest

```bash
# Configure (first time)
cp .env.example .env  # then edit with your API key

# Step 1: Analyze document → extract specs (auto-detects format)
uv run python scripts/analyze.py paper.pdf -o library/my_paper/
uv run python scripts/analyze.py strategy_draft.md -o library/my_draft/
uv run python scripts/analyze.py report.docx -o library/my_report/

# Step 2: Generate code from spec
uv run python scripts/generate.py library/my_paper/spec.json --strategy-index 0

# Step 3: Validate generated code
uv run python scripts/validate_strategy.py library/my_paper/strategy.py

# Step 4: Run backtest
uv run python scripts/backtest.py library/my_paper/strategy.py -o library/my_paper/results/
```

### Paper2Spec Only

```bash
uv run python scripts/analyze.py paper.pdf -o library/my_paper/
uv run python scripts/analyze.py strategy.md -o library/my_draft/
# → content.json, content.md, spec.json, spec.md, metadata.json
```

### Spec2Code Only

```bash
uv run python scripts/generate.py library/my_paper/spec.json --strategy-index 0
# → strategy.py, validation report, backtest results, diagnosis
```

## Features

| Feature | Description |
|---------|-------------|
| **Multi-format input** | PDF, Markdown, DOCX, plain text — auto-detected |
| **End-to-end pipeline** | Document → spec → code → backtest → diagnosis in one workflow |
| **Multi-strategy detection** | Automatically identifies N independent strategies per paper |
| **5-layer LLM extraction** | L0 (detect) → L1-L4 (metadata, indicators, logic, execution) |
| **3-step code generation** | Data module → signal module → backtest module → integration |
| **AST + structural validation** | Syntax check + Backtrader structure verification |
| **Automated backtesting** | Subprocess execution with metric extraction |
| **Result diagnosis** | Compare backtest metrics against paper-reported results |
| **Any LLM provider** | Any [litellm-supported model](https://docs.litellm.ai/docs/providers) |
| **~$0.01/paper** | DeepSeek recommended for best cost-performance ratio |

## Examples

| Paper | Strategies | Status |
|-------|-----------|--------|
| Tactical Asset Allocation (Faber) | 1: GTAA with SMA timing | spec + code |
| Pairs Trading (Goncalves-Pinto et al.) | 3: Distance, Stationarity, Cointegration | spec |
| Value and Momentum (Asness et al.) | 2: Value Factor, Momentum Factor | spec |

Pre-generated outputs → [`examples/`](examples/)

## Project Structure

```
paper2spec/          # PDF → structured spec
  parser.py          #   PDF → PaperContent (Mode A / Mode B)
  extractor.py       #   PaperContent → ExtractionResult (L0-L4)
  models.py, render.py, llm.py, prompts.py, search.py

spec2code/           # Spec → code → backtest → diagnosis
  prompts.py         #   Data/Signal/Backtest/Integration templates
  validator.py       #   AST + structural validation
  executor.py        #   Subprocess-based backtest execution
  analyzer.py        #   Result comparison + report
  models.py, config.py

scripts/             # CLI entry points
  analyze.py         #   Full paper2spec pipeline
  generate.py        #   Full spec2code pipeline
  validate_strategy.py, backtest.py, parse.py, extract.py, search.py

references/          # Agent deep-dive docs (read on demand)
  paper2spec.md, spec2code.md, backtrader_patterns.md,
  indicator_cookbook.md, data_sources.md

schemas/             # JSON Schema for outputs
examples/            # Pre-generated reference outputs
tests/               # Unit + E2E tests
SKILL.md             # Agent instructions (auto-loaded by Copilot / Claude)
```

## Documentation

| Doc | Description |
|-----|-------------|
| [SKILL.md](SKILL.md) | Agent operating instructions — routing, setup, workflow |
| [references/paper2spec.md](references/paper2spec.md) | Paper2spec detailed guide |
| [references/spec2code.md](references/spec2code.md) | Spec2code detailed guide |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Pipeline architecture (中英双语) |

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `PAPER2SPEC_LIBRARY_PATH` | `./library` | Default output root |
| `PAPER2SPEC_MODEL` | `openai/gpt-4o-mini` | LLM model identifier |
| `SPEC2CODE_BACKTEST_TIMEOUT` | `300` | Backtest timeout (seconds) |
| `SPEC2CODE_DATA_CACHE` | `<library>/data_cache` | Data download cache |
| `DEEPSEEK_API_KEY` | — | For DeepSeek models |
| `OPENAI_API_KEY` | — | For OpenAI models |
| `ANTHROPIC_API_KEY` | — | For Anthropic models |

All scripts accept `--model` to override `PAPER2SPEC_MODEL`.

## License

Apache-2.0 — Created by [ALAGENT AI](https://github.com/ALAGENT-HKU)
