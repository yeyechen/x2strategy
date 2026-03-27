# Backtrader Patterns Reference

Common patterns for generating correct Backtrader code from strategy specifications.

## Strategy Class Structure

```python
import backtrader as bt

class MyStrategy(bt.Strategy):
    params = (
        ('period', 20),
        ('threshold', 0.02),
    )

    def __init__(self):
        # Compute indicators once — these are lazy (Lines objects)
        self.sma = bt.indicators.SMA(self.data.close, period=self.p.period)
        self.rsi = bt.indicators.RSI(self.data.close, period=14)

    def next(self):
        # Called on every bar — make trading decisions here
        if not self.position:
            if self.data.close[0] > self.sma[0]:
                self.buy()
        else:
            if self.data.close[0] < self.sma[0]:
                self.sell()
```

## Data Loading Patterns

### Single Symbol (yfinance)
```python
import yfinance as yf
import backtrader as bt

data = bt.feeds.PandasData(
    dataname=yf.download('AAPL', start='2020-01-01', end='2024-01-01'),
)
cerebro.adddata(data)
```

### Multiple Symbols
```python
symbols = ['AAPL', 'MSFT', 'GOOGL']
for sym in symbols:
    df = yf.download(sym, start='2020-01-01', end='2024-01-01')
    data = bt.feeds.PandasData(dataname=df, name=sym)
    cerebro.adddata(data)
```

### Accessing Multiple Data Feeds in Strategy
```python
class MultiStrategy(bt.Strategy):
    def __init__(self):
        # self.datas[0], self.datas[1], etc.
        # or self.data0, self.data1
        for d in self.datas:
            self.sma = bt.indicators.SMA(d.close, period=20)

    def next(self):
        for i, d in enumerate(self.datas):
            if d.close[0] > d.close[-1]:
                self.buy(data=d)
```

## Position Sizing Patterns

### Equal Weight
```python
def next(self):
    n = len(self.datas)
    for d in self.datas:
        target = 1.0 / n
        self.order_target_percent(data=d, target=target)
```

### Volatility-Scaled
```python
def next(self):
    for d in self.datas:
        atr = self.atrs[d._name][0]
        risk_per_trade = self.broker.getvalue() * 0.01
        size = int(risk_per_trade / atr) if atr > 0 else 0
        self.buy(data=d, size=size)
```

### Long-Short Portfolio
```python
def next(self):
    # Rank assets by signal
    ranked = sorted(range(len(self.datas)),
                    key=lambda i: self.signals[i][0], reverse=True)
    n_long = len(ranked) // 5   # Top quintile
    n_short = len(ranked) // 5  # Bottom quintile

    for i, d in enumerate(self.datas):
        if i in ranked[:n_long]:
            self.order_target_percent(data=d, target=1.0/n_long)
        elif i in ranked[-n_short:]:
            self.order_target_percent(data=d, target=-1.0/n_short)
        else:
            self.order_target_percent(data=d, target=0)
```

## Rebalancing Patterns

### Monthly Rebalancing
```python
class MonthlyRebalance(bt.Strategy):
    def __init__(self):
        self._last_month = -1

    def next(self):
        current_month = self.data.datetime.date(0).month
        if current_month == self._last_month:
            return
        self._last_month = current_month
        # Rebalance logic here
```

### Signal-Driven with Cooldown
```python
class SignalStrategy(bt.Strategy):
    params = (('cooldown', 5),)

    def __init__(self):
        self._bars_since_trade = 0

    def next(self):
        self._bars_since_trade += 1
        if self._bars_since_trade < self.p.cooldown:
            return
        if self.signal_triggered():
            self.buy()
            self._bars_since_trade = 0
```

## Cerebro Runner Template

```python
def run_backtest():
    cerebro = bt.Cerebro()

    # Add data
    data = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data)

    # Add strategy
    cerebro.addstrategy(MyStrategy, period=20)

    # Broker settings
    cerebro.broker.setcash(100000)
    cerebro.broker.setcommission(commission=0.001)

    # Analyzers
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')

    # Run
    results = cerebro.run()
    return results

if __name__ == '__main__':
    run_backtest()
```

## Common Pitfalls

1. **Data alignment**: When using multiple data feeds, Backtrader auto-aligns
   by datetime. Ensure all feeds have overlapping date ranges.
2. **Warmup period**: Indicators need N bars before producing values. Don't
   trade until `len(self) >= max_period`.
3. **Order types**: `self.buy()` creates a market order. Use `self.buy(exectype=bt.Order.Limit, price=p)`
   for limit orders.
4. **Position check**: Always check `self.position` or `self.getposition(data)`
   before placing orders to avoid doubling up.
5. **Column names**: yfinance returns `Open/High/Low/Close/Volume` (capitalized).
   PandasData expects these exact names.
