"""Data-access primitives — encode correct query patterns for specific tables.

Unlike the pure-pandas primitives in ``utils.quantile`` / ``portfolio`` /
``metrics``, the functions here take a ``fetch_fn`` callable (the
strategy's own copy-pasted ``fetch_data_cached``) and do I/O. They exist
because certain tables have query patterns where the "obvious" approach
is silently wrong — e.g. filtering ``dsenames`` by the paper's sample
window excludes stocks listed before the start date.

By routing those queries through a primitive, the correct pattern
(wide date range, required columns, filter logic) is baked in and the
agent cannot accidentally reproduce the bug.

Usage in a generated ``strategy.py``::

    from utils.data import fetch_universe_filter

    valid_permnos = fetch_universe_filter(
        fetch_data_cached,
        names_table="crsp_202601.dsenames",
        shrcd_filter=[10, 11],
        exchcd_filter=[1, 2, 3],
    )
    daily = daily[daily["permno"].isin(valid_permnos)]
"""

from __future__ import annotations

from typing import Callable, Optional

import pandas as pd


class DataError(Exception):
    """Raised when a data-access primitive fails."""
    pass


def fetch_universe_filter(
    fetch_fn: Callable,
    names_table: str = "crsp_202601.dsenames",
    shrcd_filter: Optional[list[int]] = None,
    exchcd_filter: Optional[list[int]] = None,
) -> set[int]:
    """Return the set of valid CRSP permnos passing share/exchange code filters.

    Queries ``dsenames`` for the full history (1900-2100), applies the
    ``shrcd`` / ``exchcd`` filters, and returns the set of qualifying
    permnos. The caller filters its daily/monthly stock frame:

    .. code-block:: python

        valid = fetch_universe_filter(fetch_data_cached, shrcd_filter=[10, 11])
        daily = daily[daily["permno"].isin(valid)]

    **Why this exists:** ``dsenames.namedt`` is the name-start date, not
    a trading date. Filtering ``namedt >= '1962-01-01'`` (the paper's
    sample start) silently excludes every stock listed before 1962 —
    the opposite of what you want. This helper enforces the correct
    pattern: query the full history with a very wide date range, include
    ``namedt`` in the SELECT list, apply the filters, return permnos.

    Args:
        fetch_fn: The strategy's own ``fetch_data_cached`` function
            (copy-pasted from the template). Called with the correct
            kwargs — the agent never constructs these itself.
        names_table: Fully-qualified ``dsenames`` table name. Defaults
            to the current default vintage (``crsp_202601.dsenames``).
        shrcd_filter: Share codes to keep (e.g. ``[10, 11]`` for
            ordinary common shares). ``None`` = no filter.
        exchcd_filter: Exchange codes to keep (e.g. ``[1, 2, 3]`` for
            NYSE / NYSE MKT / NASDAQ). ``None`` = no filter.

    Returns:
        Set of ``permno`` integers passing both filters.

    Raises:
        DataError: if the query returns no rows or required columns
            are missing.
    """
    columns = ["permno", "shrcd", "exchcd", "namedt", "nameendt"]
    names = fetch_fn(
        table=names_table,
        columns=columns,
        start="1900-01-01",
        end="2100-01-01",
        date_col="namedt",
    )

    if names is None or names.empty:
        raise DataError(
            f"No rows returned from {names_table} — check the table name "
            f"and ClickHouse connection."
        )

    for col in ("permno", "shrcd", "exchcd"):
        if col not in names.columns:
            raise DataError(
                f"Column '{col}' missing from {names_table} — "
                f"got columns {list(names.columns)}"
            )

    mask = pd.Series(True, index=names.index)
    if shrcd_filter:
        mask &= names["shrcd"].isin(shrcd_filter)
    if exchcd_filter:
        mask &= names["exchcd"].isin(exchcd_filter)

    valid = set(names.loc[mask, "permno"].unique())
    if not valid:
        raise DataError(
            f"No permnos pass the universe filter "
            f"(shrcd={shrcd_filter}, exchcd={exchcd_filter}) — "
            f"check the filter values."
        )
    return valid
