"""Tests for spec2code.analyzer — result comparison and report rendering."""

import pytest

from paper2spec.models import StrategySpec
from spec2code.models import BacktestMetrics, BacktestResult, DiagnosisReport
from spec2code.analyzer import analyze_results, render_report


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def sample_spec():
    """Minimal StrategySpec with expected performance."""
    return StrategySpec(
        strategy_name="Test Strategy",
        strategy_type="technical",
        asset_class=["equity"],
        description="A test strategy",
        expected_sharpe=1.5,
        expected_return=0.12,
        max_drawdown=0.10,
    )


@pytest.fixture
def successful_result():
    return BacktestResult(
        status="success",
        metrics=BacktestMetrics(
            total_return=0.234,
            annual_return=0.112,
            sharpe_ratio=1.45,
            max_drawdown=-0.089,
            num_trades=47,
            final_value=123400.0,
            start_value=100000.0,
        ),
        execution_time_seconds=5.0,
    )


@pytest.fixture
def failed_result():
    return BacktestResult(
        status="error",
        error_message="ModuleNotFoundError: No module named 'backtrader'",
        execution_time_seconds=0.5,
    )


# ── analyze_results Tests ────────────────────────────────────


class TestAnalyzeResults:
    def test_error_backtest(self, sample_spec, failed_result):
        report = analyze_results(sample_spec, failed_result)
        assert report.match_status == "error"
        assert "failed" in report.summary.lower()

    def test_no_expectations(self, successful_result):
        spec = StrategySpec(strategy_name="No Exp", description="test")
        report = analyze_results(spec, successful_result)
        assert report.match_status == "no_expectation"

    def test_close_match(self, sample_spec, successful_result):
        # Sharpe: expected 1.5, actual 1.45 → 3.3% diff → under 50% threshold
        # Annual return: expected 0.12, actual 0.112 → 6.7% diff → under 50%
        report = analyze_results(sample_spec, successful_result)
        assert report.match_status in ("match", "partial")
        assert report.actual["sharpe_ratio"] == 1.45

    def test_large_deviation(self, sample_spec):
        result = BacktestResult(
            status="success",
            metrics=BacktestMetrics(
                sharpe_ratio=0.3,
                annual_return=-0.05,
                max_drawdown=-0.35,
            ),
        )
        report = analyze_results(sample_spec, result)
        assert report.match_status in ("partial", "mismatch")
        assert len(report.deviations) > 0


# ── render_report Tests ──────────────────────────────────────


class TestRenderReport:
    def test_renders_markdown(self, sample_spec, successful_result):
        report = analyze_results(sample_spec, successful_result)
        md = render_report(report, successful_result)
        assert "# Backtest Report" in md
        assert "Test Strategy" in md
        assert "SUCCESS" in md

    def test_renders_error_report(self, sample_spec, failed_result):
        report = analyze_results(sample_spec, failed_result)
        md = render_report(report, failed_result)
        assert "ERROR" in md

    def test_renders_metrics_table(self, sample_spec, successful_result):
        report = analyze_results(sample_spec, successful_result)
        md = render_report(report, successful_result)
        assert "Sharpe Ratio" in md
        assert "Total Return" in md
