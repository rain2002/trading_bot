# Forensic Audit Report: Phase 5 NSE Whole-Market Candidate S2

**Document ID**: `AUDIT-PHASE5-NSE-WHOLE-MARKET-20261115`  
**Classification**: Post-Evaluation Quantitative Forensics & Fiduciary Audit  
**Author**: @Raja Nithin  
**Date**: 2026-11-15  
**Evaluation Window**: In-Sample `2007-09-17` to `2022-07-05` (14.8 years)  
**Governance Authority**: Multi-Bot Trading System Master Plan (Phase 5: NSE Whole-Market Alpha Sleeve)  
**Final Status**: **GATE A FAILED — BOT 4 PERMANENTLY PARKED**  

---

## 1. Executive Summary & Gate A Verdict

Candidate $S_2$ (Asymmetric Profit-Trail Compounder) was subjected to the 9 pre-registered Gate A hurdles across the 15-year survivor-free causal Bhavcopy panel (3,232 total equities, 1,422 delisted/merged companies).

### Summary Verdict
- **Gate A Outcome**: **FAILED (2 of 9 hurdles breached)**.
  - **H1 (Excess CAGR $\ge 14.30\%$)**: Failed. Candidate achieved **14.00%** (missed by 0.30% against Nifty 50 TRI + 4.0%).
  - **H4 (Deflated Sharpe Ratio $\ge 0.95$)**: Failed. With honest accounting for all prior exploratory experiments ($N = 85$), DSR evaluated to **0.3268** (32.68%), well below institutional significance.
- **Holdout Status**: Under strict fiduciary invariants, the 2-year out-of-sample holdout (`2022-07-06` to `2024-07-05`) **remained strictly sealed and unopened**.
- **Governance Mandate**: **Bot 4 is permanently parked**. Zero live capital and zero execution code are allocated. The core portfolio remains strictly anchored to the validated 3-bot architecture (Bot 1 ETF, Bot 2 Debt/Cash, Central Manager).

---

## 2. Process Deviation Audit (Stamping Discrepancy)

A forensic audit of the Git history and `trial_log.csv` confirms a workflow stamping discrepancy:
- **Discrepancy**: The runner `run_phase5_nse_whole_market_gate_a.py` and its results ledger `phase5_nse_whole_market_gate_a_results.json` were committed together in commit `dc73f16`. The logged trial row stamped commit hash `839778d` (which was the prior amendment commit) because HEAD had not yet advanced to the runner commit at the moment of execution.
- **Resolution**: A formal process deviation row has been appended to `trading_system/data/trial_log.csv` (Row 141) explicitly documenting this commit mismatch.
- **Fiduciary Impact**: The discrepancy does not alter the quantitative verdict: Candidate $S_2$ failed Gate A, the holdout remained unopened, and the strategy is parked.

---

## 3. Trade Concentration & Top 5 Trades Sensitivity

Candidate $S_2$ exhibited extreme return kurtosis (68.47) and positive skewness (1.10), indicating that performance was heavily driven by a tiny handful of outlier winners.

### Top 5 Trades by Realized PnL (Baseline)

| Ticker | Entry Date | Exit Date | Return % | Realized PnL | Exit Trigger |
|---|---|---|---|---|---|
| **`ADANIGREEN`** | 2020-08-03 | 2022-05-13 | +608.55% | +₹91,806.12 | Emergency Tier 4 Liquidation |
| **`OLECTRA`** | 2021-03-01 | 2022-02-25 | +236.99% | +₹75,938.05 | Profit Trail Stop (-25%) |
| **`IBVENTURES`** | 2017-04-03 | 2017-08-11 | +192.10% | +₹46,033.51 | Emergency Tier 4 Liquidation |
| **`GATI`** | 2014-02-03 | 2014-12-26 | +282.29% | +₹30,816.01 | Profit Trail Stop (-25%) |
| **`SUVEN`** | 2013-11-01 | 2015-06-05 | +349.69% | +₹30,315.50 | Profit Trail Stop (-25%) |

### Top 5 Concentration Audit
- **Total Realized PnL from Top 5 Trades**: **₹274,909.20**.
- **Percentage of Strategy Lifetime Profit**: The starting capital was ₹80,000 and ending equity was ₹556,004.71 (net profit = ₹476,004.71). The top 5 trades generated **57.75% of total net profits** across 429 total trades (1.16% of trades drove nearly 60% of gains).
- **Sensitivity (Excluding Top 5 Trades)**:
  - Ending equity drops from ₹556,004.71 to **₹281,095.51**.
  - **CAGR collapses from 14.00% to 8.86%** (a 5.14 percentage point decline).
  - At 8.86% CAGR, the strategy significantly trails the passive benchmark (10.30% Nifty 50 TRI), confirming that the headline 14% return is fragile and reliant on extreme outlier multi-baggers.

---

## 4. Top 10 Contributor Tickers & Unadjusted Split Audit

An audit of daily price series for the top 10 contributor tickers revealed significant corporate action distortions in the historical Bhavcopy panel:

| Ticker | Trades | Total Realized PnL | Max 1-Day Price Jump | Corporate Action Audit |
|---|---|---|---|---|
| **`ADANIGREEN`** | 2 | +₹116,057.29 | +20.0% | Clean secular momentum; legitimate clean runner |
| **`OLECTRA`** | 1 | +₹75,938.05 | +234.3% | Reverse-split / capital reduction anomaly in Bhavcopy |
| **`IBVENTURES`** | 2 | +₹44,776.01 | +20.0% | High-beta midcap bull-run runner |
| **`TANLA`** | 4 | +₹34,183.57 | +48.0% | 2020 cloud software breakout |
| **`GATI`** | 1 | +₹30,816.01 | +21.9% | 2014 logistics sector re-rating |
| **`SUVEN`** | 1 | +₹30,315.50 | +91.1% | Demerger / corporate restructuring event |
| **`AUROPHARMA`** | 3 | +₹27,951.67 | +79.2% | Unadjusted bonus/split artifact |
| **`ADANITRANS`** | 2 | +₹24,566.84 | +20.0% | Clean secular utility runner |
| **`ICIL`** | 2 | +₹18,822.03 | +81.4% | Textile sector multi-bagger with corporate action gap |
| **`HEG`** | 3 | +₹16,811.57 | +20.0% | 2017 graphite electrode super-cycle |

### Critical Finding: Phantom Corporate Action Disasters
Forensic examination of the worst individual trade losses in the baseline run revealed that multiple severe losses were **artificial phantom drawdowns caused by unadjusted stock splits**:
1. **`DWARKESH`**: Bought in March 2017. On 2017-08-10, the company executed a **10:1 stock split**, with the market price dropping from ₹667.40 to ₹66.45. Lacking a corresponding entry in `nse_corporate_actions_audited.csv`, the simulation registered an artificial **-84.16% crash (-₹20,019.77 loss)**.
2. **`AEGISCHEM`**: On 2015-09-16, executed a **10:1 stock split**, dropping from ₹814.60 to ₹80.60. The system registered an artificial **-88.10% loss (-₹14,689.20)**.
3. **`ZENSARTECH`**: On 2018-09-07, executed a **5:1 stock split**, dropping from ₹1676.15 to ₹326.30. The system registered an artificial **-75.09% loss (-₹11,581.21)**.

Combined, these three unadjusted splits alone subtracted **₹46,290.18** in phantom losses from the baseline strategy.

---

## 5. Decomposition of the Stressed-Run Gap (18.06% vs. 14.00%)

In Hurdle H9, doubling transaction friction from 27 bps to 54 bps buy and 25.5 bps to 51 bps sell increased CAGR from 14.00% to **18.06%** and Sharpe from 0.84 to **1.04**. 

A trade-by-trade comparison explains this counter-intuitive result as **extreme path-dependency and entry timing jitter**:
- **Total Trades**: 429 in Baseline vs. 417 in Stressed.
- **Common Trades**: 331 trades were identical.
- **Diverged Trades**: 98 trades were taken ONLY by Baseline; 86 trades were taken ONLY by Stressed.

### The Mechanism of Divergence
1. **Avoiding the 3 Split Disasters**:
   - Because the stressed run paid higher fees on earlier trades in 2015–2018, its cash balance was marginally lower on monthly rebalance dates.
   - Consequently, the stressed run ranked stocks slightly differently or had just enough cash to pick alternative names. It **completely avoided `DWARKESH`, `AEGISCHEM`, and `ZENSARTECH`**, entirely dodging **₹46,290.18 in artificial phantom losses**.
2. **Catching Alternative 3x Compounders**:
   - In late 2020, because the stressed run had open portfolio slots that were blocked in the baseline run, it entered:
     - **`CGPOWER`** (2020-12-01 to 2022-05-16): **+282.09% gain (+₹91,598.71)**
     - **`INTELLECT`** (2020-09-01 to 2021-08-11): **+242.20% gain (+₹88,235.37)**
   - These two trades alone contributed **+₹179,834.08** in net profit to the stressed run.
3. **Net Swing**:
   - Trades taken ONLY by Baseline: **-₹54,466.06**.
   - Trades taken ONLY by Stressed: **+₹210,273.77**.
   - **Total Net Divergence**: **+₹264,739.83**.

### Conclusion on Stressed Run
The 18.06% stressed return was not an indication of cost resilience; it was an artifact of discrete 15-slot portfolio capacity where tiny cost perturbations caused a lucky reshuffling into multi-baggers while bypassing unadjusted corporate split traps. This confirms the reviewer's thesis: the 14%–18% numbers are fragile, path-dependent, and unfit for institutional fiduciary capital.

---

## 6. Final Fiduciary Decision & Next Actions

1. **Park Bot 4 Permanently**: **YES**. Candidate $S_2$ failed Gate A hurdles H1 and H4. Out-of-sample data remains sealed. Zero capital is deployed.
2. **Shadow Logging at Zero Capital**: **YES**. Candidate $S_2$ may log forward daily signals sequentially in the pipeline at **₹0 capital** solely as an unmanaged diagnostic shadow observer, without creating any risk or capital drag on the active paper portfolio.
3. **Three-Bot Core Preserved**: The 13-week Gate B paper trading clock continues exclusively for the validated 3-bot core:
   - **Bot 1**: Multi-Asset ETF & Gold Rotation.
   - **Bot 2**: Sovereign Debt & Cash Reserve (`LIQUIDBEES`).
   - **Central Manager**: 100% active allocation to Bot 1, daily reconciliation under 0.1%, automated CRO kill switch.
