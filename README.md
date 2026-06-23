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
- **🧾 Grounded Extraction Quality** — Optional instruction/customization/clarification context, retrieved repair-time operator-pitfall checks, canonical `portfolio_weights`, and structured `needs_human_review` flags.
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
| **Extract** | PaperContent | `StrategySpec[]` | 5-layer LLM with optional instruction grounding: detect strategies → extract indicators, logic, execution, risk |
| **Generate** | StrategySpec | `strategy.py` | Data module → signal module → backtest module → integration |
| **Validate** | strategy.py | Pass / Fail | AST syntax + Backtrader structure + indicator existence checks |
| **Backtest** | strategy.py | Metrics | Subprocess execution with timeout, metric extraction |
| **Diagnose** | Metrics | `report.md` | Compare against paper-reported results, flag deviations |

## Getting Started

### As an Agent Skill

[Agent Skills](https://agentskills.io/) is an open standard. Clone into the agent's skill directory — it auto-discovers `SKILL.md` and registers the `/x2strategy` slash command.

#### Install to OpenClaw / OpenClaw Users

For OpenClaw users, install directly from ClawHub:

```bash
openclaw skills install patrick-lew/x2strategy
```

Or use the ClawHub CLI:

```bash
npx clawhub@latest install x2strategy
```

For remote or guided setup, paste this prompt into OpenClaw:

```text
Install the skill "X2strategy" (patrick-lew/x2strategy) from ClawHub.
Skill page: https://clawhub.ai/patrick-lew/x2strategy
Keep the work scoped to this skill only.
After install, inspect the skill metadata and help me finish setup.
Use only the metadata you can verify from ClawHub; do not invent missing requirements.
Ask before making any broader environment changes.
```

#### Install to Claude Code / Codex / Copilot 

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

Then install dependencies. After successful skill installation, the agent may auto-install them during initialization, but manual setup is the most predictable path:

```bash
cd ~/.copilot/skills/x2strategy   # or wherever you cloned
# if you haven't installed uv, run `pip install uv`
uv sync --all-extras
```

<details>
<summary>Manual dependency variants</summary>

```bash
# minimum skill runtime
uv sync --extra agent --extra codegen

# add DOCX parsing support
uv sync --extra agent --extra codegen --extra docx

# pip alternative
python -m venv .venv && source .venv/bin/activate
pip install -e ".[codegen,agent,docx,dev]"
```

</details>

> [!IMPORTANT]
> The directory name **must** be `x2strategy` (matching the `name` field in `SKILL.md`). Once installed, type `/x2strategy` in chat or the agent auto-activates when relevant.

### Skill Quick Start

```bash
# 1. Configure the skill workspace
cp .env.example .env          # add your API key (DEEPSEEK_API_KEY recommended)

# 2. Start the skill in your agent
# /x2strategy
```

Then ask for work in natural language, for example:

> *"Analyze this paper and implement the main strategy."* + attach a PDF + optional data files + optional clarification/user-customization prompts such as *"When the paper underspecifies a formula, you can either explicitly ask me or refer to the sample_instruction.md file."*

The skill handles parsing, extraction, code generation, validation, backtesting, and diagnosis.
Before extraction, it should ask whether you want to add custom instructions, implementation constraints, known pitfalls, or reference files.
After extraction and strategy/plan selection, it must read [references/extraction_quality.md](references/extraction_quality.md) before any repair, code generation, or deterministic local implementation.
It should also use the same interactive flow when you pick search results, add repair-time pitfall notes or clarifications, approve inferred defaults, or resolve any `needs_human_review` items surfaced by compare/repair.
After code generation and diagnosis, it should present an interactive next-action menu instead of assuming the workflow is finished.

Generated files should be written under `PAPER2SPEC_REPLICATIONS_PATH/<slug>/` by default, for example `content.json`, `spec.json`, the generated implementation file, and `results/metrics.json`. If a referenced Copilot/VS Code log path is empty or incomplete, regenerate the artifacts from the original paper, instructions, and data instead of relying on the log summary.

Spec2Code outputs should include Sharpe ratio, maximum drawdown, total return, and return value/final portfolio value whenever those metrics are meaningful for the confirmed implementation target.

Here, “custom instructions” means extra extraction requirements you want the skill to follow, not shell commands or implementation details.

- Use them to say which rules or assumptions must be preserved.
- Use them to point out mistakes or pitfalls the skill should avoid.
- Use them to add background context that you have already confirmed.

Examples:
"Only implement the main strategy in the paper, not the appendix variants."
"If the weighting rule is ambiguous, prefer equal weight."
"Treat the rebalance frequency as monthly, not weekly."

If extraction, compare, or repair leaves `needs_human_review` questions, it should ask them through an interactive dialog before generating code. In VS Code Copilot, that means `vscode_askQuestions` when available rather than only writing the questions in prose. If validation or diagnosis still leaves unresolved decisions, it should ask again before silently retrying or stopping.

## Supported Input Formats

| Format | Extensions | Parser | Notes |
|:-------|:-----------|:-------|:------|
| **PDF** | `.pdf` | PyMuPDF → Mode A (direct) or Mode B (FAISS) | Full support, covering 95%+ of papers |
| **Markdown** | `.md` `.markdown` | Direct text read | Ideal for strategy drafts and notes |
| **Word** | `.docx` | python-docx (`uv sync --extra docx`) | Internal research reports |
| **Plain text** | `.txt` | Direct read | Raw strategy descriptions |

Format is auto-detected from file extension. No configuration needed.

## Examples

The primary shipped example in [`examples/`](examples/) is the UPSA paper2code case, generated by Copilot GPT-5.4:

| Paper | Strategies Detected | Artifacts |
|:------|:-------------------|:----------|
| **Universal Portfolio Shrinkage Approximation** (Kelly, Malamud, Pourmohammadi & Trojani 2025) | 1 — UPSA ridge-ensemble portfolio | content + spec + paper2code contract |

The UPSA example lives in `examples/upsa/`. Reproducible inputs are stored in `examples/upsa/input/`, and the generated implementation is `examples/upsa/universal_portfolio_shrinkage_approximation.py`.

<details>
<summary>Example output structure</summary>

```
examples/upsa/
├── README.md
├── upsa_content.json
├── upsa_content.md
├── upsa_spec.json
├── upsa_spec.md
├── upsa_operator_pitfall_context.md
├── upsa_review_and_diagnosis.md
├── upsa_metadata.json
├── universal_portfolio_shrinkage_approximation.py
└── input/
    ├── P10_Kelly_Malamud_Pourmohammadi_Trojani_2025_NBER.pdf
    ├── sample_instruction.md
    ├── jkp_factors_wide.csv
    ├── jkp_factors_long.csv
    └── upsa_weights.csv
```

</details>

> [!IMPORTANT]
> Not every strategy extracted by this skill is suitable for direct broker-connected (live/paper) trading. Many research strategies consume factor returns, synthetic portfolios, ranking panels, or other non-tradable inputs; some are portfolio-construction or SDF/asset-pricing procedures rather than order-generating live strategies. The open-source skill focuses on grounded extraction, code generation, validation, and research backtests. ALAGENT's website can generate broker-connected strategies when the selected strategy and data contract are suitable for live/paper trading.

## Project Structure

```
x2strategy/
├── paper2spec/                 # Phase 1: Document → Structured Spec
│   ├── __init__.py
│   ├── config.py               #   Environment and replications-path configuration
│   ├── parser.py               #   Multi-format parser (PDF / MD / DOCX / TXT)
│   ├── pdf_utils.py            #   PDF extraction helpers
│   ├── extractor.py            #   PaperContent → ExtractionResult (L0-L4)
│   ├── models.py               #   Data models (PaperContent, StrategySpec, etc.)
│   ├── prompts.py              #   5-layer extraction prompt templates
│   ├── operator_pitfall.py      #   Semantic retrieval for repair pitfall checks
│   ├── resources/
│   │   └── operator_pitfall_index.md # Editable pitfall corpus for retrieval
│   ├── llm.py                  #   LiteLLM unified interface
│   ├── render.py               #   JSON → Markdown rendering
│   └── search.py               #   arXiv + SSRN paper search
│
├── spec2code/                  # Phase 2 support: agent-driven codegen validation
│   ├── __init__.py
│   ├── validator.py            #   AST + structural + indicator validation
│   ├── config.py               #   Codegen and backtest configuration
│   └── models.py               #   CodeModules, ValidationResult, BacktestMetrics
│
├── references/                 # Verified domain knowledge (not LLM hallucinations)
│   ├── backtrader_patterns.md  #   Source-verified Backtrader patterns
│   ├── indicator_cookbook.md    #   Official indicator params (from bt source code)
│   ├── data_sources.md         #   yfinance + akshare API docs
│   ├── extraction_quality.md    #   Grounded extraction / repair quality rules
│   ├── paper2spec.md           #   Paper2Spec deep-dive guide
│   ├── spec2code.md            #   Spec2Code deep-dive guide
│   └── skill-internals.md      #   Skill setup and environment details
│
├── scripts/                    # CLI entry points
│   ├── analyze.py              #   Full paper2spec pipeline
│   ├── extract.py              #   Extract specs from parsed content
│   ├── parse.py                #   Parse documents into PaperContent
│   ├── search.py               #   Search for papers
│   ├── operator_pitfalls.py     #   Retrieve matched operator-pitfall context
│   ├── generate_schemas.py     #   Generate JSON schemas
│   ├── run_full_tests.sh       #   Test runner helper
│   └── validate_strategy.py    #   Standalone validation
│
├── docs/                       # Architecture and design docs
│   └── ARCHITECTURE.md
│
├── assets/                     # README / skill images
├── schemas/                    # JSON Schema definitions
├── examples/                   # Pre-generated reference outputs
├── tests/                      # 180+ unit & integration tests
├── .env.example                # Environment variable template
├── requirements.txt            # pip fallback dependencies
├── README_CN.md                # Chinese README
├── SKILL.md                    # Agent Skill entry point
├── pyproject.toml              # Project config & dependencies
└── uv.lock                     # Locked uv dependency graph
```

## Key Design Decisions

### Why Reference Docs, Not Prompts?

LLMs frequently hallucinate Backtrader API details:
- SMA default `period` is `30`, not `20`
- RSI uses `SmoothedMovingAverage`, not EMA
- BollingerBands lines are `.top/.mid/.bot`, not `.upper/.lower`

Our `references/` directory contains **source-code-verified** knowledge. The agent reads these docs on demand instead of relying on improvised API recall.

### Why Structured Specs as Intermediate?

Going directly from paper → code loses auditability. The `StrategySpec` intermediate:
- **Auditable** — humans can review the spec before code generation
- **Reusable** — the same spec can target different backtest engines
- **Testable** — extraction and code generation are independently verifiable

### Grounded Extraction and Repair

`paper2spec` supports optional instruction/clarification context during
extraction. Use this when a paper has appendix-only formulas, missing constants,
ambiguous allocation logic, or the user wants to customize extraction requirements.

- The skill should ask for instruction files, clarifications, or reference notes before extraction when the input is ambiguous.
- [references/extraction_quality.md](references/extraction_quality.md) is the canonical audit guide for manual review.
- For repair-style RAG, use only the pitfalls retrieved from [paper2spec/resources/operator_pitfall_index.md](paper2spec/resources/operator_pitfall_index.md), not the full index.
- Ground truth still comes from the paper, selected plan, user clarifications, and approved customization notes. The pitfall index is only an audit aid.

## Configuration

| Variable | Default | Description |
|:---------|:--------|:------------|
| `PAPER2SPEC_REPLICATIONS_PATH` | `./replications` | Output root directory |
| `PAPER2SPEC_MODEL` | `openai/gpt-4o-mini` | LLM model ([LiteLLM format](https://docs.litellm.ai/docs/providers)) |
| `SPEC2CODE_BACKTEST_TIMEOUT` | `300` | Backtest timeout in seconds |
| `DEEPSEEK_API_KEY` | — | DeepSeek (recommended: best cost/quality) |
| `OPENROUTER_API_KEY` | — | OpenRouter (one key, all models) |
| `OPENAI_API_KEY` | — | OpenAI direct |
| `ANTHROPIC_API_KEY` | — | Anthropic direct |

All scripts accept `--model` to override `PAPER2SPEC_MODEL`.

## Documentation

| Resource | Description |
|:---------|:------------|
| [SKILL.md](SKILL.md) | Agent skill instructions — setup, single workflow, HITL review, output paths |
| [references/paper2spec.md](references/paper2spec.md) | Paper → Spec extraction deep-dive |
| [references/extraction_quality.md](references/extraction_quality.md) | Grounded extraction and repair quality rules |
| [paper2spec/resources/operator_pitfall_index.md](paper2spec/resources/operator_pitfall_index.md) | Editable semantic retrieval corpus for high-risk formula pitfalls |
| [references/spec2code.md](references/spec2code.md) | Spec → Code generation deep-dive |
| [references/backtrader_patterns.md](references/backtrader_patterns.md) | Source-verified Backtrader patterns |
| [references/indicator_cookbook.md](references/indicator_cookbook.md) | Official indicator parameter reference |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Pipeline architecture |

## Testing

```bash
pytest tests/ -v              # 180+ deterministic tests
pytest tests/ -v --run-real   # + real API tests (requires DEEPSEEK_API_KEY)
```

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

<a href="https://home.alagent.cloud">🌐 Website</a> &nbsp;·&nbsp; <a href="https://github.com/ALAGENT-HKU">GitHub</a> &nbsp;·&nbsp; <a href="mailto:contact@alagent.cloud">📧 contact@alagent.cloud</a>

<br>

<img src="assets/wechat_QR.jpg" alt="WeChat Group QR" width="260">

**Scan to join the ALAGENT Open-Source WeChat Group**

</div>
