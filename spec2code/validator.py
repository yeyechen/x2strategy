"""Code validator — AST syntax check + common Backtrader error detection.

Validates generated strategy code before execution. Catches:
  - Python syntax errors (via ast.parse)
  - Missing Backtrader imports
  - Missing Strategy class
  - Missing cerebro runner block
"""

import ast
import re
from typing import List, Tuple

from spec2code.models import ValidationResult


def validate_code(code: str) -> ValidationResult:
    """Validate strategy code and return a ValidationResult.

    Performs two levels of checking:
      1. AST syntax validation (hard errors)
      2. Structural checks for Backtrader patterns (warnings)
    """
    errors: List[str] = []
    warnings: List[str] = []

    # ── Level 1: Syntax check ──
    try:
        ast.parse(code)
    except SyntaxError as e:
        errors.append(f"SyntaxError at line {e.lineno}: {e.msg}")
        return ValidationResult(valid=False, errors=errors, warnings=warnings)

    # ── Level 2: Structural checks ──
    tree = ast.parse(code)

    # Check for backtrader import
    has_bt_import = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "backtrader" or (alias.asname and alias.asname == "bt"):
                    has_bt_import = True
        elif isinstance(node, ast.ImportFrom):
            if node.module and "backtrader" in node.module:
                has_bt_import = True

    if not has_bt_import:
        warnings.append("No 'import backtrader' found — strategy may not run")

    # Check for Strategy class
    has_strategy_class = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                base_name = ""
                if isinstance(base, ast.Attribute):
                    base_name = f"{_get_name(base.value)}.{base.attr}"
                elif isinstance(base, ast.Name):
                    base_name = base.id
                if "Strategy" in base_name:
                    has_strategy_class = True

    if not has_strategy_class:
        warnings.append("No class inheriting from bt.Strategy found")

    # Check for cerebro / runner
    has_cerebro = "cerebro" in code.lower() or "Cerebro" in code
    if not has_cerebro:
        warnings.append("No Cerebro runner found — code may not be self-executable")

    # Check for if __name__ == "__main__"
    has_main_guard = '__name__' in code and '__main__' in code
    if not has_main_guard:
        warnings.append("No if __name__ == '__main__' guard")

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


def _get_name(node: ast.AST) -> str:
    """Extract name from an AST node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_get_name(node.value)}.{node.attr}"
    return ""
