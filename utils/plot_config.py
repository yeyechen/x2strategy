"""Plot configuration for the deterministic primitives.

Lifted from ``RA-2025-summer/utils/config.py`` (the ``PlotConfig`` half).
The ClickHouse side of that config was dropped — ``x2strategy`` reads
connection details from ``.env`` via ``paper2spec.config``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlotConfig:
    """Visual conventions for plotting primitives.

    Frozen dataclass — config is set once at import and never mutated.
    Override individual values by passing a new instance to the
    plotting functions (or monkey-patch via ``plot_config`` below).
    """

    blue_hex: str = "#1e88e5"     # equal-weighted line / bar
    red_hex: str = "#f31d36"      # value-weighted line / bar; drawdown fill
    default_figsize: tuple = (12, 6)
    default_dpi: int = 150         # higher = sharper PNGs, bigger files


# Module-level singleton — matches the user's `config.plot` access pattern.
plot_config = PlotConfig()


__all__ = ["PlotConfig", "plot_config"]