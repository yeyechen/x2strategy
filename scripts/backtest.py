#!/usr/bin/env python3
"""backtest.py — Run a backtest on a generated strategy file.

Usage:
    python scripts/backtest.py library/pairs_trading/strategy_1.py
    python scripts/backtest.py strategy.py -o results/ --timeout 600
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from spec2code.executor import run_backtest


def main():
    parser = argparse.ArgumentParser(description="Run backtest on a strategy file.")
    parser.add_argument("strategy", help="Path to the strategy .py file")
    parser.add_argument("-o", "--output-dir", help="Output directory for results")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout in seconds")
    args = parser.parse_args()

    if not os.path.isfile(args.strategy):
        print(f"Error: file not found: {args.strategy}", file=sys.stderr)
        sys.exit(1)

    with open(args.strategy, "r", encoding="utf-8") as f:
        code = f.read()

    out_dir = args.output_dir or os.path.dirname(os.path.abspath(args.strategy))
    os.makedirs(out_dir, exist_ok=True)

    print(f"🚀 Running backtest: {args.strategy}")
    result = run_backtest(code, output_dir=out_dir, timeout=args.timeout)

    # Save result
    basename = os.path.splitext(os.path.basename(args.strategy))[0]
    result_path = os.path.join(out_dir, f"{basename}_result.json")
    with open(result_path, "w", encoding="utf-8") as f:
        f.write(result.to_json())

    if result.status == "success":
        m = result.metrics
        print(f"✅ Done ({result.execution_time_seconds:.1f}s)")
        if m.total_return is not None:
            print(f"   Return: {m.total_return:.2%}")
        if m.sharpe_ratio is not None:
            print(f"   Sharpe: {m.sharpe_ratio:.3f}")
        if m.max_drawdown is not None:
            print(f"   Max DD: {m.max_drawdown:.2%}")
        print(f"   Trades: {m.num_trades}")
    else:
        print(f"❌ Failed: {result.error_message[:300]}")

    print(f"   → {result_path}")
    sys.exit(0 if result.status == "success" else 1)


if __name__ == "__main__":
    main()
