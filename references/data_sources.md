# Data Sources Reference

Guide for generating data-fetching code. Covers yfinance and akshare APIs.

## yfinance (US/Global Markets)

### Install
```bash
pip install yfinance
```

### Single Symbol
```python
import yfinance as yf

df = yf.download('AAPL', start='2020-01-01', end='2024-01-01')
# Columns: Open, High, Low, Close, Adj Close, Volume
```

### Multiple Symbols
```python
df = yf.download(['AAPL', 'MSFT', 'GOOGL'], start='2020-01-01', end='2024-01-01')
# Returns MultiIndex columns: (Price, Symbol)
# Access single: df['Close']['AAPL']
```

### Common Tickers
| Asset Class | Examples |
|-------------|----------|
| US Equities | AAPL, MSFT, GOOGL, AMZN, TSLA, JPM |
| ETFs | SPY, QQQ, IWM, TLT, GLD, XLF |
| Indices | ^GSPC (S&P500), ^DJI (Dow), ^IXIC (Nasdaq) |
| Forex | EURUSD=X, GBPUSD=X, JPYUSD=X |
| Crypto | BTC-USD, ETH-USD |

### Intervals
```python
# Daily (default)
df = yf.download('AAPL', period='1y')
# Weekly
df = yf.download('AAPL', period='5y', interval='1wk')
# Monthly
df = yf.download('AAPL', period='10y', interval='1mo')
# Intraday (max 60 days)
df = yf.download('AAPL', period='60d', interval='1h')
```

### Fundamentals
```python
ticker = yf.Ticker('AAPL')
info = ticker.info             # P/E, market cap, etc.
bs = ticker.balance_sheet      # Balance sheet
cf = ticker.cashflow           # Cash flow
earn = ticker.earnings_dates   # Earnings dates
```

## akshare (China A-Share, HK, Macro)

### Install
```bash
pip install akshare
```

### A-Share Daily Data
```python
import akshare as ak

# Daily bars (前复权)
df = ak.stock_zh_a_hist(
    symbol="000001",           # Stock code
    period="daily",            # daily/weekly/monthly
    start_date="20200101",
    end_date="20240101",
    adjust="qfq"              # qfq=前复权 hfq=后复权 ""=不复权
)
# Columns: 日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 振幅, 涨跌幅, 涨跌额, 换手率
```

### Rename for Backtrader
```python
df = df.rename(columns={
    '日期': 'date', '开盘': 'open', '收盘': 'close',
    '最高': 'high', '最低': 'low', '成交量': 'volume'
})
df['date'] = pd.to_datetime(df['date'])
df = df.set_index('date')
```

### Index Data
```python
# Shanghai Composite
df = ak.stock_zh_index_daily(symbol="sh000001")
# CSI 300
df = ak.stock_zh_index_daily(symbol="sh000300")
```

### HK Stocks
```python
df = ak.stock_hk_hist(
    symbol="00700",   # Tencent
    period="daily",
    start_date="20200101",
    end_date="20240101",
    adjust="qfq"
)
```

### Macro Data
```python
# China CPI
cpi = ak.macro_china_cpi()
# GDP
gdp = ak.macro_china_gdp()
# PMI
pmi = ak.macro_china_pmi()
# Shibor
shibor = ak.rate_interbank(market="上海银行间同业拆放利率")
```

## FRED (US Macro — via yfinance or pandas-datareader)

```python
# Via yfinance (limited)
import yfinance as yf
treasury = yf.download('^TNX', start='2020-01-01')  # 10Y Treasury Yield

# Via pandas-datareader (requires FRED API key)
# import pandas_datareader as pdr
# gdp = pdr.get_data_fred('GDP', start='2000-01-01')
```

## Data Quality Checklist

When generating data-fetching code, ensure:

1. **Date range validation**: start_date < end_date, reasonable range
2. **NaN handling**: `df.dropna()` or `df.fillna(method='ffill')`
3. **Column naming**: Backtrader expects `open, high, low, close, volume`
4. **Timezone**: Remove timezone info: `df.index = df.index.tz_localize(None)`
5. **Sorting**: Ensure ascending date order: `df.sort_index(inplace=True)`
6. **Type conversion**: Ensure numeric types: `df = df.astype(float)`

## Backtrader Data Feed Creation

### From yfinance DataFrame
```python
data = bt.feeds.PandasData(
    dataname=df,
    fromdate=datetime(2020, 1, 1),
    todate=datetime(2024, 1, 1),
)
```

### From akshare DataFrame (after rename)
```python
data = bt.feeds.PandasData(
    dataname=df,
    datetime=None,  # Use index
    open='open', high='high', low='low',
    close='close', volume='volume',
    openinterest=-1,
)
```

### From CSV
```python
data = bt.feeds.GenericCSVData(
    dataname='data.csv',
    dtformat='%Y-%m-%d',
    datetime=0, open=1, high=2, low=3, close=4, volume=5,
    openinterest=-1,
)
```
