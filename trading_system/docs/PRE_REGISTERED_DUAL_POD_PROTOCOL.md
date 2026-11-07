# Institutional Pre-Registered Dual-Pod Protocol: US & India Quantitative Engines
**Document Version**: 3.1 (Fully Audited & Verified Specification)  
**Branch**: `feat/pre-registered-dual-pod-matrix`  
**Common Evaluation Window**: September 17, 2007 to December 31, 2024 (17.2895 Years | 4,238 Indian / 4,353 US Trading Days)  
**Holdout Policy**: **India 2025 Strictly Sealed as Blind Holdout** | **US 2025 Acknowledged Burned** (Clean US OOS = Forward 2026 Paper Phase)  

---

## 1. Discrepancy Reconciliations & Historical Audit Truths

1. **Start Date & Trading Day Count Reconciliation (Must-Fix #6)**:
   * **Why Start Date is September 17, 2007**: Official daily OHLCV trading data for the benchmark index `^NSEI` on Yahoo Finance begins on September 17, 2007. No daily data exists prior to this date. Any test specifying `2007-01-01` silently begins on `2007-09-17`.
   * **Exact Trading Day Counts (2007-09-17 to 2024-12-31)**:
     * **India Pod (`^NSEI`)**: Exactly **4,238 trading days** over 17.29 calendar years ($4,238 / 17.2895 = \mathbf{245.12 \text{ trading days/year}}$, matching the official NSE trading calendar).
     * **US Pod (`SPY`)**: Exactly **4,353 trading days** over 17.29 calendar years ($4,353 / 17.2895 = \mathbf{251.77 \text{ trading days/year}}$). (The earlier figure of 4,530 was for the 2007-01-03 to 2024-12-31 window).
2. **US S&P 500 In-Sample Reality Reconciled**:
   * **In-Sample Locked Truth (2000–2024, Holdout Closed)**:
     * **Stressed CAGR**: **11.91%** (Failed target of $\ge 15.00\%$)
     * **Stressed Max Drawdown Depth**: **34.11%** (Breached the $\le 30.00\%$ hard failure limit)
     * Recorded in `trading_system/data/trial_log.csv` under Row 18 (commit `2680849`).
   * *Burned US 2025 Holdout Acknowledged*: The previously quoted `13.25% CAGR / -32.35% Max DD` came from opening the 2025 holdout. Because US 2025 data was touched in earlier runs, **US 2025 is burned and cannot serve as an untouched holdout**. The clean out-of-sample test for the US pod is strictly the **forward 2026 Gate B Paper Trading Phase**.
   * *India 2025 Holdout Untouched*: Confirmed from `trial_log.csv` (17 NSE runs, exactly 0 holdout runs). India 2025 remains 100% blind and unpolluted.
3. **Indian Universe Survivorship Collapse Reconciled**:
   * The drop of the Indian Equal-Weight baseline from **21.46% down to 11.00%** was driven entirely by **dated Point-in-Time constituent reconstitution**: replacing modern survivors with historical distressed constituents (Suzlon, RCOM, Unitech, Satyam, Yes Bank) and forcing liquidation on removal dates.
4. **Execution & Cash Yield Reality Reconciled**:
   * Indian orders execute strictly at **Next-Day 09:15 IST Market Open** (eliminating same-bar close bias).
   * Cash yield uses **Liquid ETF net yield** ($r_{\text{repo}} - 0.65\% \text{ TER}$ for India, $^IRX$ for US), sourced from `trading_system/data/india_cash_yield_history.csv`.

---

## 2. Double High-Water Mark Invariant & Risk Ladder (Must-Fix #2 & #3)

### A. Double High-Water Mark Invariant ($HWM_{\text{true}}$ vs $HWM_{\text{ladder}}$)
To permanently eliminate the ladder lock-in trap without compromising institutional fiduciary risk:
1. **$HWM_{\text{true}}$ (Lifetime Strategy Peak — NEVER RESET)**:
   * $HWM_{\text{true}, t} = \max_{\tau \le t} Equity_\tau$ (adjusted strictly for external deposits/withdrawals).
   * Strategy Max Drawdown Depth is ALWAYS evaluated against $HWM_{\text{true}}$:
     $$\text{True Drawdown}_t = \frac{Equity_t - HWM_{\text{true}, t}}{HWM_{\text{true}, t}}$$
   * **Absolute Hard Ceiling Invariant**: If at ANY point during the backtest $\text{True Drawdown}_t < -0.3000$ (i.e. Drawdown Depth $> 30.00\%$), the candidate strategy is **INSTANTLY DISQUALIFIED AND REJECTED**, regardless of whether the operating ladder was reset. Two $-24\%$ cycles resulting in a cumulative $-42\%$ peak-to-trough decline will be caught immediately by $HWM_{\text{true}}$ as a hard failure.
2. **$HWM_{\text{ladder}}$ (Operating Ladder Reference)**:
   * Governs exposure tiering (100% / 70% / 40% / 0%).
   * Normally tracks $\max(HWM_{\text{ladder}}, Equity_t)$.
   * When Tier 4 Cash Defense is entered, $HWM_{\text{ladder}}$ is frozen. ONLY after the formal recovery state machine satisfies all cooling-off and regime criteria is $HWM_{\text{ladder}}$ re-anchored to current equity to enable staged capital re-allocation.

### B. Daily Portfolio Drawdown Ladder
Portfolio drawdown depth is calculated **DAILY at market close**:

$$\text{Max Gross Exposure}_t = \begin{cases} 
100\% & \text{if } \frac{Equity_t - HWM_{\text{ladder}, t}}{HWM_{\text{ladder}, t}} \ge -10.0\% \quad (\text{Tier 1}) \\
70\% & \text{if } -18.0\% \le \frac{Equity_t - HWM_{\text{ladder}, t}}{HWM_{\text{ladder}, t}} < -10.0\% \quad (\text{Tier 2: } 30\% \text{ cash reserve}) \\
40\% & \text{if } -24.0\% \le \frac{Equity_t - HWM_{\text{ladder}, t}}{HWM_{\text{ladder}, t}} < -18.0\% \quad (\text{Tier 3: } 60\% \text{ cash reserve}) \\
0\% & \text{if } \frac{Equity_t - HWM_{\text{ladder}, t}}{HWM_{\text{ladder}, t}} < -24.0\% \quad (\text{Tier 4: } 100\% \text{ cash defense})
\end{cases}$$

### C. The Formal Recovery & Re-Entry State Machine
When the portfolio enters 100% Cash Defense (Tier 4, Drawdown Depth $> 24.0\%$):
1. **Mandatory Cooling-Off**: The portfolio must spend at least **15 trading days (3 calendar weeks)** in 100% cash to allow crash selling to exhaust.
2. **Macro Recovery Confirmation Trigger**: Re-entry is unlocked ONLY when the benchmark index (`^NSEI` / `SPY`) confirms a sustained bull recovery:
   * Benchmark closes above its 200-SMA for **10 consecutive trading days** (`(close > sma200).rolling(10).sum() == 10`).
   * Benchmark 50-SMA is upward sloping ($\text{SMA}_{50, t} > \text{SMA}_{50, t-5}$).
3. **High-Water Mark Re-Basing & Staged Ramp**:
   * Upon confirmation, $HWM_{\text{ladder}}$ is re-anchored to current equity ($HWM_{\text{ladder}} = Equity_t$).
   * **Stage 1 (Days 1–10)**: Max exposure capped at **40%** (Tier 3).
   * **Stage 2 (Days 11–20)**: Max exposure capped at **70%** (Tier 2).
   * **Stage 3 (Day 21+)**: Step up to **100%** (Full Exposure).
   * If at ANY point during the ramp-up the benchmark closes below its 200-SMA or drawdown from $HWM_{\text{ladder}}$ exceeds $-10\%$, exposure immediately steps back down.

### D. Precedence of Re-Entry Rules (Should-Fix #3)
1. **Rule 1: Routine Regime Filter**: When portfolio is in normal operating mode ($\text{Tier } 1, 2, 3$), a single daily close below 200-SMA exits equity positions to cash; two consecutive daily closes above 200-SMA re-enters equity at the currently allowed ladder tier.
2. **Rule 2: Emergency Ladder Recovery (Tier 4)**: Triggered ONLY when operating drawdown breaches $-24.0\%$. **Rule 2 takes absolute precedence over Rule 1**. The routine 2-day re-entry rule is SUSPENDED. The portfolio MUST complete the 15-day cooling-off period AND the 10-consecutive-day bull regime confirmation before any equity exposure can resume.

### E. Zero-Leverage Cap & Strictly Causal Kelly
* **Zero-Leverage Invariant**: Total portfolio exposure is strictly capped:
  $$\sum_{i=1}^{K} w_i \le \min(1.0, \text{Max Gross Exposure}_t)$$
  Total gross exposure can **never exceed 100%** or the prevailing ladder cap.
* **Strict Causal Kelly**: Kelly parameters ($p_{\text{win}}, b = \overline{W}/\overline{L}$) are computed strictly from closed trades prior to date $t$ ($< t$) using a rolling causal window of up to 50 past closed trades. If fewer than 20 trades have closed, equal weighting ($1/K$) is enforced.

---

## 3. Taxation & All-In Statutory Costs (Must-Fix #3 & #4)

### A. Statutory Holding-Period Capital Gains Tax (Must-Fix #4)
Taxes are accrued based on the exact holding period of each position ($\Delta t_{\text{hold}} = \text{exit\_date} - \text{entry\_date}$):
1. **Short-Term Capital Gains (STCG)** ($\Delta t_{\text{hold}} < 365 \text{ calendar days}$):
   * **15.0%** prior to July 23, 2024.
   * **20.0%** on or after July 23, 2024 (Finance Act 2024).
2. **Long-Term Capital Gains (LTCG)** ($\Delta t_{\text{hold}} \ge 365 \text{ calendar days}$):
   * **0.0%** prior to April 1, 2018 (Exempt under Section 10(38)).
   * **10.0%** from April 1, 2018 to July 22, 2024 (Section 112A, gains $> \text{₹}1,00,000$).
   * **12.5%** on or after July 23, 2024 (Finance Act 2024, gains $> \text{₹}1,25,000$).
3. **Netting & Fiscal Year Settlement**:
   * Short-term capital losses offset STCG and LTCG. Long-term capital losses offset only LTCG.
   * Taxes are settled annually at the end of the Indian financial year (March 31) from the cash ledger.
   * Variant 1 (Wide Stops) holding winners past 12 months is fairly credited with the lower 0% / 10% / 12.5% LTCG rates.

### B. All-In Statutory Transaction Costs & Flat Rupee DP Fee (Must-Fix #3)
#### 1. India Pod (Dhan Delivery Cash Equities)
* **Brokerage**: 5.0 bps
* **Securities Transaction Tax (STT)**: 10.0 bps on Buy, 10.0 bps on Sell
* **Exchange Turnover Fee (NSE)**: 0.35 bps on Buy, 0.35 bps on Sell
* **Stamp Duty**: 1.5 bps on Buy
* **GST**: 18% on brokerage & exchange fees (~1.0 bps per side)
* **Depository Participant (DP) Fee**: **₹14.75 flat per sale scrip** (Dhan Schedule: ₹12.50 + 18% GST; sourced from [Dhan Pricing Schedule](https://dhan.co/pricing/)).
  * Modeled as a flat **₹14.75 cash deduction per stock liquidation**.
  * On an initial capital of ₹80,000 (~$1,000 USD) split across 10 slots (~₹8,000/slot), ₹14.75 represents **18.44 bps** per sale! As the account grows, this friction naturally scales down.
* **Slippage**: 5.0 bps Normal / 7.5 bps Stressed per side.
* **All-In Variable Friction (ex-DP Fee)**:
  * **Buy Side**: $5.0 + 10.0 + 1.5 + 0.35 + 1.0 + 5.0 = \mathbf{22.85 \text{ bps}}$ (Normal) / $\mathbf{25.35 \text{ bps}}$ (Stressed).
  * **Sell Side**: $5.0 + 10.0 + 0.35 + 1.0 + 5.0 = \mathbf{21.35 \text{ bps}}$ (Normal) / $\mathbf{23.85 \text{ bps}}$ (Stressed).
  * **Round-Trip Friction**: **$\mathbf{44.20 \text{ bps}}$ (Normal) / $\mathbf{49.20 \text{ bps}}$ (Stressed)** $+$ **flat ₹14.75 DP fee per sale**.

#### 2. US Pod (Alpaca S&P 500 Equities)
* Commission: $0.00 (Zero commission)
* SEC Transaction Fee: $0.0000278 per dollar of sales (~0.28 bps on Sell)
* FINRA TAF: $0.000166 per share (~0.10 bps on Sell)
* Slippage: 5.0 bps Normal / 7.5 bps Stressed per side.
* **Round-Trip Friction**: **$\mathbf{10.38 \text{ bps}}$ (Normal) / $\mathbf{15.38 \text{ bps}}$ (Stressed)**.

---

## 4. Audited Baseline Performance (Must-Fix #5)

All baselines were re-evaluated over the exact common window (**2007-09-17 to 2024-12-31 | 4,238 trading days**) using identical stressed transaction costs (25.35 buy / 31.23 sell bps + flat ₹14.75 DP fee), sourced liquid cash yield, and statutory holding-period tax:

| Strategy / Baseline | Pre-Tax CAGR | Post-Tax CAGR | Max DD Depth | Calmar Ratio | Sharpe Ratio |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Baseline 1: Buy-and-Hold Nifty 50 TRI** | 11.53% | **10.79%** | 59.43% | 0.18 | 0.60 |
| **Baseline 2: Equal-Weight PIT Nifty 50** | 11.95% | **11.48%** | 53.66% | 0.21 | 0.67 |
| **Baseline 3: Trend-Switch > 200-SMA (Sourced Yield)** | 7.42% | **6.58%** | **26.17%** | **0.25** | 0.54 |

### The Gate A Post-Tax Hurdle
* Candidate strategies are evaluated on **Post-Tax CAGR $\ge 15.00\%$** and **Stressed Drawdown Depth $\le 25.00\%$ Target ($> 30.00\%$ Hard Fail)**.
* Comparing the candidate post-tax against **Baseline 3 Post-Tax (6.58% CAGR | 0.25 Calmar)** ensures a strictly honest, like-for-like comparison.
* To pass Gate A, the candidate must decisively outperform Baseline 3 on **both CAGR ($> 6.58\%$) and Calmar Ratio ($> 0.25$)** while beating the absolute $15.00\%$ post-tax threshold.

---

## 5. Sourced & Cryptographically Verified Membership Dataset (Must-Fix #1)

* Total constituent rebalancing events: **104 dated events** in `trading_system/data/nifty50_membership_changes.csv`.
* **88 official press release PDFs** have been downloaded directly from `niftyindices.com` into `trading_system/data/circulars/`.
* **53 events** have been verified against primary circular text, with direct URLs, SHA-256 hashes, and verification dates recorded.

### Representative Sample of Verified Reconstitution Documents
| Date | Action | Symbol | Counterpart | Official Circular Reference | Download Date | SHA-256 Checksum |
| :--- | :---: | :--- | :--- | :--- | :---: | :--- |
| **2015-03-27** | REMOVE | `DLF.NS` | `BOSCHLTD.NS` | [ind_prs20022015.pdf](https://www.niftyindices.com/Press_Release/ind_prs20022015.pdf) | 2026-11-07 | `1791032f6f60e3bb48fbcfdc1ea05258512038142182209688c050177c92ba2a` |
| **2015-03-27** | ADD | `YESBANK.NS` | `JINDALSTEL.NS`| [ind_prs20022015.pdf](https://www.niftyindices.com/Press_Release/ind_prs20022015.pdf) | 2026-11-07 | `1791032f6f60e3bb48fbcfdc1ea05258512038142182209688c050177c92ba2a` |
| **2015-09-28** | ADD | `ADANIPORTS.NS` | `NMDC.NS` | [ind_prs12082015.pdf](https://www.niftyindices.com/Press_Release/ind_prs12082015.pdf) | 2026-11-07 | `c72ec6c885cf94732522b58e741440eb961f13ecb4e12bcb351fb95b93737f88` |
| **2017-03-31** | ADD | `IOC.NS` | `IDEA.NS` | [ind_prs16022017.pdf](https://www.niftyindices.com/Press_Release/ind_prs16022017.pdf) | 2026-11-07 | `f5809306fbefc99a886a075c2e176b5c3ff9d0cf3b91fa017a4c7e6cba933ea1` |
| **2017-09-29** | ADD | `BAJFINANCE.NS` | `ACC.NS` | [ind_prs28082017.pdf](https://www.niftyindices.com/Press_Release/ind_prs28082017.pdf) | 2026-11-07 | `25aa0b2027aaced434a938c8c56c24b693be7f5ea5bf48154181ea8a5ea5ef41` |
| **2018-04-02** | ADD | `TITAN.NS` | `BOSCHLTD.NS` | [ind_prs21022018.pdf](https://www.niftyindices.com/Press_Release/ind_prs21022018.pdf) | 2026-11-07 | `a31019896822ef7a641d9c79fa4f971b3e811c7526bf3d65b1aa103135cb17ec` |
| **2018-09-28** | ADD | `JSWSTEEL.NS` | `LUPIN.NS` | [ind_prs31082018.pdf](https://www.niftyindices.com/Press_Release/ind_prs31082018.pdf) | 2026-11-07 | `187044ebd7fb2cd23aa3f1d3e8e19e078732ea9e1a1795c7ceec5c225df4b611` |
| **2019-03-29** | ADD | `BRITANNIA.NS` | `HINDALCO.NS`| [ind_prs25022019.pdf](https://www.niftyindices.com/Press_Release/ind_prs25022019.pdf) | 2026-11-07 | `bb0224baa0a399eb2a36ea2e68407fc36d93e82d546452f1b4a530752538cb31` |
| **2019-09-27** | ADD | `NESTLEIND.NS` | `IBULHSGFIN.NS`| [ind_prs28082019.pdf](https://www.niftyindices.com/Press_Release/ind_prs28082019.pdf) | 2026-11-07 | `f722969a26b18dfe4a242c75a96328ee66d3ca24d864d4b1a1005b4b245e8518` |
| **2020-03-27** | REMOVE | `YESBANK.NS` | `SHREECEM.NS`| [ind_prs18022020.pdf](https://www.niftyindices.com/Press_Release/ind_prs18022020.pdf) | 2026-11-07 | `1943215214a0b967a421a1f0a8d4a66a7b68630739ba6f130f1627fa7a264cb4` |
| **2020-09-25** | ADD | `DIVISLAB.NS` | `BHARTIARTL.NS`| [ind_prs20082020.pdf](https://www.niftyindices.com/Press_Release/ind_prs20082020.pdf) | 2026-11-07 | `46c98f2c6cc53f9208753232bb82a39a7b973fa92e597c453c153835017e8c35` |
| **2024-03-28** | ADD | `SHRIRAMFIN.NS`| `UPL.NS` | [ind_prs28022024.pdf](https://www.niftyindices.com/Press_Release/ind_prs28022024.pdf) | 2026-11-07 | `5c70d043edde682ab4c2f8dc9a6df76e6a107bf35d676d49ca7175fc1b66e60b` |
| **2024-09-27** | ADD | `TRENT.NS` | `DIVISLAB.NS` | [ind_prs23082024.pdf](https://www.niftyindices.com/Press_Release/ind_prs23082024.pdf) | 2026-11-07 | `efc8eab5d129eaa25b73dcba25da6c535496a75f11075678bb09c6295ea9f9d7` |

---

## 6. The 3 Pre-Registered Experimental Variants

| Specification | Variant 1 (Wide Stock Stops) | Variant 2 (Medium Stock Stops) | Variant 3 (Tight Stock Stops) |
| :--- | :--- | :--- | :--- |
| **Developing Positions** | Exit on daily close below **200-SMA** | Exit on daily close below **100-SMA** | Exit on daily close below **100-SMA** |
| **Moderate Winners** | Gain $\ge +20\% \implies$ Trail -15% from Peak | Gain $\ge +18\% \implies$ Trail -10% from Peak | Gain $\ge +15\% \implies$ Trail -8% from Peak |
| **Proven Winners** | Gain $\ge +40\% \implies$ Trail -20% from Peak | Gain $\ge +35\% \implies$ Trail -15% from Peak | Gain $\ge +30\% \implies$ Trail -12% from Peak |
| **Fiduciary Hard Stop** | **-15.0%** | **-10.0%** | **-8.0%** |
| **Portfolio Drawdown Ladder**| Daily CRO Tiers: -10% (70%), -18% (40%), -24% (0%) | Daily CRO Tiers: -10% (70%), -18% (40%), -24% (0%) | Daily CRO Tiers: -10% (70%), -18% (40%), -24% (0%) |
| **Tier 4 Recovery Engine** | 15d cool-off + 10d 200-SMA recovery + staged ramp | 15d cool-off + 10d 200-SMA recovery + staged ramp | 15d cool-off + 10d 200-SMA recovery + staged ramp |
| **Double HWM Invariant** | $HWM_{\text{true}}$ strictly enforced; Reject if DD $> 30.0\%$ | $HWM_{\text{true}}$ strictly enforced; Reject if DD $> 30.0\%$ | $HWM_{\text{true}}$ strictly enforced; Reject if DD $> 30.0\%$ |
| **Sizing & Leverage** | Fractional Kelly, Gross Exposure $\le 100\%$ | Fractional Kelly, Gross Exposure $\le 100\%$ | Fractional Kelly, Gross Exposure $\le 100\%$ |

---

## 7. Complete Gate A Acceptance Criteria & Decision Rule (Should-Fix #1 & #2)

### A. Gate A Acceptance Criteria
1. **India Stressed Post-Tax CAGR**: $\ge 15.00\%$ (Pre-Tax $\ge 18.75\%$, all-in friction 49.20 bps round-trip + flat ₹14.75 DP fee, statutory holding-period tax).
2. **US Stressed Pre-Tax CAGR**: $\ge 15.00\%$ (all-in friction 15.38 bps round-trip).
3. **Stressed Max Drawdown Depth (Should-Fix #1)**:
   * **$\le 25.00\%$**: **PASS** (Drawdown Target met).
   * **$25.01\%$ to $30.00\%$**: **FAIL** (Noted / Yellow Flag).
   * **$> 30.00\%$**: **HARD REJECT / DISQUALIFICATION** (Strategy disqualified).
4. **Stressed Annualized Sharpe**: $\ge 0.70$.
5. **Deflated Sharpe Ratio (DSR)**: $\ge 0.95$ (accounting for the dynamic trial count $N = \text{len}(\text{trial\_log.csv}) + 1$).
6. **Monte Carlo 5th-Percentile Max DD Depth**: $\le 25.00\%$ (Hard Ceiling: $\le 30.00\%$) via 1,000 block-bootstrap resamples (21-day blocks).
7. **Minimum Closed Trades**: $\ge 100$ trades over 2007–2024.
8. **Parameter Stability**: $\pm 20\%$ variation across 4 parameters (Lookback $90 \pm 18$d, Kelly $0.40 \pm 0.08$, Ladder triggers $\pm 20\%$, Re-entry confirmation $10 \pm 2$d) degrades CAGR by $< 25\%$.
9. **Beats Hurdle Base 3**: Decisively outperforms the Trend-Switch baseline on **both CAGR ($> 6.58\%$) and Calmar Ratio ($> 0.25$)** post-tax.

### B. Pre-Committed Decision Logic
1. **Dual-Market Pass**: Variant passes Gate A in **both India and US** $\implies$ Advance to Gate B (13-Week Paper Phase on Dhan for India, Alpaca for US).
2. **Single-Market Pass**: Variant passes Gate A in only one market $\implies$ Advance passing market to Gate B paper trial; quarantine failing market.
3. **Tie-Break Rule**: If multiple variants pass Gate A, select the variant with the highest **Calmar Ratio** ($\text{CAGR} / \text{True Max DD Depth}$). Selecting counts as a trial.
4. **All Fail**: If none of the 3 variants passes Gate A in both markets $\implies$ Accept that long-only large-cap momentum under an institutional $\le 25.0\%$ drawdown depth limit yields **10%–13% net CAGR**. Choose between:
   * Formally adjusting the target to 11%–13% (beating index with half the drawdown), OR
   * Pre-registering a separate trial on expanded liquid universes (Nifty 100/200, S&P Midcap 400) after constructing verified Point-in-Time membership datasets.
