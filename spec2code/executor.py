"""Backtest executor — run strategy code in a subprocess and collect metrics.

Executes generated Backtrader strategy code in an isolated subprocess,
captures stdout/stderr, parses metrics from the output, and optionally
saves the equity curve plot.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

from spec2code.config import get_backtest_timeout, get_data_cache_dir
from spec2code.models import BacktestMetrics, BacktestResult


# Metrics extraction snippet injected into strategy code
METRICS_COLLECTOR = '''
# === spec2code metrics collector (injected) ===
import json as _json, sys as _sys

def _collect_metrics(cerebro_result, cerebro_instance):
    """Extract metrics from backtrader run and print as JSON to stdout."""
    strats = cerebro_result
    broker = cerebro_instance.broker

    final_value = broker.getvalue()
    start_value = getattr(cerebro_instance, '_spec2code_start_value', 100000.0)

    total_return = (final_value - start_value) / start_value if start_value else 0

    # Try to get analyzers
    metrics = {
        "total_return": round(total_return, 6),
        "final_value": round(final_value, 2),
        "start_value": round(start_value, 2),
        "num_trades": 0,
    }

    if strats and len(strats) > 0:
        strat = strats[0]
        # Trade analyzer
        try:
            ta = strat.analyzers.trade_analyzer.get_analysis()
            metrics["num_trades"] = ta.get("total", {}).get("total", 0)
            won = ta.get("won", {}).get("total", 0)
            lost = ta.get("lost", {}).get("total", 0)
            if won + lost > 0:
                metrics["win_rate"] = round(won / (won + lost), 4)
        except Exception:
            pass
        # Sharpe ratio
        try:
            sharpe = strat.analyzers.sharpe_ratio.get_analysis()
            sr = sharpe.get("sharperatio", None)
            if sr is not None:
                metrics["sharpe_ratio"] = round(float(sr), 4)
        except Exception:
            pass
        # Drawdown
        try:
            dd = strat.analyzers.drawdown.get_analysis()
            metrics["max_drawdown"] = round(-dd.get("max", {}).get("drawdown", 0) / 100, 4)
        except Exception:
            pass
        # Annual return
        try:
            ar = strat.analyzers.annual_return.get_analysis()
            if ar:
                returns = list(ar.values())
                if returns:
                    avg_annual = sum(returns) / len(returns)
                    metrics["annual_return"] = round(avg_annual, 6)
        except Exception:
            pass

    print("\\n__SPEC2CODE_METRICS_START__")
    print(_json.dumps(metrics))
    print("__SPEC2CODE_METRICS_END__")
'''

ANALYZERS_INJECTION = '''
# === spec2code analyzers (injected) ===
cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trade_analyzer')
cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe_ratio', riskfreerate=0.0)
cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
cerebro.addanalyzer(bt.analyzers.AnnualReturn, _name='annual_return')
'''


def run_backtest(
    code: str,
    *,
    output_dir: Optional[str] = None,
    timeout: Optional[int] = None,
) -> BacktestResult:
    """Execute strategy code in a subprocess and return BacktestResult.

    Args:
        code: Complete Python strategy file content.
        output_dir: Where to save equity curve plot (if any).
        timeout: Max seconds for execution. Defaults to SPEC2CODE_BACKTEST_TIMEOUT.

    Returns:
        BacktestResult with metrics, stdout, stderr, and status.
    """
    if timeout is None:
        timeout = get_backtest_timeout()

    # Inject analyzers and metrics collector into the code
    instrumented_code = _inject_instrumentation(code)

    # Write to temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(instrumented_code)
        script_path = f.name

    start_time = time.monotonic()
    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=output_dir or os.path.dirname(script_path),
            env={**os.environ, "MPLBACKEND": "Agg"},  # Non-interactive matplotlib
        )

        elapsed = time.monotonic() - start_time
        stdout = result.stdout
        stderr = result.stderr

        # Parse metrics from stdout
        metrics = _parse_metrics(stdout)

        if result.returncode != 0:
            return BacktestResult(
                status="error",
                metrics=metrics,
                error_message=stderr[-2000:] if stderr else f"Exit code {result.returncode}",
                stdout=stdout[-2000:],
                stderr=stderr[-2000:],
                execution_time_seconds=round(elapsed, 2),
            )

        return BacktestResult(
            status="success",
            metrics=metrics,
            stdout=stdout[-2000:],
            stderr=stderr[-500:],
            execution_time_seconds=round(elapsed, 2),
        )

    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start_time
        return BacktestResult(
            status="error",
            error_message=f"Backtest timed out after {timeout}s",
            execution_time_seconds=round(elapsed, 2),
        )
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass


def _inject_instrumentation(code: str) -> str:
    """Inject analyzers and metrics collector into strategy code.

    Looks for `cerebro.run()` and injects analyzers before it,
    and metrics collection after it.
    """
    import re

    # Find cerebro.run() call
    run_pattern = re.compile(
        r'^(\s*)((?:\w+)\s*=\s*)?cerebro\.run\((.*?)\)',
        re.MULTILINE,
    )
    match = run_pattern.search(code)
    if not match:
        # Can't inject — return code with just the metrics function defined
        return code + "\n" + METRICS_COLLECTOR

    indent = match.group(1)
    var_assign = match.group(2) or ""
    run_args = match.group(3)

    # Ensure we have a variable assignment for the result
    if not var_assign:
        var_assign = "_spec2code_results = "
        result_var = "_spec2code_results"
    else:
        result_var = var_assign.strip().rstrip("=").strip()

    # Build replacement
    analyzer_lines = "\n".join(
        f"{indent}{line.strip()}" for line in ANALYZERS_INJECTION.strip().split("\n")
        if line.strip() and not line.strip().startswith("#")
    )

    replacement = (
        f"{analyzer_lines}\n"
        f"{indent}{var_assign}cerebro.run({run_args})\n"
        f"{indent}_collect_metrics({result_var}, cerebro)"
    )

    instrumented = code[:match.start()] + replacement + code[match.end():]

    # Append the metrics collector function
    instrumented = METRICS_COLLECTOR + "\n" + instrumented

    return instrumented


def _parse_metrics(stdout: str) -> BacktestMetrics:
    """Extract BacktestMetrics from subprocess stdout."""
    start_marker = "__SPEC2CODE_METRICS_START__"
    end_marker = "__SPEC2CODE_METRICS_END__"

    start_idx = stdout.find(start_marker)
    end_idx = stdout.find(end_marker)

    if start_idx == -1 or end_idx == -1:
        return BacktestMetrics()

    json_str = stdout[start_idx + len(start_marker):end_idx].strip()
    try:
        data = json.loads(json_str)
        return BacktestMetrics(
            total_return=data.get("total_return"),
            annual_return=data.get("annual_return"),
            sharpe_ratio=data.get("sharpe_ratio"),
            max_drawdown=data.get("max_drawdown"),
            num_trades=data.get("num_trades", 0),
            win_rate=data.get("win_rate"),
            profit_factor=data.get("profit_factor"),
            final_value=data.get("final_value"),
            start_value=data.get("start_value", 100000.0),
        )
    except (json.JSONDecodeError, TypeError):
        return BacktestMetrics()
