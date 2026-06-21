"""Authoritative, copy-into-place template for a self-contained x2strategy
backtest runner (ClickHouse data fetch + Cerebro + analyzers + headless
visualization).

WHY THIS FILE EXISTS
--------------------
Letting the agent write the runner / plotting block from scratch produces high
variance: charts go missing, the commission sweep is skipped, SPY is not
highlighted, or plots try to open a GUI on a headless server. This template
pins the structural parts so the SKILL.md / spec2code.md output contract holds
every run.

HOW TO USE
----------
Do NOT import this module. COPY the relevant function bodies into the generated
`strategy.py` and adapt only the marked spots:
  - `fetch_data_cached`      : adapt the ClickHouse table/columns from
                                data_match_report.json
  - `MyStrategy`             : fill __init__/next from the spec (see
                                spec2code.md §4/§6/§7)
  - the universe / SPY symbol: set from the spec

The data source is ALWAYS ClickHouse via HTTP.  Connection details are
read from environment variables (CLICKHOUSE_HOST, CLICKHOUSE_PORT,
CLICKHOUSE_USER, CLICKHOUSE_PASSWORD).  Adapt `fetch_data_cached` to
query the correct table and columns for the paper.

Everything else — the local cache, the analyzer `_name` strings, the headless
matplotlib backend, the three-commission sweep, and the portfolio-vs-assets
chart with SPY + portfolio boldface — is the output contract. Keep it.

Required charts under results/ (see SKILL.md "Output Paths"):
  - results/portfolio_vs_assets.png / .csv  (3 commission curves + every asset
    buy-and-hold; SPY and portfolio boldface; distinguishable colors + legend)
  - results/key_pred/<factor>.png / .csv    (one per key observable factor)
"""

# ── Imports ──────────────────────────────────────────────────────────────────
# matplotlib backend MUST be set before any pyplot import (headless servers).
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import backtrader as bt

# RESULTS_DIR / DATA_DIR are resolved relative to the strategy file so the run
# is portable across machines. Adapt only if the user confirmed a custom path.
HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
RESULTS_DIR = HERE / "results"
KEY_PRED_DIR = RESULTS_DIR / "key_pred"
for _d in (DATA_DIR, RESULTS_DIR, KEY_PRED_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Set from the spec. SPY is the mandatory US-equity baseline (boldface in plots).
SPY_SYMBOL = "SPY"
INITIAL_CASH = 100_000.0
# The three commission rates the portfolio-vs-assets sweep must compare.
COMMISSION_RATES = (0.0, 0.0001, 0.0005)

# ── Mandatory local data cache ────────────────────────────────────────────────
# Every ClickHouse fetch is cached as a CSV and reused on later runs. Never hit
# the network when a valid cache file already exists.
# Connection details are read from environment variables.
# Adapt the table name, columns, and WHERE clause to the paper's data needs
# using data_match_report.json.

def _clickhouse_query(query: str) -> list[tuple]:
    """Run a single ClickHouse query via native driver and return rows."""
    host = os.getenv("CLICKHOUSE_HOST", "localhost")
    port = int(os.getenv("CLICKHOUSE_PORT", "9000"))
    user = os.getenv("CLICKHOUSE_USER", "default")
    pw = os.getenv("CLICKHOUSE_PASSWORD", "")
    from clickhouse_driver import Client
    client = Client(host=host, port=port, user=user, password=pw)
    return client.execute(query)


def fetch_data_cached(table: str, columns: list[str], start: str,
                      end: str, extra_where: str = "",
                      date_col: str = "date") -> pd.DataFrame:
    """Return data from ClickHouse, fetching from cache first, network second.

    ``table`` is a fully-qualified name (e.g. ``crsp.dsf``).
    ``columns`` are the SQL column names to select.
    ``extra_where`` is an optional additional WHERE clause (e.g. share codes).
    """
    cols_str = ", ".join(columns)
    cache_key = f"{table.replace('.', '_')}_{start}_{end}"
    if extra_where:
        cache_key += "_filtered"
    cache_path = DATA_DIR / f"{cache_key}.csv"
    if cache_path.is_file():
        df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
        if not df.empty:
            return df

    # ── adapt this block to the paper's match report ──
    where = f"{date_col} >= '{start}' AND {date_col} < '{end}'"
    if extra_where:
        where += f" AND {extra_where}"
    query = (
        f"SELECT {cols_str} FROM {table} "
        f"WHERE {where} "
        f"ORDER BY {date_col}"
    )
    rows = _clickhouse_query(query)
    df = pd.DataFrame(rows, columns=columns)
    if extra_where:
        pass  # filters applied in WHERE clause above
    if df is None or df.empty:
        raise ValueError(f"No data returned for {table} ({start}..{end})")
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.set_index(date_col)
    df.to_csv(cache_path)
    return df


def to_feed(df: pd.DataFrame, name: str) -> bt.feeds.PandasData:
    """Build a tradable PandasData feed with finite OHLCV.

    Never pass a close-only frame with open/high/low=None for a tradable asset:
    market orders need a finite next-bar open, or fills and broker value go NaN.
    """
    out = pd.DataFrame(index=pd.to_datetime(df.index).tz_localize(None))
    close = df["Close"].astype(float).ffill()
    out["Close"] = close
    out["Open"] = df["Open"].astype(float) if "Open" in df else close.shift(1).fillna(close.iloc[0])
    out["High"] = df["High"].astype(float) if "High" in df else pd.concat([out["Open"], close], axis=1).max(axis=1)
    out["Low"] = df["Low"].astype(float) if "Low" in df else pd.concat([out["Open"], close], axis=1).min(axis=1)
    out["Volume"] = df["Volume"].astype(float) if "Volume" in df else 1.0
    return bt.feeds.PandasData(dataname=out, name=name)


# ── Strategy class (fill from the spec — see spec2code.md §4/§6/§7) ────────────
class MyStrategy(bt.Strategy):
    params = (("fetched_data", None),)

    def __init__(self):
        # NEVER fetch data here. Receive it via params.
        self.fetched_data = self.p.fetched_data
        self.order_history = []
        self.peak_value = 0.0
        # Initialise indicators / signal state from the spec here.

    def next(self):
        current_date = self.data.datetime.datetime(0).strftime("%Y-%m-%d")
        _v = self.broker.getvalue()
        pv = float(_v) if _v is not None else 0.0
        self.peak_value = max(self.peak_value, pv)
        # Compute `sized: Dict[str, float]` (ticker -> target weight) from the
        # spec path, then translate to delta orders (never pass weight as size):
        #   target_size = (target_w * pv) / current_price
        #   trade target_size - current_position_size
        # See spec2code.md §4/§6/§7. Do not leave this as a placeholder.


# ── Single backtest run + metric extraction ──────────────────────────────────
def run_once(feeds, commission: float):
    """Run one backtest at a given commission. Returns (metrics, value_series).

    Analyzer `_name` strings are load-bearing — keep them. Sharpe is configured
    explicitly (riskfreerate=0.0, annualize) rather than left at defaults.
    """
    cerebro = bt.Cerebro()
    for feed in feeds:
        cerebro.adddata(feed)
    cerebro.addstrategy(MyStrategy, fetched_data={f._name: f for f in feeds})
    cerebro.broker.setcash(INITIAL_CASH)
    cerebro.broker.setcommission(commission=commission)

    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        riskfreerate=0.0, annualize=True)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addobserver(bt.observers.Value)

    results = cerebro.run()
    strat = results[0]

    # Pull the per-bar portfolio value series from the Value observer.
    # Use .get(size=len(strat)) — NOT list(observer.array): with multiple data
    # feeds the raw .array length is n*feed_count, which mismatches the date
    # index and raises ValueError. .get(size=len(strat)) returns the n values.
    _n = len(strat)
    value_series = pd.Series(
        list(strat.observers.value.get(size=_n)),
        index=[bt.num2date(x) for x in strat.data.datetime.get(size=_n)],
    )
    value_series = value_series[np.isfinite(value_series.values)]

    final_value = float(cerebro.broker.getvalue())
    if not np.isfinite(final_value):
        raise ValueError("Non-finite final portfolio value — strategy is broken")

    sharpe = strat.analyzers.sharpe.get_analysis().get("sharperatio")
    dd = strat.analyzers.drawdown.get_analysis()
    trades = strat.analyzers.trades.get_analysis()  # AutoOrderedDict — use .get
    metrics = {
        "commission": commission,
        "final_value": round(final_value, 2),
        "return_value": round(final_value, 2),
        "total_return": round((final_value / INITIAL_CASH - 1) * 100, 2),
        "sharpe_ratio": round(sharpe, 4) if sharpe is not None else None,
        "max_drawdown_pct": round(dd.get("max", {}).get("drawdown", 0.0), 2),
        "num_trades": trades.get("total", {}).get("closed", 0),
    }
    return metrics, value_series


# ── Portfolio-vs-assets chart (the required output contract) ──────────────────
def plot_portfolio_vs_assets(value_by_commission, asset_prices: dict) -> None:
    """One image: 3 commission portfolio curves + every asset buy-and-hold.

    Contract:
      - all three commission portfolio curves on one axis;
      - one same-capital buy-and-hold curve per used asset, distinguishable
        colors + legend labels;
      - SPY and the portfolio curves are BOLDFACE (thicker linewidth);
      - written to results/portfolio_vs_assets.png and .csv.
    """
    fig, ax = plt.subplots(figsize=(12, 7))
    combined = pd.DataFrame()

    # Buy-and-hold curves: normalise each asset to the same starting capital.
    for sym, prices in asset_prices.items():
        s = prices.astype(float).ffill()
        bh = INITIAL_CASH * (s / s.iloc[0])
        is_spy = sym.upper() == SPY_SYMBOL.upper()
        ax.plot(bh.index, bh.values, label=f"{sym} (B&H)",
                linewidth=2.6 if is_spy else 1.0,
                alpha=1.0 if is_spy else 0.7)
        combined[f"{sym}_bh"] = bh

    # Portfolio curves at each commission — boldface.
    for comm, vseries in value_by_commission.items():
        label = f"Portfolio @ {comm*100:.2f}% comm"
        ax.plot(vseries.index, vseries.values, label=label, linewidth=2.6)
        combined[f"portfolio_comm_{comm}"] = vseries

    ax.set_title("Portfolio vs Same-Capital Buy-and-Hold (SPY + portfolio boldface)")
    ax.set_xlabel("Date")
    ax.set_ylabel("Account value")
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "portfolio_vs_assets.png", dpi=120)
    plt.close(fig)
    combined.to_csv(RESULTS_DIR / "portfolio_vs_assets.csv")


def plot_key_factor(name: str, series: pd.Series) -> None:
    """One CSV + PNG per key observable factor, under results/key_pred/."""
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(series.index, series.values, linewidth=1.2)
    ax.set_title(f"Key factor: {name}")
    fig.tight_layout()
    fig.savefig(KEY_PRED_DIR / f"{name}.png", dpi=120)
    plt.close(fig)
    series.to_frame(name).to_csv(KEY_PRED_DIR / f"{name}.csv")


# ── Entry point ───────────────────────────────────────────────────────────────
def main() -> None:
    # 1. Resolve universe + dates from the spec; SPY must be included for US equity.
    universe = [SPY_SYMBOL]          # extend from the spec
    start, end = "2015-01-01", "2024-01-02"

    raw = {sym: fetch_data_cached(sym, start, end) for sym in universe}
    asset_prices = {sym: df["Close"] for sym, df in raw.items()}

    # 2. Run the commission sweep on the same feeds shape.
    value_by_commission = {}
    all_metrics = []
    for comm in COMMISSION_RATES:
        feeds = [to_feed(raw[sym], sym) for sym in universe]
        metrics, vseries = run_once(feeds, comm)
        value_by_commission[comm] = vseries
        all_metrics.append(metrics)

    # 3. Required artifacts.
    plot_portfolio_vs_assets(value_by_commission, asset_prices)
    (RESULTS_DIR / "metrics.json").write_text(json.dumps(all_metrics, indent=2))
    print(json.dumps(all_metrics, indent=2))


if __name__ == "__main__":
    main()
