"""Tests for paper2spec.clickhouse — data requirements extraction and matching.

Follows the same pattern as test_extractor.py:
  - Mock the LLM (``achat``) for deterministic tests
  - Pure function tests for the matching logic (no mocks needed)
  - Integration test with the real catalog
"""

import json
import os
import tempfile
from unittest.mock import AsyncMock, patch

import pytest

from paper2spec.clickhouse import (
    _build_auth,
    _query_json,
    extract_data_requirements,
    load_catalog,
    match_requirements,
)


# ── Helpers ──────────────────────────────────────────────────────


def _fake_requirements_dict():
    """Return a minimal but valid requirements dict (no LLM needed)."""
    return {
        "paper_title": "MAX Factor: Stocks as Lotteries",
        "requirements": [
            {
                "id": "daily_returns",
                "description": "Daily stock returns, prices, volume, shares",
                "fields": ["date", "permno", "ret", "prc", "vol", "shrout"],
                "frequency": "daily",
                "date_range": ["1962-07-01", "2005-12-31"],
                "filters": ["share_code 10/11", "NYSE/AMEX/NASDAQ"],
            },
            {
                "id": "monthly_returns",
                "description": "Monthly returns and market cap",
                "fields": ["date", "permno", "ret", "prc", "shrout"],
                "frequency": "monthly",
                "date_range": ["1962-07-01", "2005-12-31"],
                "filters": [],
            },
        ],
    }


def _fake_catalog():
    """A minimal catalog for deterministic tests."""
    return {
        "databases": {
            "crsp": {
                "dsf": {
                    "columns": [
                        {"name": "date", "type": "Date"},
                        {"name": "permno", "type": "UInt32"},
                        {"name": "ret", "type": "Float64"},
                        {"name": "prc", "type": "Float64"},
                        {"name": "vol", "type": "Float64"},
                        {"name": "shrout", "type": "Float64"},
                        {"name": "cfacpr", "type": "Float64"},
                    ],
                    "row_count": 218_000_000,
                    "date_range": ["1925-12-31", "2022-09-30"],
                },
                "msf": {
                    "columns": [
                        {"name": "date", "type": "Date"},
                        {"name": "permno", "type": "UInt32"},
                        {"name": "ret", "type": "Float64"},
                    ],
                    "row_count": 3_500_000,
                    "date_range": ["1925-12-31", "2022-09-30"],
                },
            },
            "comp": {
                "funda": {
                    "columns": [
                        {"name": "gvkey", "type": "String"},
                        {"name": "fyear", "type": "Int32"},
                        {"name": "bkvlps", "type": "Float64"},
                    ],
                    "row_count": 856_579,
                    "date_range": None,
                },
            },
        },
    }


# ── match_requirements (pure function — no mocks) ────────────────


class TestMatchRequirements:
    """Deterministic tests for the matching logic."""

    def test_perfect_match_all_columns(self):
        """When all required fields exist in a table, score = len(fields)."""
        reqs = {
            "requirements": [
                {"id": "daily", "fields": ["date", "permno", "ret"]}
            ]
        }
        report = match_requirements(reqs, _fake_catalog())
        assert len(report["matches"]) == 1
        assert report["matches"][0]["fq_name"] == "crsp.dsf"
        assert report["matches"][0]["score"] == 3
        assert report["matches"][0]["missing_columns"] == []

    def test_partial_match_reports_missing(self):
        """Missing columns must be surfaced in the match report."""
        reqs = {
            "requirements": [
                {"id": "daily", "fields": ["date", "permno", "nonexistent"]}
            ]
        }
        report = match_requirements(reqs, _fake_catalog())
        assert report["matches"][0]["score"] == 2
        assert "nonexistent" in report["matches"][0]["missing_columns"]

    def test_best_table_selected(self):
        """When multiple tables match, the one with highest column overlap wins."""
        reqs = {
            "requirements": [
                {"id": "returns", "fields": ["date", "permno", "ret"]}
            ]
        }
        report = match_requirements(reqs, _fake_catalog())
        # dsf has 3/3 match, msf also has 3/3 — but dsf has more total columns
        match = report["matches"][0]
        assert match["score"] == 3
        assert match["fq_name"] in ("crsp.dsf", "crsp.msf")

    def test_no_match_becomes_gap(self):
        """When no table has any of the required fields, it's a gap."""
        reqs = {
            "requirements": [
                {"id": "missing", "fields": ["nonexistent_col"]}
            ]
        }
        report = match_requirements(reqs, _fake_catalog())
        assert len(report["matches"]) == 0
        assert len(report["gaps"]) == 1
        assert report["gaps"][0]["requirement"] == "missing"

    def test_empty_requirements(self):
        """Empty requirements list produces empty report."""
        report = match_requirements({"requirements": []}, _fake_catalog())
        assert report["matches"] == []
        assert report["gaps"] == []

    def test_no_fields_specified(self):
        """Requirement with no fields is flagged as a gap."""
        reqs = {"requirements": [{"id": "empty", "fields": []}]}
        report = match_requirements(reqs, _fake_catalog())
        assert len(report["gaps"]) == 1
        assert "no fields specified" in report["gaps"][0]["reason"]

    def test_coverage_calculation(self):
        """Coverage string shows fraction of matched requirements."""
        reqs = {
            "requirements": [
                {"id": "found", "fields": ["date", "permno"]},
                {"id": "not_found", "fields": ["nonexistent"]},
            ]
        }
        report = match_requirements(reqs, _fake_catalog())
        assert "50%" in report["coverage"]
        assert "1/2" in report["coverage"]

    def test_report_structure(self):
        """Report must have expected top-level keys."""
        report = match_requirements(
            {"paper_title": "Test", "requirements": []}, _fake_catalog()
        )
        assert "paper_title" in report
        assert "matches" in report
        assert "gaps" in report
        assert "coverage" in report

    def test_date_range_included(self):
        """When catalog has date_range, it must appear in match output."""
        reqs = {"requirements": [{"id": "daily", "fields": ["date"]}]}
        report = match_requirements(reqs, _fake_catalog())
        assert report["matches"][0]["date_range"] is not None
        assert "1925" in report["matches"][0]["date_range"][0]


# ── extract_data_requirements (LLM mocked) ───────────────────────


class TestExtractDataRequirements:
    """Tests for the LLM-powered requirements extraction."""

    def _write_spec(self, d, tmpdir):
        p = os.path.join(tmpdir, "spec.json")
        with open(p, "w") as f:
            json.dump(d, f)
        return p

    @patch("paper2spec.llm.achat", new_callable=AsyncMock)
    def test_extract_returns_structured_result(self, mock_achat, tmpdir):
        """With a mocked LLM response, extract returns a valid dict."""
        spec = {
            "paper_title": "Test Paper",
            "strategies": [{"strategy_name": "Momentum"}],
        }
        spec_path = self._write_spec(spec, str(tmpdir))

        mock_achat.return_value = json.dumps(_fake_requirements_dict())

        result = extract_data_requirements(
            spec_path, output_path=os.path.join(str(tmpdir), "reqs.json")
        )

        assert result["paper_title"] == "MAX Factor: Stocks as Lotteries"
        assert len(result["requirements"]) == 2
        assert result["requirements"][0]["id"] == "daily_returns"

    @patch("paper2spec.llm.achat", new_callable=AsyncMock)
    def test_extract_writes_output_file(self, mock_achat, tmpdir):
        """Output file must be written to the specified path."""
        spec = {"paper_title": "Test", "strategies": []}
        spec_path = self._write_spec(spec, str(tmpdir))
        out = os.path.join(str(tmpdir), "data_requirements.json")

        mock_achat.return_value = json.dumps(_fake_requirements_dict())
        extract_data_requirements(spec_path, output_path=out)

        assert os.path.isfile(out)
        with open(out) as f:
            written = json.load(f)
        assert "requirements" in written

    @patch("paper2spec.llm.achat", new_callable=AsyncMock)
    def test_extract_handles_markdown_fence(self, mock_achat, tmpdir):
        """LLM response wrapped in ```json``` fences is still parsed."""
        spec = {"paper_title": "Test", "strategies": []}
        spec_path = self._write_spec(spec, str(tmpdir))

        mock_achat.return_value = "```json\n" + json.dumps(_fake_requirements_dict()) + "\n```"

        result = extract_data_requirements(
            spec_path, output_path=os.path.join(str(tmpdir), "reqs.json")
        )
        assert result["paper_title"] == "MAX Factor: Stocks as Lotteries"

    @patch("paper2spec.llm.achat", new_callable=AsyncMock)
    def test_extract_default_output_alongside_spec(self, mock_achat, tmpdir):
        """When no output_path given, data_requirements.json goes next to spec.json."""
        spec = {"paper_title": "Test", "strategies": []}
        spec_path = self._write_spec(spec, str(tmpdir))

        mock_achat.return_value = json.dumps(_fake_requirements_dict())
        extract_data_requirements(spec_path)

        default_path = os.path.join(str(tmpdir), "data_requirements.json")
        assert os.path.isfile(default_path)


# ── End-to-end with real catalog (no LLM) ────────────────────────


class TestMatchWithRealCatalog:
    """Use the real ClickHouse catalog to verify matching against live data."""

    @pytest.fixture
    def real_catalog(self):
        catalog = load_catalog()
        if catalog is None:
            pytest.skip("No catalog found — run discover_clickhouse.py first")
        return catalog

    def test_catalog_is_loaded(self, real_catalog):
        """Catalog must have databases and be parseable."""
        assert "databases" in real_catalog
        assert "generated_at" in real_catalog
        assert len(real_catalog["databases"]) > 0

    def test_daily_returns_match_real_catalog(self, real_catalog):
        """The catalog must have a table matching daily stock return fields."""
        reqs = {
            "requirements": [
                {"id": "daily", "fields": ["date", "permno", "ret"]}
            ]
        }
        report = match_requirements(reqs, real_catalog)
        assert len(report["matches"]) >= 1, (
            f"No table found with date+permno+ret columns"
        )
        match = report["matches"][0]
        assert match["score"] >= 2, (
            f"Expected at least 2 columns matched, got {match['score']}"
        )

    def test_fundamental_data_match_real_catalog(self, real_catalog):
        """The catalog must have a table matching Compustat fundamental fields."""
        reqs = {
            "requirements": [
                {"id": "fundamentals", "fields": ["gvkey", "fyear", "bkvlps"]}
            ]
        }
        report = match_requirements(reqs, real_catalog)
        assert len(report["matches"]) >= 1, (
            "No table found with gvkey+fyear+bkvlps columns"
        )

    def test_nonexistent_fields_are_gaps(self, real_catalog):
        """A requirement for impossible columns must produce a gap."""
        reqs = {
            "requirements": [
                {"id": "impossible", "fields": ["zzz_nonexistent_column_xyz"]}
            ]
        }
        report = match_requirements(reqs, real_catalog)
        assert len(report["gaps"]) >= 1, (
            "Expected at least one gap for nonexistent column"
        )


# ── _build_auth (pure function) ──────────────────────────────────


class TestBuildAuth:
    """Tests for HTTP query-string auth builder."""

    def test_basic_auth(self):
        cfg = {"user": "testuser", "password": "secret", "database": "mydb"}
        result = _build_auth(cfg)
        assert "user=testuser" in result
        assert "password=secret" in result
        assert "database=mydb" in result

    def test_no_password(self):
        cfg = {"user": "default", "password": "", "database": "mydb"}
        result = _build_auth(cfg)
        assert "password" not in result

    def test_exclude_database(self):
        cfg = {"user": "u", "password": "p", "database": "db"}
        result = _build_auth(cfg, include_database=False)
        assert "database" not in result

    def test_override_database(self):
        cfg = {"user": "u", "password": "p", "database": "default"}
        result = _build_auth(cfg, database="other_db")
        assert "database=other_db" in result
        assert "database=default" not in result

    def test_ampersand_separated(self):
        cfg = {"user": "u", "password": "p", "database": "d"}
        result = _build_auth(cfg)
        parts = result.split("&")
        assert len(parts) == 3


# ── _query_json (mocked HTTP) ───────────────────────────────────


class TestQueryJson:
    """Tests for ClickHouse HTTP query + response parsing."""

    @patch("urllib.request.urlopen")
    def test_ndjson_parsing(self, mock_urlopen):
        """JSONEachRow returns NDJSON — one object per line."""
        mock_urlopen.return_value.__enter__.return_value.read.return_value = (
            b'{"name":"dsf","total_rows":218000000}\n'
            b'{"name":"msf","total_rows":3500000}\n'
        )
        rows = _query_json("http://example.com/", "user=u", "SHOW TABLES")
        assert len(rows) == 2
        assert rows[0]["name"] == "dsf"
        assert rows[0]["total_rows"] == 218000000
        assert rows[1]["name"] == "msf"

    @patch("urllib.request.urlopen")
    def test_json_array_parsing(self, mock_urlopen):
        """Single JSON array response must be parsed correctly."""
        mock_urlopen.return_value.__enter__.return_value.read.return_value = (
            b'[{"result": 42}]'
        )
        rows = _query_json("http://example.com/", "user=u", "SELECT 1")
        assert len(rows) == 1
        assert rows[0]["result"] == 42

    @patch("urllib.request.urlopen")
    def test_empty_response(self, mock_urlopen):
        """Empty response returns empty list."""
        mock_urlopen.return_value.__enter__.return_value.read.return_value = b""
        rows = _query_json("http://example.com/", "user=u", "SELECT 1")
        assert rows == []

    @patch("urllib.request.urlopen")
    def test_whitespace_only_response(self, mock_urlopen):
        """Whitespace-only response returns empty list."""
        mock_urlopen.return_value.__enter__.return_value.read.return_value = b"  \n  "
        rows = _query_json("http://example.com/", "user=u", "SELECT 1")
        assert rows == []

    @patch("urllib.request.urlopen")
    def test_http_error_returns_empty(self, mock_urlopen):
        """HTTP errors are caught and return empty list."""
        mock_urlopen.side_effect = Exception("Connection refused")
        rows = _query_json("http://example.com/", "user=u", "BAD QUERY")
        assert rows == []

    @patch("urllib.request.urlopen")
    def test_malformed_json_returns_empty(self, mock_urlopen):
        """Malformed JSON returns empty list (graceful degradation)."""
        mock_urlopen.return_value.__enter__.return_value.read.return_value = (
            b"not json at all"
        )
        rows = _query_json("http://example.com/", "user=u", "SELECT 1")
        assert rows == []


# ═══════════════════════════════════════════════════════════════════
# Phase 1: E2E contract tests (TDD — these DEFINE what must work)
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def max_paper_spec_path():
    """Path to the real MAX factor paper spec.json."""
    import os
    p = os.path.join(
        os.path.dirname(__file__),
        "..", "library", "ssrn_1262416", "spec.json",
    )
    if not os.path.isfile(p):
        pytest.skip("MAX paper spec.json not found")
    return p


@pytest.fixture
def max_paper_catalog():
    """Real catalog for matching."""
    catalog = load_catalog()
    if catalog is None:
        pytest.skip("Catalog not found — run discover_clickhouse.py first")
    return catalog


@pytest.fixture
def codegen_ready_requirements():
    """A requirements dict that matches the MAX paper's actual data needs."""
    return {
        "paper_title": "MAX Factor: Stocks as Lotteries",
        "requirements": [
            {
                "id": "daily_returns",
                "description": "Daily stock returns, prices, volume for NYSE/AMEX/NASDAQ",
                "fields": ["date", "permno", "ret", "prc", "vol", "shrout"],
                "frequency": "daily",
                "date_range": ["1962-07-01", "2005-12-31"],
                "filters": ["share_code 10/11", "NYSE/AMEX/NASDAQ"],
            },
            {
                "id": "monthly_market_cap",
                "description": "Monthly market capitalization for SIZE filter",
                "fields": ["date", "permno", "prc", "shrout"],
                "frequency": "monthly",
                "date_range": ["1962-07-01", "2005-12-31"],
                "filters": [],
            },
            {
                "id": "fundamentals",
                "description": "Annual Compustat fundamentals for BM ratio",
                "fields": ["gvkey", "fyear", "bkvlps", "at", "lt"],
                "frequency": "annual",
                "date_range": ["1961-01-01", "2005-12-31"],
                "filters": [],
            },
        ],
    }


class TestE2EContract:
    """Tests that define the contract the E2E pipeline must satisfy.

    These tests encode what a code-generation agent needs from the
    data bridge.  They MUST pass once the implementation is complete.
    """

    def test_full_pipeline_requirements_to_match_report(
        self, max_paper_catalog, codegen_ready_requirements
    ):
        """match_requirements on known reqs must produce ≥3 matches.

        The MAX paper needs CRSP daily returns, CRSP monthly, and
        Compustat fundamentals.  All three must match real tables.
        """
        report = match_requirements(codegen_ready_requirements, max_paper_catalog)
        assert len(report["matches"]) >= 3, (
            f"Expected ≥3 matches for MAX paper core datasets, got {len(report['matches'])}"
        )

    def test_match_report_has_codegen_fields(
        self, max_paper_catalog, codegen_ready_requirements
    ):
        """Every match entry must contain fields the agent needs to write SQL.

        Required fields per match:
          - fq_name:  fully-qualified table name (e.g. crsp.dsf)
          - matched_columns:  columns that exist in the table
          - missing_columns:  columns the paper needs but the table lacks
          - date_range:  min/max dates in the table
          - row_count:  approximate row count
        """
        report = match_requirements(codegen_ready_requirements, max_paper_catalog)
        required_fields = {
            "fq_name", "matched_columns", "missing_columns",
            "date_range", "row_count",
        }
        for match in report["matches"]:
            missing = required_fields - set(match.keys())
            assert not missing, (
                f"Match [{match['requirement']}] missing required fields: {missing}"
            )

    def test_match_report_fq_name_is_dotted(
        self, max_paper_catalog, codegen_ready_requirements
    ):
        """Every fq_name must be in 'database.table' format for SQL generation."""
        report = match_requirements(codegen_ready_requirements, max_paper_catalog)
        for match in report["matches"]:
            fq = match["fq_name"]
            assert "." in fq, (
                f"fq_name must be 'db.table' format, got '{fq}'"
            )
            db, table = fq.split(".", 1)
            assert db, f"Database part missing in '{fq}'"
            assert table, f"Table part missing in '{fq}'"

    def test_daily_returns_date_range_covers_paper_period(
        self, max_paper_catalog, codegen_ready_requirements
    ):
        """The daily returns table must cover 1962–2005.

        If the catalog shows coverage outside this range, the agent
        must be warned so it can constrain the SQL query.
        """
        report = match_requirements(codegen_ready_requirements, max_paper_catalog)
        daily = next(
            (m for m in report["matches"] if m["requirement"] == "daily_returns"),
            None,
        )
        assert daily is not None, (
            "daily_returns must have a match — check crsp.dsf or similar"
        )
        dr = daily.get("date_range")
        assert dr is not None, "daily_returns table must have a date_range"
        # At minimum, the table must overlap with the paper's period
        assert dr[0] <= "2005-12-31", (
            f"Table starts {dr[0]} — later than paper end 2005-12-31"
        )
        assert dr[1] >= "1962-07-01", (
            f"Table ends {dr[1]} — earlier than paper start 1962-07-01"
        )

    def test_missing_columns_surfaced_in_match(
        self, max_paper_catalog
    ):
        """When a required field doesn't exist, it must appear in missing_columns.

        The agent uses missing_columns to decide: workaround? warn user?
        """
        reqs = {
            "requirements": [
                {
                    "id": "daily",
                    "fields": ["date", "permno", "this_field_does_not_exist_xyz"],
                }
            ]
        }
        report = match_requirements(reqs, max_paper_catalog)
        assert len(report["matches"]) >= 1, "date and permno match something"
        match = report["matches"][0]
        assert "this_field_does_not_exist_xyz" in match["missing_columns"], (
            "Missing column must appear in missing_columns"
        )

    def test_gap_when_no_column_overlap(self, max_paper_catalog):
        """A requirement with zero column matches must be a gap, not a match.

        The agent must NOT generate SQL when nothing matches.
        """
        reqs = {
            "requirements": [
                {
                    "id": "impossible",
                    "fields": ["zzz_nonexistent_1", "zzz_nonexistent_2"],
                }
            ]
        }
        report = match_requirements(reqs, max_paper_catalog)
        assert len(report["matches"]) == 0, (
            "Zero-column-overlap requirement must NOT produce a match"
        )
        assert len(report["gaps"]) >= 1

    @patch("paper2spec.llm.achat", new_callable=AsyncMock)
    def test_max_paper_e2e_requirements_to_matches(
        self, mock_achat, max_paper_spec_path, max_paper_catalog
    ):
        """Full pipeline: real spec → mocked LLM → match against real catalog.

        This is the defining E2E test.  When this passes, the bridge works.
        """
        # LLM returns known-good requirements
        mock_achat.return_value = json.dumps({
            "paper_title": "MAX Factor: Stocks as Lotteries",
            "requirements": [
                {
                    "id": "daily_returns",
                    "description": "Daily stock returns from CRSP",
                    "fields": ["date", "permno", "ret", "prc", "vol", "shrout"],
                    "frequency": "daily",
                    "date_range": ["1962-07-01", "2005-12-31"],
                    "filters": ["share_code 10/11"],
                },
                {
                    "id": "fundamentals",
                    "description": "Annual Compustat fundamentals",
                    "fields": ["gvkey", "fyear", "bkvlps", "at", "lt"],
                    "frequency": "annual",
                    "date_range": ["1961-01-01", "2005-12-31"],
                    "filters": [],
                },
            ],
        })

        import tempfile, os
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "data_requirements.json")
            requirements = extract_data_requirements(
                max_paper_spec_path, output_path=out
            )

        # Bridge: match against real catalog
        report = match_requirements(requirements, max_paper_catalog)

        # Contract assertions
        assert len(report["matches"]) >= 2, (
            f"Expected ≥2 matches from MAX paper spec, got {len(report['matches'])}"
        )
        for match in report["matches"]:
            assert match["score"] >= 2, (
                f"Match [{match['requirement']}] score={match['score']} too low"
            )
            assert "." in match["fq_name"], (
                f"fq_name must be dotted: {match['fq_name']}"
            )
            assert len(match["matched_columns"]) >= 2
