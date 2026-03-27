#!/usr/bin/env python3
"""generate.py — Full spec2code pipeline: spec.json → strategy.py → backtest → report.

Usage:
    python scripts/generate.py library/pairs_trading/spec.json
    python scripts/generate.py library/pairs_trading/spec.json --strategy-index 0
    python scripts/generate.py library/pairs_trading/spec.json -o library/pairs_trading/
"""

import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from paper2spec.config import get_library_path
from paper2spec.models import ExtractionResult, StrategySpec
from spec2code.models import CodeModules
from spec2code.validator import validate_code
from spec2code.executor import run_backtest
from spec2code.analyzer import analyze_results, render_report


def main():
    parser = argparse.ArgumentParser(
        description="Generate Backtrader strategy code from spec.json, validate, backtest, and report."
    )
    parser.add_argument("spec", help="Path to spec.json (ExtractionResult)")
    parser.add_argument(
        "-i", "--strategy-index", type=int, default=0,
        help="Which strategy to implement (0-based index, default: 0)",
    )
    parser.add_argument("-o", "--output-dir", help="Output directory (default: same as spec.json)")
    parser.add_argument("--model", help="Override LLM model for code generation")
    parser.add_argument("--skip-backtest", action="store_true", help="Skip backtest execution")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    if not os.path.isfile(args.spec):
        print(f"Error: spec file not found: {args.spec}", file=sys.stderr)
        sys.exit(1)

    # ── Load spec ──
    with open(args.spec, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = ExtractionResult.from_dict(data)
    if args.strategy_index >= len(result.strategies):
        print(
            f"Error: strategy index {args.strategy_index} out of range "
            f"(paper has {len(result.strategies)} strategies)",
            file=sys.stderr,
        )
        sys.exit(1)

    spec = result.strategies[args.strategy_index]
    print(f"📋 Strategy: {spec.strategy_name} (index {args.strategy_index})")
    print(f"   Type: {spec.strategy_type}")
    print(f"   Indicators: {len(spec.indicators)}, Logic steps: {len(spec.logic_pipeline)}")

    # ── Output dir ──
    out_dir = args.output_dir or os.path.dirname(os.path.abspath(args.spec))
    os.makedirs(out_dir, exist_ok=True)

    strategy_prefix = f"strategy_{args.strategy_index + 1}"

    # ── Stage 1: Code Generation ──
    # NOTE: In v0.1, code generation is done by the agent (SKILL.md instructions).
    # This script expects the agent to have already generated the strategy file,
    # OR it loads a pre-existing one for validation and backtesting.
    #
    # The agent-driven workflow:
    #   1. Agent reads spec.json
    #   2. Agent generates strategy.py (using prompts from spec2code.prompts)
    #   3. Agent calls this script to validate and backtest

    strategy_path = os.path.join(out_dir, f"{strategy_prefix}.py")

    if not os.path.isfile(strategy_path):
        print(f"\n⚠️  No strategy file found at {strategy_path}")
        print(f"   The agent should generate the strategy code first.")
        print(f"   Expected path: {strategy_path}")
        print(f"\n   Spec saved for reference:")

        # Save individual spec for the agent to reference
        spec_out = os.path.join(out_dir, f"{strategy_prefix}_spec.json")
        with open(spec_out, "w", encoding="utf-8") as f:
            f.write(spec.to_json())
        print(f"   → {spec_out}")
        sys.exit(0)

    # ── Stage 2: Validate ──
    print(f"\n🔍 Validating {strategy_path}...")
    with open(strategy_path, "r", encoding="utf-8") as f:
        code = f.read()

    validation = validate_code(code)
    if not validation.valid:
        print(f"   ❌ Validation failed:")
        for err in validation.errors:
            print(f"      {err}")
        sys.exit(1)

    if validation.warnings:
        print(f"   ⚠️  Warnings:")
        for w in validation.warnings:
            print(f"      {w}")
    else:
        print(f"   ✅ Syntax valid")

    # ── Stage 3: Backtest ──
    if args.skip_backtest:
        print(f"\n⏭️  Skipping backtest (--skip-backtest)")
    else:
        print(f"\n🚀 Running backtest...")
        bt_result = run_backtest(code, output_dir=out_dir)

        # Save result
        result_path = os.path.join(out_dir, f"{strategy_prefix}_result.json")
        with open(result_path, "w", encoding="utf-8") as f:
            f.write(bt_result.to_json())
        print(f"   → {result_path}")

        if bt_result.status == "success":
            m = bt_result.metrics
            print(f"   ✅ Backtest complete ({bt_result.execution_time_seconds:.1f}s)")
            if m.total_return is not None:
                print(f"      Return: {m.total_return:.2%}")
            if m.sharpe_ratio is not None:
                print(f"      Sharpe: {m.sharpe_ratio:.3f}")
            if m.max_drawdown is not None:
                print(f"      Max DD: {m.max_drawdown:.2%}")
            print(f"      Trades: {m.num_trades}")
        else:
            print(f"   ❌ Backtest failed: {bt_result.error_message[:200]}")

        # ── Stage 4: Diagnosis ──
        print(f"\n📊 Analyzing results...")
        diagnosis = analyze_results(spec, bt_result)
        report_md = render_report(diagnosis, bt_result)

        report_path = os.path.join(out_dir, f"{strategy_prefix}_report.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_md)
        print(f"   → {report_path}")
        print(f"   Match status: {diagnosis.match_status}")

    # ── Summary ──
    print(f"\n✅ Pipeline complete → {out_dir}/")
    print(f"   {strategy_prefix}.py         — Strategy code")
    if not args.skip_backtest:
        print(f"   {strategy_prefix}_result.json — Backtest metrics")
        print(f"   {strategy_prefix}_report.md   — Analysis report")


if __name__ == "__main__":
    main()
