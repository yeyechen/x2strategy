<div align="center">

<img src="assets/alagent_logo.png" alt="ALAGENT Logo" width="120">

# X2Strategy

**Any Research Input → Strategy Spec → Executable Code → Backtest → Diagnosis**

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)](https://python.org)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-green.svg)](LICENSE)
[![Agent Skills](https://img.shields.io/badge/Agent_Skills-compatible-blueviolet?logo=visualstudiocode)](https://agentskills.io/)
[![Tests](https://img.shields.io/badge/tests-180_passed-brightgreen)]()
[![LiteLLM](https://img.shields.io/badge/LLM-any_provider-orange?logo=openai)](https://docs.litellm.ai/docs/providers)

[Getting Started](#-getting-started) · [How It Works](#-how-it-works) · [Examples](#-examples) · [Docs](#-documentation) · [简体中文](README_CN.md)

---

*Turn quantitative finance research — papers, drafts, reports, or strategy ideas — into validated, executable trading strategies. Automatically.*

</div>

## Highlights

- **🔬 Multi-Format Input** — PDF papers, Markdown drafts, DOCX reports, plain text. Auto-detected.
- **🧠 5-Layer LLM Extraction** — Multi-strategy detection → indicators → signal logic → execution plan → risk controls.
- **✅ Verified Code Generation** — AST validation + Backtrader structural checks + indicator registry, not just "generate and hope".
- **📊 Automated Backtesting** — Execute, extract metrics, and diagnose against paper-reported performance.
- **🤖 Agent-Native** — Works as an [Agent Skill](https://agentskills.io/) (`/x2strategy`) in VS Code Copilot, Claude Code, or any compatible agent.
- **💰 ~$0.1 per paper** — DeepSeek-powered. Any [LiteLLM-supported provider](https://docs.litellm.ai/docs/providers) works.

## How It Works

```
                        ┌──────────────────────────────────────────────────────────────┐
                        │                    X2Strategy                              │
                        │                                                              │
  PDF / MD / DOCX / TXT │   ┌─────────┐   ┌───────────┐   ┌──────────┐   ┌─────────┐ │
  ─────────────────────►│   │  Parse   ├──►│  Extract   ├──►│ Generate ├──►│Backtest │ │
                        │   │ (parser) │   │ (L0 → L4) │   │  (code)  │   │+ Diagnose││
                        │   └─────────┘   └───────────┘   └──────────┘   └─────────┘ │
                        │        ▼              ▼               ▼             ▼        │
                        │   PaperContent   StrategySpec   Backtrader.py   Report.md   │
                        └──────────────────────────────────────────────────────────────┘
```

| Stage | Input | Output | What Happens |
|:------|:------|:-------|:-------------|
| **Parse** | Any document | `PaperContent` | Format-aware extraction (PyMuPDF / direct read / python-docx) |
| **Extract** | PaperContent | `StrategySpec[]` | 5-layer LLM: detect strategies → extract indicators, logic, execution, risk |
| **Generate** | StrategySpec | `strategy.py` | Data module → signal module → backtest module → integration |
| **Validate** | strategy.py | Pass / Fail | AST syntax + Backtrader structure + indicator existence checks |
| **Backtest** | strategy.py | Metrics | Subprocess execution with timeout, metric extraction |
| **Diagnose** | Metrics | `report.md` | Compare against paper-reported results, flag deviations |

## Getting Started

### Option A: As an Agent Skill (Recommended)

> [Agent Skills](https://agentskills.io/) is an open standard. Clone into the agent's skill directory — it auto-discovers `SKILL.md` and registers the `/x2strategy` slash command.

<table>
<tr><td><b>GitHub Copilot</b></td><td>

```bash
git clone https://github.com/ALAGENT-HKU/x2strategy.git ~/.copilot/skills/x2strategy
```

</td></tr>
<tr><td><b>Claude Code</b></td><td>

```bash
git clone https://github.com/ALAGENT-HKU/x2strategy.git ~/.claude/skills/x2strategy
```

</td></tr>
<tr><td><b>Project-scoped</b></td><td>

```bash
git clone https://github.com/ALAGENT-HKU/x2strategy.git .github/skills/x2strategy
```

</td></tr>
</table>

Then install dependencies:

```bash
cd ~/.copilot/skills/x2strategy   # or wherever you cloned
# if you haven't installed uv, run `pip install uv`
uv sync --extra codegen                  # core + backtrader + yfinance + akshare
```

> [!IMPORTANT]
> The directory name **must** be `x2strategy` (matching the `name` field in `SKILL.md`). Once installed, type `/x2strategy` in chat or the agent auto-activates when relevant.

### Option B: Standalone CLI

```bash
git clone https://github.com/ALAGENT-HKU/x2strategy.git && cd x2strategy
uv sync --extra codegen    # core + backtest
uv sync --extra agent      # + FAISS semantic search (for 100+ page papers)
uv sync --extra dev        # + pytest
```

<details>
<summary>pip alternative</summary>

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[codegen,agent,dev]"
```

</details>

### Quick Start

```bash
# 1. Configure
cp .env.example .env          # add your API key (DEEPSEEK_API_KEY recommended)

# 2. Extract strategy specs from any input format
uv run python scripts/analyze.py paper.pdf -o library/my_paper/
uv run python scripts/analyze.py strategy_draft.md -o library/my_draft/
uv run python scripts/analyze.py report.docx -o library/my_report/

# 3. Generate Backtrader code from spec
uv run python scripts/generate.py library/my_paper/spec.json --strategy-index 0

# 4. Validate + backtest
uv run python scripts/validate_strategy.py library/my_paper/strategy.py
uv run python scripts/backtest.py library/my_paper/strategy.py -o library/my_paper/results/
```

Or use the **agent skill** — just say:

> *"Analyze this paper and implement the main strategy"* + attach a PDF

The agent handles everything: parsing, extraction, code generation, validation, backtesting, and diagnosis.

## Supported Input Formats

| Format | Extensions | Parser | Notes |
|:-------|:-----------|:-------|:------|
| **PDF** | `.pdf` | PyMuPDF → Mode A (direct) or Mode B (FAISS) | Full support, covering 95%+ of papers |
| **Markdown** | `.md` `.markdown` | Direct text read | Ideal for strategy drafts and notes |
| **Word** | `.docx` | python-docx (`uv sync --extra docx`) | Internal research reports |
| **Plain text** | `.txt` | Direct read | Raw strategy descriptions |

Format is auto-detected from file extension. No configuration needed.

## Examples

Pre-generated outputs from real papers are available in [`examples/`](examples/):

| Paper | Strategies Detected | Artifacts |
|:------|:-------------------|:----------|
| **Tactical Asset Allocation** (Faber 2007) | 1 — GTAA with SMA timing | spec + code |
| **Pairs Trading** (Goncalves-Pinto et al.) | 3 — Distance, Stationarity, Cointegration | spec |
| **Value and Momentum** (Asness et al.) | 2 — Value Factor, Momentum Factor | spec |

<details>
<summary>Example output structure</summary>

```
library/tactical_aa/
├── content.json          # Parsed paper content
├── content.md            # Human-readable paper summary
├── spec.json             # Structured strategy specification
├── spec.md               # Human-readable spec
├── metadata.json         # Run metadata (model, timing, etc.)
├── strategy.py           # Generated Backtrader code
├── validation_report.md  # AST + structural validation results
└── results/
    ├── backtest_output.txt
    └── diagnosis_report.md
```

</details>

## Project Structure

```
x2strategy/
├── paper2spec/                 # Phase 1: Document → Structured Spec
│   ├── parser.py               #   Multi-format parser (PDF / MD / DOCX / TXT)
│   ├── extractor.py            #   PaperContent → ExtractionResult (L0-L4)
│   ├── models.py               #   Data models (PaperContent, StrategySpec, etc.)
│   ├── prompts.py              #   5-layer extraction prompt templates
│   ├── llm.py                  #   LiteLLM unified interface
│   ├── render.py               #   JSON → Markdown rendering
│   └── search.py               #   arXiv + SSRN paper search
│
├── spec2code/                  # Phase 2: Spec → Code → Backtest → Diagnosis
│   ├── prompts.py              #   Data / Signal / Backtest / Integration templates
│   ├── validator.py            #   AST + structural + indicator validation
│   ├── executor.py             #   Subprocess-based backtest execution
│   ├── analyzer.py             #   Result comparison + diagnosis report
│   └── models.py               #   CodeModules, ValidationResult
│
├── references/                 # Verified domain knowledge (not LLM hallucinations)
│   ├── backtrader_patterns.md  #   Source-verified Backtrader patterns
│   ├── indicator_cookbook.md    #   Official indicator params (from bt source code)
│   ├── data_sources.md         #   yfinance + akshare API docs
│   ├── paper2spec.md           #   Paper2Spec deep-dive guide
│   └── spec2code.md            #   Spec2Code deep-dive guide
│
├── scripts/                    # CLI entry points
│   ├── analyze.py              #   Full paper2spec pipeline
│   ├── generate.py             #   Full spec2code pipeline
│   └── validate_strategy.py    #   Standalone validation
│
├── schemas/                    # JSON Schema definitions
├── examples/                   # Pre-generated reference outputs
├── tests/                      # 180+ unit & integration tests
├── SKILL.md                    # Agent Skill entry point
└── pyproject.toml              # Project config & dependencies
```

## Key Design Decisions

<table>
<tr>
<td width="50%">

### Why Reference Docs, Not Prompts?

LLMs frequently hallucinate Backtrader API details:
- SMA default `period` is `30`, not `20`
- RSI uses `SmoothedMovingAverage`, not EMA
- BollingerBands lines are `.top/.mid/.bot`, not `.upper/.lower`

Our `references/` directory contains **source-code-verified** knowledge. The agent reads these docs on demand — zero hallucination on API details.

</td>
<td width="50%">

### Why Structured Specs as Intermediate?

Going directly from paper → code loses auditability. The `StrategySpec` intermediate:
1. **Auditable** — humans can review the spec before code generation
2. **Reusable** — same spec can target different backtest engines
3. **Testable** — spec extraction and code generation are independently verifiable

</td>
</tr>
</table>

## Configuration

| Variable | Default | Description |
|:---------|:--------|:------------|
| `PAPER2SPEC_LIBRARY_PATH` | `./library` | Output root directory |
| `PAPER2SPEC_MODEL` | `openai/gpt-4o-mini` | LLM model ([LiteLLM format](https://docs.litellm.ai/docs/providers)) |
| `SPEC2CODE_BACKTEST_TIMEOUT` | `300` | Backtest timeout in seconds |
| `DEEPSEEK_API_KEY` | — | DeepSeek (recommended: best cost/quality) |
| `OPENROUTER_API_KEY` | — | OpenRouter (one key, all models) |
| `OPENAI_API_KEY` | — | OpenAI direct |

All scripts accept `--model` to override `PAPER2SPEC_MODEL`.

## Documentation

| Resource | Description |
|:---------|:------------|
| [SKILL.md](SKILL.md) | Agent skill instructions — routing, setup, interaction gates |
| [references/paper2spec.md](references/paper2spec.md) | Paper → Spec extraction deep-dive |
| [references/spec2code.md](references/spec2code.md) | Spec → Code generation deep-dive |
| [references/backtrader_patterns.md](references/backtrader_patterns.md) | Source-verified Backtrader patterns |
| [references/indicator_cookbook.md](references/indicator_cookbook.md) | Official indicator parameter reference |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Pipeline architecture |

## Testing

```bash
pytest tests/ -v              # 180+ deterministic tests
pytest tests/ -v --run-real   # + real API tests (requires DEEPSEEK_API_KEY)
```

## Roadmap

- [ ] Multi-engine support (Zipline, VectorBT)
- [ ] Table & formula extraction from PDFs
- [ ] Batch processing (multiple papers in parallel)
- [ ] [qsa-benchmark](https://github.com/ALAGENT-HKU) integration (50-paper regression suite)
- [ ] Canonical `StrategySpec` schema unification with QSA platform

## Contributing

We welcome contributions! Please see the [Architecture Doc](docs/ARCHITECTURE.md) for codebase orientation.

```bash
git clone https://github.com/ALAGENT-HKU/x2strategy.git && cd x2strategy
uv sync --all-extras
cp .env.example .env  # add API key
pytest tests/ -v      # verify everything passes
```

## License

[Apache-2.0](LICENSE) · Built by **[ALAGENT AI 优彦智能](http://home.alagent.cloud)** — Verifiable & Trustworthy Financial AI

---

<div align="center">

## 💬 Join the Community

<a href="https://home.alagent.cloud">🌐 Website</a> &nbsp;·&nbsp; <a href="https://github.com/ALAGENT-HKU">GitHub</a>

<br>

<img src="assets/wechat_qr.jpg" alt="WeChat Group QR" width="260">

**Scan to join the ALAGENT Open-Source WeChat Group**

</div>
