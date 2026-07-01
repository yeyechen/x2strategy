"""Data-access primitives — encode correct query patterns for specific tables.

Unlike the pure-pandas primitives in ``utils.quantile`` / ``portfolio`` /
``metrics``, the functions here take a ``fetch_fn`` callable (the
strategy's own copy-pasted ``fetch_data_cached``) and do I/O. They exist
because certain tables have query patterns where the "obvious" approach
is silently wrong — e.g. filtering ``dsenames`` by the paper's sample
window excludes stocks listed before the start date, or filtering by
"ever was a common stock" includes stocks that were REITs during the
sample period.

By routing those queries through a primitive, the correct pattern
(wide date range, point-in-time merge, required columns) is baked in
and the agent cannot accidentally reproduce the bug.

Usage in a generated ``strategy.py``::

    from utils.data import apply_universe_filter

    daily = fetch_data_cached(table="crsp_202601.dsf", ...)
    daily = apply_universe_filter(
        daily, fetch_data_cached,
        shrcd_filter=[10, 11],
        exchcd_filter=[1, 2, 3],
    )
"""

from __future__ import annotations

from typing import Callable, Optional

import pandas as pd


class DataError(Exception):
    """Raised when a data-access primitive fails."""
    pass


def apply_universe_filter(
    daily: pd.DataFrame,
    fetch_fn: Callable,
    date_col: str = "date",
    permno_col: str = "permno",
    hdr_table: str = "crsp_202601.dsfhdr",
    shrcd_filter: Optional[list[int]] = None,
    exchcd_filter: Optional[list[int]] = None,
) -> pd.DataFrame:
    """Filter daily stock data to common stocks on major exchanges, **point-in-time**.

    Uses ``dsfhdr`` (CRSP header records with validity windows) to do a
    proper point-in-time filter: a stock is included for a given date
    **only if** its header record on that date has ``hshrcd`` in
    ``shrcd_filter`` AND ``hexcd`` in ``exchcd_filter``.

    This prevents two bugs that the "filter by a set of valid permnos"
    approach causes:

    1. **"Ever was common stock" contamination** — a stock that was a
       REIT (``hshrcd=70``) during 1962-2005 but became a common stock
       (``hshrcd=10``) in 2010 is incorrectly included in the 1962-2005
       sample if you filter by "ever matched" rather than
       "matched on this date".
    2. **``dsenames`` date-filter exclusion** — filtering
       ``dsenames.namedt >= paper_start`` excludes stocks listed before
       the sample start. This primitive uses ``dsfhdr`` with a wide
       1900-2100 date range and joins on the validity window.

    Args:
        daily: Daily stock data (e.g. from ``fetch_data_cached``). Must
            contain ``permno_col`` and either have ``date_col`` as a
            column or as the index.
        fetch_fn: The strategy's own ``fetch_data_cached`` function.
        date_col: Name of the date column (or index) in ``daily``.
        permno_col: Name of the permno column in ``daily``.
        hdr_table: Fully-qualified ``dsfhdr`` table name.
        shrcd_filter: Share codes to keep (e.g. ``[10, 11]``).
        exchcd_filter: Exchange codes to keep (e.g. ``[1, 2, 3]``).

    Returns:
        Filtered ``daily`` DataFrame with the same structure (same
        index, same columns) as the input — just fewer rows.

    Raises:
        DataError: if the dsfhdr query returns no rows, the required
            columns are missing, or no daily rows survive the filter.
    """
    # 1. Query dsfhdr for all header records (wide date range)
    hdr = fetch_fn(
        table=hdr_table,
        columns=["permno", "hshrcd", "hexcd", "begdat", "enddat"],
        start="1900-01-01",
        end="2100-01-01",
        date_col="begdat",
    )

    if hdr is None or hdr.empty:
        raise DataError(
            f"No rows returned from {hdr_table} — check the table name "
            f"and ClickHouse connection."
        )

    for col in ("permno", "hshrcd", "hexcd", "begdat", "enddat"):
        if col not in hdr.columns:
            raise DataError(
                f"Column '{col}' missing from {hdr_table} — "
                f"got columns {list(hdr.columns)}"
            )

    # 2. Filter header records by share/exchange code
    mask = pd.Series(True, index=hdr.index)
    if shrcd_filter:
        mask &= hdr["hshrcd"].isin(shrcd_filter)
    if exchcd_filter:
        mask &= hdr["hexcd"].isin(exchcd_filter)
    valid_hdr = hdr.loc[mask, ["permno", "begdat", "enddat"]].copy()

    if valid_hdr.empty:
        raise DataError(
            f"No header records pass the universe filter "
            f"(shrcd={shrcd_filter}, exchcd={exchcd_filter}) — "
            f"check the filter values."
        )

    # 3. Prepare daily data for merge (get date as a column)
    was_indexed = date_col not in daily.columns
    if was_indexed:
        daily_reset = daily.reset_index()
    else:
        daily_reset = daily.copy()

    # 4. Point-in-time merge: for each daily row, find matching header
    #    records (permno matches AND date falls within [begdat, enddat])
    valid_hdr["begdat"] = pd.to_datetime(valid_hdr["begdat"])
    valid_hdr["enddat"] = pd.to_datetime(valid_hdr["enddat"])
    daily_reset[date_col] = pd.to_datetime(daily_reset[date_col])

    merged = daily_reset.merge(
        valid_hdr, on=permno_col, how="inner",
    )
    in_range = (merged[date_col] >= merged["begdat"]) & (merged[date_col] <= merged["enddat"])
    filtered = merged.loc[in_range].drop(columns=["begdat", "enddat"])

    # Drop duplicates in case a permno has overlapping header records
    filtered = filtered.drop_duplicates()

    if filtered.empty:
        raise DataError(
            f"No daily rows survive the point-in-time universe filter "
            f"(shrcd={shrcd_filter}, exchcd={exchcd_filter}). "
            f"Check that the daily data and header records overlap in time."
        )

    # 5. Restore original structure (date back as index if it was)
    if was_indexed:
        filtered = filtered.set_index(date_col)

    return filtered
