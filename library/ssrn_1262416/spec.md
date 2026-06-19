# ssrn-1262416

## MAX Factor: Stocks as Lotteries

**Type**: hybrid
**Asset Class**: equity

The strategy exploits a negative cross-sectional relation between a stock's maximum daily return over the past month (MAX) and its expected return in the following month. Stocks with the highest MAX (lottery-like payoffs) are overvalued and subsequently underperform, while those with the lowest MAX outperform. A long-short portfolio that buys the lowest MAX decile and shorts the highest MAX decile generates significant raw and risk-adjusted returns.

### Data Requirements

- **Source**: CRSP, COMPUSTAT, Kenneth French's Data Library
- **Period**: July 1962 to December 2005
- **Frequency**: daily
- **Universe**: US equities
- **Filters**: NYSE/AMEX/NASDAQ stocks; robustness checks exclude stocks with price < $5, exclude AMEX/NASDAQ, exclude smallest NYSE size quintile (microcaps); book-to-market winsorized at 0.5% and 99.5%
- **Data fields**: Price, Volume, Book-to-Market
- **Lookback**: None bars

### Indicators (15)

| ID | Name | Category | Formula | Scope |
|:---|:-----|:---------|:--------|:------|
| `max_daily_return` | Maximum Daily Return (MAX) | technical | For each stock i in month t, compute the maximum of daily returns over all tradi… | time_series |
| `max_5_avg` | Average of Five Highest Daily Returns (MAX(5)) | technical | For each stock i in month t, compute the average of the five highest daily retur… | time_series |
| `max_3m_avg` | Averaged MAX over Past 3 Months | technical | For each stock i, compute the maximum daily return in each of the past 3 months,… | time_series |
| `beta_scholes_williams` | Market Beta (Scholes-Williams) | technical | Market beta estimated using the Scholes-Williams (1977) / Dimson (1979) method w… | time_series |
| `size_market_cap` | Market Capitalization (SIZE) | fundamental | Natural logarithm of market capitalization at the end of month t-1. | cross_sectional |
| `book_to_market` | Book-to-Market Ratio (BM) | fundamental | Book value of equity divided by market value of equity at the end of December of… | cross_sectional |
| `momentum_12m_1m` | Momentum (MOM) | technical | Cumulative return over the 11 months ending 2 months prior to the current month … | time_series |
| `short_term_reversal` | Short-term Reversal (REV) | technical | Return in the previous month (month t-1). | time_series |
| `illiquidity_amihud` | Illiquidity (ILLIQ) | technical | Ratio of absolute monthly stock return to its dollar trading volume. | time_series |
| `idiosyncratic_volatility` | Idiosyncratic Volatility (IVOL) | technical | Standard deviation of daily residuals from a single-factor market model regressi… | time_series |
| `min_daily_return` | Negative of Minimum Daily Return (MIN) | technical | Negative of the minimum daily return within a month. | time_series |
| `total_skewness` | Total Skewness (TSKEW) | technical | Skewness of daily returns within a year. | time_series |
| `systematic_skewness` | Systematic Skewness / Co-skewness (SSKEW) | technical | Coefficient on squared market return from a regression of stock returns on marke… | time_series |
| `idiosyncratic_skewness` | Idiosyncratic Skewness (ISKEW) | technical | Skewness of daily residuals from the SSKEW regression. | time_series |
| `expected_total_skewness` | Expected Total Skewness (E(TSKEW)) | derived | Fitted values from a cross-sectional regression of TSKEW on lagged TSKEW and con… | cross_sectional |

### Logic Pipeline (4 steps)

step1. **filter** (cross_sectional): Filter stocks based on price and size to exclude micro-caps and low-priced stocks — `Keep stocks with price >= $5 and market capitalization above the smallest two NYSE size deciles (i.e., exclude micro-caps).`  
   → output: `filtered_universe` (boolean)
step2. **custom** (time_series): Calculate MAX indicator: maximum daily return over the past one month — `MAX_i,t = max(R_i,d) for d = 1 to D_t, where R_i,d is the daily return on stock i on day d, and D_t is the number of trading days in month t.`  
   → output: `max_indicator` (scalar)
step3. **quantile_sort** (cross_sectional): Sort all stocks into deciles based on MAX indicator from the previous month — `Each month, sort all filtered stocks into 10 decile portfolios based on MAX. Decile 1 = lowest MAX, Decile 10 = highest MAX.`  
   → output: `max_decile` (label)
step4. **condition** (cross_sectional): Generate long-short trade signal based on MAX decile assignment — `IF max_decile == 'Q1' THEN 'long_target' (buy low MAX stocks); IF max_decile == 'Q10' THEN 'short_target' (sell high MAX stocks); ELSE 'hold' (no position).`  
   → output: `trade_signal` (label)

### Execution (1 plans)

**exec_1**: Monthly long-short portfolio based on MAX decile sorts from previous month
- Trigger: time_driven, monthly, delay=1 bar(s)
- Action: `WHEN 'decile_1': LONG; WHEN 'decile_10': SHORT`
- Sizing: quantile_based, exposure=None, long_short

### Risk Management (3 rules)

- No explicit stop-loss, position limit, sector exposure cap, or drawdown constraint is specified in the paper.
- The paper applies price filters (exclude stocks below $5/share) and size filters (exclude microcaps) as robustness checks, but these are not part of the primary strategy's risk management rules.
- Winsorization of MAX at the 99th percentile is used in robustness checks, not as a live risk rule.
