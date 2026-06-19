"""MAX Factor: Stocks as Lotteries — self-contained Backtrader backtest.

Strategy: long the lowest-MAX decile, short the highest-MAX decile, monthly
rebalancing.  MAX = maximum daily return over the past month (~21 trading days).

Paper: Bali, Cakici & Whitelaw (2011), "Maxing Out: Stocks as Lotteries"
       SSRN 1262416.  Monthly long-short decile-sorted portfolio on MAX.
"""

# ── matplotlib backend MUST be set before any pyplot import ─────────────────
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

import backtrader as bt

# ── Paths (relative to this file) ───────────────────────────────────────────
HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
RESULTS_DIR = HERE / "results"
KEY_PRED_DIR = RESULTS_DIR / "key_pred"
for _d in (DATA_DIR, RESULTS_DIR, KEY_PRED_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── Strategy constants ──────────────────────────────────────────────────────
SPY_SYMBOL = "SPY"
INITIAL_CASH = 100_000.0
COMMISSION_RATES = (0.0, 0.0001, 0.0005)  # 0%, 0.01%, 0.05%

# 25 large-cap US equities across diverse sectors + SPY as benchmark.
UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
    "JPM", "BAC", "WMT", "PG", "JNJ", "XOM", "CVX",
    "HD", "MCD", "KO", "PEP", "DIS", "NFLX",
    "ADBE", "CRM", "INTC", "VZ", "UNH",
]

# ── Mandatory local data cache ──────────────────────────────────────────────
def fetch_data_cached(symbol: str, start: str, end: str) -> pd.DataFrame:
    """Return OHLCV for `symbol`, fetching from cache first, network second."""
    cache_path = DATA_DIR / f"{symbol}_{start}_{end}.csv"
    if cache_path.is_file():
        df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
        if not df.empty:
            return df

    import yfinance as yf

    df = yf.download(
        symbol,
        start=start,
        end=end,
        auto_adjust=True,
        multi_level_index=False,
        progress=False,
    )
    if df is None or df.empty:
        raise ValueError(f"No data returned for {symbol} ({start}..{end})")
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df.to_csv(cache_path)
    return df


def to_feed(df: pd.DataFrame, name: str) -> bt.feeds.PandasData:
    """Build a tradable PandasData feed with finite OHLCV.

    Never pass a close-only frame for a tradable asset — market orders need a
    finite next-bar open.
    """
    out = pd.DataFrame(index=pd.to_datetime(df.index).tz_localize(None))
    close = df["Close"].astype(float).ffill()
    out["Close"] = close
    out["Open"] = (
        df["Open"].astype(float)
        if "Open" in df
        else close.shift(1).fillna(close.iloc[0])
    )
    out["High"] = (
        df["High"].astype(float)
        if "High" in df
        else pd.concat([out["Open"], close], axis=1).max(axis=1)
    )
    out["Low"] = (
        df["Low"].astype(float)
        if "Low" in df
        else pd.concat([out["Open"], close], axis=1).min(axis=1)
    )
    out["Volume"] = df["Volume"].astype(float) if "Volume" in df else 1.0
    return bt.feeds.PandasData(dataname=out, name=name)


# ── Strategy class ──────────────────────────────────────────────────────────
class MAXStrategy(bt.Strategy):
    """Monthly long-short decile portfolio sorted on Maximum Daily Return (MAX).

    At each month boundary, compute MAX (max daily return over the past ~21
    trading days) for every stock in the universe, rank cross-sectionally, go
    long the bottom decile (lowest MAX / least lottery-like), and go short the
    top decile (highest MAX / most lottery-like).  Equal-weight within each
    leg; dollar-neutral with 100% gross exposure per leg (200% total).
    """

    params = (
        ("max_window", 22),  # trading days to approximate one calendar month
        ("n_deciles", 10),
        ("min_data_bars", 10),  # minimum bars required to compute MAX
    )

    def __init__(self):
        self._last_ym = None  # (year, month) of previous bar — drives rebalance
        self.order_history: list = []

    def next(self):
        # ── Month-change detection ──────────────────────────────────────
        if len(self) <= 1:
            return
        dt = self.data.datetime.date(0)  # type: ignore[attr-defined]
        ym = (dt.year, dt.month)
        if ym == self._last_ym:
            return
        self._last_ym = ym

        pv = float(self.broker.getvalue())
        if not np.isfinite(pv) or pv <= 0:
            return

        # ── Compute MAX for each stock using previous month's daily data ─
        # We look back from bar -1 (last bar of previous month) to avoid
        # including current bar's data in the signal.
        max_vals: dict[str, float] = {}
        for d in self.datas:
            sym = d._name  # type: ignore[attr-defined]
            if sym == SPY_SYMBOL:
                continue

            # Collect past closes, skipping NaN / out-of-range
            closes = []
            for j in range(1, self.p.max_window + 2):
                try:
                    c = d.close[-j]  # type: ignore[attr-defined]
                except (IndexError, KeyError):
                    break
                if c == c and np.isfinite(c):  # not NaN
                    closes.append(c)

            if len(closes) < self.p.min_data_bars:
                continue

            # Daily returns: ret[i] = (close[i] - close[i+1]) / close[i+1]
            # closes[0] = t-1, closes[-1] = oldest
            rets = []
            for i in range(len(closes) - 1):
                if closes[i + 1] != 0:
                    rets.append((closes[i] - closes[i + 1]) / closes[i + 1])
            if not rets:
                continue
            max_vals[sym] = max(rets)

        # ── Cross-sectional ranking ─────────────────────────────────────
        if len(max_vals) < 10:
            return  # insufficient stocks this month

        ranked = sorted(max_vals.items(), key=lambda x: x[1])  # ascending MAX
        n_stocks = len(ranked)
        n_per_decile = max(1, n_stocks // self.p.n_deciles)

        long_syms = {sym for sym, _ in ranked[:n_per_decile]}
        short_syms = {sym for sym, _ in ranked[-n_per_decile:]}

        # ── Generate orders (translate target weight → delta size) ──────
        # Never pass a weight directly as size — compute target_size first.
        for d in self.datas:
            sym = d._name  # type: ignore[attr-defined]
            if sym == SPY_SYMBOL:
                continue

            price = d.close[0]  # type: ignore[attr-defined]
            if not (np.isfinite(price) and price > 0):
                continue

            # Determine target weight
            if sym in long_syms:
                target_w = 1.0 / len(long_syms)
            elif sym in short_syms:
                target_w = -1.0 / len(short_syms)
            else:
                target_w = 0.0

            target_size = int((target_w * pv) / price)
            current_size = int(self.getposition(d).size)  # type: ignore[attr-defined]
            delta = target_size - current_size

            if delta > 0:
                self.buy(data=d, size=delta)
            elif delta < 0:
                self.sell(data=d, size=abs(delta))

    def notify_order(self, order):
        if order.status in (order.Completed,):
            self.order_history.append(
                {
                    "date": self.data.datetime.date(0).isoformat(),  # type: ignore[attr-defined]
                    "symbol": order.data._name,  # type: ignore[attr-defined]
                    "type": "buy" if order.isbuy() else "sell",
                    "size": order.executed.size,
                    "price": order.executed.price,
                    "value": order.executed.value,
                    "commission": order.executed.comm,
                }
            )


# ── Single backtest run + metric extraction ─────────────────────────────────
def run_once(feeds, commission: float):
    """Run one backtest at a given commission rate.

    Returns (metrics, value_series, strategy_instance).
    """
    cerebro = bt.Cerebro()
    for feed in feeds:
        cerebro.adddata(feed)
    cerebro.addstrategy(MAXStrategy)
    cerebro.broker.setcash(INITIAL_CASH)
    cerebro.broker.setcommission(commission=commission)

    cerebro.addanalyzer(
        bt.analyzers.SharpeRatio,
        _name="sharpe",
        riskfreerate=0.0,
        annualize=True,
    )
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.SQN, _name="sqn")
    cerebro.addanalyzer(bt.analyzers.AnnualReturn, _name="annual")
    cerebro.addobserver(bt.observers.Value)

    results = cerebro.run()
    strat = results[0]

    # Pull per-bar portfolio value series from the Value observer.
    _n = len(strat)
    value_series = pd.Series(
        list(strat.observers.value.get(size=_n)),  # type: ignore[attr-defined]
        index=[bt.num2date(x) for x in strat.data.datetime.get(size=_n)],  # type: ignore[attr-defined]
    )
    value_series = value_series[np.isfinite(value_series.values)]

    final_value = float(cerebro.broker.getvalue())
    if not np.isfinite(final_value):
        raise ValueError("Non-finite final portfolio value — strategy is broken")

    sharpe = strat.analyzers.sharpe.get_analysis().get("sharperatio")
    dd = strat.analyzers.drawdown.get_analysis()
    trades = strat.analyzers.trades.get_analysis()
    rets = strat.analyzers.returns.get_analysis()
    sqn_a = strat.analyzers.sqn.get_analysis()

    total_closed = trades.get("total", {}).get("closed", 0)
    metrics = {
        "commission": commission,
        "final_value": round(final_value, 2),
        "return_value": round(final_value, 2),
        "total_return": round((final_value / INITIAL_CASH - 1) * 100, 2),
        "sharpe_ratio": round(sharpe, 4) if sharpe is not None else None,
        "max_drawdown_pct": round(dd.get("max", {}).get("drawdown", 0.0), 2),
        "num_trades": total_closed,
        "won_trades": trades.get("won", {}).get("total", 0),
        "lost_trades": trades.get("lost", {}).get("total", 0),
        "normalized_annual_return": round(rets.get("rnorm100", 0), 2),
        "sqn": round(sqn_a.get("sqn", 0), 4),
    }
    if total_closed > 0:
        won_count = trades.get("won", {}).get("total", 0)
        metrics["win_rate"] = round(won_count / total_closed * 100, 2)
        gross_profit = trades.get("won", {}).get("pnl", {}).get("total", 0)
        gross_loss = abs(trades.get("lost", {}).get("pnl", {}).get("total", 0))
        metrics["profit_factor"] = (
            round(gross_profit / gross_loss, 2) if gross_loss > 0 else None
        )
    else:
        metrics["win_rate"] = None
        metrics["profit_factor"] = None

    return metrics, value_series, strat


# ── Portfolio-vs-assets chart (required output contract) ────────────────────
def plot_portfolio_vs_assets(value_by_commission, asset_prices: dict) -> None:
    """One image: 3 commission portfolio curves + every asset buy-and-hold.

    SPY and portfolio curves are boldface; all asset curves are distinguishable
    colours with legend labels.
    """
    fig, ax = plt.subplots(figsize=(12, 7))
    combined = pd.DataFrame()

    # Buy-and-hold curves: normalise each asset to the same starting capital.
    for sym, prices in asset_prices.items():
        s = prices.astype(float).ffill()
        bh = INITIAL_CASH * (s / s.iloc[0])
        is_spy = sym.upper() == SPY_SYMBOL.upper()
        ax.plot(
            bh.index,
            bh.values,
            label=f"{sym} (B&H)",
            linewidth=2.6 if is_spy else 1.0,
            alpha=1.0 if is_spy else 0.7,
        )
        combined[f"{sym}_bh"] = bh

    # Portfolio curves at each commission — boldface.
    for comm, vseries in value_by_commission.items():
        label = f"Portfolio @ {comm * 100:.2f}% comm"
        ax.plot(vseries.index, vseries.values, label=label, linewidth=2.6)
        combined[f"portfolio_comm_{comm}"] = vseries

    ax.set_title(
        "MAX Factor — Portfolio vs Same-Capital Buy-and-Hold\n"
        "(SPY + portfolio boldface)"
    )
    ax.set_xlabel("Date")
    ax.set_ylabel("Account value ($)")
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "portfolio_vs_assets.png", dpi=120)
    plt.close(fig)
    combined.to_csv(RESULTS_DIR / "portfolio_vs_assets.csv")


# ── Key-factor plots ────────────────────────────────────────────────────────
def plot_key_factor(name: str, series: pd.Series) -> None:
    """One CSV + PNG per key observable factor, under results/key_pred/."""
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(series.index, series.values, linewidth=1.2)
    ax.set_title(f"Key factor: {name}")
    fig.tight_layout()
    fig.savefig(KEY_PRED_DIR / f"{name}.png", dpi=120)
    plt.close(fig)
    series.to_frame(name).to_csv(KEY_PRED_DIR / f"{name}.csv")


def compute_max_factor_series(
    raw: dict[str, pd.DataFrame],
) -> dict[str, pd.Series]:
    """Compute MAX factor time series from raw price data.

    For each month-end, compute MAX for every stock (max daily return over the
    past ~21 trading days), then average the bottom and top deciles.  This is
    independent of the Backtrader backtest — it runs on the raw data directly.

    Returns dict with keys: 'max_bottom_decile_avg', 'max_top_decile_avg',
    'max_spread'.
    """
    # Build a panel of daily returns for all stocks.
    returns_panel = {}
    for sym, df in raw.items():
        if sym == SPY_SYMBOL:
            continue
        close = df["Close"].astype(float).ffill()
        rets = close.pct_change().dropna()
        if len(rets) > 0:
            returns_panel[sym] = rets

    if not returns_panel:
        return {}

    # Resample to monthly: for each month, compute MAX per stock.
    monthly_records = []
    all_rets = pd.DataFrame(returns_panel)
    # Group by calendar month
    grouped = all_rets.groupby(
        [all_rets.index.year, all_rets.index.month]
    )

    for (year, month), group in grouped:
        if len(group) < 5:
            continue
        max_per_stock = group.max()  # max daily return in this month for each stock
        valid = max_per_stock.dropna()
        if len(valid) < 10:
            continue
        sorted_vals = valid.sort_values()
        n = len(sorted_vals)
        n_extreme = max(1, n // 10)
        avg_bottom = sorted_vals.iloc[:n_extreme].mean()
        avg_top = sorted_vals.iloc[-n_extreme:].mean()

        monthly_records.append(
            {
                "date": pd.Timestamp(year=int(year), month=int(month), day=1),
                "max_bottom_decile_avg": avg_bottom,
                "max_top_decile_avg": avg_top,
                "max_spread": avg_top - avg_bottom,
            }
        )

    if not monthly_records:
        return {}

    df_factor = pd.DataFrame(monthly_records).set_index("date").sort_index()
    return {
        "max_bottom_decile_avg": df_factor["max_bottom_decile_avg"],
        "max_top_decile_avg": df_factor["max_top_decile_avg"],
        "max_spread": df_factor["max_spread"],
    }


# ── Entry point ─────────────────────────────────────────────────────────────
def main() -> None:
    print("[PROGRESS] spec2code/data — downloading universe + SPY")
    start, end = "2015-01-01", "2025-01-02"  # end exclusive → through 2024

    all_symbols = [SPY_SYMBOL] + UNIVERSE
    raw: dict[str, pd.DataFrame] = {}
    failed_symbols: list[str] = []
    for sym in all_symbols:
        try:
            raw[sym] = fetch_data_cached(sym, start, end)
        except Exception as e:
            print(f"  [WARN] {sym}: {e}")
            failed_symbols.append(sym)

    if SPY_SYMBOL not in raw:
        raise RuntimeError("SPY data is required but could not be fetched")

    traded_symbols = [s for s in UNIVERSE if s in raw]
    print(
        f"  Universe: {len(traded_symbols)} stocks + SPY  "
        f"(failed: {len(failed_symbols)}/{len(UNIVERSE)})"
    )
    if len(traded_symbols) < 10:
        raise RuntimeError(
            f"Only {len(traded_symbols)} stocks available — need at least 10"
        )

    # Prepare asset price series for the portfolio-vs-assets chart.
    asset_prices = {
        sym: df["Close"] for sym, df in raw.items() if sym in traded_symbols + [SPY_SYMBOL]
    }

    # ── Commission sweep ─────────────────────────────────────────────────
    print("[PROGRESS] spec2code/backtest — running 3-commission sweep")
    value_by_commission: dict[float, pd.Series] = {}
    all_metrics: list[dict] = []

    for comm in COMMISSION_RATES:
        feeds = [to_feed(raw[sym], sym) for sym in [SPY_SYMBOL] + traded_symbols]
        metrics, vseries, strat = run_once(feeds, comm)
        value_by_commission[comm] = vseries
        all_metrics.append(metrics)
        print(
            f"  comm={comm * 100:.2f}%  "
            f"return={metrics['total_return']:+.1f}%  "
            f"sharpe={metrics['sharpe_ratio']}  "
            f"maxDD={metrics['max_drawdown_pct']:.1f}%  "
            f"trades={metrics['num_trades']}"
        )

    # ── Required artifacts ───────────────────────────────────────────────
    print("[PROGRESS] spec2code/artifacts — generating plots and reports")

    # Portfolio-vs-assets chart (required).
    plot_portfolio_vs_assets(value_by_commission, asset_prices)
    print(f"[ARTIFACT] results/portfolio_vs_assets.png — portfolio vs B&H chart")
    print(f"[ARTIFACT] results/portfolio_vs_assets.csv — portfolio vs B&H data")

    # Metrics JSON.
    (RESULTS_DIR / "metrics.json").write_text(
        json.dumps(all_metrics, indent=2)
    )
    print(f"[ARTIFACT] results/metrics.json — metrics for all commission rates")

    # Key-factor plots: MAX bottom-decile avg, top-decile avg, spread.
    factor_series = compute_max_factor_series(raw)
    for name, series in factor_series.items():
        plot_key_factor(name, series)
        print(f"[ARTIFACT] results/key_pred/{name}.png — factor chart")
        print(f"[ARTIFACT] results/key_pred/{name}.csv — factor data")

    # Diagnosis report.
    best = all_metrics[0]  # 0% commission as baseline
    diag_lines = [
        "# Diagnosis Report — MAX Factor Strategy",
        "",
        f"**Strategy**: MAX Factor — Stocks as Lotteries (SSRN 1262416)",
        f"**Data period**: {start} → 2024-12-31",
        f"**Universe**: {len(traded_symbols)} US large-cap stocks + SPY benchmark",
        f"**Rebalancing**: Monthly, at month-boundary open",
        f"**Position sizing**: Equal-weight within deciles, dollar-neutral",
        f"**Risk management**: None (matches paper design)",
        "",
        "## Backtest Results (0% commission)",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Final value | \\${best['final_value']:,.2f} |",
        f"| Total return | {best['total_return']:+.2f}% |",
        f"| Sharpe ratio | {best['sharpe_ratio']} |",
        f"| Max drawdown | {best['max_drawdown_pct']:.2f}% |",
        f"| SQN | {best['sqn']} |",
        f"| Number of trades | {best['num_trades']} |",
        f"| Win rate | {best.get('win_rate', 'N/A')}% |",
        f"| Profit factor | {best.get('profit_factor', 'N/A')} |",
        "",
        "## Paper Expected Performance (reference only)",
        "",
        "| Metric | Paper Value | Notes |",
        "|--------|-------------|-------|",
        "| Value-weighted raw return (L−H MAX) | −1.03% / month | July 1962 – Dec 2005 |",
        "| Four-factor alpha (L−H MAX) | −1.18% / month | Fama-French + momentum |",
        "| Fama-MacBeth slope on MAX | −0.0637 (t=−6.16) | Cross-sectional regression |",
        "",
        "## Deviation Analysis",
        "",
        "- **Different universe**: Paper uses full CRSP (NYSE/AMEX/NASDAQ); this",
        "  backtest uses 25 S&P 500 large-cap stocks — MAX spreads are narrower in",
        "  large caps.",
        "- **Different period**: Paper: 1962–2005; backtest: 2015–2024. The MAX",
        "  premium may have decayed post-publication.",
        "- **No short-constituent costs**: Paper reports academic portfolio returns",
        "  without short-selling fees, borrow costs, or execution slippage.",
        "- **Survivorship bias**: Current S&P 500 constituents have survived; CRSP",
        "  includes delisted stocks.",
        "",
        "## Generated files",
        "",
        "- `strategy_1.py` — self-contained strategy code",
        "- `spec.json` — strategy specification (with HITL resolutions)",
        "- `results/metrics.json` — backtest metrics for all commission rates",
        "- `results/portfolio_vs_assets.png` / `.csv` — portfolio vs B&H comparison",
        "- `results/key_pred/` — MAX factor time-series plots",
        "- `data/` — local cached price data",
    ]
    report = "\n".join(diag_lines)
    (RESULTS_DIR / "diagnosis_report.md").write_text(report)
    print(f"[ARTIFACT] results/diagnosis_report.md — diagnosis report")

    # Print final summary.
    print("\n" + "=" * 60)
    print("Backtest complete.  Summary (0% commission):")
    print(json.dumps(best, indent=2))
    print("=" * 60)


if __name__ == "__main__":
    main()
