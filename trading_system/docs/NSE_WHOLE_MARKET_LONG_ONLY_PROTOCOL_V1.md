# Protocol: NSE Whole-Market Long-Only Bot (V1.0)

**Document ID**: `PROTOCOL-NSE-WHOLE-MARKET-LONG-ONLY-V1-20261115`  
**Classification**: Production Quantitative Research Protocol & Indian Equities Satellite Sleeve  
**Author**: @Raja Nithin  
**Date**: 2026-11-15  
**Target Platform**: Live Paper Trading / Zerodha-Groww Paper Pipeline (`GATE_B_PAPER`)  
**Declared Trial Family**: $S_2$ (Asymmetric Profit-Trail Compounder) + Honest Prior History ($N \ge 82$)  
**Governance Authority**: Multi-Bot Trading System Master Plan (Phase 5: NSE Whole-Market Alpha Sleeve)  

---

## 1. Context, Starting Baseline, and Fiduciary Mandate

### Rejection and Invalidation of Un-Preregistered & Survivor-Biased Numbers
Previous exploratory runs reporting CAGR of 17.77%–18.55% with Sharpe ratios of 1.30–1.35 are **formally rejected and declared invalid** for institutional deployment. This protocol supersedes the legacy `GROWTH_STOCK_MOMENTUM_PROTOCOL.md`. An internal quantitative audit revealed:
1. **Survivorship Bias**: The previous exploratory runner loaded cached `*-NS` parquet files, mechanically truncating historical bankruptcies, delistings, and liquidations.
2. **Honest Baseline Evidence**: Point-in-time, survivor-free runs of this strategy family across historical NSE Bhavcopy data yielded between **5.4% and 5.61% CAGR** with Sharpe ratios of **0.37 to 0.63** (e.g. Causal Top-500 with Vol Radar: 5.61% CAGR / -30.4% MaxDD / 0.47 Sharpe; Nifty 50 PIT: 5.4% CAGR / 0.63 Sharpe; Nifty 100 PIT Plain Momentum: 11.4% CAGR / 0.37 Sharpe).
3. **Post-Hoc Knobs**: The multi-tiered trailing stop ladder and volatility radar overlay contained parameters adjusted post-hoc on the evaluation sample.
4. **Historical Log Invalidation**: All prior exploratory rows in `trial_log.csv` claiming $> 15\%$ CAGR on survivor-biased NSE data are marked invalid.

### Realistic Institutional Expectation
The honest survivor-free expectation for systematic momentum across Indian equities sits at **5% to 8% CAGR**. This protocol subjects the strategy family to unyielding institutional hurdles. If the survivor-free Gate A evaluation does not decisively clear all 9 hurdles, **the NSE stock bot is permanently parked**, and the portfolio relies solely on the proven Phase 1 ETF + Phase 3 Cash core.

---

## 2. Universe Definition: Entire NSE Market (Point-in-Time, Survivor-Free)

1. **Constituent Universe**:
   - All equity series (`EQ`, `BE`, `SM`) actively traded on the National Stock Exchange of India (NSE) on each historical session, sourced directly from daily official NSE Bhavcopy records.
   - Fully inclusive of all tickers subsequently delisted, suspended, merged, or declared bankrupt. Zero survivorship filtering.
2. **Liquidity Quality Filter** (Evaluated on every rebalance date):
   - **Traded Value**: 60-day median daily turnover of at least **₹2.0 crore** (INR 20,000,000) per session.
   - **Seasoning**: Actively listed and traded for at least **12 calendar months** (252 trading sessions) prior to eligibility.
   - **Circuit Limit Filter**: Any stock locked at an upper or lower circuit band on the signal date is strictly barred from entry or exit execution.
   - **Surveillance Exclusion**: Any stock flagged under SEBI/NSE Enhanced Surveillance Measure (ESM), Additional Surveillance Measure (ASM), or Graded Surveillance Measure (GSM) stages is excluded.
3. **Corporate Actions & Adjustments**:
   - Backward split- and bonus-adjusted price series verified against official NSE corporate actions.
   - Cash dividends credited at historical ex-dates to total portfolio cash.
4. **Size Tiers**:
   - Market capitalization buckets (Large, Mid, Small, Micro) are tracked strictly for exposure attribution and portfolio caps, never as stock-selection criteria.

---

## 3. Pre-Registered Strategy Candidate & Empirical Controls

To eliminate multi-variant cherry-picking, the strategy candidate is frozen as written. Candidate $S_1$ (Wide-Trend Runner) was retired prior to pre-registration due to parameter instability across commits. Candidate $S_2$ is pre-registered as the sole active strategy candidate.

### Candidate S2: Asymmetric Profit-Trail Compounder
- **Philosophy**: Multi-stage trend runner with asymmetric trailing profit protection allowing multi-bagger compounders room to run while protecting harvested gains.
- **Momentum Score**: Blended score of 60% 90-day ($\text{Slope} \times R^2$) + 40% 180-day ($\text{Slope} \times R^2$). Minimum threshold $> 0.15$.
- **Portfolio Slots**: 15 equal-weighted positions (maximum 8.0% allocation per stock at entry).
- **Developing Trend Exit**: Daily Close $< 150$-day Simple Moving Average (SMA).
- **Initial Hard Stop**: **-12.0%** from trade execution price.
- **Trailing Profit Tiers**:
  - Gain $\ge +25\%$: Trail stop set to **-15.0%** from peak price.
  - Gain $\ge +50\%$: Trail stop set to **-20.0%** from peak price.
  - Gain $\ge +100\%$: Trail stop set to **-25.0%** from peak price (allowing compounding multi-baggers wide volatility tolerance).
- **Macro Volatility Radar Overlay**:
  - Pre-registered directly into strategy logic before any backtest execution.
  - When the benchmark (Nifty 500) closes below its 200-day SMA, all new buy orders are frozen.
  - Unallocated cash compounds daily in risk-free overnight repo yield (`LIQUIDBEES` model @ 6.0% p.a.).
- **Staged Drawdown Ladder**:
  - Drawdown from lifetime HWM $\in [-8\%, -14\%]$: Exposure capped at 70%.
  - Drawdown from lifetime HWM $\in [-14\%, -18\%]$: Exposure capped at 40%.
  - Drawdown from lifetime HWM $< -18\%$: 0% exposure (Emergency cash defense; open positions queued for liquidation at next open).

### Empirical Control Benchmarks
1. **Control A (Random-Selection Null Distribution)**:
   - 1,000 Monte Carlo iterations selecting random liquid stocks from the identical survivor-free universe with identical turnover, slot count (15), fee structure, and volatility radar overlay.
   - The candidate must beat the **95th percentile Sharpe Ratio** ($p_{95}$) of this distribution.
2. **Control B (Equal-Weight Liquid Top-100)**:
   - Monthly rebalanced equal-weighted basket of the Top 100 most liquid NSE stocks.
   - Proves whether performance stems from genuine stock-picking alpha or unmanaged small/mid-cap market beta.
3. **Passive Benchmark**:
   - Nifty 500 Total Return Index (Buy-and-Hold).

### Honest Trial Family Accounting ($N$)
- Total trial family size $N$ is declared as:
  $$N = S_2 + N_{\text{prior}} = 1 + 81 = 82$$
  where $N_{\text{prior}} = 81$ represents every earlier exploratory NSE momentum trial recorded in `trial_log.csv`.
- The Deflated Sharpe Ratio (DSR) must be calculated using this cumulative $N \ge 82$, strictly penalizing all prior data mining.
- Zero post-hoc variants are permitted after observing backtest returns.

---

## 4. Gate A Hurdle Criteria

To clear Gate A, Candidate $S_2$ must pass **all nine hurdles simultaneously** over the survivor-free in-sample period (`2007-09-03` to `2022-07-05`, ~15 years):

| # | Hurdle Metric | Pass Threshold | Institutional Rationale |
|---|---|---|---|
| **H1** | **Excess CAGR over Benchmark** | $\ge \text{Nifty 500 CAGR} + 4.00\%$ | Minimum alpha margin over passive index. |
| **H2** | **Annualized Sharpe Ratio** | $\ge 0.80$ | Net of all costs, slippage, and DP fees ($r_f = 0.0\%$). |
| **H3** | **Maximum Drawdown** | $\ge -35.00\%$ (magnitude $\le 35.0\%$) | Absolute capital preservation across severe market crises (2008, 2020). |
| **H4** | **Deflated Sharpe Ratio (DSR)** | $\ge 0.95$ ($95.0\%$) | Multi-testing deflation across honest cumulative $N \ge 82$ trials. |
| **H5** | **Random-Selection Null Test** | Sharpe $> 95\text{th}$ percentile of Control A | Proves stock-picking skill exceeds random selection. |
| **H6** | **Passive Liquidity Null Test** | Sharpe $>$ Control B AND CAGR $>$ Control B | Proves alpha exceeds unmanaged equal-weight liquidity beta. |
| **H7** | **Multi-Cycle Sub-Period Stability**| Positive excess return in $\ge 3$ of 4 equal sub-periods | Rejects episodic return spikes; verifies regime persistence. |
| **H8** | **Parameter Plateau Sensitivity** | Sharpe $\ge 0.70$ across all $\pm 20\%$ parameter shifts | Validates absence of fragile, razor-thin parameter overfit. |
| **H9** | **Severe Cost & Slippage Stress** | Passes hurdles at $2\times$ baseline costs (30 bps/side) | Verifies resilience against real-world liquidity friction and impact cost. |

### Strict Out-of-Sample Holdout Protocol
- The **last 2 calendar years** of available causal data (`2022-07-06` to `2024-07-05`) are strictly sealed and excluded from all in-sample backtests and parameter sensitivity runs.
- The holdout is opened **once and once only**, strictly conditional upon Candidate $S_2$ passing all 9 Gate A hurdles. If $S_2$ fails Gate A, the holdout remains sealed.

---

## 5. Bot Architecture & Execution Constraints (Gate B Incubation)

If and only if Candidate $S_2$ clears Gate A, Bot 4 is constructed under these strict constraints:
1. **Instrument Mandate**: Cash delivery equities only (`CNC`). Zero overnight short positions (strictly barred under SEBI equity rules). Zero derivatives, leverage, or intraday margin.
2. **Execution Timing**: Signals generated at daily close (15:45 IST); orders execute at the next market open (09:15 IST) with modeled slippage.
3. **Portfolio Caps**: Maximum 15–20 positions, single-stock exposure capped at 8.0% of bot equity, sector exposure capped at 25.0%.
4. **Fail-Closed Safety**: Any stale quote, missing bhavcopy record, or circuit-locked price halts order placement.
5. **Manager Allocation & Risk Governance**:
   - Central Manager allocates **0% capital** during the mandatory 13-week Gate B paper trading incubation.
   - Upon successful Gate B completion, Bot 4 receives a capped allocation of **maximum 20% of portfolio NAV**, scaling strictly with live audited performance.
   - Runs sequentially as Bot 4 in the daily paper trading pipeline without modifying the 3 frozen paper bots.

---

## 6. Pre-Commitment Build Order

1. **Protocol Pre-Registration (This Commit)**: This document is committed alone with its SHA-256 seal to `main` before any code is executed.
2. **Runner Implementation**: Build `run_phase5_nse_whole_market_gate_a.py` utilizing survivor-free causal Bhavcopy records, implementing Candidate $S_2$, Controls A and B, parameter plateau tests, and 2× cost stress.
3. **Audit Stamping**: Execute runner, stamp runner commit hash into `trial_log.csv`, and record comprehensive results.
4. **Gate A Verdict**: If failed, record result and permanently park the NSE bot. If passed, build Bot 4 for Gate B incubation.

---

## 7. Approved Decisions (Fiduciary Sign-Off)

- [x] **Decision 1**: Entire NSE point-in-time universe with ₹2 crore median daily turnover liquidity filter: **YES**.
- [x] **Decision 2**: The nine hurdles in Section 4 (including $\ge 4.0\%$ CAGR margin over Nifty 500): **YES**.
- [x] **Decision 3**: Honest cumulative trial accounting ($N \ge 82$) penalizing all prior exploratory runs, with zero post-hoc variants: **YES**.
- [x] **Decision 4**: Bot 4 capped at maximum 20% of portfolio NAV post-Gate B, scaling only with live forward track record: **YES**.
