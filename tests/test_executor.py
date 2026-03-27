"""Tests for spec2code.executor — metrics parsing and instrumentation."""

import pytest
from spec2code.executor import _parse_metrics, _inject_instrumentation
from spec2code.models import BacktestMetrics


# ── _parse_metrics Tests ──────────────────────────────────────


class TestParseMetrics:
    def test_valid_metrics_output(self):
        stdout = (
            "Starting backtest...\n"
            "Some output\n"
            "__SPEC2CODE_METRICS_START__\n"
            '{"total_return": 0.234, "sharpe_ratio": 1.45, '
            '"num_trades": 47, "final_value": 123400.0, "start_value": 100000.0}\n'
            "__SPEC2CODE_METRICS_END__\n"
            "Done.\n"
        )
        metrics = _parse_metrics(stdout)
        assert metrics.total_return == 0.234
        assert metrics.sharpe_ratio == 1.45
        assert metrics.num_trades == 47
        assert metrics.final_value == 123400.0

    def test_missing_markers(self):
        stdout = "No metrics here\n"
        metrics = _parse_metrics(stdout)
        assert metrics.total_return is None
        assert metrics.num_trades == 0

    def test_partial_markers(self):
        stdout = "__SPEC2CODE_METRICS_START__\n{bad json"
        metrics = _parse_metrics(stdout)
        assert metrics.total_return is None

    def test_empty_stdout(self):
        metrics = _parse_metrics("")
        assert isinstance(metrics, BacktestMetrics)
        assert metrics.total_return is None

    def test_only_some_fields(self):
        stdout = (
            "__SPEC2CODE_METRICS_START__\n"
            '{"total_return": 0.1, "num_trades": 5}\n'
            "__SPEC2CODE_METRICS_END__\n"
        )
        metrics = _parse_metrics(stdout)
        assert metrics.total_return == 0.1
        assert metrics.num_trades == 5
        assert metrics.sharpe_ratio is None


# ── _inject_instrumentation Tests ─────────────────────────────


class TestInjectInstrumentation:
    def test_injects_before_cerebro_run(self):
        code = '''
import backtrader as bt

cerebro = bt.Cerebro()
cerebro.addstrategy(MyStrat)
cerebro.run()
'''
        instrumented = _inject_instrumentation(code)
        # Should contain the analyzers
        assert "trade_analyzer" in instrumented
        assert "sharpe_ratio" in instrumented
        assert "drawdown" in instrumented
        # Should contain the metrics collector
        assert "_collect_metrics" in instrumented
        assert "__SPEC2CODE_METRICS_START__" in instrumented

    def test_preserves_result_assignment(self):
        code = '''
import backtrader as bt

cerebro = bt.Cerebro()
results = cerebro.run()
print(results)
'''
        instrumented = _inject_instrumentation(code)
        assert "results" in instrumented
        assert "_collect_metrics(results, cerebro)" in instrumented

    def test_no_cerebro_run_still_works(self):
        """Code without cerebro.run() should still get metrics function appended."""
        code = "print('hello')\n"
        instrumented = _inject_instrumentation(code)
        assert "_collect_metrics" in instrumented

    def test_cerebrorun_with_args(self):
        code = '''
import backtrader as bt

cerebro = bt.Cerebro()
cerebro.run(stdstats=False)
'''
        instrumented = _inject_instrumentation(code)
        assert "stdstats=False" in instrumented
