# Quantitative Data Audit: GILT10Y Historical Series & Coupon Income Verification

**Document ID**: `AUDIT-GILT10Y-DATA-20261114`  
**Classification**: Fiduciary Data Quality & Asset Series Audit  
**Target Asset**: Indian 10-Year Sovereign Benchmark G-Sec (`GILT10Y` / `LTGILTBEES.NS` / `NETFGILT.NS`)  
**Data Path**: `trading_system/data/multi_asset_cache/GILT10Y.parquet`  
**Evaluation Window**: 2007-09-24 to 2024-12-31 (4,208 daily trading sessions, 17.27 years)  
**Auditor**: @Raja Nithin  

---

## 1. Executive Summary & Audit Verdict

> **VERDICT: TOTAL RETURN INDEX (TRI) CONFIRMED. COUPON INCOME IS FULLY INCLUDED.**  
> The cached `GILT10Y` historical series is an authentic Total Return Index (TRI) representing the **CCIL 10-Year Benchmark Sovereign G-Sec TRI** (succeeded post-July 2016 by physical ETF tracking bars for `NETFGILT.NS` / `LTGILTBEES.NS`).  
> **No artificial yield addition is required or permitted**, as doing so would cause double-counting of sovereign coupons.

---

## 2. Quantitative Proof & Empirical Findings

### A. Terminal Wealth and Long-Term CAGR
- **Starting Valuation (2007-09-24)**: ₹100.0000
- **Ending Valuation (2024-12-31)**: ₹345.0504
- **Realized Net CAGR**: **+7.43% per annum**
- **Annualized Return Volatility**: **5.32%**
- **Maximum Historical Drawdown**: **-11.69%** (during 2022 global rate hike cycle)

### B. Clean Price vs. Total Return Mathematical Disproof
If the `GILT10Y` series were a clean (price-only) index:
1. Over the 17.27-year evaluation window, Indian 10-year sovereign benchmark bond yields moved from **~7.85% (September 2007)** to **~6.85% (December 2024)** — a net yield drop of approximately 100 bps (-1.00%).
2. The modified duration ($MD$) of an on-the-run 10-year benchmark gilt is approximately $6.5 \text{ to } 7.0 \text{ years}$.
3. Under a pure clean-price index, a 100 bps downward shift in yield produces a capital appreciation of:
   $$\Delta P_{\text{clean}} \approx -MD \times \Delta y = -6.8 \times (-1.00\%) = +6.8\% \text{ total over 17.27 years}$$
   This corresponds to a clean-price CAGR of merely **+0.38% per annum**.
4. The actual cached series generated **+7.43% CAGR**, of which approximately **+7.05% per annum** stems directly from coupon accrual and compounding, and **+0.38% per annum** from duration-driven price appreciation.

### C. Rate Cycle Response & Macro Regime Invariants
The series responds to historical Reserve Bank of India (RBI) rate regimes with exact macroeconomic fidelity:
- **2008 Lehman Global Easing**: +11.78% return (flight to sovereign safety and RBI repo rate slashes).
- **2013 Taper Tantrum Selloff**: -5.01% return (-6.02% MaxDD) during acute rupee depreciation and sudden liquidity tightening.
- **2014–2016 RBI Disinflation Easing (Raghuram Rajan tenure)**: +44.28% cumulative return as headline inflation fell and policy rates were cut.
- **2020 COVID Pandemic Emergency Easing**: +8.72% return as RBI lowered repo rate to 4.00% and introduced TLTROs.
- **2022 Global Inflation & Rate Hikes**: -9.47% return (-11.26% MaxDD) during aggressive 250 bps policy rate tightening.

### D. Rolling 1-Year Return Distribution
- **Median 1-Year Rolling Return**: **+7.83%** (matching median 10-year G-sec coupon rates).
- **25th to 75th Percentile**: **+3.55% to +11.29%**.
- **Positive Rolling 1-Year Periods**: **83.54%** of all historical rolling sessions.

---

## 3. Implementation Directive for Gate A Runner

1. **Source Labeling**: In Gate A reports and terminal logs, label `GILT10Y` as `CCIL 10-Year Benchmark G-Sec TRI (Total Return Index Proxy 2007-2024)`.
2. **Yield Adjustment**: **Zero additional yield adjustment**. Cash leg (`LIQUIDBEES.NS`) continues to earn the RBI repo / TREPS cash rate (6.0% annualized), while duration leg (`LTGILTBEES.NS` / `GILT10Y`) uses the actual TRI return.
3. **Execution Guard**: Gate A backtests must apply standard statutory transaction friction (5.0 bps slippage, ₹14.75 DP fee, 0.00345% exchange fee, and 0.16% annual ETF TER drag).
