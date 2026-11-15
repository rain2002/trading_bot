# Protocol: Factor-ETF Market-Neutral Test (V1.0)

**Document ID**: `PROTOCOL-FACTOR-ETF-MARKET-NEUTRAL-V1-20261115`  
**Classification**: Production Quantitative Research Protocol & Market-Neutral US Sleeve  
**Author**: @Raja Nithin  
**Date**: 2026-11-15  
**Target Platform**: Alpaca Paper Trading (`ALPACA_LIVE: "0"`)  
**Trial Family Size**: $N = 5$ (`F1: SPLV`, `F2: USMV`, `F3: QUAL`, `F4: VLUE`, `F5: MTUM`)  
**Governance Authority**: Multi-Bot Trading System Master Plan (Phase 4.1: Factor-ETF Market-Neutral Test)  

---

## 1. Mandate, Scope, and Universe

### Institutional Role
This test evaluates whether US equity factor premiums (Low Volatility, Quality, Value, Momentum) generate positive risk-adjusted returns after hedging broad equity market risk with a beta-matched short index position (`SPY`). The core empirical question is:

$$\text{Does a factor ETF earn more than the market return its own beta explains?}$$

Because the factor premium itself serves as the systematic exposure, there is no cross-sectional ranking, no market timing, and no parameter tuning. This establishes an honest, low-friction market-neutral test utilizing the existing quantitative simulation and Gate A evaluation harness.

The strategy operates **strictly on paper** in Alpaca. Real US capital deployment remains barred until a separate currency risk and FX translation amendment is pre-registered.

### Universe: Factor ETFs, Hedge Instrument, and Control Set
All instruments use total-return adjusted prices (split- and dividend-adjusted):

| Role | Ticker | Factor Description / Asset Class | Launch (Approx) | Inception Note |
|---|---|---|---|---|
| **Factor Leg** | `SPLV` | Invesco S&P 500 Low Volatility ETF | May 2011 | S&P 500 100 least volatile stocks |
| **Factor Leg** | `USMV` | iShares MSCI USA Min Vol Factor ETF | Oct 2011 | MSCI USA minimum variance optimization |
| **Factor Leg** | `QUAL` | iShares MSCI USA Quality Factor ETF | Jul 2013 | High ROE, stable earnings, low leverage |
| **Factor Leg** | `VLUE` | iShares MSCI USA Value Factor ETF | Apr 2013 | Forward P/E, P/B, EV/CFO |
| **Factor Leg** | `MTUM` | iShares MSCI USA Momentum Factor ETF | Apr 2013 | 6-month & 12-month momentum |
| **Hedge Instrument** | `SPY` | SPDR S&P 500 ETF Trust | Jan 1993 | Market capitalization benchmark |

- **Dual Low-Volatility Candidates**: `SPLV` and `USMV` represent two distinct index methodologies for low-volatility; both are tested and each counts individually toward the declared trial family size ($N = 5$).
- **Data Audit Prerequisite**: Real historical launch dates must be audited from daily parquet cache prior to runner execution.

### Control Universe (15 ETFs for Null Distribution)
To evaluate whether a factor premium genuinely exceeds plain equity baskets hedged identically, a 15-ETF control universe is evaluated under the identical long/short rules over each factor's matching date window:
1. Core Sector SPDRs (11 ETFs): `XLB`, `XLE`, `XLF`, `XLI`, `XLK`, `XLP`, `XLU`, `XLV`, `XLY`, `XLRE`, `XLC`
2. Size & Style Benchmarks (4 ETFs): `MDY` (S&P MidCap 400), `IWM` (Russell 2000), `QQQ` (Nasdaq 100), `DIA` (Dow Jones Industrial Average)

### Data Windows and Partitions
- **In-Sample Period**: From each factor ETF's individual historical start date, following a **126 trading day (~6 month)** rolling beta warm-up, through `2022-12-31`.
- **Out-of-Sample Holdout**: `2023-01-03` to Present (`2026-11-13`). Explicitly designated as *partly seen*.
- **Strict Holdout Lock**: The holdout is opened **once and once only**, strictly conditional upon a candidate passing **all nine Gate A hurdles**. If no candidate passes, the holdout remains unopened.

---

## 2. Candidates, Position Sizing, and Execution Rules

### Declared Trial Family ($N = 5$)
The trial family is declared and frozen upfront at $N = 5$. Parameters and rules are immutable:

| Candidate ID | Long Leg Instrument | Short Leg Instrument | Sizing Rule | Rebalance Frequency |
|---|---|---|---|---|
| **F1** | `SPLV` (100% equity) | `SPY` ($-\min(\beta, 1.0)$) | Full beta cancel capped at 1.0 | Monthly beta refresh |
| **F2** | `USMV` (100% equity) | `SPY` ($-\min(\beta, 1.0)$) | Full beta cancel capped at 1.0 | Monthly beta refresh |
| **F3** | `QUAL` (100% equity) | `SPY` ($-\min(\beta, 1.0)$) | Full beta cancel capped at 1.0 | Monthly beta refresh |
| **F4** | `VLUE` (100% equity) | `SPY` ($-\min(\beta, 1.0)$) | Full beta cancel capped at 1.0 | Monthly beta refresh |
| **F5** | `MTUM` (100% equity) | `SPY` ($-\min(\beta, 1.0)$) | Full beta cancel capped at 1.0 | Monthly beta refresh |

### Sizing and Beta Neutrality
1. **Long Position**: Long 100% ($w_{\text{long}} = 1.00$) of portfolio equity in the factor ETF at inception.
2. **Beta Estimation**:
   - Estimated via ordinary least squares (OLS) regression of the factor ETF's daily returns against `SPY` daily returns over a rolling **126 trading day** window.
   - The estimated beta $\beta_{\text{factor}}$ is clamped to $[0.50, 1.00]$:
     $$\beta_{\text{hedged}} = \max(0.50, \min(1.00, \beta_{\text{OLS}}))$$
3. **Short Leg Sizing**:
   - Short `SPY` is sized to cancel market beta:
     $$w_{\text{SPY}} = - w_{\text{long}} \times \beta_{\text{hedged}} = - \beta_{\text{hedged}}$$
   - Gross exposure is $|w_{\text{long}}| + |w_{\text{SPY}}| \in [1.50, 2.00]$, strictly compliant with standard Regulation T margin (maximum 2× gross exposure; zero leverage beyond 100% short collateral limit).
4. **Trading Schedule**:
   - Single initial entry at start of in-sample history.
   - Monthly rebalance solely to adjust the `SPY` short hedge quantity to match the updated rolling beta.

### Execution Mechanics and Cost Modeling
- **Rebalance Trigger**: Evaluated on the closing prices of the final trading day of each calendar month.
- **Order Execution**: Fills execute at the **Open of the next trading session** ($T+1$ Open).
- **Slippage**: 2.0 basis points ($0.02\%$) per side ($0.04\%$ round-trip) applied to all executions.
- **Borrow Fees**: $0.50\%$ annualized borrow fee assessed daily on the short market value of `SPY`.
- **Financing / Cash Drag**: Short sale cash proceeds fund the long factor position; excess cash collateral earns $0.0\%$ annual interest (conservative assumption).
- **Commissions**: $\$0.00$ per share (matching Alpaca institutional structure).

---

## 3. Gate A Hurdle Criteria and Evaluation Protocol

Each candidate ($N = 5$) is evaluated over its in-sample window. To clear Gate A, a candidate must satisfy **all nine hurdles simultaneously**:

| # | Metric / Hurdle | Pass Threshold | Institutional Rationale |
|---|---|---|---|
| **H1** | **Annualized Sharpe Ratio** | $\ge 0.50$ | Net of slippage and borrow fees ($r_f = 0.0\%$). |
| **H2** | **CAGR on Total Equity** | $\ge 4.00\%$ | Minimum unleveraged real return on capital. |
| **H3** | **Maximum Drawdown** | $\ge -20.00\%$ (magnitude $\le 20.0\%$) | Capital preservation under factor drawdowns. |
| **H4** | **Worst Single Month** | $\ge -8.00\%$ (magnitude $\le 8.0\%$) | Tail-risk protection against sudden factor crashes. |
| **H5** | **Market Neutrality** | Realized $\beta \in [-0.15, +0.15]$ AND $\|\rho\| \le 0.35$ | Verifies true isolation from market index direction. |
| **H6** | **Consistency** | Positive in $\ge 70.0\%$ of rolling 3-year windows | Eliminates cyclical or regime-dependent anomalies. |
| **H7** | **Turnover Frequency** | $\le 24$ total trades per year | Limits friction (1 initial + 12 monthly adjustments). |
| **H8** | **Deflated Sharpe Ratio (DSR)** | $\ge 0.95$ ($95.0\%$) | Multi-testing deflation across $N = 5$ trials (Bailey-López de Prado). |
| **H9** | **15-ETF Control Null Test** | Real Sharpe $> 95\text{th}$ percentile of 15 controls | Verifies candidate delivers edge beyond arbitrary equity ETFs hedged identically. |

### Decision Rule
- A candidate ships to Gate B incubation if and only if it passes all 9 hurdles.
- If multiple candidates pass, the candidate with the highest Deflated Sharpe Ratio is elected champion.
- If **no candidate passes**, the Factor-ETF Market-Neutral project is immediately halted. All trial results are stamped into `trial_log.csv`, and price-only market-neutral research is terminated.

### Reported Diagnostics (Non-Hurdle Verification)
1. **Jensen's Alpha**: Annualized alpha against `SPY` with t-statistic from monthly return regressions.
2. **Sub-Period Stability**: Annualized Sharpe Ratio in the first half vs. second half of the in-sample window.
3. **SPLV vs. USMV Divergence**: Comparative consistency check between both low-volatility formulations.

### Out-of-Sample Holdout Protocol
- The holdout window (`2023-01-03` to `2026-11-13`) is **sealed**.
- It is opened **once and once only** if and only if a candidate clears all 9 Gate A hurdles.
- If no candidate clears Gate A, the runner is strictly forbidden from executing or reporting the holdout period.

---

## 4. Gate B Incubation and System Integration

Gate B applies only if a candidate passes Gate A:
1. **Broker Reconciliation**: Daily equity from positions and live quotes matches Alpaca equity within $\pm 0.10\%$.
2. **Execution Fidelity**: Next-open trade fills land within 5 bps of the theoretical opening price.
3. **Realized Market Neutrality**: Realized net beta to `SPY` stays strictly within $[-0.25, +0.25]$ over 13 weeks.
4. **Hedge Protection Drill**: Automated circuit breaker drill: if the `SPY` short order is rejected, the long position is halted/liquidated.
5. **Quote Freshness**: Zero trades on stale or halted quotes.
6. **Workflow Reliability**: Scheduled execution succeeds on $\ge 95\%$ of US equity sessions.
7. **Paper Isolation**: Registers with the Central Manager with `GATE_B_PAPER` status and a dedicated 0% real capital allocation.

---

## 5. Build Order and Review Schedule

1. **Protocol Pre-Registration (This Commit)**: This document is committed alone with its SHA-256 seal to `main` before any source code or runner modifications.
2. **Runner Fix**: Commit a targeted fix and unit test ensuring the Gate A runner opens the holdout strictly for a candidate that clears all 9 hurdles.
3. **Data Loader Extension**: Extend the data loader to fetch, cache, and audit parquet coverage for `SPLV`, `USMV`, `QUAL`, `VLUE`, `MTUM`, and the 4 size/style control ETFs (`MDY`, `IWM`, `QQQ`, `DIA`).
4. **Gate A Runner**: Implement `run_phase4_factor_etf_gate_a.py` with static factor spread, 15-ETF control null test, diagnostics, and $N = 5$ trial logging. Commit runner, execute, and stamp runner hash.
5. **Verdict**: If nothing clears, log trials and halt. If a candidate passes, proceed to bot and workflow integration.
