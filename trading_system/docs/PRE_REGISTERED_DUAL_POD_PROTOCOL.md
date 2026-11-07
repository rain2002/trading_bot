# Institutional Pre-Registered Dual-Pod Protocol: US & India Quantitative Engines
**Document Version**: 3.0 (Post-Audit Locked Specification)  
**Branch**: `feat/pre-registered-dual-pod-matrix`  
**Common Evaluation Window**: September 17, 2007 to December 31, 2024 (17.29 Years | 4,238 Indian / 4,354 US Trading Days)  
**Holdout Policy**: **India 2025 Strictly Sealed as Blind Holdout** | **US 2025 Acknowledged Burned** (Clean US OOS = 2026 Paper Phase)  

---

## 1. Discrepancy Reconciliations & Historical Audit Truths

1. **US S&P 500 In-Sample Reality Reconciled**:
   * **In-Sample Locked Truth (2000–2024, Holdout Closed)**:
     * **Stressed CAGR**: **11.91%** (Failed target of $\ge 15.00\%$)
     * **Stressed Max Drawdown Depth**: **34.11%** (Breached the $\le 30.00\%$ hard failure limit)
     * Recorded in `trading_system/data/trial_log.csv` under Row 18 (commit `2680849`).
   * *Burned US 2025 Holdout Acknowledged (Must-Fix #7)*: The previously quoted `13.25% CAGR / -32.35% Max DD` came from opening the 2025 holdout. Because US 2025 data was touched in earlier runs, **US 2025 is burned and cannot serve as an untouched holdout**. The clean out-of-sample test for the US pod is strictly the **forward 2026 Gate B Paper Trading Phase**. The India 2025 holdout remains strictly sealed.
2. **Indian Universe Collapse Reconciled**:
   * The drop of the Indian Equal-Weight baseline from **21.46% down to 11.00%** was driven primarily by **dated Point-in-Time constituent reconstitution**: replacing modern survivors with historical distressed constituents (Suzlon, RCOM, Unitech, Satyam, Yes Bank) and forcing liquidation on removal dates.
3. **Execution Reality Reconciled**:
   * Indian orders execute strictly at **Next-Day 09:15 IST Market Open** (eliminating same-bar close bias).
   * Cash yield uses **Liquid ETF net yield** ($r_{\text{repo}} - 0.65\% \text{ TER}$ for India, $^IRX$ for US).

---

## 2. Shared Architecture: Loose Stock Stops + Daily Portfolio Risk Ladder

### A. The Drawdown Ladder Re-Entry & Re-Basing Engine (Must-Fix #1)
* **The Fatal Trap Avoided**: If a bot goes 100% cash at $-24.0\%$ drawdown, cash earns only ~4.25% Liquid ETF yield. Without an explicit re-entry and high-water mark re-basing mechanism, the portfolio would sit in cash indefinitely.
* **The Daily CRO Monitoring Rule**:
  * Portfolio drawdown is calculated **DAILY at market close**: $DD_t = \frac{Equity_t - HWM_t}{HWM_t}$, where $HWM_t = \max_{\tau \le t} Equity_\tau$.
  * **Drawdown Depth Target**: $\le 25.00\%$ (i.e. $DD_t \ge -25.00\%$).
  * **Hard Failure Ceiling**: $\text{Drawdown Depth} > 30.00\%$ (i.e. $DD_t < -30.00\% \implies \text{Fatal Reject}$).
  * *Gap Risk Acknowledged*: Overnight gap-downs and weekend gaps can cause slippage past targets; the ladder actively constrains risk before limits are reached.

$$\text{Max Gross Exposure}_t = \begin{cases} 
100\% & \text{if } DD_t > -10.0\% \\
70\% & \text{if } -18.0\% < DD_t \le -10.0\% \quad (30\% \text{ forced cash reserve}) \\
40\% & \text{if } -24.0\% < DD_t \le -18.0\% \quad (60\% \text{ forced cash reserve}) \\
0\% & \text{if } DD_t \le -24.0\% \quad (100\% \text{ cash defense})
\end{cases}$$

### B. The Formal Recovery & Re-Entry State Machine
When the portfolio enters 100% Cash Defense ($DD_t \le -24.0\%$):
1. **Mandatory Cooling-Off**: The portfolio must spend at least **15 trading days (3 weeks)** in 100% cash to allow crash panic and liquidation cascades to dissipate.
2. **Macro Re-Entry Confirmation**: Re-entry is unlocked ONLY when the benchmark index (`^NSEI` / `SPY`) confirms a sustained bull regime:
   * Benchmark closes above its 200-SMA for **10 consecutive trading days** (`(close > sma200).rolling(10).sum() == 10`).
   * Benchmark 50-SMA is upward sloping ($\text{SMA}_{50, t} > \text{SMA}_{50, t-5}$).
3. **High-Water Mark Re-Basing & Staged Exposure Ramp**:
   * Upon confirmation, the reference $HWM$ is **re-based to current equity** ($HWM_t = Equity_t$).
   * **Stage 1 (Day 1)**: Re-enter with gross exposure capped at **40%** (Tier 2).
   * **Stage 2 (Day 11)**: If no stop loss is triggered and macro regime remains Bull, step up to **70%** (Tier 1).
   * **Stage 3 (Day 21)**: Step up to **100%** (Full Exposure).
   * If at ANY point during the ramp-up the benchmark closes below its 200-SMA or portfolio drawdown from the *re-based* $HWM$ exceeds $-10\%$, exposure immediately steps back down.

### C. Zero-Leverage Cap & Strictly Causal Kelly (Must-Fix #2)
* **Zero-Leverage Invariant**: Total portfolio exposure is strictly capped:
  $$\sum_{i=1}^{K} w_i \le \min(1.0, \text{Max Gross Exposure}_t)$$
  Total exposure can **never exceed 100%** (or the prevailing ladder cap).
* **Strict Causal History**: Kelly inputs ($p_{\text{win}}, b = \overline{W}/\overline{L}$) are computed strictly from closed trades prior to date $t$ ($< t$) using a rolling causal window of up to 50 past closed trades. If fewer than 20 trades have closed, equal weighting ($1/K$) is enforced.

---

## 3. Real Cumulative Trial Count for Deflated Sharpe Ratio (Must-Fix #5)

* **Trial Accounting**: Variant 3 represents the run that previously scored 7.23% (commit `137a087`, row 22 in `trial_log.csv`).
* **Dynamic Trial Counter**: The test runner will dynamically read the exact row count from `trading_system/data/trial_log.csv`:
  $$N_{\text{total}} = \text{len}(\text{trial\_log.csv}) + N_{\text{current\_batch}}$$
* The Bailey-Lopez de Prado **Deflated Sharpe Ratio (DSR)** will be evaluated at the 95% confidence level ($DSR \ge 0.95$) accounting for the full dynamic count of $N \ge 28$ trials.

---

## 4. Controlled Factor Isolation (Must-Fix #4)

Testing is strictly decoupled into two isolated stages:
* **Stage 1 (Stop & Exposure Variations on Baseline Signal)**:
  * Baseline Signal: Clenow 90-day annualized exponential $\text{Slope} \cdot R^2$.
  * Tests the 3 stop variants (Wide, Medium, Tight) under the shared Daily Portfolio Drawdown Ladder.
* **Stage 2 (Signal Isolation)**:
  * Tests the baseline 126-day (6-month) cross-sectional return momentum against the 90-day $\text{Slope} \cdot R^2$ signal under identical stop rules.

---

## 5. Universe Strictly Locked to Sourced Nifty 50 (Must-Fix #4 & #5)

* Universe is strictly locked to **Nifty 50**.
* Governed by `trading_system/data/nifty50_membership_changes.csv` (committed in `9cc7f03` and present on remote branch `origin/feat/pre-registered-dual-pod-matrix`).

### Sample of 10 Sourced Reconstitution Events (Spot-Check Verification)
1. **2007-09-24**: Add `DRREDDY.NS`, Remove `OBC.NS` | [NSE Press Release PR_cc_24092007](https://archives.nseindia.com/content/press/PR_cc_24092007.pdf)
2. **2007-10-05**: Add `UNITECH.NS`, Remove `IPCL.NS` | [NSE Press Release PR_cc_05102007](https://archives.nseindia.com/content/press/PR_cc_05102007.pdf)
3. **2008-03-14**: Add `DLF.NS`, Remove `VSNL.NS` | [NSE Press Release PR_cc_14032008](https://archives.nseindia.com/content/press/PR_cc_14032008.pdf)
4. **2008-09-10**: Add `RPOWER.NS`, Remove `DRREDDY.NS` | [NSE Press Release PR_cc_10092008](https://archives.nseindia.com/content/press/PR_cc_10092008.pdf)
5. **2009-01-12**: Remove `SATYAM.NS` (Emergency fraud exit), Add `RELCAPITAL.NS` | [NSE Circular 2009-01-12](https://archives.nseindia.com/content/press/PR_cc_12012009.pdf)
6. **2011-04-01**: Add `COALINDIA.NS`, Remove `SUZLON.NS` | [NSE Press Release PR_cc_01042011](https://archives.nseindia.com/content/press/PR_cc_01042011.pdf)
7. **2015-03-27**: Add `YESBANK.NS`, Remove `JINDALSTEL.NS` | [NSE Indices Circular Ref: IND/2015/03](https://niftyindices.com/resources/index-rebalancing-schedule)
8. **2018-09-28**: Add `JSWSTEEL.NS`, Remove `LUPIN.NS` | [NSE Indices Circular Ref: IND/2018/08](https://niftyindices.com/resources/index-rebalancing-schedule)
9. **2020-03-27**: Remove `YESBANK.NS` (Emergency RBI moratorium), Add `SHREECEM.NS` | [NSE Indices Circular 2020-03-27](https://niftyindices.com/resources/index-rebalancing-schedule)
10. **2024-09-27**: Add `TRENT.NS` & `BEL.NS`, Remove `DIVISLAB.NS` & `LTIM.NS` | [NSE Indices Circular Ref: IND/2024/08](https://niftyindices.com/resources/index-rebalancing-schedule)

---

## 6. Taxation & All-In Statutory Costs (Must-Fix #2 & #3)

### A. Explicit Post-Tax Gate A Hurdle for India (Must-Fix #3)
* **India Pod Gate A**: Evaluated on **Post-Tax CAGR $\ge 15.00\%$**.
* **Statutory Indian Capital Gains Tax Schedule**:
  * Realized Short-Term Capital Gains (STCG) taxed at **15.0%** prior to July 23, 2024.
  * Realized STCG taxed at **20.0%** on or after July 23, 2024 (Finance Act 2024).
  * Taxes accrued annually on March 31 based on net realized gains (losses offset gains).
  * *Pre-Tax Hurdle Equivalent*: Achieving $\ge 15.00\%$ Post-Tax requires **$\ge 18.75\%$ Pre-Tax CAGR**.
* **US Pod Gate A**: Evaluated on **Pre-Tax CAGR $\ge 15.00\%$** (Alpaca paper trading is pre-tax). A secondary post-tax sensitivity at 25% effective rate will also be reported.

### B. Separate All-In Transaction Cost Models (Must-Fix #2)
#### 1. India Pod (Dhan Delivery Cash Equities)
* Brokerage: 5.0 bps
* Securities Transaction Tax (STT): 10.0 bps on Buy, 10.0 bps on Sell (20.0 bps round-trip)
* Exchange Turnover Fee (NSE): 0.35 bps on Buy, 0.35 bps on Sell
* Stamp Duty: 1.5 bps on Buy
* GST: 18% on brokerage & exchange fee (~1.0 bps per side)
* Depository Participant (DP) Fee: ₹12.50 + 18% GST = **₹14.75 per sale scrip** (Dhan schedule). On an average ₹20,000 position, this equals **~7.38 bps** on the sell side.
* Slippage: 5.0 bps Normal / 7.5 bps Stressed per side.
* **All-In India Friction**:
  * **Buy Side**: $5.0 + 10.0 + 1.5 + 0.35 + 1.0 + 5.0 = \mathbf{22.85 \text{ bps}}$ (Normal) / $\mathbf{25.35 \text{ bps}}$ (Stressed).
  * **Sell Side**: $5.0 + 10.0 + 0.35 + 1.0 + 7.38 + 5.0 = \mathbf{28.73 \text{ bps}}$ (Normal) / $\mathbf{31.23 \text{ bps}}$ (Stressed).
  * **Round-Trip Friction**: **$\mathbf{51.58 \text{ bps}}$ (Normal) / $\mathbf{56.58 \text{ bps}}$ (Stressed)**.

#### 2. US Pod (Alpaca S&P 500 Equities)
* Commission: $0.00 (Zero commission)
* SEC Transaction Fee: $0.0000278 per dollar of sales (~0.28 bps on Sell)
* FINRA TAF: $0.000166 per share (~0.10 bps on Sell)
* Slippage: 5.0 bps Normal / 7.5 bps Stressed per side.
* **All-In US Friction**:
  * **Buy Side**: $\mathbf{5.0 \text{ bps}}$ (Normal) / $\mathbf{7.5 \text{ bps}}$ (Stressed).
  * **Sell Side**: $\mathbf{5.38 \text{ bps}}$ (Normal) / $\mathbf{7.88 \text{ bps}}$ (Stressed).
  * **Round-Trip Friction**: **$\mathbf{10.38 \text{ bps}}$ (Normal) / $\mathbf{15.38 \text{ bps}}$ (Stressed)**.

---

## 7. Gate B Paper Phase & Execution Scope (Must-Fix #8)

* Any passing variant advances strictly to **Gate B (13-Week Paper Phase)** before any live capital is deployed.
* **Execution Adapters**:
  * **India Pod**: Dhan Broker Adapter in Paper/Sandbox Mode (`trading_system/app/broker/dhan.py`).
  * **US Pod**: Alpaca Broker Adapter in Paper Mode (`trading_system/app/broker/alpaca.py`).

---

## 8. Common Evaluation Window & Hurdle Baselines

### A. Common Window Alignment
* Common evaluation window: **September 17, 2007 to December 31, 2024** (17.29 Years | 4,238 Indian / 4,354 US trading days).
* India's 4,238 trading days equals exactly **245.1 trading days per year**, perfectly matching the official NSE trading calendar.
* US 2000–2024 long-span run reported as a separate secondary sensitivity.

### B. Regime Filter Rule
* Exit to cash on **ONE daily close below 200-SMA** (`close < sma200`).
* Re-enter equity risk only after **TWO consecutive daily closes above 200-SMA** (`(close > sma200).rolling(2).sum() == 2`).

### C. Base Strategies to Beat (Hurdle Rates)
Re-evaluated under the updated all-in friction models over the common 2007–2024 window:
* **India Base 1 (Nifty 50 TRI Buy & Hold)**: **11.53% CAGR**, Max DD Depth 59.43%
* **India Base 2 (PIT Equal-Weight Nifty 50)**: **11.00% CAGR**, Max DD Depth 56.22%
* **India Base 3 (Trend Switch > 200-SMA)**: **9.82% CAGR**, **Max DD Depth 17.85%** (Calmar: **0.55**)
* **US Base 1 (S&P 500 Buy & Hold)**: **10.50% CAGR**, Max DD Depth 55.20%
* **US Base 2 (S&P 500 Trend Switch > 200-SMA)**: **9.10% CAGR**, **Max DD Depth 19.40%** (Calmar: **0.47**)

*Mandatory Hurdle Requirement*: A candidate variant must beat **Base 3 (Trend Switch)** on **both CAGR and Calmar Ratio** after all-in stressed costs.

---

## 9. The 3 Pre-Registered Experimental Variants

| Specification | Variant 1 (Wide Stock Stops) | Variant 2 (Medium Stock Stops) | Variant 3 (Tight Current Stops) |
| :--- | :--- | :--- | :--- |
| **Developing Positions** | Exit on daily close below **100-SMA** | Exit on daily close below **50-SMA** | Exit on daily close below **100-SMA** |
| **Proven Winners** | Gain $\ge +25\% \implies$ 150-SMA / -22% Peak Trail | Gain $\ge +15\% \implies$ 100-SMA / -15% Peak Trail | Gain $\ge +15\% \to -8\%$ Trail; $\ge +30\% \to -12\%$ Trail |
| **Fiduciary Hard Stop** | **-10.0%** | **-8.0%** | **-8.0%** |
| **Daily Portfolio Ladder**| Step-down at -10% / -18% / -24% | Step-down at -10% / -18% / -24% | Step-down at -10% / -18% / -24% |
| **Re-Entry State Machine**| 15d cool-off + 10d 200-SMA recovery | 15d cool-off + 10d 200-SMA recovery | 15d cool-off + 10d 200-SMA recovery |
| **Max Gross Exposure** | $\le \min(1.0, \text{ladder\_cap})$ | $\le \min(1.0, \text{ladder\_cap})$ | $\le \min(1.0, \text{ladder\_cap})$ |

---

## 10. Complete Gate A Acceptance Criteria & Decision Rule

### Gate A Acceptance Criteria (Must-Fix #6: Correct Inequalities)
1. **India Stressed Post-Tax CAGR**: $\ge 15.00\%$ (Pre-Tax $\ge 18.75\%$, all-in friction 56.58 bps round-trip, 20% STCG).
2. **US Stressed Pre-Tax CAGR**: $\ge 15.00\%$ (all-in friction 15.38 bps round-trip).
3. **Stressed Max Drawdown Depth**: $\le 25.00\%$ Target (**Hard Failure Ceiling: $> 30.00\% \implies \text{Instant Reject}$**).
4. **Stressed Annualized Sharpe**: $\ge 0.70$.
5. **Deflated Sharpe Ratio (DSR)**: $\ge 0.95$ (accounting for $N \ge 28$ dynamic trials).
6. **Monte Carlo 5th-Percentile Max DD Depth**: $\le 25.00\%$ Target (Hard Ceiling: $\le 30.00\%$) via 1,000 block-bootstrap resamples (21-day blocks).
7. **Minimum Closed Trades**: $\ge 100$ trades over 2007–2024.
8. **Parameter Stability**: $\pm 20\%$ variation across 4 parameters (Lookback $90 \pm 18$d, Kelly $0.40 \pm 0.08$, Ladder triggers $\pm 20\%$, Re-entry confirmation $10 \pm 2$d) degrades CAGR by $< 25\%$.
9. **Beats Hurdle Base 3**: Outperforms the Trend-Switch baseline on **both CAGR and Calmar Ratio** after all-in costs.

### Pre-Committed Decision Logic
1. **Dual-Market Pass**: Variant passes Gate A in **both India and US** $\implies$ Advance to Gate B (13-Week Paper Phase on Dhan for India, Alpaca for US).
2. **Single-Market Pass**: Variant passes Gate A in only one market $\implies$ Advance passing market to Gate B paper trial; quarantine failing market.
3. **Tie-Break Rule**: If multiple variants pass Gate A, select the variant with the highest **Calmar Ratio** ($\text{CAGR} / \text{Max DD Depth}$). Selecting counts as a trial.
4. **All Fail**: If none of the 3 variants passes Gate A in both markets $\implies$ Accept that long-only large-cap momentum under an institutional $\le 25\%$ to $30\%$ drawdown depth limit yields **10%–13% net CAGR**. Choose between:
   * Formally adjusting the target to 11%–13% (beating index with half the drawdown), OR
   * Pre-registering a separate trial on expanded liquid universes (Nifty 100/200, S&P Midcap 400) after constructing verified Point-in-Time membership datasets.
