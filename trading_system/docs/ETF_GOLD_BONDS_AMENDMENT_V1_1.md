# Protocol Amendment V1.1: Phase 1 ETF, Gold & Sovereign Bonds Strategy

**Document ID**: `AMENDMENT-ETF-GOLD-BONDS-V1-1-20261114`  
**Classification**: Formal Protocol Amendment & Champion Designation  
**Base Protocol**: [`ETF_GOLD_BONDS_ROTATION_PROTOCOL_V1.md`](ETF_GOLD_BONDS_ROTATION_PROTOCOL_V1.md) (`PROTOCOL-ETF-GOLD-BONDS-ROTATION-V1-20261112`)  
**Base Protocol SHA-256**: `2434e15bd3b9dcbeaee010ef29a1080f82e0117334b603d6e375dec5b3cc8d75`  
**Date**: 2026-11-14  
**Target Capital**: ₹80,000 (Initial Gate B allocation)  
**Governance Authority**: Multi-Bot Trading System Master Plan (Phase 1: ETF & Gold Bot)  

---

## 1. Designation of the Phase 1 Champion

Under the explicit governance rules of the Master Plan (Page 2 & Page 8) and Base Protocol V1 (Section 3), the **Static 5-Asset Mix with Sovereign Gilts** is formally designated as the sole Phase 1 Champion:

### Target Asset Allocation:
- **`GOLDBEES.NS`**: 25.0% (Domestic Physical Gold ETF)
- **`MON100.NS`**: 25.0% (Nasdaq 100 US Secular Tech ETF)
- **`NIFTYBEES.NS`**: 15.0% (Nifty 50 Large-Cap Equity ETF)
- **`MID150BEES.NS`**: 15.0% (Nifty Midcap 150 Equity ETF)
- **Sovereign Gilt / Liquid Sleeve (`LTGILTBEES.NS` / `LIQUIDBEES.NS`)**: 20.0%

### Rebalancing Rules:
1. **Annual Rebalance**: Target weights are realigned on the final trading session of each calendar year.
2. **Tolerance Band (Drift Rebalance)**: If any individual asset's weight drifts by more than $\pm 5.0\%$ absolute from its target weight (e.g. Gold $> 30.0\%$ or $< 20.0\%$), an interim rebalance is triggered at the next market close to restore target weights.

---

## 2. Formal Retirement of Dynamic Trend Rotation for Phase 1

The candidate dynamic 200-SMA trend rotation with portfolio drawdown throttle was evaluated across the 17.27-year historical dataset (2007–2024, 4,076 trading days) in Gate A. 

It failed all primary protocol hurdles:
1. **Benchmark Superiority**: Generated 9.84% CAGR vs 15.47% Static Hurdle (Failed).
2. **Drawdown Ratio**: Achieved -17.01% MaxDD vs the required $\le -13.81\%$ ($0.65 \times -21.25\%$) (Failed).
3. **Annualized Sharpe**: Achieved 0.59 vs the $\ge 0.65$ hurdle (Failed).
4. **Trade Frequency**: Executed ~32.5 trades/year vs the $\le 24$ trades/year limit (Failed).
5. **Deflated Sharpe Ratio (DSR)**: DSR = 0.0000 vs the $\ge 0.95$ hurdle (Failed).

**Verdict**: Candidate Dynamic Trend Rotation is retired and disqualified for Phase 1 deployment. Per protocol mandate, the fund falls back to the static champion mix.

---

## 3. Invalidation and Dropping of the Ad-Hoc 4-ETF (25% Each) Mix

The four-ETF equal-weight mix (25% Gold, 25% Nasdaq 100, 25% Nifty 50, 25% Midcap 150 without gilts) was deployed post-hoc without prior protocol pre-registration. 

Furthermore, historical backtesting demonstrates that this mix suffered a maximum drawdown of **-43.18%**, which breaches the protocol's strict $\le -35.0\%$ risk limit.

**Verdict**: The un-registered 4-ETF 25% mix is formally dropped and invalidated.

---

## 4. Frozen Gate A Hurdles & Standards

All Gate A validation standards from Protocol V1 remain in full effect as written:

| Metric | Hurdle Requirement | Purpose |
| :--- | :--- | :--- |
| **Benchmark Superiority** | $\text{CAGR} > 14.17\%$ OR $\text{MaxDD} \le 0.65 \times \text{MaxDD}_{\text{static}}$ | Verifies economic value over passive baseline |
| **Maximum Drawdown ($MaxDD$)** | $\le -35.0\%$ | Fund risk ceiling |
| **Annualized Sharpe Ratio** | $\ge 0.65$ (Net of all statutory taxes and friction) | Institutional risk-adjusted baseline |
| **Deflated Sharpe Ratio ($DSR$)** | $\ge 0.95$ | Corrects for multiple testing across all $N \ge 124$ trials |
| **Trade Frequency** | $\le 24$ trades/year | Prevents turnover drag, fees, and friction |

---

## 5. Cash & Sovereign Gilt Yield Specification

Uninvested cash balances and capital allocated to the Sovereign Debt / Gilt sleeve (`LTGILTBEES.NS` / `LIQUIDBEES.NS`) earn a stated gross annualized yield of **6.00%** (`CASH_YIELD_ANNUAL = 0.06`), compounded daily based on a 252-day trading year, reflecting the prevailing Reserve Bank of India (RBI) repo and sovereign overnight TREPS yield net of fund expenses.

---

## 6. Execution Governance

- **Execution Venue**: NSE Cash Delivery (Whole Shares Only, Fail-Closed Broker Adapter).
- **Gate B Incubation**: 13 Weeks forward paper trading starting from clean reset.
- **State Branch Isolation**: All live paper state, execution logs, and equity curves must be committed exclusively to the `state` Git branch.
- **Sign-off**: @Raja Nithin
