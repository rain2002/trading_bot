# Pre-Registered Research Protocol: Phase 1 ETF, Gold & Sovereign Bonds Rotation Strategy
**Document ID**: `PROTOCOL-ETF-GOLD-BONDS-ROTATION-V1-20261112`  
**Classification**: Institutional Pre-Registration Document (Fiduciary Stage 1)  
**Status**: PRE-REGISTERED (LOCKED PRIOR TO CODE EXECUTION)  
**Creation Date**: 2026-11-12  
**Target Capital**: ₹80,000 (Initial deployment, scalable with top-ups)  
**In-Sample Window**: 2007-09-24 to 2024-12-31 (17.27 Years | 4,235 Trading Days)  
**Out-of-Sample Holdout**: 2025-01-01 to Present (Strictly Sealed & Blinded)  
**Governance Authority**: Multi-Bot Trading System Master Plan (Phase 1: ETF & Gold Bot)

---

## 1. Executive Summary & Core Mandate

The objective of Phase 1 is to build, validate, and deploy the foundational **ETF, Gold & Sovereign Bonds Rotation Bot** (Bot 1). 

Following the retirement of failed raw stock momentum strategies (Pods A & B), this bot serves as the central capital compounding engine of the fund. It operates strictly across liquid, non-correlated macro exchange-traded funds (ETFs) on the National Stock Exchange of India (NSE).

### The Invariant Hurdle (The Static Benchmark)
Historically, a simple, static equal-weight mix of Gold, US Tech, Indian Equities, and Gilt/Cash generated **~14.17% CAGR** in-sample. 
**The Hard Rule of Phase 1**: The dynamic trend rotation and drawdown-throttled strategy must statistically beat the static benchmark out-of-sample, or we do not ship dynamic rotation and instead hold the static asset mix.

---

## 2. Asset Universe & Instrument Specifications

The universe consists of 5 liquid NSE-listed exchange-traded funds representing distinct macroeconomic asset classes:

| Asset Class | ETF Ticker | Underlying Index / Asset | Expense Ratio | Expected Spread | Statutory STT (Sell) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Precious Metals** | `GOLDBEES.NS` | Physical Domestic Gold (1 gram) | ~0.50% | 7.5 bps | 0.00% (Commodity) |
| **US Mega-Cap Tech** | `MON100.NS` | Nasdaq 100 Total Return Index | ~0.58% | 12.0 bps | 0.00% (International) |
| **India Large-Cap Equity** | `NIFTYBEES.NS` | Nifty 50 Total Return Index | ~0.04% | 5.0 bps | 0.10% (Equity Delivery) |
| **India Mid-Cap Equity** | `MID150BEES.NS` | Nifty Midcap 150 Index | ~0.20% | 12.5 bps | 0.10% (Equity Delivery) |
| **Sovereign Debt (Bonds Sleeve)** | `LTGILTBEES.NS` / `LIQUIDBEES.NS` | 10-Year Indian Government Gilts / Overnight Triparty Repo (TREPS) | ~0.25% / 0.15% | 5.0 bps | 0.00% (Debt / Liquid) |

### Instrument Invariants:
1. **Survivor & Inception Invariant**: If an instrument had not yet commenced trading on historical date $t$ (e.g. `MID150BEES` or `MON100` before inception), its target allocation weight is strictly diverted to `LTGILTBEES.NS` / `LIQUIDBEES.NS` (Sovereign Cash Buffer). No lookahead or back-filling is permitted.
2. **Cash Sleeve Mandate**: `LTGILTBEES.NS` and `LIQUIDBEES.NS` serve as the **Bonds Sleeve (Cash Retreat)**. When equity or commodity assets enter a bear regime, capital retreats into this sovereign debt sleeve.

---

## 3. Shared Strategy Interface Specification

All bots in the Multi-Bot Trading System must plug into a standardized, clean strategy interface in the shared core:

```python
from abc import ABC, abstractmethod
from typing import Dict, Any
import pandas as pd

class StrategyInterface(ABC):
    """
    Standardized Strategy Interface for Multi-Bot Architecture.
    Plugs directly into the shared execution engine and state persistence branch.
    """
    @abstractmethod
    def evaluate_allocations(
        self,
        current_date: pd.Timestamp,
        market_data: Dict[str, pd.DataFrame],
        portfolio_state: Dict[str, Any]
    ) -> Dict[str, float]:
        """
        Takes point-in-time daily bars up to current_date and current portfolio state.
        Returns target portfolio weights summing to <= 1.0.
        Unallocated capital automatically defaults to the Sovereign Cash Sleeve (LIQUIDBEES).
        """
        pass

    @abstractmethod
    def get_risk_status(self) -> Dict[str, Any]:
        """
        Returns strategy-specific risk state (drawdown, active regime, throttle scale).
        """
        pass
```

---

## 4. Candidate Strategy 1: Trend Rotation with Drawdown Throttle

### A. Baseline Weights (Anchor Allocation)
In normal market conditions, target baseline weights are:
- `GOLDBEES.NS`: 25.0%
- `MON100.NS`: 25.0%
- `NIFTYBEES.NS`: 15.0%
- `MID150BEES.NS`: 15.0%
- `BONDS / CASH SLEEVE` (`LTGILTBEES` / `LIQUIDBEES`): 20.0%

### B. Dynamic Trend Filter & Asset-Level Rotation
Rebalancing is evaluated on the final trading day of each month ($t_{\text{rebal}}$):
1. **Asset Trend Condition**:
   For each equity and commodity asset $i \in \{\text{GOLDBEES}, \text{MON100}, \text{NIFTYBEES}, \text{MID150BEES}\}$:
   $$\text{TrendCondition}_i = \begin{cases} \text{BULLISH} & \text{if } P_{i, t} \ge \text{SMA}_{200}(P_i) \\ \text{BEARISH} & \text{if } P_{i, t} < \text{SMA}_{200}(P_i) \end{cases}$$
2. **Capital Defense Reallocation**:
   - If asset $i$ is `BULLISH`: It receives its full target allocation weight $W_i$.
   - If asset $i$ is `BEARISH`: Its entire target allocation $W_i$ is **recalled and rotated 100% into the Sovereign Bonds Sleeve (`LTGILTBEES.NS` / `LIQUIDBEES.NS`)**.
   - Equity capital is **never** held in a declining asset trading below its 200-day moving average.

### C. Portfolio-Level Drawdown Throttle
To prevent capital erosion during macro liquidity crises (e.g. 2008 GFC, March 2020):
1. **Operating High-Water Mark ($HWM_t$)**:
   $$HWM_t = \max_{\tau \le t} (NAV_\tau)$$
   $$DD_t = \frac{NAV_t - HWM_t}{HWM_t}$$
2. **Throttle Multiplier ($\lambda_{DD}$)**:
   $$\lambda_{DD} = \begin{cases} 
   1.00 & \text{if } DD_t \ge -10.0\% \text{ (Normal Operation)} \\
   0.50 & \text{if } -20.0\% \le DD_t < -10.0\% \text{ (Moderate Throttle: 50% equity shifted to Gilts)} \\
   0.00 & \text{if } DD_t < -20.0\% \text{ (Severe Circuit Breaker: 100% portfolio shifted to Sovereign Gilts/Cash)} 
   \end{cases}$$

---

## 5. Transaction Costs, Taxes & Slippage Model

Every backtest run must incorporate exact Indian institutional friction:
- **Brokerage**: ₹0 delivery brokerage.
- **Depository Participant (DP) Fee**: Flat ₹14.75 + GST (₹17.41) per sale scrip.
- **Securities Transaction Tax (STT)**: 0.10% on equity delivery sales (`NIFTYBEES`, `MID150BEES`); 0.00% on `GOLDBEES` and debt ETFs.
- **Stamp Duty**: 0.015% on all purchase transactions.
- **Exchange & SEBI Turnover**: 0.00345% turnover fee.
- **Execution Slippage**: Stressed conservative model:
  - `NIFTYBEES.NS`: 5.0 bps
  - `GOLDBEES.NS`: 7.5 bps
  - `LTGILTBEES.NS` / `LIQUIDBEES.NS`: 5.0 bps
  - `MON100.NS`: 12.0 bps
  - `MID150BEES.NS`: 15.0 bps
- **Tax Accounting**: Statutory Short-Term Capital Gains (STCG) at 15.0% and applicable long-term rates deducted systematically from realized gains.

---

## 6. Gate A Clearance Criteria (Pass / Fail Hurdles)

To clear Gate A and graduate to 13 weeks of Paper Incubation (Gate B), the strategy must satisfy all of the following criteria on the sealed, audited dataset:

| Metric | Hurdle Requirement | Rationale |
| :--- | :--- | :--- |
| **Out-of-Sample Benchmark Superiority** | $\text{CAGR}_{\text{strategy}} > 14.17\%$ OR $\text{MaxDD}_{\text{strategy}} < 0.65 \times \text{MaxDD}_{\text{static}}$ | Must prove dynamic rotation adds alpha or cuts drawdown vs. static mix |
| **Maximum Drawdown ($MaxDD$)** | $\le -35.0\%$ | Within the fund's stated $-45\%$ risk budget |
| **Deflated Sharpe Ratio ($DSR$)** | $\ge 0.95$ | Corrects for trial multiple testing per Bailey & López de Prado (2014) |
| **Annualized Sharpe Ratio** | $\ge 0.65$ (Net of all taxes and friction) | Institutional risk-adjusted return baseline |
| **Annual Trade Count** | $\le 24$ trades/year | Low-turnover regime to prevent fee and tax drag |

---

## 7. Protocol Approval & Governance Sign-Off

- **Author**: Antigravity Quant Engineering  
- **Sign-off**: @Raja Nithin  
- **Execution Rule**: This document is committed alone with its SHA-256 hash before any backtest code is executed.
