# Forensic Audit & Post-Mortem Report: Pre-Registered Gate A Evaluation
**Audit Date**: 2026-11-07  
**Auditor**: Antigravity Quantitative Verification & Risk Desk  
**Protocol Version**: v3.1 ([`PRE_REGISTERED_DUAL_POD_PROTOCOL.md`](file:///d:/paper_trading_bot/trading_system/docs/PRE_REGISTERED_DUAL_POD_PROTOCOL.md))  
**In-Sample Common Window**: 2007-09-17 to 2024-12-31 (17.29 years | 4,238 trading days)  
**Starting Capital**: ₹80,000.00 INR (India Pod) | $1,000.00 USD (US Pod)  
**Holdout Status**: 2025 Calendar Year **Strictly Sealed and Unopened**  

---

## 1. Executive Verdict: REJECT PROMOTION TO GATE B (ALL VARIANTS FAIL GATE A)

Following user review and rigorous forensic execution of the 5 requested sanity checks, **we formally rescind the earlier promotion recommendation**. 

The previously reported 23.42% CAGR for Variant 1 was an **artifact of a catastrophic double-split adjustment bug** introduced in commit `75b8583`. Correcting this bug reveals that the underlying strategy achieves only **5.56% Post-Tax Stressed CAGR**, underperforming every baseline benchmark. 

Furthermore, under the pre-committed rules of Protocol v3.1:
1. **DSR Deflation Failure**: DSR was $0.910 < 0.95$. Relabeling this as a `[NOTE]` broke protocol rules.
2. **Monte Carlo Failure**: 5th-percentile Max Drawdown is **-38.17%**, severely breaching the -30.00% hard disqualification limit.
3. **Benchmark Failure**: Variant 1 ($5.56\%$) fails to beat Baseline 3 ($6.88\%$), Baseline 2 ($9.04\%$), or Baseline 1 TRI ($10.80\%$).
4. **US Pod Failure**: US Pod achieved $13.59\%$ CAGR and a **-32.53% Max Drawdown**, breaching the -30.00% hard limit.

```
========================================================================================================
                                 AUDITED GATE A SCOREBOARD (STRESSED)
========================================================================================================
 Hurdle Metric               Hurdle Target        Variant 1         Variant 2       Variant 3    US Pod
--------------------------------------------------------------------------------------------------------
 Post-Tax Stressed CAGR         >= 15.00%            5.56% [FAIL]      3.33% [FAIL]    3.41% [FAIL] 13.59% [FAIL]
 Max DD Depth (HWM_true)        <= 25.00%          -20.43% [PASS]    -21.16% [PASS]  -21.18% [PASS] -32.53% [FAIL]
 Max DD Hard Failure Ceiling    > 30.00%             None  [PASS]      None  [PASS]    None  [PASS] BREACH [FAIL]
 Annualized Sharpe              >= 0.70              0.58  [FAIL]      0.38  [FAIL]    0.40  [FAIL]  0.76  [PASS]
 Calmar vs Baseline 3           > 0.27 (B3)          0.27  [TIE]       0.16  [FAIL]    0.16  [FAIL]  0.42  [PASS]
 CAGR vs Baseline 3             > 6.88% (B3)         5.56% [FAIL]      3.33% [FAIL]    3.41% [FAIL]   N/A
 Closed Trades Count            >= 100               428   [PASS]      663   [PASS]    742   [PASS]   654   [PASS]
 Deflated Sharpe (N = 35)       >= 0.95              0.910 [FAIL]      0.540 [FAIL]    0.785 [FAIL]   N/A
 Monte Carlo 5th-%ile MaxDD     <= -28.00%         -38.17% [FAIL]    -39.40% [FAIL]  -40.12% [FAIL] -44.20% [FAIL]
 Parameter Stability Grid       Stable >= 15%        4.6%-6.1%[FAIL]   2.8%-3.8%[FAIL] 2.9%-4.0%[FAIL] N/A
--------------------------------------------------------------------------------------------------------
 FINAL AUDITED GATE A VERDICT                       >> FAIL <<        >> FAIL <<      >> FAIL <<   >> FAIL <<
========================================================================================================
```

---

## 2. Root Cause Analysis: The Double-Split Bug

### A. The Bug Mechanics
In commit `75b8583`, the backtester logic was altered to process corporate split events:
```python
# The Flawed Code in backtest_nse50.py (lines 556-560 in commit 75b8583)
split_ratio = p_sym["splits"][idx]
if split_ratio > 0 and split_ratio != 1.0:
    positions[sym] = shares * split_ratio            # <-- FATAL BUG
    entry_prices[sym] = entry_prices[sym] / split_ratio
    splits_count += 1
```
However, the historical parquet cache files downloaded from Yahoo Finance (`open`, `high`, `low`, `close`) are **already backward split-adjusted across their entire history**:
- On `ADANIPORTS.NS`, before its 5:1 split on 2010-09-23, historical prices were already divided by 5 (~₹170 vs pre-split unadjusted ~₹850).
- When the bot bought at ₹170 and the split date arrived, the engine multiplied shares by 5.0 while market price remained ₹170.
- The position value instantly **quintupled (500% phantom profit)** out of thin air.

### B. Impact on Returns
Over the 17.29-year backtest, 19 split events were triggered on active portfolio positions. Three splits alone fabricated **₹1,375,818** in phantom profits:
1. `NESTLEIND.NS` (10:1 split on 2024-01-05): Manufactured **₹526,481.57** in fake gains (+912.6% trade).
2. `EICHERMOT.NS` (10:1 split on 2020-08-24): Manufactured **₹512,137.21** in fake gains (+1,034.0% trade).
3. `DRREDDY.NS` (5:1 split on 2024-10-28): Manufactured **₹337,200.43** in fake gains (+584.5% trade).

When the double-split multiplier is eliminated (treating split occurrences as tracking metadata only, matching `backtest_multi_pod.py`):
- **Variant 1 CAGR collapses from 23.42% to 5.56%**.
- **Variant 2 CAGR collapses from 15.06% to 3.33%**.
- **Variant 3 CAGR collapses from 14.54% to 3.41%**.

---

## 3. Results of the 5 Mandatory Sanity Checks

### Check 1: Price Adjustments (Splits & Dividends)
- **Splits**: Parquet OHLC data is already backward split-adjusted. Multiplying shares on split dates was 100% duplicate counting.
- **Dividends**: Yahoo Finance `close` is **unadjusted for dividends** (unlike `adj_close`). Adding cash dividends (`divs`) into the cash ledger is mathematically sound and not double-counted.

### Check 2: Fill Prices & Gap Execution
- **Baseline Simulation**: Stops are checked on daily close and filled at that day's close $\times (1 - \text{fee})$.
- **Gap-Down Open Fill Simulation**: When stops were forced to fill at **Next-Day Open** (capturing overnight gap downs), Variant 1 metrics were:
  - CAGR: **4.62%** (vs 5.56%)
  - Max Drawdown: **-24.34%** (vs -20.43%)
  - Sharpe: **0.52** (vs 0.58)

### Check 3: Profit Concentration & Top 5 Trades
- **With Split Bug**:
  - Total Realized PnL: ₹3,048,794.05
  - Top 5 Trades: ₹1,940,360.06 (**63.6%** of total profit, driven by Nestle, Eicher, Wipro, Dr Reddy, TCS splits).
- **Clean Audit (No Bug)**:
  - Total Realized PnL: **₹65,111.88** across 428 closed trades.
  - Top 5 Trades: ₹44,001.44 (**67.6%** of total profit): Bajaj Auto (₹14.3k), Wipro (₹7.6k), ONGC (₹7.5k), Tata Steel (₹7.4k), PowerGrid (₹7.1k).
  - **CAGR Without Top 5 Trades**: Drops to **4.08%** (Terminal Equity: ₹159,788.68).

### Check 4: Look-Ahead in Ranking & Membership
- **Ranking**: Vectorized momentum slope $\cdot R^2$ is calculated up to day $t$ close. Entries occur at day $t+1$ open. No forward lookahead in feature engineering.
- **Membership**: Uses point-in-time constituent dates. However, pre-2015 constituent history remains unverified by cryptographic PDF hashes (addressed below).

### Check 5: Transaction Cost Sanity
- **Clean Stressed Run** (7.5 bps slippage, ₹14.75 DP fee, holding-period tax, liquid cash yield): **5.56% CAGR** / ₹203,790 terminal.
- **Clean Zero-Cost Run** (0 bps slippage, ₹0 DP fee, 0 tax, 0 cash yield): **4.05% CAGR** / ₹159,001 terminal.
  - *Why is zero-cost lower than stressed?* Because the bot spends **33.5% of all trading days 100% in cash**. In the stressed run, cash earns the RBI liquid fund yield (~6.18% p.a., generating ₹108,442 in cumulative interest). In the zero-cost run, cash earns 0%, creating massive cash drag during bear/flat regimes.

---

## 4. Reconciling Baseline 1 (TRI vs Price Return)

- Earlier reported pre-tax figure of **10.08%** was the **Nifty 50 Price Return Index (PR)** (zero dividends, pure price appreciation from 4,494.65 to 23,644.80).
- The true **Nifty 50 Total Return Index (TRI)** with 1.35% historical dividend reinvestment compounded at **11.53% pre-tax**.
- After deducting statutory Long-Term Capital Gains tax (12.5% LTCG on terminal liquidation above ₹1.25L exemption) and selling costs, the **Post-Tax TRI CAGR is 10.80%**.
- Comparing the 10.80% post-tax TRI against the 10.08% pre-tax PR caused the confusion. Both figures are reconciled.

---

## 5. Other Gaps & Audited Invariants

### A. Pre-2015 Membership Provenance
- Of 104 membership changes:
  - **Post-2015**: 47 of 56 events have verified SHA-256 PDF hashes from `niftyindices.com`.
  - **Pre-2015**: Only 6 of 48 events have verified PDF hashes; 42 are reconstructed from NSE text notices. The 2007–2014 period remains unverified against primary PDFs.

### B. Reconciliation of Trials 28 to 35 ($N = 35$)
The 7 additional trials beyond the planned 28 were logged due to recording both normal (5 bps) and stressed (7.5 bps) runs:
- **Trial 28 (row 29)**: Commit `9cc7f03` Normal Run (7.26% CAGR, -25.28% MaxDD)
- **Trial 29 (row 30)**: Commit `9cc7f03` Stressed Run (7.05% CAGR, -25.59% MaxDD)
- **Trial 30 (row 31)**: Commit `75b8583` Variant 1 Normal (23.53% CAGR) [Bugged]
- **Trial 31 (row 32)**: Commit `75b8583` Variant 1 Stressed (23.42% CAGR) [Bugged]
- **Trial 32 (row 33)**: Commit `75b8583` Variant 2 Normal (15.23% CAGR) [Bugged]
- **Trial 33 (row 34)**: Commit `75b8583` Variant 2 Stressed (15.06% CAGR) [Bugged]
- **Trial 34 (row 35)**: Commit `75b8583` Variant 3 Normal (15.17% CAGR) [Bugged]
- **Trial 35 (row 36)**: Commit `75b8583` Variant 3 Stressed (14.54% CAGR) [Bugged]

### C. Missing Gate A Metrics (Monte Carlo & Parameter Stability)
- **Monte Carlo Permutation (1,000 runs)** on clean Variant 1:
  - Median Max Drawdown: **-23.50%**
  - **5th-Percentile Max Drawdown: -38.17%** (Breaches -30.00% hard limit -> **FAIL**).
- **Parameter Stability Grid** ($\pm 20\%$ Lookback & Kelly on Clean Variant 1):
  - Lookback 72d, Kelly 0.32: 4.99% CAGR / -21.66% MaxDD / 0.53 Sharpe
  - Lookback 72d, Kelly 0.40: 4.97% CAGR / -22.28% MaxDD / 0.52 Sharpe
  - Lookback 72d, Kelly 0.48: 4.61% CAGR / -22.73% MaxDD / 0.49 Sharpe
  - Lookback 90d, Kelly 0.32: 5.41% CAGR / -20.43% MaxDD / 0.58 Sharpe
  - Lookback 90d, Kelly 0.40: 5.56% CAGR / -20.43% MaxDD / 0.58 Sharpe
  - Lookback 90d, Kelly 0.48: 5.41% CAGR / -20.43% MaxDD / 0.56 Sharpe
  - Lookback 108d, Kelly 0.32: 6.08% CAGR / -21.47% MaxDD / 0.61 Sharpe
  - Lookback 108d, Kelly 0.40: 6.06% CAGR / -21.47% MaxDD / 0.60 Sharpe
  - Lookback 108d, Kelly 0.48: 5.95% CAGR / -21.47% MaxDD / 0.58 Sharpe
  *Verdict*: The strategy performance is stable across parameter space, but stable at **4.6% to 6.1% CAGR**, failing the 15% hurdle.

### D. US Pod Common Window Evaluation (2007–2024)
- **Stressed Run (7.5 bps)**:
  - CAGR: **13.59%** (Hurdle $\ge 15.00\%$ -> **FAIL**)
  - Max Drawdown: **-32.53%** (Hard Limit $\le -30.00\%$ -> **HARD DISQUALIFICATION**)
  - Sharpe Ratio: 0.76

---

## 6. Corrected Head-to-Head Comparative Table (2007–2024 Stressed)

| Metric | Baseline 1 (TRI) | Baseline 2 (EW) | Baseline 3 (Trend 200) | Audited Variant 1 | Audited Variant 2 | Audited Variant 3 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Initial Capital** | ₹80,000 | ₹80,000 | ₹80,000 | ₹80,000 | ₹80,000 | ₹80,000 |
| **Terminal Equity** | **₹469,816** | ₹356,222 | ₹252,660 | ₹203,790 | ₹141,012 | ₹142,922 |
| **Post-Tax CAGR** | **10.80%** | **9.04%** | **6.88%** | **5.56%** | **3.33%** | **3.41%** |
| **Max Drawdown** | -59.43% | -57.88% | -25.13% | **-20.43%** | **-21.16%** | **-21.18%** |
| **Calmar Ratio** | 0.18 | 0.16 | **0.27** | **0.27** | 0.16 | 0.16 |
| **Annualized Sharpe**| 0.60 | 0.55 | 0.57 | 0.58 | 0.38 | 0.40 |
| **Win Rate** | N/A | N/A | N/A | 34.35% | 32.43% | 31.27% |
| **Profit Factor** | N/A | N/A | N/A | 1.43 | 1.10 | 1.11 |
| **Closed Trades** | 0 | 17 | 12 | 428 | 663 | 742 |
| **Trades / Year** | 0.0 | 1.0 | 0.7 | 24.8 | 38.3 | 42.9 |
| **Total DP Charges**| ₹0.00 | ₹0.00 | ₹0.00 | ₹6,313.00 | ₹9,779.25 | ₹10,944.50 |
| **Total Tax Paid** | ₹57,000 | Deferred | ₹24,000 | ₹27,377.70 | ₹28,254.88 | ₹31,208.92 |
| **Gate A Status** | Benchmark | Benchmark | Benchmark | **FAILED** | **FAILED** | **FAILED** |

---

## 7. Strategic Conclusions & Next Steps

1. **Protocol Verdict**: The pre-registered dual-pod momentum engine **fails Gate A across all variants and both markets**.
2. **The Survivorship Reality**: When point-in-time dated constituent membership is combined with statutory taxes, flat transaction friction, and mathematically clean split data, **unleveraged equity momentum on the Nifty 50 produces ~5.5% CAGR**, underperforming a passive index investment and simple trend-following.
3. **No Paper Trading Promotion**: Gate B will **NOT** be activated.
4. **Holdout Preserved**: Calendar year 2025 remains pristine, unopened, and sealed.


---

## 8. Pre-Registered Multi-Asset Tactical Trend Matrix V2.1 Scoreboard

**Protocol Reference**: `MULTI_ASSET_TREND_PROTOCOL_V2_1.md` (SHA-256: `4C9151EC251FE5AB871876BDF8FF3491544681DB39C87DBD60C953357DA668FA`)  
**In-Sample Window**: `2007-09-24` to `2024-12-31` (17.27 Years | 4,235 Trading Days)  
**Starting Capital**: ₹80,000.00 INR | **2025 Holdout Window**: Strictly Sealed & Unopened  

```
====================================================================================================================================================
                                      MULTI-ASSET V2.1 TACTICAL TREND SCOREBOARD (POST-TAX & STRESSED)
====================================================================================================================================================
 Performance Metric         | Variant A (Dual Mom)  | Variant B (Anti-Whip) | Variant C (Risk-Parity) | Baseline 1 (1/N EW)   | Baseline 4 (Nifty TRI) 
----------------------------------------------------------------------------------------------------------------------------------------------------
 Post-Tax Stressed CAGR     | 9.82%                 | 5.26%                 | 5.41%                   | 14.17% [BENCHMARK]    | 10.14%                 
 Max Drawdown Depth         | -26.21% [FAIL]        | -32.92% [FAIL]        | -21.89% [PASS]          | -45.20% [FAIL]        | -59.48% [FAIL]         
 Annualized Sharpe Ratio    | 0.69                  | 0.40                  | 0.61                    | 0.98                  | 0.58                   
 Calmar Ratio (CAGR/|DD|)   | 0.37                  | 0.16                  | 0.25                    | 0.31                  | 0.17                   
 Terminal Equity (from 80k) | ₹4,03,650.05          | ₹1,93,982.40          | ₹1,98,920.15            | ₹7,88,899.70          | ₹4,24,431.12           
 Total Closed Trades        | 117                   | 106                   | 60                      | 17 (Annual Rebal)     | 0 (Buy & Hold)         
 Trades Per Year            | 6.8                   | 6.1                   | 3.5                     | 1.0                   | 0.0                    
 Total DP Fees Paid         | ₹1,725.75             | ₹1,563.50             | ₹885.00                 | ₹250.75               | ₹0.00                  
 Total Statutory Friction   | ₹12,061.60            | ₹10,240.15            | ₹6,412.30               | ₹4,110.50             | Deferred LTCG          
 Total Taxes (31.2% Slab)   | ₹1,06,009.06          | ₹45,212.80            | ₹48,310.20              | ₹98,450.00            | Deferred LTCG          
----------------------------------------------------------------------------------------------------------------------------------------------------
 In-Sample Date Window      | 2007-09-24:2024-12-31 | 2007-09-24:2024-12-31 | 2007-09-24:2024-12-31   | 2007-09-24:2024-12-31 | 2007-09-24:2024-12-31  
 Canonical Trial Log Row    | Row 77                | Row 79                | Row 81                  | Row 82                | Row 83                 
 Results JSON File          | ...variant_1.json     | ...variant_2.json     | ...variant_3.json       | ...baselines_v2_1.json| ...baselines_v2_1.json 
 Hurdle vs Baseline 1 (1/N) | FAILED (-4.35% Alpha) | FAILED (-8.91% Alpha) | FAILED (-8.76% Alpha)   | BENCHMARK HURDLE      | FAILED (-4.03% Alpha)  
 Gate A Clearance Verdict   | >> REJECTED <<        | >> REJECTED <<        | >> REJECTED <<          | >> BENCHMARK <<       | >> BENCHMARK <<        
====================================================================================================================================================
```

---

## 9. Formal Institutional Decision: Baseline 1 (14.17% CAGR, -45.2% Max DD) as the Mandatory Benchmark Hurdle

### The Decision:
**YES. Baseline 1 (Static 1/N Equal-Weight Multi-Asset Benchmark: 14.17% CAGR, -45.2% Max Drawdown) is formally ratified as the permanent, mandatory hurdle that EVERY active trading strategy must beat on a post-tax, post-friction basis to justify active management.**

### Quantitative Rationale:
1. **Economic Opportunity Cost**: A completely passive retail or institutional investor allocating equally across the 7 macro assets (`NIFTY50`, `NEXT50`, `MIDCAP150`, `GOLDBEES`, `SILVERBEES`, `NETFGILT`, `MON100`) and rebalancing once annually turns ₹80,000 into **₹7,88,899.70** (14.17% CAGR) post-tax. Active trading variants (Variant A: ₹4.03L / 9.82% CAGR; Variant B: ₹1.94L / 5.26% CAGR; Variant C: ₹1.98L / 5.41% CAGR) destroyed between ₹3.85L and ₹5.95L in investor terminal wealth through excessive friction, bad timing, and cash drag.
2. **The Dual Hurdle Standard**:
   - To pass Gate A, an active system must satisfy BOTH:
     $$\text{Strategy Post-Tax CAGR} > \text{Baseline 1 CAGR (14.17\%)}$$
     $$\text{Strategy Peak-to-Trough Max Drawdown} \ge -25.0\% \quad (\text{vs Baseline 1's catastrophic } -45.2\% \text{ drawdown})$$
   - If a strategy cannot beat 14.17% CAGR, active switching and stock-picking add negative alpha.
   - If a strategy beats 14.17% CAGR but suffers $> 25.0\%$ drawdown, it fails capital preservation.

---

## 10. Canonical Scoreboard-to-Artifact Mapping & Parity Table

Every headline number in the dashboard and institutional reports is verified to maintain exact 1:1 parity with its results JSON and `trial_log.csv`:

| Variant / Baseline | Metric | Results JSON File | Trial Log Row | In-Sample Window | Gate A Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Variant A (Dual Mom)** | 9.82% CAGR, -26.21% DD | `backtest_results_multi_asset_v2_1_variant_1.json` | Row 77 | 2007-09-24 to 2024-12-31 | REJECTED (MaxDD & Benchmark) |
| **Variant B (Anti-Whip)**| 5.26% CAGR, -32.92% DD | `backtest_results_multi_asset_v2_1_variant_2.json` | Row 79 | 2007-09-24 to 2024-12-31 | REJECTED (MaxDD & Benchmark) |
| **Variant C (Risk-Parity)**| 5.41% CAGR, -21.89% DD| `backtest_results_multi_asset_v2_1_variant_3.json` | Row 81 | 2007-09-24 to 2024-12-31 | REJECTED (Benchmark CAGR) |
| **Baseline 1 (1/N Equal)**| 14.17% CAGR, -45.20% DD | `multi_asset_baselines_v2_1.json` | Row 82 | 2007-09-24 to 2024-12-31 | MANDATORY HURDLE |
| **Baseline 4 (Nifty TRI)**| 10.14% CAGR, -59.48% DD | `multi_asset_baselines_v2_1.json` | Row 83 | 2007-09-24 to 2024-12-31 | PASSIVE MARKET BENCHMARK |
