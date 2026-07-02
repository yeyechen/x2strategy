"""Tests for scripts/validate_replication.py — config + hardcoded-constant hygiene checks.

The hygiene check (``_check_run_config``) is run automatically by
``validate_replication.py`` before the per-target report. It catches
two common agent mistakes:

  1. ``config/run_config.yaml`` is missing — the agent forgot to run
     ``scripts/render_run_config.py`` (or analyze.py didn't generate it).
  2. ``strategy.py`` hardcodes canonical run constants
     (``N_BINS``, ``FORMATION_MONTHS``, etc.) — these belong in
     run_config.yaml, loaded via ``load_run_config(slug)``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make scripts/ importable
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

from validate_replication import _check_run_config  # noqa: E402


# ── Fixtures ─────────────────────────────────────────────────


@pytest.fixture
def replication_root_clean(tmp_path) -> Path:
    """A replication dir with a strategy.py that uses load_run_config."""
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "run_config.yaml").write_text(
        "start_date: '1976-01-01'\nend_date: '2007-12-31'\n",
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "strategy.py").write_text(
        "from utils import load_run_config\n"
        "cfg = load_run_config('test_slug')\n"
        "n_bins = cfg['n_bins']\n"
        "hold = cfg['holding_months']\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def replication_root_hardcoded(tmp_path) -> Path:
    """A replication dir with hardcoded constants in strategy.py."""
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "run_config.yaml").write_text(
        "start_date: '1976-01-01'\n", encoding="utf-8"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "strategy.py").write_text(
        "N_BINS = 5\n"
        "FORMATION_MONTHS = 12\n"
        "HOLDING_MONTHS = 6\n"
        "PRICE_FILTER = 5.0\n"
        "SAMPLE_START = '1976-01-01'\n"
        "SAMPLE_END = '2007-12-31'\n"
        "START_DATE = '1975-01-01'\n"
        "END_DATE = '2008-12-31'\n",
        encoding="utf-8",
    )
    return tmp_path


# ── Clean case: no warnings ─────────────────────────────────


class TestCleanReplication:
    def test_no_warnings_when_config_and_strategy_clean(self, replication_root_clean):
        warnings = _check_run_config(replication_root_clean)
        assert warnings == []

    def test_empty_dir_warns_missing_config(self, tmp_path):
        # An empty replication dir is missing config/run_config.yaml
        # — that's exactly what the hygiene check is designed to catch.
        warnings = _check_run_config(tmp_path)
        assert len(warnings) == 1
        assert "config/run_config.yaml missing" in warnings[0]

    def test_no_strategy_py_is_ok(self, tmp_path):
        # config exists but no strategy.py
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "run_config.yaml").write_text("x: 1")
        warnings = _check_run_config(tmp_path)
        assert warnings == []


# ── Missing config ──────────────────────────────────────────


class TestMissingConfig:
    def test_missing_run_config_yaml_warns(self, tmp_path):
        (tmp_path / "config").mkdir()  # dir exists but file doesn't
        warnings = _check_run_config(tmp_path)
        assert len(warnings) == 1
        assert "config/run_config.yaml missing" in warnings[0]
        assert "auto-generated" in warnings[0]
        assert "scripts/analyze.py" in warnings[0]

    def test_no_config_dir_warns(self, tmp_path):
        # no config/ dir at all
        warnings = _check_run_config(tmp_path)
        assert len(warnings) == 1
        assert "config/run_config.yaml missing" in warnings[0]


# ── Hardcoded constants ─────────────────────────────────────


class TestHardcodedConstants:
    def test_hardcoded_n_bins_warns(self, replication_root_hardcoded):
        warnings = _check_run_config(replication_root_hardcoded)
        # Should warn for each hardcoded constant
        n_bins_warnings = [w for w in warnings if "N_BINS" in w]
        assert len(n_bins_warnings) == 1
        assert "strategy.py line" in n_bins_warnings[0]
        assert "load_run_config" in n_bins_warnings[0]

    def test_all_canonical_constants_flagged(self, replication_root_hardcoded):
        warnings = _check_run_config(replication_root_hardcoded)
        # Extract the constant names from warnings
        warned_names = set()
        for w in warnings:
            for name in (
                "N_BINS", "FORMATION_MONTHS", "SKIP_MONTHS", "HOLDING_MONTHS",
                "PRICE_FILTER", "SAMPLE_START", "SAMPLE_END",
                "START_DATE", "END_DATE", "FETCH_START", "FETCH_END",
            ):
                if f"'{name} = ...' is hardcoded" in w:
                    warned_names.add(name)
        # All 8 hardcoded constants should be flagged
        assert warned_names == {
            "N_BINS", "FORMATION_MONTHS", "HOLDING_MONTHS", "PRICE_FILTER",
            "SAMPLE_START", "SAMPLE_END", "START_DATE", "END_DATE",
        }

    def test_warnings_have_line_numbers(self, tmp_path):
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "run_config.yaml").write_text("x: 1")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "strategy.py").write_text(
            "# header comment\n"
            "import os\n"
            "N_BINS = 10\n",
            encoding="utf-8",
        )
        warnings = _check_run_config(tmp_path)
        assert len(warnings) == 1
        # N_BINS is on line 3
        assert "line 3" in warnings[0]

    def test_load_run_config_assignment_not_flagged(self, tmp_path):
        # The pattern should NOT flag `n_bins = load_run_config(...)` etc.
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "run_config.yaml").write_text("n_bins: 5")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "strategy.py").write_text(
            "from utils import load_run_config\n"
            "cfg = load_run_config('test')\n"
            "n_bins = cfg['n_bins']  # local var, lowercase\n"
            "N_BINS = load_run_config('test')['n_bins']  # load from config\n",
            encoding="utf-8",
        )
        warnings = _check_run_config(tmp_path)
        # No warnings — the second N_BINS assignment is via load_run_config
        assert warnings == [], f"unexpected warnings: {warnings}"

    def test_function_call_assignment_not_flagged(self, tmp_path):
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "run_config.yaml").write_text("n_bins: 5")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "strategy.py").write_text(
            "import os\n"
            "START_DATE = os.environ.get('START_DATE', '1976-01-01')\n",
            encoding="utf-8",
        )
        warnings = _check_run_config(tmp_path)
        # `os.environ.get(...)` is a function call, should not be flagged
        assert warnings == []

    def test_indented_assignment_not_flagged(self, tmp_path):
        # Assignments inside a function body should not be flagged
        # (the regex requires line-start, but the more common false
        # positive would be a parameter default like `def f(n_bins=5)`).
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "run_config.yaml").write_text("x: 1")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "strategy.py").write_text(
            "def make_bins(n_bins=5):\n"
            "    return n_bins\n",
            encoding="utf-8",
        )
        warnings = _check_run_config(tmp_path)
        # `n_bins=5` is a kwarg default, not an assignment — should not flag
        # N_BINS (uppercase, line-start). The current regex only matches
        # at line start, so this should produce no warnings.
        assert warnings == []


# ── Combined ────────────────────────────────────────────────


class TestCombined:
    def test_missing_config_AND_hardcoded(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "strategy.py").write_text("N_BINS = 5\n")
        warnings = _check_run_config(tmp_path)
        # Both warnings should fire
        assert len(warnings) == 2
        assert any("config/run_config.yaml missing" in w for w in warnings)
        assert any("N_BINS" in w for w in warnings)
