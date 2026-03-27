"""Result analyzer — compare backtest metrics vs spec expectations.

Generates a structured DiagnosisReport and renders it as Markdown.
"""

from typing import Optional

from paper2spec.models import StrategySpec
from spec2code.models import BacktestMetrics, BacktestResult, DiagnosisReport


def analyze_results(
    spec: StrategySpec,
    result: BacktestResult,
) -> DiagnosisReport:
    """Compare backtest results against paper expectations.

    Returns a DiagnosisReport with match status, deviations, and recommendations.
    """
    report = DiagnosisReport(strategy_name=spec.strategy_name)

    if result.status != "success":
        report.match_status = "error"
        report.summary = f"Backtest failed: {result.error_message}"
        report.recommendations.append("Fix the runtime error and re-run.")
        return report

    metrics = result.metrics
    expected = spec.expected_performance or {}

    # Also check top-level expected fields
    if spec.expected_sharpe is not None:
        expected.setdefault("sharpe", spec.expected_sharpe)
    if spec.expected_return is not None:
        expected.setdefault("annual_return", spec.expected_return)
    if spec.max_drawdown is not None:
        expected.setdefault("max_drawdown", spec.max_drawdown)

    if not expected:
        report.match_status = "no_expectation"
        report.summary = "No expected performance in spec — cannot compare."
        report.actual = _metrics_to_dict(metrics)
        return report

    report.expected = expected
    report.actual = _metrics_to_dict(metrics)

    deviations = []

    # Compare Sharpe ratio
    if "sharpe" in expected and metrics.sharpe_ratio is not None:
        exp_sharpe = float(expected["sharpe"])
        act_sharpe = metrics.sharpe_ratio
        pct_diff = _pct_diff(act_sharpe, exp_sharpe)
        if abs(pct_diff) > 0.5:
            deviations.append(
                f"Sharpe ratio: expected {exp_sharpe:.2f}, got {act_sharpe:.2f} "
                f"({pct_diff:+.0%} deviation)"
            )
            report.recommendations.append(
                "Large Sharpe deviation — check signal logic and execution timing."
            )

    # Compare annual return
    for key in ("annual_return", "return", "cagr"):
        if key in expected and metrics.annual_return is not None:
            exp_ret = float(expected[key])
            act_ret = metrics.annual_return
            pct_diff = _pct_diff(act_ret, exp_ret)
            if abs(pct_diff) > 0.5:
                deviations.append(
                    f"Annual return: expected {exp_ret:.2%}, got {act_ret:.2%} "
                    f"({pct_diff:+.0%} deviation)"
                )
            break

    # Compare max drawdown
    for key in ("max_drawdown", "drawdown"):
        if key in expected and metrics.max_drawdown is not None:
            exp_dd = float(expected[key])
            act_dd = metrics.max_drawdown
            if exp_dd > 0:
                exp_dd = -exp_dd  # Normalize to negative
            if abs(act_dd - exp_dd) > 0.1:
                deviations.append(
                    f"Max drawdown: expected {exp_dd:.2%}, got {act_dd:.2%}"
                )
            break

    report.deviations = deviations

    if len(deviations) == 0:
        report.match_status = "match"
        report.summary = "Backtest results are consistent with paper expectations."
    elif len(deviations) <= 1:
        report.match_status = "partial"
        report.summary = "Minor deviations from paper — generally consistent."
    else:
        report.match_status = "mismatch"
        report.summary = "Significant deviations from paper expectations."
        report.recommendations.append(
            "Review data source, time period, and signal implementation."
        )

    return report


def render_report(
    report: DiagnosisReport,
    result: BacktestResult,
) -> str:
    """Render a diagnosis report as Markdown."""
    lines = [
        f"# Backtest Report: {report.strategy_name}",
        "",
        f"**Status**: {result.status.upper()}",
        f"**Match**: {report.match_status}",
        f"**Execution time**: {result.execution_time_seconds:.1f}s",
        "",
    ]

    if result.status == "success":
        m = result.metrics
        lines.extend([
            "## Performance Metrics",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total Return | {m.total_return:.2%}" if m.total_return is not None else "| Total Return | N/A |",
            f"| Annual Return | {m.annual_return:.2%}" if m.annual_return is not None else "| Annual Return | N/A |",
            f"| Sharpe Ratio | {m.sharpe_ratio:.3f}" if m.sharpe_ratio is not None else "| Sharpe Ratio | N/A |",
            f"| Max Drawdown | {m.max_drawdown:.2%}" if m.max_drawdown is not None else "| Max Drawdown | N/A |",
            f"| Trades | {m.num_trades} |",
            f"| Win Rate | {m.win_rate:.1%}" if m.win_rate is not None else "| Win Rate | N/A |",
            f"| Final Value | ${m.final_value:,.2f}" if m.final_value is not None else "| Final Value | N/A |",
            "",
        ])

    if report.expected:
        lines.extend([
            "## Expected vs Actual",
            "",
            "| Metric | Expected | Actual |",
            "|--------|----------|--------|",
        ])
        for key, exp_val in report.expected.items():
            act_val = report.actual.get(key, "N/A")
            lines.append(f"| {key} | {exp_val} | {act_val} |")
        lines.append("")

    if report.deviations:
        lines.extend(["## Deviations", ""])
        for d in report.deviations:
            lines.append(f"- {d}")
        lines.append("")

    if report.recommendations:
        lines.extend(["## Recommendations", ""])
        for r in report.recommendations:
            lines.append(f"- {r}")
        lines.append("")

    lines.extend(["---", f"*{report.summary}*", ""])
    return "\n".join(lines)


def _metrics_to_dict(m: BacktestMetrics) -> dict:
    """Convert BacktestMetrics to a flat dict, excluding None values."""
    d = m.to_dict()
    return {k: v for k, v in d.items() if v is not None}


def _pct_diff(actual: float, expected: float) -> float:
    """Percentage difference: (actual - expected) / |expected|."""
    if expected == 0:
        return 0.0 if actual == 0 else float("inf")
    return (actual - expected) / abs(expected)
