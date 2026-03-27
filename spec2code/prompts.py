"""Prompt templates for spec2code code generation.

Each prompt takes a StrategySpec (serialized) and produces a specific
code module. The three-module approach (data → signal → backtest) mirrors
the QSA pipeline's proven architecture.
"""

CODEGEN_SYSTEM = (
    "You are an expert quantitative developer specializing in Backtrader. "
    "Generate clean, correct, self-contained Python code. "
    "Use only standard libraries (pandas, numpy) plus backtrader and yfinance. "
    "Always include error handling for data fetching. "
    "Never use TA-Lib or other C-extension libraries."
)


DATA_MODULE_PROMPT = """Generate a Python data module for this trading strategy.

Strategy specification:
{spec_json}

Requirements:
1. Create a `fetch_data()` function that downloads required market data
2. Use yfinance for US equities/ETFs, akshare for A-shares (if applicable)
3. Date range: use the spec's `time_period` if available, otherwise 2018-01-01 to 2024-12-31
4. Return a dict of symbol → pd.DataFrame with columns: Open, High, Low, Close, Volume
5. Handle multi-asset universes (download each ticker)
6. Include proper error handling and retry logic
7. Cache data locally using the provided cache_dir path

Assets from spec:
- Universe: {universe}
- Asset class: {asset_class}
- Data frequency: {frequency}
- Time period: {time_period}

Generate ONLY the Python code. No markdown fences. No explanation text.
"""


SIGNAL_MODULE_PROMPT = """Generate a Python signal computation module for this trading strategy.

Strategy specification:
{spec_json}

Indicators to implement:
{indicators_text}

Logic pipeline to implement:
{logic_text}

Requirements:
1. Implement each indicator as a standalone function
2. Implement the logic pipeline as a `compute_signals(data)` function
3. Use only pandas and numpy — NO TA-Lib
4. Each indicator function takes a DataFrame and returns a Series or DataFrame
5. The final `compute_signals()` function should:
   - Call each indicator function
   - Apply the logic pipeline steps in order
   - Return a final signal (boolean Series or float score Series)
6. Include docstrings explaining the math

Generate ONLY the Python code. No markdown fences.
"""


BACKTEST_MODULE_PROMPT = """Generate a Backtrader strategy class and runner for this trading strategy.

Strategy specification:
{spec_json}

Execution plan:
{execution_text}

Data module interface:
- `fetch_data()` → dict[str, pd.DataFrame] with OHLCV columns

Signal module interface:
- `compute_signals(data)` → pd.Series (boolean or float)

Requirements:
1. Create a `Strategy` class inheriting from `bt.Strategy`
2. In `__init__()`: compute signals using the signal module
3. In `next()`: implement trade execution based on execution plan
4. Implement position sizing from spec: {position_sizing}
5. Implement risk management: {risk_management}
6. Create a `run_backtest()` function that:
   - Creates Cerebro instance
   - Loads data using the data module
   - Adds the strategy
   - Sets initial cash to 100000
   - Runs and returns results
7. Add `if __name__ == "__main__"` block that calls run_backtest()

Generate ONLY the Python code. No markdown fences.
"""


INTEGRATION_PROMPT = """Combine these three code modules into a single self-contained Python file.

DATA MODULE:
```python
{data_code}
```

SIGNAL MODULE:
```python
{signal_code}
```

BACKTEST MODULE:
```python
{backtest_code}
```

Requirements:
1. Merge into ONE executable .py file
2. Deduplicate imports (put all at the top)
3. Preserve all function/class definitions
4. Ensure the data module is called by the signal module
5. Ensure signals are passed to the strategy class
6. Keep the `if __name__ == "__main__"` runner at the bottom
7. Add a brief header comment with the strategy name
8. The file must be fully self-contained and runnable with:
   `python strategy.py`

Generate ONLY the complete Python code. No markdown fences.
"""


def format_indicators(spec_dict: dict) -> str:
    """Format indicators from spec dict into a readable text block."""
    indicators = spec_dict.get("indicators", [])
    if not indicators:
        return "No indicators specified."

    lines = []
    for i, ind in enumerate(indicators, 1):
        name = ind.get("name", f"indicator_{i}")
        formula = ind.get("formula", "")
        inputs = ind.get("inputs", [])
        params = ind.get("parameters", {})
        scope = ind.get("scope", "time_series")
        lines.append(f"{i}. {name}")
        if formula:
            lines.append(f"   Formula: {formula}")
        if inputs:
            lines.append(f"   Inputs: {', '.join(inputs)}")
        if params:
            lines.append(f"   Parameters: {params}")
        lines.append(f"   Scope: {scope}")
    return "\n".join(lines)


def format_logic_pipeline(spec_dict: dict) -> str:
    """Format logic pipeline from spec dict into a readable text block."""
    steps = spec_dict.get("logic_pipeline", [])
    if not steps:
        return "No logic pipeline specified."

    lines = []
    for i, step in enumerate(steps, 1):
        func = step.get("function", "")
        desc = step.get("description", "")
        expr = step.get("expression", "")
        inputs = step.get("inputs", [])
        output = step.get("output", "")
        lines.append(f"Step {i}: {func}")
        if desc:
            lines.append(f"  Description: {desc}")
        if expr:
            lines.append(f"  Expression: {expr}")
        if inputs:
            lines.append(f"  Inputs: {', '.join(inputs)}")
        if output:
            lines.append(f"  Output: {output}")
    return "\n".join(lines)


def format_execution(spec_dict: dict) -> str:
    """Format execution plan from spec dict into a readable text block."""
    plans = spec_dict.get("execution_plan", [])
    if not plans:
        return "No execution plan specified."

    lines = []
    for plan in plans:
        trigger = plan.get("trigger", {})
        action = plan.get("action", {})
        sizing = plan.get("position_sizing", {})
        lines.append(f"Trigger: {trigger.get('trigger_type', 'time_driven')} "
                      f"({trigger.get('frequency', 'daily')})")
        if action.get("logic"):
            lines.append(f"Action: {action['logic']}")
        lines.append(f"Sizing: {sizing.get('method', 'equal_weight')}")
    return "\n".join(lines)
