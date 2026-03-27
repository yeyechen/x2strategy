# Indicator Implementation Cookbook

Quick reference for translating common technical indicators into Backtrader code.
Used during signal module code generation.

## Built-in Indicators (bt.indicators)

### Trend
| Indicator | Code | Notes |
|-----------|------|-------|
| SMA | `bt.indicators.SMA(data, period=20)` | Simple Moving Average |
| EMA | `bt.indicators.EMA(data, period=12)` | Exponential Moving Average |
| MACD | `bt.indicators.MACD(data)` | Returns macd, signal, histo |
| Bollinger | `bt.indicators.BollingerBands(data, period=20)` | .top, .mid, .bot |
| ADX | `bt.indicators.ADX(data, period=14)` | Average Directional Index |

### Momentum
| Indicator | Code | Notes |
|-----------|------|-------|
| RSI | `bt.indicators.RSI(data, period=14)` | Relative Strength Index |
| Stochastic | `bt.indicators.Stochastic(data)` | %K and %D |
| MFI | `bt.indicators.MFI(data, period=14)` | Money Flow Index |
| ROC | `bt.indicators.ROC(data, period=12)` | Rate of Change |

### Volatility
| Indicator | Code | Notes |
|-----------|------|-------|
| ATR | `bt.indicators.ATR(data, period=14)` | Average True Range |
| StdDev | `bt.indicators.StdDev(data, period=20)` | Standard Deviation |

### Volume
| Indicator | Code | Notes |
|-----------|------|-------|
| OBV | `bt.indicators.OBV(data)` | On-Balance Volume |
| VWAP | custom (see below) | Volume-Weighted Average Price |

## Custom Indicator Patterns

### Z-Score
```python
class ZScore(bt.Indicator):
    lines = ('zscore',)
    params = (('period', 20),)

    def __init__(self):
        mean = bt.indicators.SMA(self.data, period=self.p.period)
        std = bt.indicators.StdDev(self.data, period=self.p.period)
        self.lines.zscore = (self.data - mean) / std
```

### VWAP
```python
class VWAP(bt.Indicator):
    lines = ('vwap',)

    def __init__(self):
        cumvol = bt.indicators.CumSum(self.data.volume)
        cumtp = bt.indicators.CumSum(
            (self.data.high + self.data.low + self.data.close) / 3.0 * self.data.volume
        )
        self.lines.vwap = cumtp / cumvol
```

### Spread / Pair Ratio
```python
class PairSpread(bt.Indicator):
    lines = ('spread', 'zscore')
    params = (('period', 20),)

    def __init__(self):
        self.lines.spread = self.data0.close / self.data1.close
        mean = bt.indicators.SMA(self.lines.spread, period=self.p.period)
        std = bt.indicators.StdDev(self.lines.spread, period=self.p.period)
        self.lines.zscore = (self.lines.spread - mean) / std
```

### Rolling Beta
```python
class RollingBeta(bt.Indicator):
    lines = ('beta',)
    params = (('period', 60),)

    def next(self):
        asset = list(self.data0.close.get(size=self.p.period))
        market = list(self.data1.close.get(size=self.p.period))
        if len(asset) < self.p.period:
            return
        import numpy as np
        ret_a = np.diff(asset) / asset[:-1]
        ret_m = np.diff(market) / market[:-1]
        cov = np.cov(ret_a, ret_m)[0][1]
        var = np.var(ret_m)
        self.lines.beta[0] = cov / var if var > 0 else 0
```

## Signal Generation Patterns

### Crossover
```python
# Built-in crossover detection
self.cross = bt.indicators.CrossOver(self.fast_ma, self.slow_ma)

def next(self):
    if self.cross[0] > 0:   # fast crossed above slow
        self.buy()
    elif self.cross[0] < 0: # fast crossed below slow
        self.sell()
```

### Threshold Breakout
```python
def next(self):
    if self.rsi[0] < 30 and not self.position:
        self.buy()
    elif self.rsi[0] > 70 and self.position:
        self.sell()
```

### Multi-Factor Composite
```python
def __init__(self):
    self.momentum = bt.indicators.ROC(self.data.close, period=12)
    self.value = -bt.indicators.StdDev(self.data.close, period=20)
    self.quality = bt.indicators.RSI(self.data.close, period=14) - 50

def next(self):
    score = (0.4 * self.momentum[0] + 0.3 * self.value[0] + 0.3 * self.quality[0])
    if score > self.p.threshold:
        self.buy()
```

## Common Spec-to-Code Mappings

| Spec Description | Backtrader Code |
|-----------------|-----------------|
| "20-day moving average" | `bt.indicators.SMA(data.close, period=20)` |
| "MACD signal line" | `bt.indicators.MACD(data).signal` |
| "upper Bollinger band" | `bt.indicators.BollingerBands(data).top` |
| "momentum score" | `bt.indicators.ROC(data.close, period=N)` |
| "volatility-adjusted" | divide by `bt.indicators.ATR(data, period=14)` |
| "z-score normalization" | custom ZScore indicator (see above) |
| "pairs trading" | PairSpread + zscore on ratio of two feeds |
| "buy at open, sell at close" | use `exectype=bt.Order.Market`, check bar timing |
| "stop loss at 2%" | `self.sell(exectype=bt.Order.Stop, price=entry*0.98)` |
| "trailing stop" | `bt.observers.StopTrail` or manual tracking in `next()` |
