# Spec2Code — Strategy Specification → Executable Backtest

Convert structured strategy specifications into executable Backtrader code,
run backtests locally, and diagnose results against paper-reported metrics.

## What This Does

Given a **spec.json** produced by paper2spec, spec2code:

1. **Generates** executable Backtrader code in 3 modules (data fetching,
   signal logic, backtest runner) plus an integration module.
2. **Validates** the generated code via AST syntax check + structural
   verification (Strategy class, cerebro runner, etc.).
3. **Executes** the backtest in a local subprocess with metric extraction.
4. **Diagnoses** results by comparing backtest metrics against the spec's
   expected performance (Sharpe, returns, drawdown, etc.).

## Quick Start

### Full Pipeline (agent-driven)

The agent workflow for spec2code:

```
1. Read spec.json from library/<paper>/spec.json
2. Select strategy index (0 for first strategy)
3. For each module, generate code using LLM with the appropriate prompt
4. Validate → fix → execute → diagnose
```

### CLI Scripts

```bash
# Validate existing strategy code
uv run python scripts/validate_strategy.py strategy.py

# Run backtest on existing code
uv run python scripts/backtest.py strategy.py -o results/ --timeout 600

# Full pipeline (spec → validate → backtest → report)
uv run python scripts/generate.py library/pairs_trading/spec.json --strategy-index 0
```

## Agent Workflow (Detailed)

### Phase 1: Data Module

Generate code that fetches the required market data.

**Input**: Strategy spec's `data_description`, asset class, date ranges.
**Output**: Python script that downloads data via yfinance/akshare and saves to CSV
or returns a DataFrame.

Read [data_sources.md](data_sources.md) for yfinance/akshare API patterns.

### Phase 2: Signal Module

Generate the signal computation logic.

**Input**: Strategy spec's `indicators` and `logic_pipeline`.
**Output**: Backtrader Strategy class with `__init__` (indicators) and `next` (signals).

Read [indicator_cookbook.md](indicator_cookbook.md) for indicator implementations.

### Phase 3: Backtest Module

Generate the backtest runner (cerebro setup, broker config, analyzers).

**Input**: Strategy spec's `execution_plan` and `risk_management`.
**Output**: Complete runnable backtest script with metrics output.

Read [backtrader_patterns.md](backtrader_patterns.md) for common patterns.

### Phase 4: Integration & Validation

Merge all modules into a single self-contained Python script, validate, execute.

```python
from spec2code.validator import validate_code
from spec2code.executor import run_backtest
from spec2code.analyzer import analyze_results, render_report

# 1. Validate
result = validate_code(combined_code)
if not result.valid:
    # Fix errors and retry

# 2. Execute
backtest = run_backtest(combined_code, output_dir="results/")

# 3. Diagnose
report = analyze_results(spec, backtest)
markdown = render_report(report, backtest)
```

## Scripts Reference

### `scripts/generate.py` — Full Pipeline

```
uv run python scripts/generate.py <spec.json> [--strategy-index N] [-o DIR] [--timeout SEC]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--strategy-index` | `0` | Which strategy from spec to generate code for |
| `-o, --output-dir` | `<spec_dir>/` | Where to save generated code and report |
| `--timeout` | `300` | Backtest execution timeout in seconds |

### `scripts/validate_strategy.py` — Validate Code

```
uv run python scripts/validate_strategy.py <strategy.py>
```

Checks: syntax (AST parse), backtrader import, Strategy class definition,
cerebro runner, `__main__` guard.

### `scripts/backtest.py` — Run Backtest

```
uv run python scripts/backtest.py <strategy.py> [-o DIR] [--timeout SEC]
```

Executes in subprocess, extracts metrics (Sharpe, return, drawdown, trades).

## Output Formats

### BacktestResult

The executor returns:
```json
{
  "status": "success",
  "metrics": {
    "total_return": 0.234,
    "annual_return": 0.112,
    "sharpe_ratio": 1.45,
    "max_drawdown": -0.089,
    "num_trades": 47,
    "win_rate": 0.617,
    "profit_factor": 1.82,
    "final_value": 123400.0,
    "start_value": 100000.0
  },
  "execution_time_seconds": 12.3
}
```

### DiagnosisReport

The analyzer compares backtest results vs spec expectations:
```json
{
  "strategy_name": "Minimum Distance Pairs Trading",
  "match_status": "partial_match",
  "expected": {"sharpe_ratio": 1.8, "annual_return": 0.15},
  "actual": {"sharpe_ratio": 1.45, "annual_return": 0.112},
  "deviations": ["Sharpe ratio 19% below expected"],
  "recommendations": ["Check signal entry/exit thresholds"]
}
```

## Module Structure

```
spec2code/
├── __init__.py     # v0.1.0
├── config.py       # Shared config (reuses paper2spec .env)
├── models.py       # CodeModules, ValidationResult, BacktestResult, DiagnosisReport
├── prompts.py      # Data/Signal/Backtest/Integration prompt templates
├── validator.py    # AST + structural validation
├── executor.py     # Subprocess-based backtest execution
└── analyzer.py     # Result comparison + Markdown report
```

## Code Generation Prompts

The agent uses 4 prompt templates (in `spec2code/prompts.py`):

1. **DATA_MODULE_PROMPT** — Generates data fetching code from spec's data requirements
2. **SIGNAL_MODULE_PROMPT** — Generates indicator computation + signal logic
3. **BACKTEST_MODULE_PROMPT** — Generates cerebro runner + broker config
4. **INTEGRATION_PROMPT** — Merges 3 modules into one self-contained script

Each prompt receives the strategy spec as structured context and produces
a Python code block. The agent extracts the code and passes it through
validation before execution.

## Configuration

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `SPEC2CODE_BACKTEST_TIMEOUT` | `300` | Max seconds for backtest execution |
| `SPEC2CODE_DATA_CACHE` | `<library>/data_cache` | Cache dir for downloaded data |

These are in addition to the shared paper2spec config (LLM model, API keys, etc.).

## Limitations (v0.1)

- **Single strategy**: Generates code for one strategy at a time (structure supports multi).
- **Local execution only**: No Docker isolation — runs in subprocess.
- **Data sources**: yfinance + akshare only (no Bloomberg/Reuters).
- **Code generation**: Agent-driven (LLM generates code interactively); no fully
  automatic code synthesis without agent mediation yet.
