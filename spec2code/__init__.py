"""spec2code — Generate executable Backtrader strategies from StrategySpec.

Pipeline stages:
  Stage 1 (Generator): StrategySpec → data/signal/backtest code modules
  Stage 2 (Validator): AST syntax check + common error detection
  Stage 3 (Executor):  Run backtest locally → metrics + equity curve
  Stage 4 (Analyzer):  Compare results vs spec expectations → diagnosis report
"""

__version__ = "0.1.0"
