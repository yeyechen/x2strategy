"""Tests for scripts/extract_requirements.py — BLOCKED.md emission and exit code.

The BLOCKED.md file is the canonical signal that the data verification
step found insufficient data to replicate the paper. The agent reads
this file to know it must stop (do not write strategy.py) and report
to the user. This test covers the happy path of writing BLOCKED.md,
the non-zero exit, and the corresponding non-emission when data is
sufficient.

The tests import ``_write_blocked_md`` from the script. The script is
importable as a module (no ``if __name__ == "__main__"`` work happens
on import), so we can test the function directly.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

# Load the script as a module
_SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent / "scripts" / "extract_requirements.py"
)
_spec = importlib.util.spec_from_file_location("extract_requirements", _SCRIPT_PATH)
_extract = importlib.util.module_from_spec(_spec)
sys.modules["extract_requirements"] = _extract
_spec.loader.exec_module(_extract)

_write_blocked_md = _extract._write_blocked_md


# ── Fixtures ─────────────────────────────────────────────────


@pytest.fixture
def sample_report_with_gap() -> dict:
    """A report with one unmatched requirement (no candidates at all)."""
    return {
        "matches": [
            {
                "requirement": "crsp_daily",
                "database": "crsp_202601",
                "table": "dsf",
                "fq_name": "crsp_202601.dsf",
                "matched_columns": ["date", "permno", "ret", "prc", "shrout"],
                "missing_columns": [],
                "score": 5,
                "row_count": 107663470,
            },
        ],
        "gaps": [
            {
                "requirement": "dq_holdings",
                "reason": "no table found with ≥2/3 required fields. Required: ['filing_date', 'shares', 'value']",
            },
        ],
        "coverage": "50% (1/2)",
        "status": "ok",
    }


@pytest.fixture
def sample_requirements() -> dict:
    return {
        "paper": "Da, Gurun & Warachka (2012) — Frog in the Pan",
        "requirements": [
            {"id": "crsp_daily", "fields": ["permno", "date", "ret"]},
            {"id": "dq_holdings", "fields": ["filing_date", "shares", "value"]},
        ],
    }


# ── Tests ────────────────────────────────────────────────────


class TestBlockedMdEmission:
    def test_blocked_md_written_with_required_sections(
        self, tmp_path, sample_report_with_gap, sample_requirements
    ):
        """BLOCKED.md is written with the right heading and the gap details."""
        out_dir = tmp_path / "diagnostics"
        out_dir.mkdir()
        blocked_path = _write_blocked_md(out_dir, sample_report_with_gap, sample_requirements)

        assert blocked_path.name == "BLOCKED.md"
        assert blocked_path.is_file()
        content = blocked_path.read_text()
        # Heading — greppable by '# BLOCKED'
        assert "# BLOCKED: Insufficient Data for Replication" in content
        # Paper title carried through
        assert "Frog in the Pan" in content
        # Coverage from the report
        assert "50% (1/2)" in content
        # The unmatched requirement is named
        assert "[dq_holdings]" in content
        # Resolution guidance
        assert "Do NOT write `src/strategy.py`" in content

    def test_blocked_md_includes_partial_matches(
        self, tmp_path, sample_requirements
    ):
        """When the BEST match has missing_columns, the file lists it under
        'Partial Matches' so the agent knows which columns are missing."""
        report = {
            "matches": [
                {
                    "requirement": "ibes_analyst",
                    "database": "ibes202301",
                    "table": "nstatsum_xepsint",
                    "fq_name": "ibes202301.nstatsum_xepsint",
                    "matched_columns": ["meanest"],
                    "missing_columns": ["stdev", "medest"],
                    "score": 1,
                },
            ],
            "gaps": [],
            "coverage": "0% (0/1)",
        }
        out_dir = tmp_path / "diagnostics"
        out_dir.mkdir()
        blocked_path = _write_blocked_md(out_dir, report, sample_requirements)
        content = blocked_path.read_text()
        assert "## Partial Matches" in content
        assert "ibes_analyst" in content
        assert "stdev" in content
        assert "medest" in content


class TestEndToEndExit:
    """End-to-end test: run the actual script via subprocess and check
    the exit code and BLOCKED.md presence. This is the integration test
    that proves the script-level guard works (the agent cannot ignore it)."""

    def test_gap_causes_blocked_md_and_exit_1(self, tmp_path):
        """A requirement with no matching table produces BLOCKED.md + exit 1."""
        # Setup: a requirement that has NO matching table (fictional fields)
        diag = tmp_path / "diagnostics"
        diag.mkdir()
        (diag / "data_requirements.json").write_text(json.dumps({
            "paper": "Fictional Paper",
            "requirements": [{
                "id": "fictional_data_source",
                "description": "Some data we definitely don't have",
                "fields": ["xyz_nonexistent_col_1", "xyz_nonexistent_col_2"],
                "date_range": ["2000-01-01", "2020-12-31"],
                "frequency": "daily",
            }],
        }))

        # Invoke the script
        import subprocess
        result = subprocess.run(
            ["python", str(_SCRIPT_PATH), str(diag / "data_requirements.json")],
            capture_output=True, text=True,
            env={**__import__("os").environ,
                 "PYTHONPATH": str(Path(__file__).resolve().parent.parent)},
        )
        # Exit 1 on block
        assert result.returncode == 1, f"expected exit 1, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
        # BLOCKED.md was written
        assert (diag / "BLOCKED.md").is_file()
        # The block message was printed
        assert "BLOCKED" in result.stdout
        # Status is "blocked" in the JSON report
        report = json.loads((diag / "data_match_report.json").read_text())
        assert report["status"] == "blocked"

    def test_sufficient_data_does_not_write_blocked(self, tmp_path):
        """A requirement that matches well produces no BLOCKED.md, exit 0."""
        diag = tmp_path / "diagnostics"
        diag.mkdir()
        (diag / "data_requirements.json").write_text(json.dumps({
            "paper": "Test Paper",
            "requirements": [{
                "id": "crsp_daily",
                "description": "CRSP daily stock file",
                "fields": ["permno", "date", "ret", "prc", "shrout"],
                "date_range": ["1975-01-01", "2007-12-31"],
                "frequency": "daily",
            }],
        }))

        import subprocess
        result = subprocess.run(
            ["python", str(_SCRIPT_PATH), str(diag / "data_requirements.json")],
            capture_output=True, text=True,
            env={**__import__("os").environ,
                 "PYTHONPATH": str(Path(__file__).resolve().parent.parent)},
        )
        assert result.returncode == 0, f"expected exit 0, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
        assert not (diag / "BLOCKED.md").exists()
        report = json.loads((diag / "data_match_report.json").read_text())
        assert report["status"] == "ok"
