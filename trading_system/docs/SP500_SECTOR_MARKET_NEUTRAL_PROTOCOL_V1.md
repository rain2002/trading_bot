# Protocol: S&P 500 Sector Market-Neutral Bot (V1.0)

**Document ID**: `PROTOCOL-SP500-SECTOR-MARKET-NEUTRAL-V1-20261114`  
**Classification**: Production Quantitative Trading Protocol & Market-Neutral US Sleeve  
**Author**: @Raja Nithin  
**Date**: 2026-11-14  
**Target Platform**: Alpaca Paper Trading (`ALPACA_LIVE: "0"`)  
**Trial Family Size**: $N = 3$ (`M1`, `R1`, `L1`)  
**Governance Authority**: Multi-Bot Trading System Master Plan (Phase 4: S&P 500 Sector Market-Neutral Bot)  

---

## 1. Mandate, Scope, and Universe

### Institutional Role
This protocol governs the system's first market-neutral quantitative strategy. The bot buys the strongest or weakest US equity sectors and hedges broad market exposure by shorting the market index (or anti-momentum sector basket), isolating the cross-sectional alpha spread from directional equity market beta.

The strategy operates **strictly on paper** in Alpaca. Real US capital deployment is barred until a formal currency risk and cash translation rule is pre-registered.

### Universe: Sector ETFs vs. Single Stocks
- **Rationale**: Historical single-stock backtests suffer from survivorship bias because delisted US stocks lack affordable survivorship-free daily pricing (artificially truncating the bottom decile). US Sector SPDR ETFs are survivor-bias free: sector funds mechanically reflect all member additions, removals, and bankruptcies. Furthermore, sector ETFs eliminate idiosyncratic single-stock bankruptcy risk, have high liquidity, and have zero commission on Alpaca. The trade-off is a tighter, more competitive cross-sectional spread.
- **Instruments & Inception Dates**:
  All instruments use split- and dividend-adjusted prices (Total Return):

  | Group | Tickers | Launch Date | Inception Note |
  |---|---|---|---|
  | **Core Nine Sectors** | `XLB`, `XLE`, `XLF`, `XLI`, `XLK`, `XLP`, `XLU`, `XLV`, `XLY` | Dec 1998 | Continuous trading history from 1998 |
  | **Real Estate** | `XLRE` | Oct 2015 | Carved out of Financials (`XLF`) |
  | **Communication Services**| `XLC` | Jun 2018 | Carved out of Info Tech (`XLK`) and Discretionary (`XLY`) |
  | **Hedge Instrument** | `SPY` | Jan 1993 | S&P 500 broad market tracker |

- **Strict Inception Rule**: A sector enters the cross-sectional ranking basket strictly on its first valid historical trading session. No back-filled synthetic data is permitted. Before October 2015, the universe comprises 9 sectors; from October 2015 to June 2018, 10 sectors; from June 2018 onward, all 11 sectors.

### Data Windows & Partitions
- **In-Sample Period**: `2000-01-03` to `2022-12-31` (23 full calendar years, spanning the 2000–2002 dot-com bust, 2007–2009 Global Financial Crisis, and 2022 inflation/rate shock).
- **Out-of-Sample Holdout**: `2023-01-01` to Present (`2026-11-14`). Labelled explicitly as *partly seen* due to historical US research conducted in 2025. The holdout is opened **once and once only for the single winning candidate**.
- **Forward Paper Horizon**: 13 weeks of live Alpaca paper trading (Gate B incubation).

### Position Limits & Constraints
- Long and short exchange-traded funds (ETFs) only.
- Single stocks, options, and futures are barred.
- **Gross exposure cap**: Total gross exposure $\le 1.0$ (strictly zero leverage).

---

## 2. Candidate Strategies, Sizing, and Execution

### Declared Trial Family ($N = 3$)
To enforce statistical validity and eliminate hidden trial degrees of freedom, the trial family is frozen at $N = 3$. Parameters are fixed a priori and cannot be tuned:

| Candidate ID | Signal Generation (Month-End Close) | Long Leg Composition | Short Leg Composition |
|---|---|---|---|
| **M1** | 12-month total return skipping the most recent month (12-1 Momentum) | Top 3 sectors, equal weight (16.67% each; 50% equity total) | `SPY`, sized to cancel long leg's rolling beta |
| **R1** | 1-month (21-day) total return reversal (Short-Term Mean Reversion) | Bottom 3 sectors, equal weight (16.67% each; 50% equity total) | `SPY`, sized to cancel long leg's rolling beta |
| **L1** | 12-month total return skipping the most recent month (12-1 Momentum) | Top 3 sectors, equal weight (16.67% each; 50% equity total) | Bottom 3 sectors, equal weight, sized to cancel top 3 beta |

*Context*: Sector momentum was empirically documented by Moskowitz and Grinblatt (1999). Short-term reversal (`R1`) and long/short sector spreads (`L1`) represent standard cross-sectional benchmarks. At least one candidate is expected to fail.

### Sizing and Beta Neutrality
1. **Long Leg**: Allocated exactly 50% ($0.50$) of portfolio equity, equally distributed across the 3 selected sectors ($16.67\%$ each).
2. **Rolling Beta Estimation**:
   - Beta is estimated using an ordinary least squares (OLS) regression of the synthetic long leg daily returns against `SPY` daily returns over a rolling **126 trading day** window (~6 calendar months).
   - The estimated beta $\beta_{\text{long}}$ is strictly clamped to the range $[0.50, 1.50]$ to prevent extreme sizing artifacts during sudden volatility spikes.
3. **Short Leg Sizing**:
   - For `M1` and `R1`: The hedge weight in `SPY` is set to cancel the long leg's market beta:
     $$w_{\text{SPY}} = - w_{\text{long}} \times \beta_{\text{long}} = - 0.50 \times \beta_{\text{long}}$$
     Since $\beta_{\text{long}} \in [0.50, 1.50]$, the short `SPY` exposure spans $[-0.25, -0.75]$.
   - For `L1`: The short leg consists of the bottom 3 sectors equal-weighted, sized to offset the top 3 beta:
     $$w_{\text{short}} = - 0.50 \times \frac{\beta_{\text{top3}}}{\beta_{\text{bottom3}}}$$
     clamped to $[-0.50, -0.25]$.
4. **Gross Exposure Constraint**:
   - Total gross exposure is defined as $|w_{\text{long}}| + |w_{\text{short}}|$.
   - If total gross exposure exceeds $1.00$, both long and short weights are scaled down proportionally:
     $$\text{Scale} = \frac{1.00}{|w_{\text{long}}| + |w_{\text{short}}|}$$
     ensuring zero portfolio leverage at all times.

### Execution Protocol and Cost Modeling
- **Signal Frequency**: Monthly rebalance evaluated on the closing prices of the final trading session of each calendar month.
- **Execution Timing**: Trades execute at the **Open of the next trading session** ($T+1$ Open).
- **Slippage**: 2.0 basis points ($0.02\%$) per side ($0.04\%$ round-trip) applied to all executions.
- **Commission**: $\$0.00$ per share, reflecting Alpaca Securities institutional zero-commission equity pricing.
- **Borrow Fees**: $0.50\%$ annualized borrow fee assessed daily on the short market value (`SPY` or short ETF basket).
- **Cash Drag / Collateral Yield**: Cash collateral earns $0.0\%$ annual interest (conservative assumption).

---

## 3. Gate A Hurdle Criteria and Evaluation Protocol

All 3 candidates ($N = 3$) are evaluated over the in-sample period (`2000-01-03` to `2022-12-31`). To pass Gate A, a candidate must satisfy **all nine hurdles simultaneously**:

| # | Metric / Hurdle | Pass Threshold | Institutional Rationale |
|---|---|---|---|
| **H1** | **Annualized Sharpe Ratio** | $\ge 0.50$ | Net of all slippage and borrow costs ($r_f = 0.0\%$). |
| **H2** | **CAGR on Total Equity** | $\ge 4.00\%$ | Minimum unleveraged real return on capital. |
| **H3** | **Maximum Drawdown** | $\ge -20.00\%$ (magnitude $\le 20.0\%$) | Peak-to-trough capital preservation. |
| **H4** | **Worst Single Month** | $\ge -8.00\%$ (magnitude $\le 8.0\%$) | Tail-risk protection against sudden sector rotations. |
| **H5** | **Market Neutrality** | Realized $\beta \in [-0.15, +0.15]$ AND $\|\rho\| \le 0.35$ | Verifies genuine market independence to `SPY`. |
| **H6** | **Consistency** | Positive in $\ge 70.0\%$ of rolling 3-year windows | Rejects episodic return regimes; verifies persistence. |
| **H7** | **Turnover Frequency** | $\le 60$ total round-trip trades per year | Limits friction and turnover churn. |
| **H8** | **Deflated Sharpe Ratio (DSR)** | $\ge 0.95$ ($95.0\%$) | Corrects for multiple testing across $N = 3$ trials via Bailey-López de Prado formula. |
| **H9** | **Random-Selection Null Test** | Real Sharpe $> 95\text{th}$ percentile of 1,000 runs | Monte Carlo test picking random sectors with identical hedge and costs. |

### Decision Rule
- A candidate ships to Gate B incubation if and only if it passes all 9 hurdles.
- If multiple candidates pass, the candidate with the highest Sharpe Ratio is designated champion.
- If **no candidate passes**, the S&P 500 Sector Market-Neutral project is immediately halted. All trial results are logged into `trial_log.csv`, and no bot, adapter, or workflow code is constructed.

### Robustness Diagnostics (Reported, Excluded from $N$)
The winning candidate is subjected to parameter sensitivity tests without selection bias:
1. **Sector Breadth**: Evaluated holding Top 2 and Top 4 sectors (vs. base 3).
2. **Lookback Horizon**: Evaluated at 9-month and 11-month momentum lookbacks (vs. base 12-1).
3. **Diagnostic Hurdle**: Sharpe Ratio must remain $\ge 0.30$ across all 4 diagnostic variations. A strategy that only functions at exactly $K = 3$ sectors and 12-month lookback is discarded as spurious overfit.

### Out-of-Sample Holdout Verification
- Evaluated **once and once only** on the single winning candidate over `2023-01-01` to Present (`2026-11-14`).
- Must maintain a positive annualized Sharpe Ratio ($> 0.00$) and Maximum Drawdown $\ge -20.00\%$.
- DSR is reported for audit records but not penalized due to sample size constraints ($< 4$ years).

---

## 4. Gate B Incubation and System Integration

### Pass Conditions (13 Weeks Alpaca Paper Trading)
1. **Reconciliation Precision**: Recomputed daily equity from positions and live market prices matches Alpaca broker equity within $\pm 0.10\%$.
2. **Execution Fidelity**: Next-open trade fills land within 5 bps of the theoretical opening benchmark price.
3. **Realized Market Neutrality**: Realized net beta to `SPY` stays strictly within $[-0.25, +0.25]$ over the 13-week period.
4. **Hedge Protection Drill**: The bot passes an automated circuit breaker drill: if the `SPY` short order fails or is rejected, the bot immediately aborts the long sector leg rather than running unhedged.
5. **Quote Freshness**: Zero orders placed on stale, missing, or halted quotes.
6. **Workflow Reliability**: The scheduled execution runs successfully on $\ge 95\%$ of US equity trading sessions without manual state recovery.

### Execution Workflow Architecture
- **Dedicated Workflow**: `.github/workflows/daily_us_market_neutral_pipeline.yml`.
- **Schedule**: Weekdays at `21:45 UTC` (~5:45 PM EDT / 4:45 PM EST), safely after the 4:00 PM US equity market close.
- **Order Placement**: Submits next-day Market-on-Open (MOO) or market opening orders for execution at 9:30 AM New York time.
- **State Persistence**: Checks out and commits state to the central `state` branch under the shared concurrency group `trading-state`.
- **Security Guard**: `ALPACA_LIVE: "0"` strictly enforced. Credentials guarded against leakage.

### Manager Bot Interface & Currency Isolation
- **Paper Capital Allocation**: The S&P Bot registers with the Central Manager as a paper bot (`GATE_B_PAPER`) with a dedicated **0% real capital allocation share**.
- **Currency Isolation**: Central Manager NAV is accounted in Indian Rupees (₹ INR), whereas Alpaca paper equity is in US Dollars ($ USD).
- **Rule of Isolation**: The S&P Bot equity is strictly partitioned from the Manager's consolidated rupee NAV ledger. Real US capital deployment and rupee ledger integration require a separately pre-registered Currency and FX Risk Protocol Amendment.

---

## 5. Build Order and Pre-Commitment Schedule

1. **Protocol Pre-Registration**: This protocol is committed alone with its SHA-256 seal to `main` before any source code is created.
2. **Data Loader & Coverage Audit**: Build cached adjusted daily data loader for `XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY, XLRE, XLC, SPY` and generate data coverage report.
3. **Gate A Runner**: Commit `run_phase4_sp500_sector_gate_a.py`, run candidates $N = 3$, execute 1,000-run Monte Carlo null test, run diagnostics, open holdout once for champion, and stamp runner commit into `trial_log.csv`.
4. **Gate A Verdict**: If failed, record and halt. If passed, proceed to implementation.
5. **Bot Implementation**: Implement `trading_system/app/bots/sp500_sector_market_neutral_bot.py` with fail-closed hedge logic and Alpaca paper adapter.
6. **Workflow Implementation**: Build `.github/workflows/daily_us_market_neutral_pipeline.yml`.
7. **Comprehensive Unit Tests**: Test beta-cancel sizing, hedge-failure abortion, stale quote refusal, month-end triggers, and Alpaca paper reconciliation.
