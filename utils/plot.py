"""Plotting primitives — ported from RA-2025-summer/utils/plotting.py.

Key adaptation: ``plt.show()`` is replaced with a ``save_to=Path``
parameter (defaults to ``None`` for backward compat). This makes the
plots headless-safe (no GUI required on the backtest server) and
idempotent — same input → same output PNG.

The agent calls these directly from generated ``strategy.py`` to
populate ``results/pnl_curve.png`` and ``results/drawdown.png`` etc.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .plot_config import plot_config


PathLike = Union[str, Path]


class PlotError(Exception):
    """Raised when plotting fails."""
    pass


def _save_or_show(fig: plt.Figure, save_to: Optional[PathLike]) -> None:
    """Save the figure to ``save_to`` (if provided) and always close it.

    The user source uses ``plt.show()`` for interactive notebooks. Here we
    always save (if a path is given) and close — no GUI windows pop up
    on headless backtest servers.
    """
    if save_to is not None:
        path = Path(save_to)
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=plot_config.default_dpi, bbox_inches="tight")
    plt.close(fig)


def plot_cumulative_returns(
    portfolio_df: pd.DataFrame,
    index_col_name: str,
    ret_col_lst: List[str],
    figsize: Optional[Tuple[int, int]] = None,
    title: Optional[str] = None,
    save_to: Optional[PathLike] = None,
) -> None:
    """Plot cumulative returns for one or more portfolio return columns.

    The "P&L curve" primitive. Each ``ret_col_lst[i]`` becomes a line;
    column naming convention ``_EW`` / ``_VW`` triggers the canonical
    blue / red color palette.

    Args:
        portfolio_df: DataFrame with the return columns and a date column.
        index_col_name: name of the date column.
        ret_col_lst: list of return column names to plot.
        figsize: (width, height) override. Default: ``plot_config.default_figsize``.
        title: plot title. Default: ``"Cumulative Returns of Portfolios"``.
        save_to: if given, save the PNG to this path and close the figure.
            If None, the figure is created and closed without saving.

    Raises:
        PlotError: if required columns are missing or plotting fails.
    """
    required = [index_col_name] + ret_col_lst
    missing = [c for c in required if c not in portfolio_df.columns]
    if missing:
        raise PlotError(f"plot_cumulative_returns: missing columns {missing}")

    try:
        fig, ax = plt.subplots(figsize=figsize or plot_config.default_figsize)

        for col in ret_col_lst:
            cum = (1 + portfolio_df[col]).cumprod() - 1
            color = None
            if "_EW" in col:
                color = plot_config.blue_hex
            elif "_VW" in col:
                color = plot_config.red_hex

            ax.plot(portfolio_df[index_col_name], cum, label=col, color=color, linewidth=2)

        ax.set_xlabel(index_col_name.title())
        ax.set_ylabel("Cumulative Returns")
        ax.set_title(title or "Cumulative Returns of Portfolios")
        ax.legend()
        ax.grid(True, alpha=0.3)
        fig.tight_layout()

        _save_or_show(fig, save_to)
    except Exception as e:
        if isinstance(e, PlotError):
            raise
        raise PlotError(f"plot_cumulative_returns failed: {e}")


def plot_drawdown(
    portfolio_df: pd.DataFrame,
    date_col: str,
    ret_col: str,
    figsize: Optional[Tuple[int, int]] = None,
    save_to: Optional[PathLike] = None,
) -> None:
    """Plot drawdown over time (filled area, percentage y-axis).

    The agent calls this with the long-short portfolio to populate
    ``results/drawdown.png``.

    Args:
        portfolio_df: DataFrame with a date column and a return column.
        date_col: name of the date column.
        ret_col: name of the return column.
        figsize: (width, height) override.
        save_to: if given, save the PNG to this path.

    Raises:
        PlotError: if required columns are missing.
    """
    required = [date_col, ret_col]
    missing = [c for c in required if c not in portfolio_df.columns]
    if missing:
        raise PlotError(f"plot_drawdown: missing columns {missing}")

    try:
        df = portfolio_df.sort_values(date_col).copy()
        df["cum_ret"] = (1 + df[ret_col]).cumprod()
        df["running_max"] = df["cum_ret"].expanding().max()
        df["drawdown"] = (df["cum_ret"] / df["running_max"] - 1) * 100

        fig, ax = plt.subplots(figsize=figsize or plot_config.default_figsize)
        ax.fill_between(df[date_col], df["drawdown"], 0,
                        color=plot_config.red_hex, alpha=0.3)
        ax.plot(df[date_col], df["drawdown"],
                color=plot_config.red_hex, linewidth=1)

        ax.set_xlabel(date_col.title())
        ax.set_ylabel("Drawdown (%)")
        ax.set_title("Portfolio Drawdown Over Time")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()

        _save_or_show(fig, save_to)
    except Exception as e:
        if isinstance(e, PlotError):
            raise
        raise PlotError(f"plot_drawdown failed: {e}")


def plot_decile_spread(
    bins_df: pd.DataFrame,
    bin_col: str = "bin",
    figsize: Optional[Tuple[int, int]] = None,
    save_to: Optional[PathLike] = None,
) -> None:
    """Plot VW and EW mean returns per bin as side-by-side bar charts.

    Two subplots: equal-weighted on the left, value-weighted on the right.
    Same color convention as the line plots (blue = EW, red = VW).

    Args:
        bins_df: DataFrame with one row per bin and columns ``bin_col``,
            ``EW``, ``VW``.
        bin_col: name of the bin column. Default ``"bin"``.
        figsize: (width, height) override.
        save_to: if given, save the PNG to this path.

    Raises:
        PlotError: if required columns are missing.
    """
    required = [bin_col, "EW", "VW"]
    missing = [c for c in required if c not in bins_df.columns]
    if missing:
        raise PlotError(f"plot_decile_spread: missing columns {missing}")

    try:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize or (12, 5))
        x = np.arange(len(bins_df))

        # Equal-weighted
        ax1.bar(x, bins_df["EW"], alpha=0.8, color=plot_config.blue_hex)
        ax1.set_xticks(x)
        ax1.set_xticklabels(bins_df[bin_col].astype(str))
        ax1.set_xlabel("Quantile Bin")
        ax1.set_ylabel("Returns")
        ax1.set_title("Equal-Weighted Returns")
        ax1.grid(True, alpha=0.3)

        # Value-weighted
        ax2.bar(x, bins_df["VW"], alpha=0.8, color=plot_config.red_hex)
        ax2.set_xticks(x)
        ax2.set_xticklabels(bins_df[bin_col].astype(str))
        ax2.set_xlabel("Quantile Bin")
        ax2.set_ylabel("Returns")
        ax2.set_title("Value-Weighted Returns")
        ax2.grid(True, alpha=0.3)

        fig.tight_layout()
        _save_or_show(fig, save_to)
    except Exception as e:
        if isinstance(e, PlotError):
            raise
        raise PlotError(f"plot_decile_spread failed: {e}")


def plot_performance_comparison(
    portfolios: Dict[str, pd.DataFrame],
    date_col: str,
    ret_col: str,
    figsize: Optional[Tuple[int, int]] = None,
    title: Optional[str] = None,
    save_to: Optional[PathLike] = None,
) -> None:
    """Plot cumulative performance of multiple portfolios side-by-side.

    Args:
        portfolios: ``{name: df}`` dict, one entry per portfolio. Each
            DataFrame must contain ``date_col`` and ``ret_col``.
        date_col: name of the date column.
        ret_col: name of the return column.
        figsize: (width, height) override.
        title: plot title. Default: ``"Portfolio Performance Comparison"``.
        save_to: if given, save the PNG to this path.

    Raises:
        PlotError: if ``portfolios`` is empty or a frame is missing columns.
    """
    if not portfolios:
        raise PlotError("plot_performance_comparison: no portfolios provided")

    try:
        fig, ax = plt.subplots(figsize=figsize or plot_config.default_figsize)
        colors = plt.cm.Set1(np.linspace(0, 1, len(portfolios)))

        for (name, df), color in zip(portfolios.items(), colors):
            missing = [c for c in [date_col, ret_col] if c not in df.columns]
            if missing:
                raise PlotError(
                    f"plot_performance_comparison: portfolio '{name}' "
                    f"missing columns {missing}"
                )
            df_sorted = df.sort_values(date_col)
            cum_ret = (1 + df_sorted[ret_col]).cumprod() - 1
            ax.plot(df_sorted[date_col], cum_ret, label=name, color=color, linewidth=2)

        ax.set_xlabel(date_col.title())
        ax.set_ylabel("Cumulative Returns")
        ax.set_title(title or "Portfolio Performance Comparison")
        ax.legend()
        ax.grid(True, alpha=0.3)
        fig.tight_layout()

        _save_or_show(fig, save_to)
    except Exception as e:
        if isinstance(e, PlotError):
            raise
        raise PlotError(f"plot_performance_comparison failed: {e}")


def plot_portfolio_vs_assets(
    portfolios: Dict[str, pd.DataFrame],
    asset_curves: Dict[str, pd.DataFrame],
    date_col: str = "date",
    ret_col: str = "ret",
    figsize: Optional[Tuple[int, int]] = None,
    title: Optional[str] = None,
    save_to: Optional[PathLike] = None,
) -> None:
    """The standard replication plot: strategy portfolios + same-capital buy-and-hold assets.

    This is the plot every paper replication produces — `portfolio_vs_assets.png`
    in `results/`. Combines :func:`plot_performance_comparison` (portfolios)
    with same-capital buy-and-hold curves for the assets used in the paper
    (e.g. SPY / CRSP_VW for US equity strategies).

    Color convention (matches the rest of the utils):
    - Portfolio lines use ``plot_config.blue_hex``
    - Asset buy-and-hold lines use ``plot_config.red_hex``
    - The first portfolio (typically "Portfolio @ 0% comm") is drawn with
      a thicker line for emphasis.

    Args:
        portfolios: ``{name: df}`` dict. Each df must contain ``date_col``
            and ``ret_col``. Names like ``"Portfolio @ 0.000% comm"`` are
            drawn first / boldface.
        asset_curves: ``{name: df}`` dict of same-capital buy-and-hold
            series. Same column convention as ``portfolios``.
        date_col: name of the date column.
        ret_col: name of the return column.
        figsize: (width, height) override.
        title: plot title. Default: ``"Strategy vs Buy-and-Hold Assets"``.
        save_to: if given, save the PNG to this path.

    Raises:
        PlotError: if a portfolio or asset df is missing required columns.
    """
    if not portfolios:
        raise PlotError("plot_portfolio_vs_assets: no portfolios provided")
    if not asset_curves:
        raise PlotError("plot_portfolio_vs_assets: no asset_curves provided")

    try:
        fig, ax = plt.subplots(figsize=figsize or plot_config.default_figsize)

        # Plot asset buy-and-hold first (so they sit behind portfolio lines)
        for name, df in asset_curves.items():
            missing = [c for c in [date_col, ret_col] if c not in df.columns]
            if missing:
                raise PlotError(
                    f"plot_portfolio_vs_assets: asset '{name}' missing {missing}"
                )
            df_sorted = df.sort_values(date_col)
            cum_ret = (1 + df_sorted[ret_col]).cumprod() - 1
            ax.plot(
                df_sorted[date_col], cum_ret,
                label=name, color=plot_config.red_hex, linewidth=1.5, alpha=0.7,
            )

        # Plot portfolios. First one (typically 0% comm) is boldface.
        for i, (name, df) in enumerate(portfolios.items()):
            missing = [c for c in [date_col, ret_col] if c not in df.columns]
            if missing:
                raise PlotError(
                    f"plot_portfolio_vs_assets: portfolio '{name}' missing {missing}"
                )
            df_sorted = df.sort_values(date_col)
            cum_ret = (1 + df_sorted[ret_col]).cumprod() - 1
            ax.plot(
                df_sorted[date_col], cum_ret,
                label=name,
                color=plot_config.blue_hex,
                linewidth=3.5 if i == 0 else 2.0,
                alpha=1.0 if i == 0 else 0.85,
            )

        ax.set_xlabel(date_col.title())
        ax.set_ylabel("Cumulative Returns")
        ax.set_title(title or "Strategy vs Buy-and-Hold Assets")
        ax.legend(loc="upper left")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()

        _save_or_show(fig, save_to)
    except Exception as e:
        if isinstance(e, PlotError):
            raise
        raise PlotError(f"plot_portfolio_vs_assets failed: {e}")


def plot_decile_spread(
    bins_df: pd.DataFrame,
    bin_col: str = "bin",
    figsize: Optional[Tuple[int, int]] = None,
    save_to: Optional[PathLike] = None,
    *,
    ew_col: str = "EW",
    vw_col: str = "VW",
    agg: str = "mean",
) -> None:
    """Plot VW and EW mean returns per bin as side-by-side bar charts.

    Accepts either:
      (a) **Per-bin shape** — one row per bin with columns ``bin_col``,
          ``ew_col``, ``vw_col``. Plots directly.
      (b) **Per-date-per-bin shape** — one row per (date, bin) with
          columns including ``bin_col``, ``ew_col``, ``vw_col``. Auto-aggregates
          per the ``agg`` argument (default ``"mean"``) before plotting.

    Two subplots: equal-weighted on the left, value-weighted on the right.
    Same color convention as the line plots (blue = EW, red = VW).

    Args:
        bins_df: per-bin or per-(date, bin) DataFrame.
        bin_col: name of the bin column. Default ``"bin"``.
        ew_col, vw_col: names of the EW and VW columns. Defaults match
            :func:`utils.portfolio.bin_returns` output.
        agg: aggregation to apply when ``bins_df`` has multiple rows per
            bin (the per-date shape). Default ``"mean"``.
        figsize: (width, height) override.
        save_to: if given, save the PNG to this path.

    Raises:
        PlotError: if required columns are missing or plotting fails.
    """
    required = [bin_col, ew_col, vw_col]
    missing = [c for c in required if c not in bins_df.columns]
    if missing:
        raise PlotError(f"plot_decile_spread: missing columns {missing}")

    # Auto-aggregate if we got the per-date shape (multiple rows per bin).
    if bins_df[bin_col].duplicated().any():
        grouped = (
            bins_df.groupby(bin_col)
            .agg(**{ew_col: (ew_col, agg), vw_col: (vw_col, agg)})
            .reset_index()
        )
    else:
        grouped = bins_df

    try:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize or (12, 5))
        x = np.arange(len(grouped))

        # Equal-weighted
        ax1.bar(x, grouped[ew_col], alpha=0.8, color=plot_config.blue_hex)
        ax1.set_xticks(x)
        ax1.set_xticklabels(grouped[bin_col].astype(str))
        ax1.set_xlabel("Quantile Bin")
        ax1.set_ylabel("Returns")
        ax1.set_title("Equal-Weighted Returns")
        ax1.grid(True, alpha=0.3)

        # Value-weighted
        ax2.bar(x, grouped[vw_col], alpha=0.8, color=plot_config.red_hex)
        ax2.set_xticks(x)
        ax2.set_xticklabels(grouped[bin_col].astype(str))
        ax2.set_xlabel("Quantile Bin")
        ax2.set_ylabel("Returns")
        ax2.set_title("Value-Weighted Returns")
        ax2.grid(True, alpha=0.3)

        fig.tight_layout()
        _save_or_show(fig, save_to)
    except Exception as e:
        if isinstance(e, PlotError):
            raise
        raise PlotError(f"plot_decile_spread failed: {e}")


__all__ = [
    "plot_cumulative_returns",
    "plot_drawdown",
    "plot_decile_spread",
    "plot_performance_comparison",
    "plot_portfolio_vs_assets",
    "PlotError",
]