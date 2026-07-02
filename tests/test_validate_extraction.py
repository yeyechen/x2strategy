"""Tests for scripts/validate_extraction.py — spec completeness checks.

The fip_v4 run produced a spec with empty signals and
weightings_reported arrays. This validator catches that on the
first attempt, before strategy.py is written. The tests below cover
the key cases.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

# Load the script as a module
_SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "validate_extraction.py"
)
_spec = importlib.util.spec_from_file_location("validate_extraction", _SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["validate_extraction"] = _mod
_spec.loader.exec_module(_mod)

_check_spec = _mod._check_spec
_is_cross_sectional = _mod._is_cross_sectional


def _spec(**overrides) -> dict:
    """Build a minimal cross-sectional spec with overrides applied."""
    base = {
        "paper_title": "Test",
        "num_detected": 1,
        "strategies": [
            {
                "strategy_name": "Test",
                "strategy_type": "equity_long_short",
                "asset_class": ["equity"],
                "indicators": [{"indicator_id": "x", "output_type": "scalar"}],
                "logic_pipeline": [],
                "execution_plan": [],
                "replication_targets": [{"id": "spread", "paper_value": 5.0, "tolerance": 0.5}],
                "time_period": {"start_date": "2000-01-01", "end_date": "2020-12-31"},
                "n_bins": 5,
                "signals": [{"name": "x", "long_leg": "high"}],
                "weightings_reported": ["EW", "VW"],
            }
        ],
    }
    s = base["strategies"][0]
    for k, v in overrides.items():
        if k in ("time_period_str",):
            s["time_period"] = v
        else:
            s[k] = v
    return base


# ── is_cross_sectional heuristic ──


class TestIsCrossSectional:
    def test_equity_long_short_is_cross_sectional(self):
        assert _is_cross_sectional(_spec()) is True

    def test_no_strategies_is_not_cross_sectional(self):
        assert _is_cross_sectional({"paper_title": "X"}) is False


# ── Empty fields (fip_v4 case) ──


class TestEmptyFields:
    def test_empty_signals_caught(self):
        spec = _spec(signals=[])
        errors = _check_spec_from_dict(spec)
        assert any("signals is empty" in e for e in errors)

    def test_empty_weightings_caught(self):
        spec = _spec(weightings_reported=[])
        errors = _check_spec_from_dict(spec)
        assert any("weightings_reported is empty" in e for e in errors)

    def test_missing_signals_field_caught(self):
        spec = _spec()
        del spec["strategies"][0]["signals"]
        errors = _check_spec_from_dict(spec)
        assert any("signals is empty" in e for e in errors)


# ── Helpers ──


def _check_spec_from_dict(spec: dict) -> list[str]:
    """Write spec to a temp file, run _check_spec, return errors."""
    import tempfile
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        json.dump(spec, f)
        path = f.name
    return _check_spec(Path(path))


# Add the helper to the module's namespace so tests can use it
_mod._check_spec_from_dict = _check_spec_from_dict
