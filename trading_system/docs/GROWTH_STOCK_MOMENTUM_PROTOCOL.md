# PRE-REGISTERED QUANTITATIVE GROWTH STOCK MOMENTUM PROTOCOL (v1.0)
**Fiduciary Standard for Autonomous Equity Trading Across Indian Equities (NSE)**

---

## 1. Executive Mandate & Economic Hypothesis
This protocol governs the pre-registered execution and out-of-sample forward evaluation of the **Indian Equities Growth Momentum Pod**.
- **Objective**: Target 15.0% – 20.0% post-tax geometric compound annual growth rate (CAGR) over full market cycles by harvesting cross-sectional momentum and multi-bagger trend-following across liquid Large and Midcap Indian equities.
- **Risk Invariant**: Lifetime maximum portfolio drawdown must never exceed **-30.00%** ($HWM_{\text{true}}$ never resets).
- **Core Premise**: Cross-sectional momentum dispersion is concentrated in high-growth midcaps and emerging industry leaders rather than mega-caps. By combining:
  1. Exponential regression momentum ranking ($\text{Annualized Slope} \times R^2$)
  2. Multi-tiered trailing stops that allow asymmetric multi-baggers to compound while locking in substantial gains
  3. Strict macro regime cash protection (freezing new equity purchases when the benchmark is below its 200-SMA, allowing idle cash to compound in sovereign liquid ETF yield)
  4. Staged Drawdown Ladder defense (-8% / -14% / -18% / -20% with emergency cash defense)
the strategy achieves institutional compound returns while strictly constraining drawdown.

---

## 2. Universe Definition & Liquidity Quality Filter
- **Universe**: Liquid Indian equities listed on the National Stock Exchange (NSE).
- **Minimum Share Price**: $\ge \text{INR } 20.00$ to eliminate illiquid penny stocks, lower-circuit locks, and microcap manipulation.
- **Minimum History**: 100 trading days of causal price history before eligibility.
- **Corporate Action Invariant**: Backward split-adjusted parquet prices from Yahoo Finance must never multiply share counts on corporate split events (split regression invariant strictly enforced).

---

## 3. Pre-Registered Strategy Variants (Frozen Specifications)

| Parameter / Feature | Variant 1: Wide-Trend Runner | Variant 2: Asymmetric Multi-Bagger | Variant 3: Breakout Compounder |
| :--- | :--- | :--- | :--- |
| **Philosophy** | Long-term trend-following on leaders | Multi-stage runner with profit protection | 52-week high breakout compounder |
| **Max Core Positions** | 10 slots (10.0% base target) | 10 slots (10.0% base target) | 10 slots (10.0% base target) |
| **Momentum Metric** | 90-day Exp Slope $\times R^2$ | Blended 90d (60%) + 180d (40%) Slope $\times R^2$ | 90-day Exp Slope $\times R^2$ |
| **Breakout Filter** | None | None | Price within 15% of 52-week high |
| **Min Momentum Score** | $> 0.15$ | $> 0.15$ | $> 0.20$ |
| **Developing Trend Exit** | Daily Close $< 200$-SMA | Daily Close $< 150$-SMA | Daily Close $< 100$-SMA |
| **Initial Hard Stop** | **-15.0%** from fill price | **-12.0%** from fill price | **-10.0%** from fill price |
| **Trailing Profit Tiers** | • $\ge +20\%$ gain: Trail -15% from peak<br>• $\ge +40\%$ gain: Trail -20% from peak | • $\ge +25\%$ gain: Trail -15% from peak<br>• $\ge +50\%$ gain: Trail -20% from peak<br>• $\ge +100\%$ gain: Trail -25% from peak | • $\ge +15\%$ gain: Trail -10% from peak<br>• $\ge +30\%$ gain: Trail -15% from peak<br>• $\ge +60\%$ gain: Trail -20% from peak |
| **Macro Bear Defense** | Benchmark $< 200$-SMA: Freeze new buys | Benchmark $< 200$-SMA: Freeze new buys + Trail -12% on developing winners | Benchmark $< 200$-SMA: Freeze new buys |
| **Execution Timing** | Next-Day 09:15 IST Market Open | Next-Day 09:15 IST Market Open | Next-Day 09:15 IST Market Open |

---

## 4. Institutional Risk Officer & Drawdown Ladder Architecture
1. **Double High-Water Mark Architecture**:
   - $HWM_{\text{true}}$: Lifetime peak equity. Never resets. Governs strategy Max Drawdown and hard breach detection.
   - $HWM_{\text{ladder}}$: Operating reference for ladder recovery stages.
2. **Four-Tier Drawdown Exposure Ladder**:
   - Tier 1: Drawdown $\in [0\%, -8.0\%] \implies 100\%$ exposure allowed.
   - Tier 2: Drawdown $\in [-8.0\%, -14.0\%] \implies 70\%$ exposure allowed.
   - Tier 3: Drawdown $\in [-14.0\%, -18.0\%] \implies 40\%$ exposure allowed.
   - Tier 4: Drawdown $< -18.0\% \implies 0\%$ exposure (Emergency Cash Defense).
3. **Emergency State Machine Recovery**:
   - When Tier 4 triggers, all open positions are queued for immediate liquidation at next market open.
   - Minimum **15 trading days** cool-off period.
   - Benchmark must establish **10 consecutive days** above its 200-SMA.
   - Staged capital re-allocation: 40% for 10 days $\implies$ 70% for 10 days $\implies$ 100%.

---

## 5. Execution, Cost Model & Statutory Tax Invariants
- **Execution Timing**: Next-Day Open fills strictly enforced. All signals generated at Day $t$ close execute at Day $t+1$ 09:15 IST open with full gap risk.
- **Frictional Drag**:
  - Variable: 49.20 bps stressed round-trip (brokerage + STT + NSE turnover charges + SEBI turnover + stamp duty + GST + 7.5 bps slippage).
  - Fixed: Flat **INR 14.75** DP fee per sale scrip (Dhan Schedule: INR 12.50 flat + 18% GST).
- **Statutory Taxation**:
  - Trade-by-trade holding period tax deduction.
  - Short-Term Capital Gains (STCG, $< 365$ days): 15% before July 23, 2024; 20% thereafter.
  - Long-Term Capital Gains (LTCG, $\ge 365$ days): 0% before April 1, 2018; 10% from April 2018 to July 2024; 12.5% thereafter.
- **Cash Compounding**: Idle cash compounds daily based on historical RBI repo and liquid fund net yields (`india_cash_yield_history.csv`).

---

## 6. Holdout Quarantine
- **Training & Backtest Window**: 2007-09-17 through 2024-12-31.
- **Quarantine Holdout**: Calendar Year 2025 (2025-01-01 to 2025-12-30) remains strictly sealed and unbreached until forward paper trading deployment.
