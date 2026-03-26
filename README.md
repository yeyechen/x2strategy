# paper2spec

> Extract structured strategy specifications from quantitative finance research papers — with automatic multi-strategy detection.

```
PDF → PaperContent → ExtractionResult (N strategies) → JSON + Markdown
```

**paper2spec** is an [Agent Skill](https://agentskills.io/) that parses quantitative finance PDFs into machine-readable strategy specs. It works as an AI agent skill (VS Code Copilot / Claude Code / Copilot CLI) or as a standalone Python CLI tool.

## Install

### Option A: As an Agent Skill

paper2spec follows the open [Agent Skills standard](https://agentskills.io/specification). Clone it into any supported skill directory — the AI agent auto-discovers the `SKILL.md` file.

**GitHub Copilot (VS Code / CLI / Coding Agent):**
```bash
git clone https://github.com/alagent-ai/quant-paper2spec.git \
  ~/.copilot/skills/paper2spec
```

**Claude Code:**
```bash
git clone https://github.com/alagent-ai/quant-paper2spec.git \
  ~/.claude/skills/paper2spec
```

**Project-scoped** (shared via repo, add to `.gitignore` or commit):
```bash
git clone https://github.com/alagent-ai/quant-paper2spec.git \
  .github/skills/paper2spec
```

Then install Python dependencies:
```bash
cd ~/.copilot/skills/paper2spec   # or wherever you cloned it
uv sync                            # install core deps
```

**无需手动配置 API key** — 首次在 chat 中触发该 skill 时，agent 会自动引导你完成 LLM 选择、API key 配置（写入 `.env` 文件），并验证连接。

> **Tip:** You can also add a custom path via VS Code setting `chat.agentSkillsLocations`.

After setup, the skill activates automatically when you mention quant papers, strategy extraction, or PDF analysis in chat.

### Option B: As a Standalone CLI Tool

```bash
git clone https://github.com/alagent-ai/quant-paper2spec.git
cd quant-paper2spec
uv sync                        # core (litellm + PyMuPDF)
uv sync --extra agent          # + FAISS semantic search (for long papers)
uv sync --extra dev            # + pytest (for development)
```

<details>
<summary>Alternative: pip instead of uv</summary>

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .               # core
pip install -e ".[agent]"      # + FAISS
pip install -e ".[dev]"        # + pytest
```
</details>

## Quick Start

> **Agent Skill 用户**：直接在 chat 中提及论文分析即可，agent 首次会引导你完成所有配置。

**CLI 用户**：手动配置环境变量或 `.env` 文件：

```bash
# Option 1: .env file (recommended — persists across sessions)
cp .env.example .env  # then edit .env

# Option 2: shell environment
export PAPER2SPEC_MODEL="deepseek/deepseek-chat"
export DEEPSEEK_API_KEY="sk-..."

# Full pipeline: PDF → content + spec in JSON & Markdown
uv run python scripts/analyze.py paper.pdf -o library/my_paper/
```

Output:
```
library/my_paper/
├── paper.pdf       # Original PDF (auto-copied)
├── content.json    # Parsed paper (machine-readable)
├── content.md      # Parsed paper (human-readable)
├── spec.json       # Extracted strategies (machine-readable)
├── spec.md         # Strategy summary (human-readable)
└── metadata.json   # Analysis metadata
```

Step-by-step alternative:
```bash
uv run python scripts/parse.py paper.pdf -o content.json
uv run python scripts/extract.py content.json -o spec.json
```

## Features

| Feature | Description |
|---------|-------------|
| **Multi-strategy detection** | Automatically identifies N independent strategies from a single paper |
| **5-layer LLM extraction** | L0 (detect) → L1-L4 (metadata, indicators, logic, execution) per strategy |
| **Dual-format output** | JSON (machine-readable) + Markdown (human-readable) |
| **Dual-mode parsing** | Mode A: fast direct LLM (≤100 pages); Mode B: FAISS RAG (long papers) |
| **Any LLM provider** | Any [litellm-supported model](https://docs.litellm.ai/docs/providers) — DeepSeek, OpenAI, Anthropic, etc. |
| **~$0.01/paper** | DeepSeek recommended for best cost-performance ratio |

## Examples

| Paper | Detected |
|-------|----------|
| Tactical Asset Allocation (Faber) | 1 strategy: GTAA with SMA timing |
| Pairs Trading (Goncalves-Pinto et al.) | 3 strategies: Distance, Stationarity, Cointegration |
| Value and Momentum (Asness et al.) | 2 strategies: Value Factor, Momentum Factor |

Pre-generated outputs → [`examples/`](examples/)

## Project Structure

```
paper2spec/          # Core library
  parser.py          # PDF → PaperContent (Mode A / Mode B)
  extractor.py       # PaperContent → ExtractionResult (L0-L4)
  models.py          # Pydantic models
  render.py          # JSON → Markdown
scripts/             # CLI entry points
  analyze.py         # Full pipeline
  parse.py / extract.py / search.py
schemas/             # JSON Schema for outputs
examples/            # Pre-generated reference outputs
tests/               # Unit + E2E tests (132 tests)
docs/                # Architecture documentation
SKILL.md             # Agent instructions (auto-loaded by Copilot / Claude)
.env.example         # Environment config template
```

## Documentation

| Doc | Description |
|-----|-------------|
| [SKILL.md](SKILL.md) | Full agent operating instructions — setup, scripts, output formats, parser modes, multi-strategy detection, configuration |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Pipeline architecture — Mode A/B data flow, 5-layer extraction, parallelization, performance benchmarks (中英双语) |

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `PAPER2SPEC_MODEL` | `openai/gpt-4o-mini` | LLM model identifier |
| `DEEPSEEK_API_KEY` | — | For DeepSeek models |
| `OPENAI_API_KEY` | — | For OpenAI models |
| `ANTHROPIC_API_KEY` | — | For Anthropic models |

All scripts accept `--model` to override `PAPER2SPEC_MODEL`.

## License

Apache-2.0 — Created by [ALAGENT AI](https://github.com/alagent-ai)
