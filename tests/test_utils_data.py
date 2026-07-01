"""Tests for utils.data — data-access primitives."""

import pandas as pd
import pytest

from utils.data import apply_universe_filter, DataError


# ── Fixtures ──────────────────────────────────────────────────


def _make_mock_fetch(hdr_df):
    """Return a mock fetch_fn that validates kwargs and returns hdr_df."""
    def mock_fetch(**kwargs):
        # Verify the primitive enforces the correct pattern
        assert kwargs["start"] == "1900-01-01", (
            f"Expected wide start=1900-01-01, got {kwargs['start']} — "
            f"filtering by paper sample window excludes pre-listing stocks"
        )
        assert kwargs["end"] == "2100-01-01", (
            f"Expected wide end=2100-01-01, got {kwargs['end']}"
        )
        assert kwargs["date_col"] == "begdat"
        assert "begdat" in kwargs["columns"]
        assert "enddat" in kwargs["columns"]
        assert "permno" in kwargs["columns"]
        assert "hshrcd" in kwargs["columns"]
        assert "hexcd" in kwargs["columns"]
        return hdr_df
    return mock_fetch


@pytest.fixture
def hdr_df():
    """Simulated dsfhdr response.

    Permno 100: always common stock on NYSE (1960-2024)
    Permno 101: REIT until 1980, then common stock on NASDAQ
    Permno 102: never common stock (shrcd=70 throughout)
    Permno 103: common stock, delisted in 2000
    """
    return pd.DataFrame({
        "permno":  [100,    101,    101,    102,    103],
        "hshrcd":  [10,     70,     10,     70,     10],
        "hexcd":   [1,      1,      3,      1,      1],
        "begdat":  pd.to_datetime([
            "1960-01-01", "1970-01-01", "1980-01-01",
            "1965-01-01", "1975-01-01",
        ]),
        "enddat":  pd.to_datetime([
            "9999-12-31", "1979-12-31", "9999-12-31",
            "9999-12-31", "2000-06-30",
        ]),
    })


@pytest.fixture
def daily_df():
    """Daily data with date as index (as fetch_data_cached returns it)."""
    rows = []
    for permno in [100, 101, 102, 103]:
        for date in pd.to_datetime(["1985-01-15", "1990-01-15", "2005-01-15"]):
            rows.append({"date": date, "permno": permno, "ret": 0.01, "prc": 50.0})
    df = pd.DataFrame(rows)
    return df.set_index("date")


# ── apply_universe_filter ─────────────────────────────────────


class TestApplyUniverseFilter:
    def test_returns_dataframe_same_structure(self, daily_df, hdr_df):
        fetch_fn = _make_mock_fetch(hdr_df)
        out = apply_universe_filter(daily_df, fetch_fn, shrcd_filter=[10, 11])
        assert isinstance(out, pd.DataFrame)
        assert out.index.name == "date"
        assert set(out.columns) == {"permno", "ret", "prc"}

    def test_always_common_stock_included(self, daily_df, hdr_df):
        """Permno 100 (common since 1960) should be in all 3 dates."""
        fetch_fn = _make_mock_fetch(hdr_df)
        out = apply_universe_filter(daily_df, fetch_fn, shrcd_filter=[10, 11])
        assert set(out.loc[out["permno"] == 100, "permno"].unique()) == {100}
        assert len(out[out["permno"] == 100]) == 3

    def test_reit_then_common_point_in_time(self, daily_df, hdr_df):
        """Permno 101 was REIT (shrcd=70) until 1980, then common (shrcd=10).

        With the old 'ever was common' bug, permno 101 would be included
        for ALL dates (1985, 1990, 2005) because it became common in 1980.
        With point-in-time filtering, it IS included for 1985+ (correct —
        it was common by then). This test verifies the point-in-time logic
        works: permno 101 should be included for 1985, 1990, 2005 but
        NOT for a date before 1980.
        """
        fetch_fn = _make_mock_fetch(hdr_df)
        out = apply_universe_filter(daily_df, fetch_fn, shrcd_filter=[10, 11])
        dates_101 = out.loc[out["permno"] == 101].index.sort_values()
        assert len(dates_101) == 3  # 1985, 1990, 2005 — all after 1980

    def test_reit_then_common_excludes_pre_conversion(self, hdr_df):
        """Permno 101 before 1980 should NOT be in the filtered universe."""
        early_daily = pd.DataFrame({
            "date": pd.to_datetime(["1975-01-15", "1985-01-15"]),
            "permno": [101, 101],
            "ret": [0.01, 0.02],
        }).set_index("date")

        fetch_fn = _make_mock_fetch(hdr_df)
        out = apply_universe_filter(early_daily, fetch_fn, shrcd_filter=[10, 11])
        # Only the 1985 row should survive (permno 101 became common in 1980)
        assert len(out) == 1
        assert out.index[0] == pd.Timestamp("1985-01-15")

    def test_never_common_excluded(self, daily_df, hdr_df):
        """Permno 102 (shrcd=70 throughout) should never appear."""
        fetch_fn = _make_mock_fetch(hdr_df)
        out = apply_universe_filter(daily_df, fetch_fn, shrcd_filter=[10, 11])
        assert 102 not in out["permno"].values

    def test_delisted_stock_excluded_after_enddat(self, daily_df, hdr_df):
        """Permno 103 (delisted 2000-06-30) should not appear in 2005."""
        fetch_fn = _make_mock_fetch(hdr_df)
        out = apply_universe_filter(daily_df, fetch_fn, shrcd_filter=[10, 11])
        dates_103 = out.loc[out["permno"] == 103].index
        assert all(d < pd.Timestamp("2000-07-01") for d in dates_103)
        assert pd.Timestamp("2005-01-15") not in dates_103

    def test_exchcd_filter(self, daily_df, hdr_df):
        """Exchcd filter: permno 101 is on NASDAQ (3) after 1980."""
        fetch_fn = _make_mock_fetch(hdr_df)
        out = apply_universe_filter(
            daily_df, fetch_fn,
            shrcd_filter=[10, 11], exchcd_filter=[1],  # NYSE only
        )
        # Permno 101 (NASDAQ) should be excluded
        assert 101 not in out["permno"].values
        # Permno 100 (NYSE) should be included
        assert 100 in out["permno"].values

    def test_no_filters_returns_all_valid(self, daily_df, hdr_df):
        """With no shrcd/exchcd filters, all header records pass."""
        fetch_fn = _make_mock_fetch(hdr_df)
        out = apply_universe_filter(daily_df, fetch_fn)
        # All 4 permnos have header records covering 1985-2005
        # except 103 (delisted before 2005)
        permnos = set(out["permno"].unique())
        assert 100 in permnos
        assert 101 in permnos
        assert 102 in permnos
        assert 103 in permnos  # included for 1985 and 1990

    def test_empty_filter_result_raises(self, daily_df, hdr_df):
        fetch_fn = _make_mock_fetch(hdr_df)
        with pytest.raises(DataError, match="No header records pass"):
            apply_universe_filter(daily_df, fetch_fn, shrcd_filter=[99])

    def test_empty_query_result_raises(self, daily_df):
        def empty_fetch(**kwargs):
            return pd.DataFrame()
        with pytest.raises(DataError, match="No rows returned"):
            apply_universe_filter(daily_df, empty_fetch)

    def test_missing_column_raises(self, daily_df):
        bad_hdr = pd.DataFrame({
            "permno": [100],
            "hshrcd": [10],
            # hexcd, begdat, enddat missing
        })
        def bad_fetch(**kwargs):
            return bad_hdr
        with pytest.raises(DataError, match="Column 'hexcd' missing"):
            apply_universe_filter(daily_df, bad_fetch)

    def test_no_surviving_rows_raises(self, hdr_df):
        """Daily data outside all header validity windows → DataError."""
        future_daily = pd.DataFrame({
            "date": pd.to_datetime(["2050-01-15"]),
            "permno": [103],  # delisted in 2000
            "ret": [0.01],
        }).set_index("date")
        fetch_fn = _make_mock_fetch(hdr_df)
        with pytest.raises(DataError, match="No daily rows survive"):
            apply_universe_filter(future_daily, fetch_fn, shrcd_filter=[10, 11])

    def test_custom_table_name(self, daily_df, hdr_df):
        """The hdr_table kwarg should be passed through to fetch_fn."""
        captured = {}
        def capturing_fetch(**kwargs):
            captured["table"] = kwargs["table"]
            return hdr_df
        apply_universe_filter(
            daily_df, capturing_fetch, hdr_table="crsp_202501.dsfhdr",
        )
        assert captured["table"] == "crsp_202501.dsfhdr"

    def test_enforces_wide_date_range(self, daily_df, hdr_df):
        """The primitive must NOT pass the paper's sample window as start/end."""
        fetch_fn = _make_mock_fetch(hdr_df)
        # The mock asserts start=1900-01-01 and end=2100-01-01 internally.
        apply_universe_filter(daily_df, fetch_fn)

    def test_date_as_column_not_index(self, hdr_df):
        """When date is a regular column (not index), the filter should work."""
        daily = pd.DataFrame({
            "date": pd.to_datetime(["1985-01-15", "1985-01-15"]),
            "permno": [100, 102],
            "ret": [0.01, 0.02],
        })
        fetch_fn = _make_mock_fetch(hdr_df)
        out = apply_universe_filter(daily, fetch_fn, shrcd_filter=[10, 11])
        assert len(out) == 1
        assert out.iloc[0]["permno"] == 100
