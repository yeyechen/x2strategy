"""Tests for scripts/validate_strategy.py — sanity checks on metrics.json.

Catches the fip_v4 class of bugs: NaN in regression output (factor_alpha
called wrong, or dep var wrong), implausible t-stats, near-zero
headline momentum. The script is best-effort; a few targeted tests
cover the key cases.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

# Load the script as a module
_SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "validate_strategy.py"
)
_spec = importlib.util.spec_from_file_location("validate_strategy", _SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["validate_strategy"] = _mod
_spec.loader.exec_module(_mod)

_check_metrics = _mod._check_metrics


# ── Tests ──


class TestSanityChecks:
    def test_nan_alpha_caught(self):
        """fip_v4 bug: factor_alpha returned NaN due to wrong dep var or
        numpy-array factor_returns. The check must surface the NaN.
        """
        errors = _check_metrics(
            {"alpha_monthly": float("nan"), "spread": 5.0}, "fake.json"
        )
        assert any("NaN" in e for e in errors)

    def test_inf_caught(self):
        """Inf is the same class of bug as NaN."""
        errors = _check_metrics(
            {"alpha_monthly": float("inf"), "spread": 5.0}, "fake.json"
        )
        assert any("NaN" in e or "Inf" in e for e in errors)

    def test_implausible_tstat_caught(self):
        """t-stats > 10 are extremely rare in academic work. The check
        flags them as a likely bug (e.g. wrong standard error).
        """
        errors = _check_metrics(
            {"alpha_tstat": 15.5, "spread": 5.0}, "fake.json"
        )
        assert any("t-stat" in e.lower() for e in errors)

    def test_small_momentum_caught(self):
        """fip_v4 base-momentum bug: headline momentum under 0.5% is
        suspicious. The literature shows ~1%/month for JT 12-2.
        """
        errors = _check_metrics(
            {"continuous_id_momentum": 0.05}, "fake.json"
        )
        assert any("suspiciously small" in e for e in errors)

    def test_plausible_momentum_passes(self):
        """A 5% momentum spread is in the expected range — no warning."""
        errors = _check_metrics(
            {"continuous_id_momentum": 5.0, "alpha_tstat": 2.5, "n_obs": 400},
            "fake.json",
        )
        assert errors == []

    def test_zero_momentum_not_flagged(self):
        """Zero is technically valid (no signal) — only flag tiny NON-ZERO
        values that look like numerical noise.
        """
        errors = _check_metrics(
            {"continuous_id_momentum": 0.0}, "fake.json"
        )
        assert not any("suspiciously small" in e for e in errors)

    def test_small_nobs_caught(self):
        """Sample with < 100 obs is too small for monthly replication."""
        errors = _check_metrics(
            {"n_obs": 50, "spread": 5.0}, "fake.json"
        )
        assert any("n_obs" in e for e in errors)

    def test_nested_nan_caught(self):
        """NaN can be deep in the metrics dict (e.g. inside a sub-dict)."""
        errors = _check_metrics(
            {
                "fm_pret_id": {"coef": float("nan"), "tstat": 1.0},
                "spread": 5.0,
            },
            "fake.json",
        )
        assert any("NaN" in e for e in errors)
