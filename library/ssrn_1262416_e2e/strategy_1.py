"""MAX Effect: Stocks as Lotteries — Long-Short Cross-Sectional Strategy.

Implements Bali, Cakici & Whitelaw (2011) "Maxing Out: Stocks as Lotteries
and the Cross-Section of Expected Returns."

Core trade: at each month-end, sort stocks by MAX (maximum daily return over
the past month), go long the lowest-MAX decile, short the highest-MAX decile,
value-weighted within each decile. Rebalance monthly.

Data source: ClickHouse (crsp_202501.dsf, crsp_202501.dsi).
Match report: data_match_report.json.
Spec: spec.json.
"""

# ── Imports ──────────────────────────────────────────────────────────────────
# matplotlib backend MUST be set before any pyplot import (headless servers).
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import io
import json
import os
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
import backtrader as bt

# ── Paths ──
HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
RESULTS_DIR = HERE / "results"
KEY_PRED_DIR = RESULTS_DIR / "key_pred"
for _d in (DATA_DIR, RESULTS_DIR, KEY_PRED_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── Constants ──
SPY_SYMBOL = "SPY"
INITIAL_CASH = 100_000.0
COMMISSION_RATES = (0.0, 0.0001, 0.0005)

# ── ClickHouse config (from .env via paper2spec.config) ──
def _load_ch_config():
    """Load ClickHouse config from .env, falling back to env vars.

    The .env CLICKHOUSE_PORT may specify the native TCP port (9000).
    For HTTP queries we need port 8123.  If the configured port looks
    like a native port (9000, 9440), try HTTP on the standard 8123 as
    well and use whichever responds.
    """
    try:
        _proj = Path(__file__).resolve().parent.parent.parent
        if str(_proj) not in sys.path:
            sys.path.insert(0, str(_proj))
        from paper2spec.config import get_clickhouse_config
        cfg = get_clickhouse_config()
    except Exception:
        # Fallback: try dotenv directly
        try:
            from dotenv import load_dotenv
            _env_path = Path(__file__).resolve().parent.parent.parent / ".env"
            load_dotenv(_env_path, override=False)
        except ImportError:
            pass
        cfg = {
            "host": os.getenv("CLICKHOUSE_HOST", "localhost"),
            "port": os.getenv("CLICKHOUSE_PORT", "8123"),
            "user": os.getenv("CLICKHOUSE_USER", "default"),
            "password": os.getenv("CLICKHOUSE_PASSWORD", ""),
            "database": os.getenv("CLICKHOUSE_DATABASE", "default"),
        }

    # If the configured port looks like native TCP (9000-range), also try HTTP port
    _native_ports = {"9000", "9440"}
    if str(cfg.get("port", "")) in _native_ports:
        cfg["_http_port"] = "8123"
        cfg["_native_port"] = cfg["port"]
    return cfg

_ch_cfg = _load_ch_config()
CH_HOST = _ch_cfg["host"]
# Prefer HTTP port, fall back to configured port
CH_PORT = _ch_cfg.get("_http_port", _ch_cfg.get("port", "8123"))
CH_USER = _ch_cfg["user"]
CH_PASSWORD = _ch_cfg["password"]
CH_DATABASE = _ch_cfg.get("database", "default")

# Tables from data_match_report.json
DSF_TABLE = "crsp_202501.dsf"   # Daily Stock File: date, permno, prc, ret, shrout, vol, openprc
MSF_TABLE = "crsp_202501.msf"   # Monthly Stock File: same columns, monthly aggregation
DSI_TABLE = "crsp_202501.dsi"   # Daily Stock Index: date, vwretd

# Backtest period (paper covers 1962-2005; extend to available data)
BACKTEST_START = "2000-01-01"
BACKTEST_END = "2024-12-31"

# Universe: number of largest stocks by market cap to include (memory constraint)
N_LARGEST = 3000


# ═══════════════════════════════════════════════════════════════════════════════
# Data Fetching
# ═══════════════════════════════════════════════════════════════════════════════

def _clickhouse_query(query: str) -> bytes:
    """Run a single ClickHouse query via HTTP and return raw response bytes."""
    encoded = urllib.request.quote(query)
    url = (
        f"http://{CH_HOST}:{CH_PORT}/?"
        f"user={CH_USER}&password={CH_PASSWORD}&database={CH_DATABASE}"
        f"&query={encoded}"
    )
    try:
        return urllib.request.urlopen(url, timeout=300).read()
    except Exception as e:
        print(f"[ERROR] ClickHouse query failed: {e}", file=sys.stderr)
        print(f"  Host: {CH_HOST}:{CH_PORT}, DB: {CH_DATABASE}, Query: {query[:200]}...", file=sys.stderr)
        raise


def fetch_daily_crsp(start: str, end: str) -> pd.DataFrame:
    """Fetch daily stock data from crsp_202501.dsf, with caching.

    Returns DataFrame with columns: date, permno, prc, ret, shrout, vol
    Sorted by date, permno. Indexed by date.
    """
    cache_path = DATA_DIR / f"crsp_daily_{start}_{end}.parquet"
    if cache_path.is_file():
        df = pd.read_parquet(cache_path)
        if not df.empty:
            print(f"[CACHE] Loaded daily CRSP: {len(df):,} rows from {cache_path}")
            return df

    # Fetch in yearly chunks to avoid memory issues on massive queries
    dfs = []
    for year in range(int(start[:4]), int(end[:4]) + 1):
        ystart = f"{year}-01-01"
        yend = f"{year + 1}-01-01"
        chunk_path = DATA_DIR / f"crsp_daily_{ystart}_{year}.parquet"

        if chunk_path.is_file():
            chunk = pd.read_parquet(chunk_path)
            if not chunk.empty:
                dfs.append(chunk)
                continue

        cols = "date, permno, prc, ret, shrout, vol, openprc"
        where = f"date >= '{ystart}' AND date < '{yend}'"
        # Filter: require valid prc, shrout, and ret (not null for return computation)
        where += " AND prc IS NOT NULL AND shrout IS NOT NULL AND shrout > 0"
        query = (
            f"SELECT {cols} FROM {DSF_TABLE} "
            f"WHERE {where} "
            f"ORDER BY date, permno "
            f"FORMAT TabSeparatedWithNames"
        )
        try:
            raw = _clickhouse_query(query)
            chunk = pd.read_csv(
                io.StringIO(raw.decode("utf-8")),
                sep="\t",
                parse_dates=["date"],
            )
            if chunk is not None and not chunk.empty:
                chunk.to_parquet(chunk_path, index=False)
                dfs.append(chunk)
                print(f"[FETCH] Year {year}: {len(chunk):,} rows")
        except Exception as e:
            print(f"[WARN] Year {year} failed: {e}", file=sys.stderr)
            continue

    if not dfs:
        raise ValueError(f"No daily CRSP data for {start}..{end}")

    df = pd.concat(dfs, ignore_index=True)
    df = df.sort_values(["date", "permno"]).reset_index(drop=True)
    df.to_parquet(cache_path, index=False)
    print(f"[FETCH] Saved daily CRSP: {len(df):,} rows to {cache_path}")
    return df


def fetch_market_index(start: str, end: str) -> pd.DataFrame:
    """Fetch daily market index (CRSP value-weighted) from crsp_202501.dsi."""
    cache_path = DATA_DIR / f"crsp_dsi_{start}_{end}.parquet"
    if cache_path.is_file():
        df = pd.read_parquet(cache_path)
        if not df.empty:
            return df

    query = (
        f"SELECT date, vwretd FROM {DSI_TABLE} "
        f"WHERE date >= '{start}' AND date < '{end}' "
        f"ORDER BY date "
        f"FORMAT TabSeparatedWithNames"
    )
    raw = _clickhouse_query(query)
    df = pd.read_csv(io.StringIO(raw.decode("utf-8")), sep="\t", parse_dates=["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df.to_parquet(cache_path, index=False)
    print(f"[FETCH] Market index: {len(df):,} rows")
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# Portfolio-Level Price Series Construction (from returns)
# ═══════════════════════════════════════════════════════════════════════════════

def returns_to_ohlcv(dates: pd.DatetimeIndex, returns: np.ndarray,
                     name: str) -> pd.DataFrame:
    """Convert a daily return series into synthetic OHLCV DataFrame.

    Uses cumulative return starting from 1.0 as the 'Close' price.
    """
    cumret = np.cumprod(1.0 + np.nan_to_num(returns, nan=0.0))
    close = pd.Series(cumret, index=dates, name="Close").astype(float)
    close = close.replace(0.0, np.nan).ffill()
    if close.iloc[0] == 0 or np.isnan(close.iloc[0]):
        close.iloc[0] = 1.0

    out = pd.DataFrame(index=pd.to_datetime(dates).tz_localize(None))
    out["Close"] = close.values
    out["Open"] = close.shift(1).fillna(close.iloc[0]).values
    out["High"] = np.maximum(out["Open"], out["Close"])
    out["Low"] = np.minimum(out["Open"], out["Close"])
    out["Volume"] = 1.0
    return out


def to_feed(df: pd.DataFrame, name: str) -> bt.feeds.PandasData:
    """Build a tradable PandasData feed with finite OHLCV."""
    out = pd.DataFrame(index=pd.to_datetime(df.index).tz_localize(None))
    close = df["Close"].astype(float).ffill()
    out["Close"] = close
    out["Open"] = df["Open"].astype(float) if "Open" in df else close.shift(1).fillna(close.iloc[0])
    out["High"] = df["High"].astype(float) if "High" in df else pd.concat([out["Open"], close], axis=1).max(axis=1)
    out["Low"] = df["Low"].astype(float) if "Low" in df else pd.concat([out["Open"], close], axis=1).min(axis=1)
    out["Volume"] = df["Volume"].astype(float) if "Volume" in df else 1.0
    return bt.feeds.PandasData(dataname=out, name=name)


# ═══════════════════════════════════════════════════════════════════════════════
# Signal Construction: MAX, Deciles, Value-Weighted Portfolio Returns
# ═══════════════════════════════════════════════════════════════════════════════

def compute_max_signal(daily: pd.DataFrame) -> pd.DataFrame:
    """Compute MAX signal (max daily return in past calendar month) per stock.

    Parameters
    ----------
    daily : DataFrame with columns [date, permno, ret, prc, shrout]

    Returns
    -------
    DataFrame with columns [date (month-end), permno, max_ret, mcap]
      where date is the last trading day of each month.
    """
    df = daily.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna(subset=["ret", "prc", "shrout"])
    df["ret"] = df["ret"].astype(float)
    df["prc"] = df["prc"].astype(float).abs()
    df["shrout"] = df["shrout"].astype(float).abs()
    df["mcap"] = df["prc"] * df["shrout"]  # market cap in 1000s

    # Month label
    df["year_month"] = df["date"].dt.to_period("M")

    # MAX: maximum daily return within each (permno, year_month) group
    max_sig = df.groupby(["permno", "year_month"])["ret"].max().reset_index()
    max_sig.columns = ["permno", "year_month", "max_ret"]

    # Market cap at month-end: get the last observation per month
    df_sorted = df.sort_values(["permno", "year_month", "date"])
    month_end_mcap = df_sorted.groupby(["permno", "year_month"]).last().reset_index()
    month_end_mcap = month_end_mcap[["permno", "year_month", "mcap"]]

    # Merge
    result = max_sig.merge(month_end_mcap, on=["permno", "year_month"], how="inner")

    # Convert year_month back to an actual date (month-end)
    result["date"] = result["year_month"].dt.to_timestamp(how="end")
    result = result.drop(columns=["year_month"])

    # Filter: require positive market cap and valid MAX
    result = result[(result["mcap"] > 0) & result["max_ret"].notna()]

    return result


def compute_decile_portfolio_returns(
    daily: pd.DataFrame,
    max_signal: pd.DataFrame,
    market_index: pd.DataFrame,
) -> dict:
    """Sort stocks into MAX deciles at each month-end, compute value-weighted
    decile portfolio returns over the following month.

    Returns
    -------
    dict with:
      - 'ls_daily_returns': Series — daily long-short portfolio returns
      - 'long_daily_returns': Series — D1 (lowest MAX) portfolio daily returns
      - 'short_daily_returns': Series — D10 (highest MAX) portfolio daily returns
      - 'market_daily_returns': Series — CRSP value-weighted market returns
      - 'decile_summary': DataFrame — monthly decile stats
      - 'monthly_long_short': Series — monthly long-short returns
    """
    daily = daily.copy()
    daily["date"] = pd.to_datetime(daily["date"])
    daily["ret"] = daily["ret"].astype(float)
    daily["year_month"] = daily["date"].dt.to_period("M")

    max_signal = max_signal.copy()
    max_signal["date"] = pd.to_datetime(max_signal["date"])
    max_signal["year_month"] = max_signal["date"].dt.to_period("M")

    mi = market_index.copy()
    mi["date"] = pd.to_datetime(mi["date"])
    mi = mi.sort_values("date")
    mi = mi.set_index("date")
    market_returns = mi["vwretd"].astype(float)

    # ── Universe filter: top N_LARGEST by market cap each month ──
    sig_with_rank = []
    for ym, grp in max_signal.groupby("year_month"):
        grp = grp.nlargest(N_LARGEST, "mcap")
        sig_with_rank.append(grp)
    max_signal = pd.concat(sig_with_rank, ignore_index=True)

    # ── Decile assignment at each month-end ──
    max_signal["max_decile"] = max_signal.groupby("year_month")["max_ret"].transform(
        lambda x: pd.qcut(x, 10, labels=False, duplicates="drop") + 1
    )
    # qcut gives 0-9; +1 gives 1-10

    # Keep only D1 and D10 stocks
    long_stocks = max_signal[max_signal["max_decile"] == 1].copy()
    short_stocks = max_signal[max_signal["max_decile"] == 10].copy()

    # ── Value weights within each decile for each month ──
    for name, df_sub in [("long", long_stocks), ("short", short_stocks)]:
        total_mcap = df_sub.groupby("year_month")["mcap"].transform("sum")
        df_sub["weight"] = df_sub["mcap"] / total_mcap
        # For short side, weights are negative
        if name == "short":
            df_sub["weight"] = -df_sub["weight"]

    # ── Map weights to daily returns for the following month ──
    # For each month-end formation date, we hold from next month's first day to
    # next month's last day with the weights computed at formation.

    # Build a lookup: (year_month, permno) -> weight
    long_weights = long_stocks.set_index(["year_month", "permno"])["weight"]
    short_weights = short_stocks.set_index(["year_month", "permno"])["weight"]

    # The holding period for weights formed at month t is month t+1
    # Create a shifted year_month for the holding period
    def _map_weights(row, weight_map):
        """Map weights: formation at (t-1) -> holdings in month t."""
        # Look up the weight formed at the END of the previous month
        prev_ym = (row["year_month"] - 1)
        return weight_map.get((prev_ym, row["permno"]), 0.0)

    # Add weight column to daily data
    daily = daily.sort_values(["permno", "date"])

    # Pre-build weight DataFrames keyed by (year_month, permno)
    lw = long_weights.reset_index()
    sw = short_weights.reset_index()

    # Merge weights: each stock gets its D1 weight (if in long decile prev month)
    # and D10 weight (if in short decile prev month)
    # We shift the formation month forward by 1 for the holding period
    lw["hold_month"] = lw["year_month"] + 1  # weights formed at t apply to t+1
    sw["hold_month"] = sw["year_month"] + 1

    daily_weights = daily[["permno", "year_month", "date", "ret", "mcap"]].copy()
    daily_weights = daily_weights.merge(
        lw[["hold_month", "permno", "weight"]].rename(columns={"weight": "long_w"}),
        left_on=["year_month", "permno"],
        right_on=["hold_month", "permno"],
        how="left",
    )
    daily_weights = daily_weights.merge(
        sw[["hold_month", "permno", "weight"]].rename(columns={"weight": "short_w"}),
        left_on=["year_month", "permno"],
        right_on=["hold_month", "permno"],
        how="left",
    )
    daily_weights["long_w"] = daily_weights["long_w"].fillna(0.0)
    daily_weights["short_w"] = daily_weights["short_w"].fillna(0.0)

    # ── Compute daily value-weighted portfolio returns ──
    # Long portfolio return: sum(long_w_i * ret_i) for all stocks where long_w > 0
    # Short portfolio return: sum(short_w_i * ret_i) where short_w < 0
    # Long-short: long + short (short weights are negative, so this is long - |short|)

    daily_w = daily_weights.dropna(subset=["ret"])
    daily_w["ret"] = daily_w["ret"].astype(float)

    def _portfolio_return(grp, wcol):
        """Weighted portfolio return for a day."""
        if grp[wcol].abs().sum() == 0:
            return 0.0
        w = grp[wcol].values
        r = grp["ret"].values
        return float(np.dot(w, r))

    long_ret = daily_w.groupby("date").apply(lambda g: _portfolio_return(g, "long_w"))
    short_ret = daily_w.groupby("date").apply(lambda g: _portfolio_return(g, "short_w"))

    # Long-short daily return: long - short (short_w is negative)
    # Total portfolio: long_w + short_w = long_weight - |short_weight|
    # For a dollar-neutral portfolio: each side gets 50% allocation
    ls_ret = (long_ret * 0.5 + short_ret * 0.5)  # half long, half short

    # Align with market returns
    common_idx = ls_ret.index.intersection(market_returns.index)
    ls_ret = ls_ret.loc[common_idx]
    long_ret = long_ret.loc[common_idx]
    short_ret = short_ret.loc[common_idx]
    market_ret = market_returns.loc[common_idx]

    # ── Monthly summary ──
    monthly_ls = ls_ret.groupby(pd.Grouper(freq="M")).apply(
        lambda x: np.prod(1 + x.values) - 1
    )

    decile_summary_data = []
    for ym, grp in max_signal.groupby("year_month"):
        n_stocks = len(grp)
        if n_stocks < 10:
            continue
        try:
            deciles = pd.qcut(grp["max_ret"], 10, labels=False, duplicates="drop") + 1
        except ValueError:
            continue
        grp["max_decile"] = deciles
        for d in [1, 10]:
            d_stocks = grp[grp["max_decile"] == d]
            if len(d_stocks) == 0:
                continue
            avg_max = d_stocks["max_ret"].mean()
            avg_mcap = d_stocks["mcap"].mean()
            decile_summary_data.append({
                "date": ym.to_timestamp(how="end"),
                "decile": d,
                "n_stocks": len(d_stocks),
                "avg_max_ret": avg_max,
                "avg_mcap": avg_mcap,
            })

    decile_summary = pd.DataFrame(decile_summary_data)

    return {
        "ls_daily_returns": ls_ret,
        "long_daily_returns": long_ret,
        "short_daily_returns": short_ret,
        "market_daily_returns": market_ret,
        "decile_summary": decile_summary,
        "monthly_long_short": monthly_ls,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Backtrader Strategy: Trades the pre-computed long-short portfolio
# ═══════════════════════════════════════════════════════════════════════════════

class MaxLongShortStrategy(bt.Strategy):
    """Holds the MAX long-short portfolio as a single synthetic instrument.

    The feed is built from pre-computed daily long-short portfolio returns,
    converted into a price series. The strategy simply goes all-in at start
    and holds — the portfolio returns already embed the monthly rebalancing.
    """

    params = (
        ("allocation", 1.0),   # fraction of portfolio to allocate
    )

    def __init__(self):
        self.order_history = []
        self.peak_value = 0.0
        self._entered = False

    def next(self):
        pv = float(self.broker.getvalue())
        self.peak_value = max(self.peak_value, pv)

        if not self._entered and len(self) >= 2:
            target_w = self.p.allocation
            target_size = (target_w * pv) / self.data.close[0]
            current_size = self.getposition(self.data).size
            trade_size = target_size - current_size
            if abs(trade_size) > 1e-8:
                self.buy(size=trade_size)
            self._entered = True


# ═══════════════════════════════════════════════════════════════════════════════
# Backtest Runner
# ═══════════════════════════════════════════════════════════════════════════════

def run_once(feeds, commission: float):
    """Run one backtest at a given commission. Returns (metrics, value_series)."""
    cerebro = bt.Cerebro()
    for feed in feeds:
        cerebro.adddata(feed)
    cerebro.addstrategy(MaxLongShortStrategy, allocation=1.0)
    cerebro.broker.setcash(INITIAL_CASH)
    cerebro.broker.setcommission(commission=commission)

    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        riskfreerate=0.0, annualize=True)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.SQN, _name="sqn")
    cerebro.addanalyzer(bt.analyzers.AnnualReturn, _name="annual")
    cerebro.addobserver(bt.observers.Value)

    results = cerebro.run()
    strat = results[0]

    # Per-bar portfolio value series
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
    trades = strat.analyzers.trades.get_analysis()
    ret_analysis = strat.analyzers.returns.get_analysis()
    sqn_analysis = strat.analyzers.sqn.get_analysis()

    metrics = {
        "commission": commission,
        "final_value": round(final_value, 2),
        "return_value": round(final_value, 2),
        "total_return": round((final_value / INITIAL_CASH - 1) * 100, 2),
        "sharpe_ratio": round(sharpe, 4) if sharpe is not None else None,
        "max_drawdown_pct": round(dd.get("max", {}).get("drawdown", 0.0), 2),
        "num_trades": trades.get("total", {}).get("closed", 0),
        "annualized_return": round(ret_analysis.get("rnorm100", 0), 2),
        "sqn": round(sqn_analysis.get("sqn", 0), 4),
    }
    return metrics, value_series


# ═══════════════════════════════════════════════════════════════════════════════
# Portfolio-vs-Assets Chart (required output contract)
# ═══════════════════════════════════════════════════════════════════════════════

def plot_portfolio_vs_assets(value_by_commission: dict, asset_prices: dict) -> None:
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

    # Buy-and-hold curves: normalise each asset to the same starting capital
    for sym, prices in asset_prices.items():
        s = prices.astype(float).ffill()
        if s.iloc[0] <= 0:
            continue
        bh = INITIAL_CASH * (s / s.iloc[0])
        is_spy = sym.upper() == SPY_SYMBOL.upper()
        ax.plot(bh.index, bh.values, label=f"{sym} (B&H)",
                linewidth=2.6 if is_spy else 1.0,
                alpha=1.0 if is_spy else 0.7)
        combined[f"{sym}_bh"] = bh

    # Portfolio curves at each commission — boldface
    for comm, vseries in value_by_commission.items():
        label = f"Portfolio @ {comm*100:.2f}% comm"
        ax.plot(vseries.index, vseries.values, label=label, linewidth=2.6)
        combined[f"portfolio_comm_{comm}"] = vseries

    ax.set_title("MAX Long-Short Portfolio vs Same-Capital Buy-and-Hold\n(SPY + portfolio boldface)")
    ax.set_xlabel("Date")
    ax.set_ylabel("Account value ($)")
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "portfolio_vs_assets.png", dpi=120)
    plt.close(fig)
    combined.to_csv(RESULTS_DIR / "portfolio_vs_assets.csv")


def plot_key_factor(name: str, series: pd.Series) -> None:
    """One CSV + PNG per key observable factor, under results/key_pred/."""
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(series.index, series.values, linewidth=1.2)
    ax.set_title(f"Key factor: {name}")
    ax.set_xlabel("Date")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(KEY_PRED_DIR / f"{name}.png", dpi=120)
    plt.close(fig)
    series.to_frame(name).to_csv(KEY_PRED_DIR / f"{name}.csv")


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    print("=" * 60)
    print("MAX Effect: Stocks as Lotteries — Long-Short Strategy")
    print("=" * 60)

    # 1. ── Fetch data ──
    print("\n[1/6] Fetching data from ClickHouse...")
    start = BACKTEST_START
    end = BACKTEST_END

    market_idx = fetch_market_index(start, end)
    print(f"  Market index: {len(market_idx):,} rows")

    daily = fetch_daily_crsp(start, end)
    print(f"  Daily CRSP: {len(daily):,} rows, {daily['permno'].nunique():,} unique stocks")

    # 2. ── Compute MAX signal ──
    print("\n[2/6] Computing MAX signal (max daily return over past month)...")
    max_sig = compute_max_signal(daily)
    print(f"  MAX signal: {len(max_sig):,} stock-month observations")
    print(f"  Period: {max_sig['date'].min().date()} → {max_sig['date'].max().date()}")
    print(f"  Universe per month: up to {N_LARGEST:,} stocks by market cap")

    # 3. ── Compute decile portfolio returns ──
    print("\n[3/6] Sorting into deciles, computing value-weighted portfolio returns...")
    portfolio = compute_decile_portfolio_returns(daily, max_sig, market_idx)
    ls_ret = portfolio["ls_daily_returns"]
    long_ret = portfolio["long_daily_returns"]
    short_ret = portfolio["short_daily_returns"]
    market_ret = portfolio["market_daily_returns"]

    print(f"  Long-short daily returns: {len(ls_ret):,} observations")
    monthly = portfolio["monthly_long_short"]
    monthly = monthly.dropna()
    print(f"  Monthly long-short: mean={monthly.mean()*100:.2f}%, "
          f"t-stat={monthly.mean()/monthly.std()*np.sqrt(len(monthly)):.2f}, "
          f"N={len(monthly)}")

    # 4. ── Build synthetic price series for Backtrader ──
    print("\n[4/6] Building synthetic price feeds for Backtrader...")

    # Portfolio feed: convert portfolio returns to price
    ls_price = returns_to_ohlcv(ls_ret.index, ls_ret.values, "MAX_LS")
    ls_feed = to_feed(ls_price, "MAX_LS")

    # SPY/market feed: convert market returns to price
    market_dates = market_ret.index
    spy_price = returns_to_ohlcv(market_dates, market_ret.values, SPY_SYMBOL)
    spy_feed = to_feed(spy_price, SPY_SYMBOL)

    # 5. ── Run backtest with commission sweep ──
    print("\n[5/6] Running backtests...")
    value_by_commission = {}
    all_metrics = []

    for comm in COMMISSION_RATES:
        feeds = [ls_feed]  # trade only the long-short portfolio
        metrics, vseries = run_once(feeds, comm)
        value_by_commission[comm] = vseries
        all_metrics.append(metrics)
        print(f"  Commission {comm*100:.2f}%: "
              f"Sharpe={metrics['sharpe_ratio']}, "
              f"Return={metrics['total_return']:.1f}%, "
              f"MaxDD={metrics['max_drawdown_pct']:.1f}%")

    # 6. ── Generate required artifacts ──
    print("\n[6/6] Generating charts and metrics...")

    # SPY buy-and-hold price series from the market index returns
    spy_cum = np.cumprod(1.0 + market_ret.fillna(0.0).values)
    spy_prices = pd.Series(spy_cum, index=market_ret.index, name=SPY_SYMBOL)

    # Also compute the long-only decile 1 and short-only decile 10 as separate B&H
    long_cum = np.cumprod(1.0 + long_ret.fillna(0.0).values)
    long_prices = pd.Series(long_cum, index=long_ret.index, name="Long_D1")

    short_cum = np.cumprod(1.0 + short_ret.fillna(0.0).values)
    short_prices = pd.Series(short_cum, index=short_ret.index, name="Short_D10")

    asset_prices = {
        SPY_SYMBOL: spy_prices,
        "Long_MinMAX_D1": long_prices,
        "Short_MaxMAX_D10": short_prices,
    }

    plot_portfolio_vs_assets(value_by_commission, asset_prices)

    # Key factors
    # 1. MAX spread (D10 - D1): the raw signal
    decile_summary = portfolio["decile_summary"]
    if not decile_summary.empty:
        d1 = decile_summary[decile_summary["decile"] == 1].set_index("date")["avg_max_ret"]
        d10 = decile_summary[decile_summary["decile"] == 10].set_index("date")["avg_max_ret"]
        max_spread = d10 - d1
        plot_key_factor("MAX_spread_D10_minus_D1", max_spread.dropna())

    # 2. Monthly long-short returns
    plot_key_factor("monthly_long_short_returns", monthly)

    # 3. Cumulative long-short equity curve
    ls_cumret = pd.Series(
        np.cumprod(1.0 + ls_ret.fillna(0.0).values) * INITIAL_CASH,
        index=ls_ret.index,
        name="LS_equity",
    )
    plot_key_factor("cumulative_long_short_equity", ls_cumret)

    # Write metrics
    (RESULTS_DIR / "metrics.json").write_text(json.dumps(all_metrics, indent=2))
    print("\n" + json.dumps(all_metrics, indent=2))

    # Write diagnosis
    diagnosis = {
        "strategy": "MAX Effect: Stocks as Lotteries",
        "paper": "Bali, Cakici & Whitelaw (2011)",
        "implementation": "Long-short, value-weighted, monthly rebalanced MAX decile portfolio",
        "backtest_period": f"{start} → {end}",
        "universe": f"Top {N_LARGEST} by market cap per month",
        "commission_rates": list(COMMISSION_RATES),
        "expected_monthly_long_short": ">1% per month (raw return spread)",
        "actual_monthly_mean": f"{monthly.mean()*100:.2f}%",
        "actual_monthly_tstat": f"{monthly.mean()/monthly.std()*np.sqrt(len(monthly)):.2f}",
        "data_source": "CRSP via ClickHouse (crsp_202501.dsf)",
        "notes": [
            "Fama-French factors not available in ClickHouse — IVOL/beta controls skipped",
            "Book-to-market not linked (no PERMNO→GVKEY link table) — BM control skipped",
            "Exchange/share code filters not applied (hexcd/hsiccd used when available)",
            "Universe limited to top N by market cap for computational feasibility",
        ],
    }
    (RESULTS_DIR / "diagnosis_report.json").write_text(
        json.dumps(diagnosis, indent=2)
    )

    print("\n✅ Backtest complete.")
    print(f"   Metrics: {RESULTS_DIR / 'metrics.json'}")
    print(f"   Chart:   {RESULTS_DIR / 'portfolio_vs_assets.png'}")
    print(f"   Factors: {KEY_PRED_DIR}/")


if __name__ == "__main__":
    main()
