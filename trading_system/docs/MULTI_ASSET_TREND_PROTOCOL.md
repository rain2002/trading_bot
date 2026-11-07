# PRE-REGISTERED PROTOCOL SPECIFICATION: MULTI-ASSET TACTICAL TREND ENGINE
**Document Identifier**: `MULTI_ASSET_TREND_PROTOCOL_V1_0`  
**Registration Date**: 2026-11-07  
**In-Sample Test Window**: 2007-09-24 to 2024-12-31 (17.27 calendar years | 4,206 trading days)  
**Untouched Holdout Window**: 2025-01-01 to 2025-12-31 (Sealed & Untouched)  
**Primary Capital Base**: ₹80,000.00 INR  
**Protocol SHA-256**: `2130B42B3A90E5A2B27FFCFA53409DD56517FAE9C481AA0E876A483D45886A58`  
**Protocol Status**: PRE-REGISTERED & CRYPTOGRAPHICALLY LOCKED  

---

## 1. Executive Summary & Design Mandate

Following the formal post-mortem and audit of the Nifty 50 single-asset momentum engine (which demonstrated that large-cap cross-sectional stock momentum suffers severe friction and cash drag, delivering only 4.62% to 5.56% post-tax), this protocol pre-registers an institutional **Multi-Asset Class Tactical Trend Engine**.

By shifting from 10 individual mega-cap stocks to **liquid macro asset class ETFs/indices**, the strategy:
1. Eliminates survivorship bias and constituent reconstitution risk.
2. Captures multi-year secular compounding in high-growth asset classes (Indian Midcaps at 17.4% CAGR and US Tech at 20.6% CAGR in INR).
3. Reduces annual portfolio turnover by >85% (from ~25–45 trades/year down to ~3–6 trades/year).
4. Converts short-term trading profits into **12.5% Long-Term Capital Gains (LTCG)** by extending holding periods past 365 days.
5. Slashes flat depository participant (DP) fees from ₹6,000–₹10,000 down to < ₹600.

---

## 2. Universal Macro Asset Universe

The strategy trades exclusively across 5 liquid macro assets:

| Asset Name | Symbol Proxy | Underlying Economic Factor | Primary Currency |
| :--- | :--- | :--- | :--- |
| **Nifty 50 Index** | `NIFTY50` | Indian Large-Cap Equities | INR |
| **Nifty Midcap 50 Index** | `MIDCAP50` | Indian High-Beta Domestic Growth Equities | INR |
| **Gold (in INR)** | `GOLD_INR` | Global Monetary Hard Asset & Safe Haven | INR (`GC=F * USDINR`) |
| **US Tech / Nasdaq 100** | `QQQ_INR` | Global Secular Technology & US Equities | INR (`QQQ * USDINR`) |
| **Sovereign Liquid Yield** | `CASH_INR` | Overnight Liquid Fund / RBI Repo Yield | INR (Repo less 35 bps TER) |

---

## 3. The 3 Pre-Registered Experimental Variants

All three variants rebalance on the **first trading day of each calendar month**, generating orders based on the previous trading day's close and executing at **Next-Day Open**:

| Specification | Variant A (Balanced Dual Momentum) | Variant B (Asymmetric High-Growth Trend) | Variant C (3-Asset Volatility-Inverse Momentum) |
| :--- | :--- | :--- | :--- |
| **Active Asset Slots** | Top 2 Assets (50% / 50%) | Top 2 Assets (60% Rank 1 / 40% Rank 2) | Top 3 Assets (45% / 35% / 20%) |
| **Momentum Metric** | 6-Month Relative Momentum (126 trading days return) | Blended Momentum: 50% 3M (63d) + 50% 12M (252d) return | 12-Month Vectorized Exponential Slope $\cdot R^2$ |
| **Macro Trend Filter** | Asset Price > 200-day SMA | Asset Price > 200-day SMA AND 50-day SMA sloping upward | Asset Price > 150-day SMA |
| **Defensive Cash Substitution** | If an asset is below trend, its allocation goes 100% to Cash | If an asset is below trend, its allocation goes 100% to Cash | If an asset is below trend, its allocation goes 100% to Cash |
| **Intra-Month Stop Risk** | None (pure monthly cadence) | Intra-month 12.0% trailing stop from peak | CRO Drawdown Ladder (-10% / -18% / -24%) |
| **Cash Compounding** | Sourced RBI Repo Rate less 35 bps TER compounded daily | Sourced RBI Repo Rate less 35 bps TER compounded daily | Sourced RBI Repo Rate less 35 bps TER compounded daily |

---

## 4. Statutory Friction and Cost Model

All variants are evaluated under the strict, audited institutional friction model:
1. **Variable Transaction Costs (Stressed)**:
   - Buy: 25.35 bps (Brokerage 5 bps + STT 10 bps + Turnover/Stamp/GST 2.85 bps + Stressed Slippage 7.5 bps)
   - Sell: 23.85 bps (Brokerage 5 bps + STT 10 bps + Turnover/Stamp/GST 1.35 bps + Stressed Slippage 7.5 bps)
   - Round-trip variable cost: **49.20 bps**.
2. **Depository Participant Fee**: Flat **₹14.75** (₹12.50 + 18% GST) deducted on every scrip sale.
3. **Statutory Holding-Period Tax**:
   - Holding period < 365 days: Short-Term Capital Gains Tax (STCG) at 15% before July 23, 2024; 20% thereafter.
   - Holding period $\ge$ 365 days: Long-Term Capital Gains Tax (LTCG) at 0% before 2018; 10% (exemption ₹100,000/yr) 2018 to July 2024; 12.5% (exemption ₹125,000/yr) thereafter.
   - Capital losses offset gains trade-by-trade.

---

## 5. Risk Controls & Double High-Water Mark Invariant

1. **Lifetime Never-Reset Peak ($HWM_{\text{true}}$)**:
   - Evaluated daily on total portfolio equity.
   - If true drawdown from $HWM_{\text{true}}$ exceeds **-25.00%**, the variant is flagged; if it exceeds **-30.00%**, it is **HARD DISQUALIFIED**.
2. **Zero-Leverage Constraint**: Gross exposure is capped at 100.0% at all times.
3. **Fiduciary Cash Protection**: Idle cash is never left uninvested; it compounds daily at the verified RBI repo yield schedule.

---

## 6. Pre-Committed Decision Rules & Gate A Hurdles

To pass Gate A and earn recommendation for forward paper tracking, a variant must satisfy:
1. **Post-Tax Stressed Compound CAGR $\ge 11.00\%$** (Target) | Aspirational: $15.00\%+$.
2. **Must beat Baseline 1 (Nifty 50 TRI Post-Tax CAGR = 10.80%)**.
3. **Must beat Baseline 3 (Trend-Switch 200-SMA Post-Tax CAGR = 6.88% and Calmar = 0.27)**.
4. **Stressed Max Drawdown Depth $\le 20.00\%$ Target** ($> 25.00\%$ Fail, $> 30.00\%$ Disqualification).
5. **Calmar Ratio $\ge 0.50$** (vs 0.18 for Nifty TRI).
6. **Annualized Sharpe Ratio $\ge 0.80$**.
7. **Total Closed Trades $\ge 40$**.
8. **Deflated Sharpe Ratio $DSR \ge 0.95$** (accounting for all historical trials).
