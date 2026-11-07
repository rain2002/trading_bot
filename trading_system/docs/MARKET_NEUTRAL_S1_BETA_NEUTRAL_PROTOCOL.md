# Pre-Registered Research Protocol: S1 Beta-Neutral Cross-Sectional Momentum
**Document ID**: `PROTOCOL-MKT-NEUTRAL-S1-BETA-NEUTRAL-20261107`  
**Classification**: Institutional Pre-Registration Document (Fiduciary Stage 1)  
**Status**: PRE-REGISTERED (LOCKED PRIOR TO SIMULATION EXECUTION)  
**Creation Date**: 2026-11-07  
**In-Sample Window**: 2007-09-24 to 2024-12-31 (17.27 Years | 4,235 Trading Days)  
**Out-of-Sample Holdout**: 2025-01-01 to 2025-12-31 (Strictly Sealed & Blinded)  
**Governance Authority**: FINAL_MASTER_HEDGE_FUND_ROADMAP.md (Section 3, Chapter 2)

---

## 1. Research Hypothesis & Theoretical Motivation

Standard equity momentum strategies (Jegadeesh & Titman, 1993) suffer from two structural vulnerabilities in long-only portfolios:
1. **Pervasive Market Beta**: Long-only momentum exhibits a beta $\beta \approx 1.0$ to the broader equity market, rendering its performance dependent on macroeconomic bull regimes and suffering devastating drawdowns during equity bear markets.
2. **Momentum Crashes**: As established by **Barroso and Santa-Clara (2015)** (*Journal of Financial Economics*, 116(1), 111-120) and **Daniel and Moskowitz (2016)** (*Journal of Financial Economics*, 122(2), 221-247), cross-sectional momentum experiences severe, predictable crashes when recovering from panic bear markets, caused by past losers experiencing explosive high-beta rallies while past winners lag.

**Hypothesis**: By constructing a **Beta-Neutral Long-Short Portfolio** ($\sum_{i} \beta_i w_i = 0$) combined with the **Barroso & Santa-Clara (2015) Realized Volatility Scaling Rule**, the strategy will isolate pure cross-sectional stock-picking alpha, completely eliminate market directional risk, and avoid momentum crashes.

---

## 2. Point-in-Time Universe & Survivorship Immunity

1. **Universe**: Point-in-time constituents of the **Nifty 50 Index**.
2. **Constituent Tracking**: Sourced from official dated records (`nifty50_membership_changes.csv`), with verified additions, deletions, and effective dates.
3. **Survivorship Invariant**: On any trading day $t$, the candidate pool contains strictly and exactly the 50 active index constituents on that date.
4. **Corporate Actions**: Backward split-adjusted daily OHLC prices from Yahoo Finance cache (`trading_system/data/historical_cache_nse/`). Unadjusted cash dividends are credited to cash upon ex-dividend dates.

---

## 3. Signal Mechanics & Ranking Pipeline

1. **Momentum Lookback ($12-1$ and $6-1$ Rule)**:
   - To eliminate the 1-month short-term reversal anomaly (Jegadeesh & Titman, 1993), returns are computed skipping the most recent 21 trading days (1 calendar month):
     $$R_{i, t}^{12-1} = \frac{P_{i, t-21}}{P_{i, t-252}} - 1$$
     $$R_{i, t}^{6-1} = \frac{P_{i, t-21}}{P_{i, t-126}} - 1$$
   - **Trend Consistency**: Log-linear regression slope multiplied by the coefficient of determination: $\text{Rank Score}_i = \text{Slope}_i \times R_i^2$.

2. **Rolling Beta Estimation**:
   - For each constituent $i$, rolling 60-day market beta with respect to Nifty 50 ($I$):
     $$\beta_{i, t} = \frac{\text{Cov}_{60}(r_{i}, r_{I})}{\text{Var}_{60}(r_{I})}$$

3. **Beta-Neutral Long-Short Portfolio Construction**:
   - Long Leg ($L$): Top quintile (Top 10 momentum stocks).
   - Short Leg ($S$): Bottom quintile (Bottom 10 momentum stocks) or synthetic beta-matched index future hedge.
   - Weights $w_i^L > 0$ and $w_i^S < 0$ are solved subject to:
     $$\sum_{i \in L} w_i^L = +1.0, \quad \sum_{j \in S} |w_j^S| = 1.0 \quad (\text{Dollar Neutral})$$
     $$\beta_{\text{portfolio}} = \sum_{i \in L} w_i^L \beta_i + \sum_{j \in S} w_j^S \beta_j = 0.0 \quad (\text{Beta Neutral})$$

4. **Barroso & Santa-Clara (2015) Volatility-Managed Momentum Scaling**:
   - The strategy measures 20-day annualized realized volatility of the daily momentum portfolio returns:
     $$\hat{\sigma}_{t} = \sqrt{252} \times \sqrt{\frac{1}{19} \sum_{k=0}^{19} (r_{t-k}^{MOM} - \bar{r}^{MOM})^2}$$
   - Dynamic exposure scaling:
     $$W_t = \min\left(1.50, \; \frac{\sigma_{\text{target}}}{\hat{\sigma}_t}\right), \quad \text{where } \sigma_{\text{target}} = 10.0\%$$
   - **Crash Guard**: When $\hat{\sigma}_t \ge 35.0\%$, portfolio exposure drops to 0.0 (100% Cash Buffer) until $\hat{\sigma}_t < 25.0\%$ for 10 consecutive trading days.

5. **Rebalancing Frequency**: Monthly (first trading day of each calendar month).

---

## 4. Statutory Friction, Borrowing Costs, & Slippage Model

1. **Short Borrowing / Financing Cost**: RBI Repo Rate + 200 bps annualized, charged daily on short leg notionals.
2. **Cash Margin Yield**: Unencumbered cash earns the RBI Repo Rate minus 65 bps (Liquid ETF TER/cash drag), net of 31.2% slab taxation.
3. **Execution Slippage**: 10.0 bps per stock leg (Normal) | 15.0 bps (Stressed Gate A).
4. **Securities Transaction Tax (STT)**: 0.10% on deliveries, 0.025% on derivative hedges.
5. **Exchange & Statutory Fees**: NSE Turnover (0.00297%), SEBI turnover (0.0001%), Stamp Duty (0.015% on buys).
6. **DP Charges**: ₹14.75 flat per delivery sell leg.

---

## 5. Mandatory Gate A Clearance Hurdles

To achieve institutional clearance under Gate A, S1 must satisfy all criteria simultaneously over the 2007-09-24 to 2024-12-31 in-sample period:

| Metric | Hurdle Threshold | Rationale |
| :--- | :--- | :--- |
| **Market-Neutral Sharpe Ratio** | $\ge 1.00$ | True alpha must exhibit institutional risk-adjusted consistency |
| **Post-Friction, Post-Tax CAGR** | $\ge 8.00\%$ | Net positive wealth accumulation above cash drag and financing costs |
| **Maximum Drawdown (Peak-to-Trough)** | $\le -15.00\%$ | Market-neutrality must strictly contain drawdowns |
| **Market Beta ($\beta_{NSE}$)** | $|\beta| \le 0.05$ | Absolute neutrality to directional market trends |
| **Jensen's Alpha $t$-Statistic** | $t_{\alpha} \ge 2.50$ | Statistically significant at the 99% confidence level |
| **Closed Trades Sample Size** | $\ge 100$ trades | Sufficient degrees of freedom against data mining |
| **2025 Calendar Holdout** | STRICTLY SEALED | Out-of-sample holdout must remain 100% untouched |

---

## 6. Pre-Registration Integrity Hash
This protocol is committed **alone** to git prior to writing backtest code or running historical simulations.
