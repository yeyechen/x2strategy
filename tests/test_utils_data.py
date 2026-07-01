"""Tests for utils.data — data-access primitives."""

import pandas as pd
import pytest

from utils.data import fetch_universe_filter, DataError


# ── Fixtures ──────────────────────────────────────────────────


def _make_mock_fetch(names_df):
    """Return a mock fetch_fn that validates kwargs and returns names_df."""
    def mock_fetch(**kwargs):
        # Verify the primitive enforces the correct pattern
        assert kwargs["start"] == "1900-01-01", (
            f"Expected wide start=1900-01-01, got {kwargs['start']} — "
            f"filtering by paper sample window excludes pre-listing stocks"
        )
        assert kwargs["end"] == "2100-01-01", (
            f"Expected wide end=2100-01-01, got {kwargs['end']}"
        )
        assert kwargs["date_col"] == "namedt"
        assert "namedt" in kwargs["columns"]
        assert "permno" in kwargs["columns"]
        assert "shrcd" in kwargs["columns"]
        assert "exchcd" in kwargs["columns"]
        return names_df
    return mock_fetch


@pytest.fixture
def names_df():
    """Simulated dsenames response with 5 permnos across share/exchange codes."""
    return pd.DataFrame({
        "permno":   [100, 101, 102, 103, 104],
        "shrcd":    [10,  11,  12,  10,  11],
        "exchcd":   [1,   2,   3,   1,   4],
        "namedt":   pd.to_datetime([
            "1950-01-01", "1960-06-15", "1970-01-01",
            "1980-01-01", "1990-01-01",
        ]),
        "nameendt": pd.to_datetime([
            "9999-12-31", "9999-12-31", "2000-12-31",
            "9999-12-31", "9999-12-31",
        ]),
    })


# ── fetch_universe_filter ─────────────────────────────────────


class TestFetchUniverseFilter:
    def test_returns_set_of_permnos(self, names_df):
        fetch_fn = _make_mock_fetch(names_df)
        valid = fetch_universe_filter(fetch_fn, shrcd_filter=[10, 11])
        assert isinstance(valid, set)
        assert valid == {100, 101, 103, 104}

    def test_shrcd_filter_excludes_non_matching(self, names_df):
        fetch_fn = _make_mock_fetch(names_df)
        valid = fetch_universe_filter(fetch_fn, shrcd_filter=[10])
        assert valid == {100, 103}

    def test_exchcd_filter_excludes_non_matching(self, names_df):
        fetch_fn = _make_mock_fetch(names_df)
        valid = fetch_universe_filter(
            fetch_fn, shrcd_filter=[10, 11], exchcd_filter=[1, 2, 3],
        )
        # 100 (10,1)✓  101 (11,2)✓  102 (12,3)✗ shrcd  103 (10,1)✓  104 (11,4)✗ exchcd
        assert valid == {100, 101, 103}

    def test_both_filters_combined(self, names_df):
        fetch_fn = _make_mock_fetch(names_df)
        valid = fetch_universe_filter(
            fetch_fn, shrcd_filter=[10, 11], exchcd_filter=[1, 2],
        )
        # 100 (10,1)✓  101 (11,2)✓  102 shrcd✗  103 (10,1)✓  104 exchcd✗
        assert valid == {100, 101, 103}

    def test_no_filters_returns_all(self, names_df):
        fetch_fn = _make_mock_fetch(names_df)
        valid = fetch_universe_filter(fetch_fn)
        assert valid == {100, 101, 102, 103, 104}

    def test_empty_result_raises(self, names_df):
        fetch_fn = _make_mock_fetch(names_df)
        with pytest.raises(DataError, match="No permnos pass"):
            fetch_universe_filter(fetch_fn, shrcd_filter=[99])

    def test_empty_query_result_raises(self):
        def empty_fetch(**kwargs):
            return pd.DataFrame()
        with pytest.raises(DataError, match="No rows returned"):
            fetch_universe_filter(empty_fetch)

    def test_missing_column_raises(self):
        bad_df = pd.DataFrame({
            "permno": [100],
            "shrcd": [10],
            # exchcd missing
            "namedt": pd.to_datetime(["1950-01-01"]),
            "nameendt": pd.to_datetime(["9999-12-31"]),
        })
        def bad_fetch(**kwargs):
            return bad_df
        with pytest.raises(DataError, match="Column 'exchcd' missing"):
            fetch_universe_filter(bad_fetch)

    def test_custom_table_name(self, names_df):
        """The names_table kwarg should be passed through to fetch_fn."""
        captured = {}
        def capturing_fetch(**kwargs):
            captured["table"] = kwargs["table"]
            return names_df
        fetch_universe_filter(
            capturing_fetch, names_table="crsp_202501.dsenames",
        )
        assert captured["table"] == "crsp_202501.dsenames"

    def test_enforces_wide_date_range(self, names_df):
        """The primitive must NOT pass the paper's sample window as start/end.

        This is the core guardrail — if the primitive ever passes a narrow
        date range, stocks listed before the start would be excluded.
        """
        fetch_fn = _make_mock_fetch(names_df)
        # The mock asserts start=1900-01-01 and end=2100-01-01 internally.
        # If the primitive passes a narrow range, the mock raises AssertionError.
        fetch_universe_filter(fetch_fn)
