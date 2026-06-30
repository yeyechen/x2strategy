"""Tests for spec2code.validator — AST + structural validation."""

import pytest
from spec2code.validator import validate_code


# ── Valid Code ────────────────────────────────────────────────


VALID_STRATEGY = '''
import backtrader as bt

class SMAStrategy(bt.Strategy):
    params = (('period', 20),)

    def __init__(self):
        self.sma = bt.indicators.SMA(self.data.close, period=self.p.period)

    def next(self):
        if self.data.close[0] > self.sma[0]:
            self.buy()

if __name__ == '__main__':
    cerebro = bt.Cerebro()
    cerebro.addstrategy(SMAStrategy)
    cerebro.run()
'''


class TestValidCode:
    def test_valid_strategy_passes(self):
        result = validate_code(VALID_STRATEGY)
        assert result.valid is True
        assert result.errors == []
        assert result.warnings == []

    def test_valid_with_from_import(self):
        code = '''
from backtrader import Strategy, Cerebro, indicators

class MyStrat(Strategy):
    def next(self):
        pass

if __name__ == '__main__':
    cerebro = Cerebro()
    cerebro.run()
'''
        result = validate_code(code)
        assert result.valid is True


# ── Syntax Errors ─────────────────────────────────────────────


class TestSyntaxErrors:
    def test_syntax_error_detected(self):
        code = "def foo(\n  pass"
        result = validate_code(code)
        assert result.valid is False
        assert len(result.errors) >= 1
        assert "SyntaxError" in result.errors[0]

    def test_syntax_error_stops_further_checks(self):
        """Syntax errors should short-circuit — no warnings emitted."""
        code = "def broken syntax"
        result = validate_code(code)
        assert result.valid is False
        assert result.warnings == []


# ── Warnings (Structural) ────────────────────────────────────


class TestStructuralWarnings:
    def test_missing_bt_import(self):
        code = '''
class MyStrategy:
    def next(self):
        pass

if __name__ == '__main__':
    cerebro = object()
    cerebro.run()
'''
        result = validate_code(code)
        assert result.valid is True  # No syntax errors
        assert any("backtrader" in w for w in result.warnings)

    def test_missing_strategy_class(self):
        code = '''
import backtrader as bt

if __name__ == '__main__':
    cerebro = bt.Cerebro()
    cerebro.run()
'''
        result = validate_code(code)
        assert result.valid is True
        assert any("Strategy" in w for w in result.warnings)

    def test_missing_cerebro(self):
        code = '''
import backtrader as bt

class MyStrat(bt.Strategy):
    def next(self):
        pass

if __name__ == '__main__':
    print("done")
'''
        result = validate_code(code)
        assert result.valid is True
        assert any("Cerebro" in w.lower() or "cerebro" in w.lower() for w in result.warnings)

    def test_missing_main_guard(self):
        code = '''
import backtrader as bt

class MyStrat(bt.Strategy):
    def next(self):
        pass

cerebro = bt.Cerebro()
cerebro.run()
'''
        result = validate_code(code)
        assert result.valid is True
        assert any("__main__" in w for w in result.warnings)

    def test_all_warnings_for_empty_code(self):
        result = validate_code("x = 1")
        assert result.valid is True
        # Should have multiple warnings
        assert len(result.warnings) >= 3
