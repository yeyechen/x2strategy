# Spec2Code — Agent-Driven Strategy Code Generation

> Metrics extraction patterns verified against backtrader source code.
> See [backtrader_patterns.md](backtrader_patterns.md) for full analyzer return structures.

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

#### Indicators → `__init__()`
Each indicator has: `name`, `formula`, `inputs`, `parameters`, `scope`.

Mapping examples:
```
Spec: {"name": "SMA_20", "formula": "SMA(close, 20)", "parameters": {"period": 20}}
Code: self.sma20 = bt.indicators.SMA(self.data.close, period=20)

Spec: {"name": "RSI_14", "formula": "RSI(close, 14)", "parameters": {"period": 14}}
Code: self.rsi = bt.indicators.RSI(self.data.close, period=14)

Spec: {"name": "spread_zscore", "formula": "(spread - mean(spread, N)) / std(spread, N)"}
Code: Custom indicator class or inline computation
```

Common spec indicator categories and their Backtrader mappings:
- **Moving averages** (SMA, EMA, WMA) → `bt.indicators.SMA/EMA/WMA`
- **Momentum** (RSI, MACD, ROC) → `bt.indicators.RSI/MACD/ROC`
- **Volatility** (ATR, Bollinger) → `bt.indicators.ATR/BollingerBands`
- **Custom/composite** → Define as `bt.Indicator` subclass or compute in `next()`
- **Cross-sectional** (ranks, z-scores) → Compute across data feeds in `next()`

#### Logic Pipeline → `next()`
Each step has: `function`, `description`, `expression`, `inputs`, `output`.

Example:
```
Spec: {"function": "compare_sma", "expression": "close > SMA_200", "output": "trend_filter"}
Code: if self.data.close[0] > self.sma200[0]:  # trend_filter
```

#### Execution Plan → Order Logic
Each plan entry has: `trigger`, `action`, `position_sizing`.
Map trigger → entry/exit conditions, action → `self.buy()`/`self.sell()`,
sizing → `self.broker.getvalue()` calculations.

### Phase 2: Generate Code

Generate a **single self-contained Python file** (`strategy.py`) that includes:

1. **Imports** — `backtrader as bt`, `json`, `datetime`, `urllib.request`, `os`
2. **Data loading from ClickHouse** — Before writing any code, read
   `data_match_report.json` to learn which tables provide each dataset.
   Fetch ALL data via ClickHouse HTTP queries (see §Data Source below).
   Cache results locally as CSV and reuse on subsequent runs.
   **Never use yfinance, akshare, or hardcoded ticker lists.**
3. **Strategy class** — `class MyStrategy(bt.Strategy)` with `__init__` and `next`
4. **Cerebro setup** — Broker config, analyzers, initial cash
5. **Metrics output** — Print key metrics as JSON to stdout
6. **Visualization output** — Save equity curve, drawdown, traded-asset prices,
   and every used indicator chart to `results/`
7. **Commission comparison output** — For trading strategies, save a single equity-curve comparison chart for 0%, 0.01%, and 0.05% commission rates.
8. **`if __name__ == "__main__"` guard**

Read [backtrader_patterns.md](backtrader_patterns.md) for canonical patterns.
Read [indicator_cookbook.md](indicator_cookbook.md) for indicator implementations.
Read [data_sources.md](data_sources.md) for ClickHouse connection details.

**Start from the bundled runner template** [assets/backtrader_template.py](../assets/backtrader_template.py).
Copy its structural parts verbatim and adapt only the marked spots
(`fetch_data_cached` source — see §Data Source below, `MyStrategy.__init__/next`,
universe/SPY symbol). The local data cache, analyzer `_name` strings, headless
`matplotlib.use('Agg')`, the three-commission sweep, and the `portfolio_vs_assets`
chart with SPY + portfolio boldface are the output contract — keep them as-is.

#### Data Source (ClickHouse Native Driver)

All data comes from ClickHouse.  Read ``data_match_report.json`` to map
each paper dataset to a concrete table.

Connection details are in ``.env`` (``CLICKHOUSE_HOST``, ``CLICKHOUSE_PORT``,
``CLICKHOUSE_USER``, ``CLICKHOUSE_PASSWORD``, ``CLICKHOUSE_DATABASE``).
Read them via ``os.getenv()``.

```python
import os
from clickhouse_driver import Client

def fetch_cached(table: str, columns: list[str], start: str, end: str,
                 extra_where: str = "") -> pd.DataFrame:
    \"\"\"Query ClickHouse and cache the result as Parquet.\"\"\"
    cache_path = DATA_DIR / f\"{table}_{start}_{end}.parquet\"
    if cache_path.is_file():
        return pd.read_parquet(cache_path)

    host = os.getenv(\"CLICKHOUSE_HOST\", \"localhost\")
    port = int(os.getenv(\"CLICKHOUSE_PORT\", \"9000\"))
    user = os.getenv(\"CLICKHOUSE_USER\", \"default\")
    pw = os.getenv(\"CLICKHOUSE_PASSWORD\", \"\")
    client = Client(host=host, port=port, user=user, password=pw)

    cols = \", \".join(columns)
    where = f\"{date_col} >= '{start}' AND {date_col} < '{end}'\"
    if extra_where:
        where += f\" AND {extra_where}\"
    rows = client.execute(
        f\"SELECT {cols} FROM {table} WHERE {where} ORDER BY {date_col}\"
    )
    df = pd.DataFrame(rows, columns=columns)
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.set_index(date_col)
    df.to_parquet(cache_path)
    return df
```

The native driver returns proper Python ``None`` for NULL values — no ``\\N``
workaround needed.

``_clickhouse_query`` and ``fetch_data_cached`` are **immutable**.
Copy them verbatim from the template.  Do not rewrite the connection,
do not change the driver, do not switch cache format.  Only adapt:
table name, columns, WHERE clause, and date column name.

#### Mandatory Data Cache

Any generated strategy that fetches data from ClickHouse must persist
under a local cache directory before using it in the backtest.

#### Strategy File Template Structure

```python
import backtrader as bt
import json
import datetime
import os
import urllib.request

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
    # Network data must be loaded through a local cache first.
    data = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data)

    # Configure
    cerebro.broker.setcash(100000)
    cerebro.addstrategy(MyStrategy)

    # Add standard analyzers for metrics
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe',
                        riskfreerate=0.01)  # default is 0.01, explicit
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.SQN, _name='sqn')
    cerebro.addanalyzer(bt.analyzers.AnnualReturn, _name='annual')

    results = cerebro.run()
    strat = results[0]

    # Extract metrics using .get() dict access — verified against source code.
    # Analyzer.get_analysis() returns AutoOrderedDict; use .get() to avoid
    # KeyError on no-trade runs. See backtrader_patterns.md for full details.
    initial_cash = 100000
    final_value = cerebro.broker.getvalue()
    trades = strat.analyzers.trades.get_analysis()
    sharpe = strat.analyzers.sharpe.get_analysis()
    dd = strat.analyzers.drawdown.get_analysis()
    ret = strat.analyzers.returns.get_analysis()

    metrics = {
        'final_value': round(final_value, 2),
        'return_value': round(final_value, 2),
        'total_return': round((final_value / initial_cash - 1) * 100, 2),
        'sharpe_ratio': round(sharpe.get('sharperatio'), 4)
                        if sharpe.get('sharperatio') is not None else None,
        'max_drawdown_pct': round(dd.get('max', {}).get('drawdown', 0), 2),
        'num_trades': trades.get('total', {}).get('closed', 0),
        'won_trades': trades.get('won', {}).get('total', 0),
        'lost_trades': trades.get('lost', {}).get('total', 0),
        'normalized_annual_return': round(
            ret.get('rnorm100', 0), 2),  # rnorm × 100
        'sqn': round(strat.analyzers.sqn.get_analysis().get('sqn', 0), 4),
    }

    print(json.dumps(metrics, indent=2))

if __name__ == '__main__':
    run_backtest()
```

At minimum, every runnable Spec2Code output should report `sharpe_ratio`, `max_drawdown` or `max_drawdown_pct`, `total_return`, and `return_value`/`final_value`. If the confirmed target is not a broker-style strategy, compute the same metrics from the research return series when meaningful.

#### Signal / Allocation Generator Contract (§4)

Implement the strategy primarily from `logic_pipeline`, `execution_plan`, and
`executable_explanation`. Treat `indicators` as formula/reference definitions
only. Implement **only** the formulas the selected path needs — skip unused,
`theoretical_only`, `benchmark_only`, `evaluation_only`, and
`not_used_in_selected_plan` indicators. Prefer vectorised pandas/numpy over
element-wise loops.

Pick the generator shape from `strategy_type`:

| Type | Output semantics |
|------|-----------------|
| `signal` (default) | Output semantics are defined by `execution_plan`: categorical labels, ranking scores, forecasts, or directional scores. Do **not** assume every signal is a numeric score in `[-1, 1]`. |
| `allocation` | Output is target exposures / direct portfolio weights. They may be negative and may not sum to 1. **Do not normalize** unless explicit sizing constraints are non-null in the spec. |
| `hybrid` | Selection/ranking/forecast first, then allocation if `execution_plan` says so. |

Shared rules:
- All parameters (lookbacks, thresholds, weights) come from the spec **exactly** — no rounding, no invented defaults.
- Rolling windows follow `executable_explanation` and `execution_plan` timing. If weights estimated at *t* apply to returns at *t+1*, the estimation window must **not** include the return being evaluated. Never use the full series.
- NaN guard: any computation consuming a column must skip/impute None/NaN; tickers whose data is unusable on `date` get weight `0.0`.
- **Hedge separation:** if the spec specifies a hedge (e.g. `SPY`), compute its weight in a separate path. The hedge never participates in universe ranking or top-K selection.
- **Universe fallback:** if a market-cap/sector/liquidity filter leaves fewer than ~30–50 tickers, relax the filter and warn via `print(...)` — never run on a too-small universe.
- **Near-zero denominator:** never clamp with `denom = max(denom, eps)` / `np.maximum(denom, eps)` — that silently flips a legitimately negative denominator to `+eps` and reverses the sign (a short becomes a long). Instead mask: `valid = np.abs(denom) > eps`, set invalid entries to `0.0`, leave valid signs intact.
- **Pandas resample:** use `resample("ME")` (month-end), not the deprecated `resample("M")`. Pandas 2.2+ requires the new aliases: ``"ME"``, ``"QE"``, ``"YE"``, ``"h"``, ``"min"``, ``"s"``.

#### Risk Management Contract (§6)

Signatures are flexible (function, method, or inline). If the spec has no
explicit risk rules, omit risk management or make it pass-through.

- Implement **all** rules from `risk_management` (stop_loss, take_profit, cumulative_loss, drawdown) with thresholds **exactly** as specified.
- If the spec does **not** specify a drawdown rule, do **not** invent one.
- Locate `current_date` in the asset's date series to read today's data — never assume positional alignment.
- **Volume quality gate:** apply volume-based tradability filters only when `volume_data=true` or the data clearly carries real volume. For return-series/factor data with synthetic/placeholder volume, do not treat volume as a tradability filter.
- **Hedge bypass:** the hedge ticker skips every per-asset check (stop-loss, take-profit, data quality); its weight passes through unchanged.

#### Position Sizing Contract (§7)

Signatures are flexible. Pass `portfolio_value`, current prices, or broker
positions explicitly when needed.

- **Conditional capping:** apply `max_position_pct` only if it is **non-null**. If null, do not cap individual weights.
- **Conditional normalisation:** apply `total_exposure` rescaling only if it is **non-null**. If null, do not rescale.
- **Direct-weight pass-through:** if both `max_position_pct` and `total_exposure` are null, pass target exposures through **unchanged**. Never force long weights to +1 / short weights to −1 unless the spec explicitly requires it.
- **Two-pass normalisation (only when constraints are non-null):** after capping, recompute the normalisation factor so total exposure matches the spec target. Never cap-then-stop.
- **Hedge exclusion:** exclude any hedge ticker from the cap and normalisation pool, then set `hedge_weight = -sum(sized_non_hedge_weights)` to preserve market neutrality.
- **Order translation:** target weights are portfolio-exposure fractions. Translate to orders as `target_size = (target_w * portfolio_value) / current_price` and trade only the delta vs the current position. Never pass a target weight directly as `size`.

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
- **Indicator existence** — all `bt.indicators.X` / `bt.ind.X` references
  are verified against the installed backtrader version

Beyond what the bundled `validator.py` automates, also self-check these
deterministic rules (the production backend enforces them at validation time):

- **`import pandas`** is present alongside backtrader.
- **No look-ahead via `.shift(-n)`** — negative shifts pull future data into the current bar. Treat any `.shift(-1)`, `.shift(-2)`, … as an error unless it is provably a label only used out-of-sample.
- **No close-only tradable feed** — `bt.feeds.PandasData(..., close=..., open=None, high=None, low=None)` for a *tradable* asset is forbidden: market orders need a finite next-bar open, and missing OHLC yields NaN fills and a NaN portfolio value. Build finite `Open/High/Low/Close/Volume` first (see [backtrader_patterns.md](backtrader_patterns.md)), or mark the feed as auxiliary/non-tradable (e.g. a risk-free `IRX` column).

Deterministic compatibility rewrites worth applying before running (the backend
does these automatically):

- `df.fillna(method='ffill')` → `df.ffill()`; `fillna(method='bfill')` → `df.bfill()` (pandas 2.x removed the `method=` kwarg).
- `hasattr(trades.won, 'total')` on an analyzer `AutoOrderedDict` → `trades.get('won', {}).get('total', 0)`. `hasattr` is always wrong here because `__getattr__` raises `KeyError`, not `AttributeError`.

If validation fails:
- **Errors** (syntax, invalid indicators): must fix before running
- **Warnings** (missing structure): review but may be acceptable

Fix the errors and re-validate. Do not proceed to Phase 4 with errors.

### Phase 4: Run Directly

Run the strategy file directly in the terminal:

```bash
cd library/<paper>/
uv run python strategy_1.py
```

Read stdout for metrics JSON. Read stderr for errors.

**Important**: The strategy file should be self-contained — it fetches its
own data, runs the backtest, and prints results. No external executor needed.

If the strategy requires backtrader that isn't in the skill's main venv,
create a dedicated venv in the library subdirectory:

```bash
cd library/<paper>/
uv venv && uv pip install backtrader
uv run python strategy_1.py
```

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
- Different data source (paper used Bloomberg/CRSP, we use ClickHouse)
- Different time period
- Transaction costs / slippage not modeled
- Survivorship bias in paper's data

If diagnosis reveals issues, iterate: read the spec again, identify the
mismatch, regenerate the problematic section of code, re-validate, re-run.

### Phase 5.5: Debug Runtime Errors

When the strategy crashes or produces unexpected output, follow this triage flow:

**Step 1 — Classify the error from stderr:**

| Error Pattern | Category | Typical Fix |
|--------------|----------|-------------|
| `ModuleNotFoundError: No module named 'xxx'` | Missing dependency | `uv pip install xxx` in strategy venv |
| `HTTPError` / `ConnectionError` / `No data found` | Data fetch failure | Check ClickHouse connection, table/column names in match report, date range |
| `IndexError: array assignment index is out of range` | Indicator warmup | Add `if len(self) < self.p.period: return` at top of `next()` |
| `ValueError: ...` in indicator init | Bad parameters | Cross-check indicator params with [indicator_cookbook.md](indicator_cookbook.md) |
| Strategy runs but `num_trades: 0` | Dead logic | Entry conditions too strict, or data period doesn't contain signals |
| `bt.indicators.XXX` does not exist | Invalid indicator | Use validator's indicator check; see [indicator_cookbook.md](indicator_cookbook.md) for valid names |
| `KeyError` in analyzer | Missing analyzer | Ensure all 6 standard analyzers are added (see Phase 2 template) |

**Step 2 — Fix and retry loop:**

1. Read the full stderr output
2. Identify the error category from the table above
3. Apply the targeted fix (do NOT rewrite the entire file)
4. Re-validate (`scripts/validate_strategy.py`)
5. Re-run the strategy
6. If error persists after 3 attempts, re-read the spec and consider whether
   the strategy logic needs a fundamentally different approach

**Step 3 — Zero-trade debugging:**

Zero trades is the most common "silent failure". Debug checklist:
- Print `self.data.close[0]` and indicator values in `next()` to verify data flow
- Check if conditions use `[0]` indexing (current bar) not `[-1]` (previous)
- Verify the data period overlaps with the strategy's intended market regime
- Check `cerebro.broker.getvalue()` vs `setcash()` — if equal, no trades executed

### Phase 6: Present Results to User

After a successful backtest, present results in this format:

**1. Summary table** (always include):

```
策略: {strategy_name}
数据: {ticker} ({start_date} → {end_date})
初始资金: {initial_cash:,}

| 指标 | 回测结果 | 论文预期 | 偏差 |
|------|---------|---------|------|
| 总收益率 | {total_return}% | {expected_return}% | {dev}% |
| 年化收益 | {annual}% | {exp_annual}% | {dev}% |
| 夏普比率 | {sharpe} | {exp_sharpe} | {dev} |
| 最大回撤 | {max_dd}% | {exp_dd}% | {dev}pp |
| 总交易数 | {num_trades} | — | — |
| 胜率 | {win_rate}% | — | — |
| SQN | {sqn} | — | — |

最终资产: {final_value:,}
```

**2. Match assessment** (always include):
- State whether results are **匹配** (within thresholds), **部分匹配**, or **不匹配**
- For deviations, explain likely causes (data source, time period, costs)

**3. Generated files** (list paths):
- `strategy_1.py` — self-contained strategy code
- `spec.json` — strategy specification
- `results/portfolio_vs_assets.csv` and `results/portfolio_vs_assets.png` comparing the strategy portfolio value against same-capital buy-and-hold curves for every used equity/ETF/asset in one image; asset curves must use distinguishable colors and symbol labels/legend entries, and SPY and portfolio must be boldface (comparing same-parameter portfolio curves at 0%, 0.01%, and 0.05% commission in one image)
- `results/key_pred/` with one CSV and one PNG per key observerable factors used by the strategy
- `data/` local cached data paths used by the run

**4. Optional — if user requests:**
- Plot: `cerebro.plot()` generates a chart. Note this requires matplotlib and
  a display environment. For headless servers, save to file:
  `cerebro.plot(style='bar')[0][0].savefig('backtest_plot.png')`
- Detailed trade log: Add `bt.observers.Trades` or iterate `strat.analyzers.trades`
- Equity curve: Extract from `bt.observers.Broker` or compute from daily returns

## Output Structure

```
library/<paper>/
├── spec.json              # From paper2spec
├── strategy_1.py          # Generated code │   ├── data/
├── results/
│   ├── metrics.json
│   ├── backtest_output.txt
│   ├── diagnosis_report.md
│   ├── portfolio_vs_assets_commission_comparison.csv
│   └── portfolio_vs_assets_commission_comparison.png
└── metadata.json
```

## Validation Tool

The validator runs AST-level checks that the agent cannot do natively.
Use it via CLI before executing any generated strategy:

```bash
uv run python scripts/validate_strategy.py <strategy.py>
```

Checks performed:
1. **Syntax** — `ast.parse()` succeeds
2. **Backtrader import** — `import backtrader` or `import backtrader as bt`
3. **Strategy class** — At least one `bt.Strategy` subclass defined
4. **Cerebro runner** — `bt.Cerebro()` instantiation present
5. **Main guard** — `if __name__` block exists
6. **Indicator existence** — All `bt.indicators.X` / `bt.ind.X` / `btind.X` references
   are checked against `inspect.getmembers(bt.indicators)`. Non-existent indicators
   (e.g. `bt.indicators.DEMA` when you mean `bt.indicators.DoubleExponentialMovingAverage`)
   produce hard errors with a sample of valid indicator names. Only runs when
   backtrader is installed (`codegen` extra).

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

## Forbidden Patterns (Complete Catalogue, §13)

These **must not appear** in generated strategy code. Treat each as a hard
gate — if one slips in, fix it before running, not after.

1. Top-level `try/except` around `import` statements or the main flow.
2. `Dict[str, Any]` / `typing.Any` when a concrete type is obvious. (Risk / sizing / generator signatures stay flexible per §6/§7 — do not force exact signatures there.)
3. Mock / random / fake data: `random.uniform`, `np.random.rand`, hard-coded fake prices. *Exception:* synthetic OHLC **deterministically** derived from real return-series data, used only to drive Backtrader bars, is allowed.
4. Placeholder comments or stubs: `# TODO`, `# Placeholder`, `# Simplified version`, `# FIXME`, bare `pass` in logic bodies, ellipsis `...`.
5. Names containing `dummy`.
6. `cerebro.plot()` or `plt.savefig(...)` for the headless backtest charts — use the project's plotting path that writes to `results/`.
7. `hasattr(...)` on any Backtrader `AutoOrderedDict` (analyzer results) — `__getattr__` raises `KeyError`, so `hasattr` is always wrong. Use `.get(...)`.
8. Calling `fetch_*`/data-loading inside `BacktestStrategy.__init__`.
9. Assigning to `self.position`, `self.broker`, `self.data`, `self.datas` (framework-reserved — assignment silently breaks Backtrader).
10. Inventing column names not present in the cached data / data report.
11. **QP without stabilisation** — if the strategy genuinely needs a QP solver (`scipy.optimize.minimize` with a quadratic objective, or `cvxpy`), all four are mandatory: (a) symmetrise `Sigma_sym = (Sigma + Sigma.T) / 2`; (b) ridge `Sigma_reg = Sigma_sym + eps*np.eye(n)` (e.g. `eps=1e-8`); (c) warm-start `np.linalg.solve(Sigma_reg, mu)` clipped to the feasible set; (d) deterministic solver settings. If the spec uses a closed-form/analytic formula, do **not** add these.
12. Hedge asset participating in universe ranking / top-K selection.
13. Hedge asset participating in normalisation or the per-position cap pool.
14. Pre-computing time-varying indicators inside `__init__` (look-ahead).
15. `.shift(-n)` look-ahead (pulling future rows into the current bar).
16. Non-zero `setcommission(...)` or explicit slippage unless the spec / paper states a transaction-cost value. (The 0% / 0.01% / 0.05% comparison chart is a separate, explicit sweep — not a silent default.)
17. Normalising / clipping / de-leveraging allocation output when both `max_position_pct` and `total_exposure` are null (see §7 direct-weight pass-through).
18. **Near-zero denominator clamp** — `max(denom, eps)` / `np.maximum(denom, eps)` flips negative denominators to `+eps` and reverses sign. Mask invalid entries to `0.0` instead.
19. Close-only tradable feeds: `bt.feeds.PandasData(..., open=None, high=None, low=None, close=...)` for a tradable asset. Build finite OHLCV first.
20. Passing a target weight directly as order `size`. Always translate to `target_size = (target_w * portfolio_value) / current_price` and trade the delta.

## Self-Check Before Reporting "done" (§15)

Run this checklist before you tell the user the backtest is complete. It is the
cheapest quality gate in the whole pipeline — a slip here is a "runs but wrong"
result, which is worse than a crash.

- [ ] `import matplotlib; matplotlib.use('Agg')` is set before any pyplot import (headless-safe).
- [ ] Signal / allocation / hybrid logic follows `execution_plan`; outputs match the strategy's real semantics, not a fixed signal-only template.
- [ ] No unused / `theoretical_only` / `benchmark_only` / `evaluation_only` / `not_used_in_selected_plan` indicators implemented as live code.
- [ ] Risk rules implemented faithfully when present; omitted / pass-through when absent. No invented drawdown rule.
- [ ] Position sizing does not normalise or cap unless the spec says so; when both `max_position_pct` and `total_exposure` are null, target exposures pass through unchanged; hedge excluded from sizing pools.
- [ ] Orders translate `target_w` → `target_size = (target_w * portfolio_value) / current_price` and trade the delta vs current position. No `buy(size=target_w)`.
- [ ] All network data was cached locally first and reused; no live fetch inside the strategy class.
- [ ] No forbidden pattern from §13 above (especially `.shift(-n)`, near-zero clamp, close-only tradable feed, `hasattr` on analyzer dicts).
- [ ] Metrics reported: at least Sharpe, max drawdown, total return, final/return value.
- [ ] Required artifacts written to `results/`: `metrics.json`, `backtest_output.txt`, `diagnosis_report.md`, the `portfolio_vs_assets` CSV+PNG (all three commission curves + every asset buy-and-hold, SPY + portfolio boldface), and `key_pred/` (one CSV+PNG per key observable factor). For US-equity strategies SPY is included and highlighted as the baseline.
- [ ] Final broker value and computed returns are finite — guard with `np.isfinite`; a NaN/None/inf portfolio value must raise, never silently "succeed".

Only once every box is green do you report completion. Tie this to the
iteration discipline in [SKILL.md](../SKILL.md): generate once, at most one
smoke-test repair round, then stop and report if it still fails.
