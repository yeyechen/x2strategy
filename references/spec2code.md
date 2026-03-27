# Spec2Code — Agent-Driven Strategy Code Generation

Convert structured strategy specifications into executable Backtrader code.
The agent generates code, runs it directly, and analyzes the output.

## Philosophy

The agent IS the LLM. It does not need prompt templates, executor wrappers,
or analysis modules — it generates code by reading the spec, runs it in the
terminal, and reasons about the results natively. The `spec2code/` package
provides only tools the agent cannot do itself:

- **`validator.py`** — AST parsing + structural checks (agent can't parse AST)
- **`models.py`** — Serializable data structures for structured output
- **`config.py`** — Environment variable management

## Agent Workflow

### Phase 1: Read the Spec

Load `spec.json` from the paper's library directory. Each strategy has:

```json
{
  "strategy_name": "Minimum Distance Pairs Trading",
  "strategy_type": "technical",
  "asset_class": ["equity"],
  "indicators": [...],
  "logic_pipeline": [...],
  "execution_plan": [...],
  "risk_management": [...],
  "expected_performance": {"sharpe": 1.8, "annual_return": 0.15}
}
```

**Key fields to understand before generating code:**

#### Indicators
Each indicator has: `name`, `formula`, `inputs`, `parameters`, `scope`.
Map these to Backtrader indicators in `__init__()`.

Example spec indicators → code mapping:
```
Spec: {"name": "SMA_20", "formula": "SMA(close, 20)", "inputs": ["close"], "parameters": {"period": 20}}
Code: self.sma20 = bt.indicators.SMA(self.data.close, period=20)

Spec: {"name": "spread_zscore", "formula": "(spread - mean(spread, N)) / std(spread, N)"}
Code: Custom indicator class or inline computation
```

#### Logic Pipeline
Each step has: `function`, `description`, `expression`, `inputs`, `output`.
Map these to the `next()` method's decision logic.

Example:
```
Spec: {"function": "compare_sma", "expression": "close > SMA_200", "output": "trend_filter"}
Code: if self.data.close[0] > self.sma200[0]:  # trend_filter
```

#### Execution Plan
Each plan entry has: `trigger`, `action`, `position_sizing`.
Map trigger → entry/exit conditions, action → order logic, sizing → position management.

### Phase 2: Generate Code

Generate a **single self-contained Python file** (`strategy.py`) that includes:

1. **Imports** — `backtrader as bt`, `yfinance`, `datetime`, etc.
2. **Data loading** — Download OHLCV data via yfinance/akshare
3. **Strategy class** — `class MyStrategy(bt.Strategy)` with `__init__` and `next`
4. **Cerebro setup** — Broker config, analyzers, initial cash
5. **Metrics output** — Print key metrics as JSON to stdout
6. **`if __name__ == "__main__"` guard**

Read [backtrader_patterns.md](backtrader_patterns.md) for canonical patterns.
Read [indicator_cookbook.md](indicator_cookbook.md) for indicator implementations.
Read [data_sources.md](data_sources.md) for data API usage.

#### Strategy File Template Structure

```python
import backtrader as bt
import yfinance as yf
import json
import datetime

class MyStrategy(bt.Strategy):
    params = (...)

    def __init__(self):
        # Map spec indicators to bt.indicators
        ...

    def next(self):
        # Map spec logic_pipeline to trading decisions
        ...

def run_backtest():
    cerebro = bt.Cerebro()

    # Load data
    data = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data)

    # Configure
    cerebro.broker.setcash(100000)
    cerebro.addstrategy(MyStrategy)

    # Add standard analyzers for metrics
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.AnnualReturn, _name='annual')

    results = cerebro.run()
    strat = results[0]

    # Extract and print metrics as JSON
    metrics = extract_metrics(strat, cerebro)
    print(json.dumps(metrics, indent=2))

if __name__ == '__main__':
    run_backtest()
```

### Phase 3: Validate

Before running, validate the code:

```bash
uv run python scripts/validate_strategy.py library/<paper>/strategy_1.py
```

This checks:
- AST syntax (parses without error)
- `import backtrader` present
- `bt.Strategy` subclass defined
- `cerebro` runner exists
- `if __name__` guard present

If validation fails, fix the errors and re-validate.

### Phase 4: Run Directly

Run the strategy file directly in the terminal:

```bash
cd library/<paper>/
uv run python strategy_1.py
```

Read stdout for metrics JSON. Read stderr for errors.

**Important**: The strategy file should be self-contained — it fetches its
own data, runs the backtest, and prints results. No external executor needed.

### Phase 5: Diagnose

Compare the backtest output against the spec's `expected_performance`:

1. Read the metrics from stdout (JSON)
2. Read `expected_performance` from spec.json (sharpe, annual_return, max_drawdown)
3. Compare and report deviations

**Deviation thresholds** (guidelines, not hard rules):
- Sharpe ratio: >20% deviation → investigate signal logic
- Annual return: >20% deviation → check data source and time period
- Max drawdown: >10pp absolute difference → check risk management
- Zero trades → strategy logic is likely broken

**Common causes of deviation:**
- Different data source (paper used Bloomberg, we use yfinance)
- Different time period
- Transaction costs / slippage not modeled
- Survivorship bias in paper's data

## Output Structure

```
library/<paper>/
├── spec.json              # From paper2spec
├── strategy_1.py          # Generated code (self-contained)
├── strategy_1_spec.json   # Individual strategy spec (for reference)
└── metadata.json
```

## Tools Reference

### `spec2code.validator.validate_code(code: str) → ValidationResult`

```python
from spec2code.validator import validate_code

result = validate_code(code_string)
result.valid       # bool
result.errors      # list[str] — blocking issues
result.warnings    # list[str] — non-blocking concerns
```

### Data Models (`spec2code.models`)

- **`CodeModules`** — Container for data/signal/backtest code strings
- **`ValidationResult`** — valid + errors + warnings
- **`BacktestMetrics`** — total_return, annual_return, sharpe_ratio, max_drawdown, etc.
- **`BacktestResult`** — status + metrics + stdout/stderr
- **`DiagnosisReport`** — match_status + expected/actual + deviations + recommendations

All models have `to_dict()`, `from_dict()`, `to_json()` for serialization.

## Configuration

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `SPEC2CODE_BACKTEST_TIMEOUT` | `300` | Timeout guidance for agent (not enforced by code) |
| `SPEC2CODE_DATA_CACHE` | `<library>/data_cache` | Suggested cache dir for downloaded data |

These supplement the shared paper2spec config (LLM model, API keys, etc.).
