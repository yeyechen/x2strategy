# ssrn-1262416

> ## **Maxing Out: Stocks as Lotteries and the Cross-Section of Expected Returns** 
> 
> Turan G. Bali,[a] Nusret Cakici,[b] and Robert F. Whitelaw[c*] 
> 
> ## **February 2010** 
> 
> ## **ABSTRACT** 
> 
> Motivated by existing evidence of a preference among investors for assets with lottery-like payoffs and that many investors are poorly diversified, we investigate the significance of extreme positive returns in the cross-sectional pricing of stocks. Portfolio-level analyses and firm-level cross-sectional regressions indicate a negative and significant relation between the maximum daily return over the past one month (MAX) and expected stock returns. Average raw and risk-adjusted return differences between stocks in the lowest and highest MAX deciles exceed 1% per month. These results are robust to controls for size, book-to-market, momentum, short-term reversals, liquidity, and skewness. Of particular interest, including MAX reverses the puzzling negative relation between returns and idiosyncratic volatility recently documented in Ang et al. (2006, 2009). 
> 
> > a Department of Economics and Finance, Zicklin School of Business, Baruch College, One Bernard Baruch Way, Box 10-225, New York, NY 10010. Phone: (646) 312-3506, Fax: (646) 312-3451, E-mail: turan_bali@baruch.cuny.edu. 
> 
> b School of Business, Fordham University, 1790 Broadway, New York, NY 10019, Phone: (212) 6366120, Fax: (212) 586-0575, E-mail: cakici@fordham.edu. 
> 
> c Corresponding author. Stern School of Business, New York Universit

## Methodology

Based on the provided text, here is a structured synthesis of the trading strategy methodology.

### Core Trading Idea
The strategy is a **cross-sectional, factor-based** strategy exploiting a preference for lottery-like payoffs among investors. The central finding is a negative and significant relation between a stock’s maximum daily return over the past month (MAX) and its expected return in the following month. Stocks with the most extreme positive daily returns (high MAX) are overvalued and subsequently underperform, while stocks with the lowest extreme returns (low MAX) outperform.

### Signal Generation and Portfolio Formation
The primary signal is **MAX**, defined as the maximum daily return for stock *i* in month *t*:  
`MAX_i,t = max(R_i,d) for d = 1...D_t`, where `R_i,d` is the daily return and `D_t` is the number of trading days in the month.  
Each month, all NYSE/AMEX/NASDAQ stocks are sorted into **decile portfolios** based on their MAX value from the previous month. Decile 1 contains stocks with the lowest MAX, and Decile 10 contains stocks with the highest MAX. The strategy is robust to using the average of the *N* highest daily returns (e.g., MAX(5) for N=5), which yields even stronger results. The sample period is July 1962 to December 2005.

### Portfolio Construction and Rebalancing
The strategy is a **long-short** portfolio. It goes **long on Decile 1 (low MAX)** and **short on Decile 10 (high MAX)**. Portfolios are rebalanced **monthly**. The paper reports results for both **value-weighted (VW)** and **equal-weighted (EW)** portfolios. The primary performance metric is the difference in average monthly returns and the Fama-French-Carhart four-factor alpha between the low and high MAX deciles. For the VW portfolio, the raw return difference is **-1.03% per month** (t-stat -2.83), and the four-factor alpha difference is **-1.18% per month** (t-stat -4.71). The strategy is robust to controlling for size, book-to-market, momentum, short-term reversals, and liquidity via bivariate sorts and Fama-MacBeth cross-sectional regressions. In the full Fama-MacBeth specification (including six control variables), the average slope coefficient on MAX is **-0.0637** (t-stat -6.16), implying a **102 basis point** difference in expected monthly returns between the median stocks in the high and low MAX deciles.

### Key Mathematical and Methodological Details
- **Persistence of MAX:** The strategy relies on the persistence of extreme returns. Stocks in the top MAX decile have a **35%** probability of remaining in the top decile the following month and a **68%** probability of being in one of the top three deciles.
- **Relation to Idiosyncratic Volatility (IVOL):** A critical finding is that including MAX **reverses** the negative IVOL effect (Ang et al., 2006). In bivariate sorts controlling for MAX, the return difference between high and low IVOL portfolios becomes **positive** (e.g., +0.98% per month for EW portfolios, t-stat 4.88). In Fama-

*(truncated)*

## Data Description

Based on the provided text from "Maxing Out: Stocks as Lotteries and the Cross-Section of Expected Returns" by Bali, Cakici, and Whitelaw (February 2010), here are the extracted data requirements and sample description:

### 1. Data Sources
- **CRSP (Center for Research in Security Prices)**: Used for daily stock returns, monthly stock returns, volume data, share prices, and shares outstanding.
- **COMPUSTAT**: Used to obtain equity book values for calculating book-to-market ratios.
- **Kenneth French’s Data Library**: Source for Fama-French-Carhart four factors (excess market return, SMB, HML, MOM).

### 2. Asset Universe
- **Exchanges**: New York Stock Exchange (NYSE), American Stock Exchange (AMEX), and NASDAQ.
- **Firm types**: Financial and nonfinancial firms (both included).
- **Sample restrictions for robustness checks**:
  - Excluding all stocks with prices below $5/share.
  - Excluding all AMEX and NASDAQ stocks (NYSE only).
  - Excluding microcap stocks (stocks with market capitalizations in the smallest NYSE size quintile, i.e., two smallest size deciles, consistent with Keim (1999) and Fama and French (2008)).

### 3. Time Period
- **Primary sample period**: July 1962 to December 2005 (522 months).
- **Extended sample**: January 1926 through December 2005 (for some analyses).
- **Subsample**: January 1926 – June 1962 (for robustness).
- **Subperiod split**: Before and after the end of 1983 (for robustness).

### 4. Data Frequency
- **Daily data**: Used to calculate maximum daily stock returns (MAX), market beta (BETA), idiosyncratic volatility (IVOL), total volatility (TVOL), total skewness (TSKEW), systematic skewness (SSKEW), and idiosyncratic skewness (ISKEW).
- **Monthly data**: Used to calculate intermediate-term momentum (MOM), short-term reversals (REV), illiquidity (ILLIQ), and market capitalization (SIZE).
- **Returns**: Both raw returns and risk-adjusted returns (4-factor alphas) are used.

### 5. Selection/Filter Criteria
- **Price filter**: Excluding stocks with prices below $5/share (robustness check).
- **Market cap filter**: Excluding microcap stocks (stocks in the smallest NYSE size quintile) (robustness check).
- **Exchange filter**: Excluding AMEX and NASDAQ stocks (NYSE only) (robustness check).
- **Winsorization**: Book-to-market ratios are winsorized at the 0.5% and 99.5% levels (to avoid extreme observations). MAX is winsorized at the 99th and 95th percentiles (robustness check).
- **Zero trading volume handling**: For the daily Amihud illiquidity measure, stocks with zero trading volume on at least one day within the month are eliminated (robustness check). The primary illiquidity measure uses monthly data to avoid this issue.

### 6. Fundamental Data Fields
- **MAX (Maximum daily return)**: The maximum daily return within a month.
- **MAX(5)**: The average of the five highest daily returns within a month.
- **MIN (Minimum daily return)**: The negative of the minimum daily return within a month.
- **BETA**: Mark

*(truncated)*

## Signal Logic

Based on the provided text from "Maxing Out: Stocks as Lotteries and the Cross-Section of Expected Returns" by Bali, Cakici, and Whitelaw (2010), here are the precise trading rules and signal logic extracted:

### 1. Entry Conditions (Short Signal / Long Signal)

The primary strategy is a **short-selling strategy** based on the negative relation between extreme positive returns (MAX) and future returns. The paper does not describe a long-only strategy based on MAX.

- **Short Entry (Sell High MAX stocks):**
    - **Condition:** Stocks in the highest decile (Decile 10) of MAX (maximum daily return over the past one month) are identified.
    - **Signal Logic:** These stocks are expected to have the lowest future returns (negative alpha). The strategy is to short these stocks.
- **Long Entry (Buy Low MAX stocks):**
    - **Condition:** Stocks in the lowest decile (Decile 1) of MAX are identified.
    - **Signal Logic:** These stocks are expected to have the highest future returns. The strategy is to go long on these stocks.
- **Primary Trading Strategy:** The paper focuses on the **long-short spread** (buy Decile 1, short Decile 10), which yields a significant positive return.

### 2. Exit Conditions

- **Time-based:** Positions are held for **one month**. Portfolios are reformed monthly.
- **No explicit stop-loss or take-profit:** The paper does not specify any stop-loss, take-profit, or signal-reversal exit conditions. The exit is purely based on the monthly rebalancing cycle.

### 3. Technical Indicators

The core indicator is **MAX**, with several variants. Other indicators are used as control variables.

- **Primary Indicator: MAX (Maximum Daily Return)**
    - **Definition:** The maximum daily return within a month.
    - **Formula:** `MAX_i,t = max(R_i,d)` for `d = 1, ..., D_t`, where `R_i,d` is the return on stock `i` on day `d`, and `D_t` is the number of trading days in month `t`.
    - **Calculation Period:** Past one month (21 trading days on average).
    - **Variants:**
        - **MAX(N):** Average of the N highest daily returns within the month (N=1, 2, 3, 4, 5). For example, MAX(5) is the average of the five highest daily returns.
        - **MAX over longer periods:** MAX(1) computed over the past 3, 6, and 12 months.
        - **MAX(5) over longer periods:** MAX(5) computed over the past 3, 6, and 12 months.
        - **Averaged MAX:** The maximum daily return in a month *averaged* over the past 3, 6, and 12 months.

- **Control Variables (used in bivariate sorts and cross-sectional regressions):**
    - **BETA:** Market beta estimated using Scholes-Williams (1977) / Dimson (1979) method with one lead and one lag of the market return.
    - **SIZE:** Natural logarithm of market capitalization (price × shares outstanding) at the end of month t-1.
    - **BM (Book-to-Market):** Book value of equity (from COMPUSTAT) divided by market value of equity at the end of December of the previous year. Winsorized at the 0.5% and 99.5% levels

*(truncated)*

---
*Full text: 118,660 chars*
