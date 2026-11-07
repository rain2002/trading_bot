# Revised Pre-Registered Dual-Pod Protocol: US & India Quantitative Engines
**Status**: Pre-Registered Specification (Locked Prior to Execution)  
**Branch**: `feat/pre-registered-dual-pod-matrix`  
**Common Evaluation Window**: January 2, 2007 to December 31, 2024 (18.0 Years | **2025 Strictly Sealed as Holdout**)  

---

## 1. Discrepancy Reconciliations & Historical Audit Truths

Before locking this protocol, the audit discrepancies are formally reconciled on record:

1. **US S&P 500 In-Sample Performance Reconciled**:
   * **In-Sample Locked Reality (2000–2024, Holdout Closed)**:
     * **Stressed CAGR**: **11.91%** (Failed target of $\ge 15.00\%$)
     * **Stressed Max Drawdown**: **-34.11%** (Breached the $\le -30.00\%$ hard failure limit)
     * Recorded in `trading_system/data/trial_log.csv` under Row 18 (commit `2680849`).
   * *Holdout Breach Acknowledged*: Quoting "+2,421% / 13.25% CAGR / -32.35% Max DD" from the `--open-holdout` run through 2025 broke the holdout protocol. Under strict in-sample rules, **the US engine failed Gate A on both CAGR and Drawdown**. Both markets will now be evaluated on the identical in-sample window (`2007-01-02` to `2024-12-31`).
2. **Indian Universe Reconstitution Reconciled**:
   * Acknowledged: The collapse of the Indian Equal-Weight baseline from **21.46% down to 11.00%** was primarily caused by **dated constituent reconstitution** (liquidating removed stocks on removal dates and including historical non-survivors like Suzlon, RCOM, Unitech, Satyam, and Yes Bank).
3. **Execution Reality Reconciled**:
   * All Indian orders execute at **Next-Day 09:15 IST Market Open** (eliminating same-bar close bias).
   * Cash yield uses **Liquid ETF net yield** ($r_{\text{repo}} - 0.65\% \text{ TER}$ for India, $^IRX$ for US).

---

## 2. Shared Architecture: Loose Stock Stops + Daily Portfolio Risk Ladder

Per-stock trailing stops are kept wide to allow winning multi-baggers to compound. Portfolio drawdown is controlled at the **Portfolio Level** via **daily monitoring** by the Central Risk Officer (CRO).

### A. Daily CRO Drawdown Monitoring (Must-Fix #1)
* Drawdown is checked **DAILY at market close** against the portfolio's historical High-Water Mark ($HWM_t = \max_{\tau \le t} Equity_\tau$).
* Drawdown is defined as: $DD_t = \frac{Equity_t - HWM_t}{HWM_t}$.
* Target Max Drawdown is $\le -25.00\%$; the Hard Failure Ceiling is $\le -30.00\%$.
* *Gap Risk Acknowledgement*: The protocol acknowledges that gap-downs and weekend gaps can cause slippage past the target. The ladder does not "guarantee" zero drawdown breach, but actively constrains open risk before limits are reached.

$$\text{Max Gross Exposure}_t = \begin{cases} 
100\% & \text{if } DD_t > -10.0\% \\
70\% & \text{if } -18.0\% < DD_t \le -10.0\% \quad (30\% \text{ forced cash reserve}) \\
40\% & \text{if } -24.0\% < DD_t \le -18.0\% \quad (60\% \text{ forced cash reserve}) \\
0\% & \text{if } DD_t \le -24.0\% \quad (100\% \text{ forced cash preservation})
\end{cases}$$

* If $DD_t \le -24.0\%$ on any day $t$, all open equity positions are liquidated at the open of Day $t+1$ to preserve remaining capital.
* When portfolio equity recovers above ladder thresholds, gross exposure capacity steps back up on subsequent weekly rebalances.

### B. Kelly Sizing Zero-Leverage Cap & Causal Input (Must-Fix #2)
* **Zero-Leverage Invariant**: Total portfolio allocation is strictly capped:
  $$\sum_{i=1}^{K} w_i \le \min(1.0, \text{Max Gross Exposure}_t)$$
  Even if 10 slots are selected, the sum of position allocations can **never exceed 100%** (or the prevailing ladder cap).
* **Strict Causal History**: Fractional Kelly parameters ($f^* = p_{\text{win}} - \frac{1 - p_{\text{win}}}{b}$) are calculated strictly from closed trades prior to date $t$ ($< t$), using a rolling causal window of up to 50 past closed trades. If fewer than 20 trades have closed, equal weighting ($1/K$) is enforced.

---

## 3. Real Cumulative Trial Count for Deflated Sharpe Ratio (Must-Fix #3)

* **Trial Accounting**: Variant 3 represents the run that previously scored 7.23% (commit `137a087`, row 22 in `trial_log.csv`), and Variants 1 and 2 were formulated with knowledge of that outcome.
* To prevent p-hacking and maintain mathematical integrity:
  * The cumulative trial count starts at **$N = 22$**.
  * Executing the 3 pre-registered variants will record trials **$N = 23, 24, 25$**.
  * The Bailey-Lopez de Prado **Deflated Sharpe Ratio (DSR)** will be evaluated at the 95% confidence level ($DSR \ge 0.95$) accounting for the full history of $N \ge 25$ trials.

---

## 4. Controlled Factor Isolation (Must-Fix #4)

To prevent changing multiple variables simultaneously (which obscures why a strategy succeeds or fails), testing is decoupled:
1. **Factor Group 1 (Stop & Exposure Variations on Baseline Signal)**:
   * Keep the signal fixed (90-day momentum).
   * Evaluate the 3 stop variants (Wide, Medium, Tight) with the Daily Portfolio Drawdown Ladder.
2. **Factor Group 2 (Signal Isolation)**:
   * Test the baseline 126-day (6-month) cross-sectional momentum signal against the 90-day $\text{Slope} \cdot R^2$ signal under identical stop rules.

---

## 5. Universe Strictly Locked to Sourced Nifty 50 (Must-Fix #5)

* Universe is strictly locked to **Nifty 50**.
* Point-in-Time membership is governed by:
  * `trading_system/data/nifty50_membership_changes.csv` (includes official NSE press releases & circular links, committed in `9cc7f03`).
  * `trading_system/data/nifty50_historical_components_changes.csv` (34 semi-annual snapshots).
  * `trading_system/data/nifty50_ticker_start_end.csv` (102 intervals).
* Any universe expansion (Nifty 100/200, S&P Midcap 400) is barred from this trial and requires a separate pre-registration.

---

## 6. Taxation & All-In Statutory Transaction Costs (Must-Fix #6 & #7)

### A. Explicit Tax Specification (Must-Fix #6)
* **Pre-Tax Target**: The Gate A hurdle is **$\ge 15.00\%$ Pre-Tax CAGR**.
* **Post-Tax Reality**: Due to weekly turnover, virtually all Indian equity capital gains are Short-Term Capital Gains (STCG), taxed at **20%** (Finance Act 2024) or 15% historically.
  * A 15.00% Pre-Tax CAGR corresponds to approximately **~12.00% Post-Tax CAGR**.
  * Achieving 15.00% Post-Tax CAGR requires **$\ge 18.75\%$ Pre-Tax CAGR**.
  * Both Pre-Tax CAGR and Post-Tax Net CAGR will be explicitly reported in the tear sheet.

### B. All-In Institutional Transaction Cost Model (Must-Fix #7)
The backtester incorporates statutory costs beyond simple slippage:
* **Brokerage**: 5.0 bps (or ₹20 flat equivalent)
* **Securities Transaction Tax (STT)**: 10.0 bps on Buy, 10.0 bps on Sell (20.0 bps round-trip)
* **Exchange Turnover Fee (NSE)**: 0.35 bps
* **Stamp Duty**: 1.5 bps on Buy
* **GST**: 18% on brokerage & transaction charges (~1.0 bps)
* **Slippage**: 5.0 bps (Normal) / 7.5 bps (Stressed)
* **Total Stressed Friction**: **~20.0 bps per one-way trade** (~40.0 bps round-trip).

---

## 7. Gate B Paper Phase & Execution Adapter Scope (Must-Fix #8)

* Any passing variant proceeds strictly to **Gate B: 13-Week Paper Trading Phase** (no direct live trading).
* **Execution Adapters**:
  * **India Pod**: Dhan Broker Adapter in Paper/Sandbox Mode (`trading_system/app/broker/dhan.py`).
  * **US Pod**: Alpaca Broker Adapter in Paper Mode (`trading_system/app/broker/alpaca.py`).
* Live trading is permitted only after Gate B's 13-week paper trial passes with zero fatal invariant breaches.

---

## 8. Common Evaluation Window & US Baselines (Should-Fix Items)

### A. Common Evaluation Horizon
* **Primary Common Window**: January 2, 2007 to December 31, 2024 (18.0 Years | Exactly 4,238 Indian / 4,530 US trading days).
* **Long-Span US Sensitivity**: 2000–2024 reported separately as a secondary reference.
* **2025 Sealed Holdout**: Untouched across all runs.

### B. Regime Filter Rule
* Exit to cash on **ONE daily close below 200-SMA** (`close < sma200`).
* Re-enter equity risk only after **TWO consecutive daily closes above 200-SMA** (`(close > sma200).rolling(2).sum() == 2`).

### C. Base Strategies to Beat (Hurdle Rates)
All hurdle baselines run through the engine with identical costs and liquid cash yields over the common 2007–2024 window:
* **India Base 1 (Nifty 50 TRI Buy & Hold)**: **11.53% CAGR**, Max DD -59.43%
* **India Base 2 (PIT Equal-Weight Nifty 50)**: **11.00% CAGR**, Max DD -56.22%
* **India Base 3 (Trend Switch > 200-SMA)**: **9.82% CAGR**, **Max DD -17.85%**
* **US Base 1 (S&P 500 Buy & Hold 2007–2024)**: **10.50% CAGR**, Max DD -55.20%
* **US Base 2 (S&P 500 Trend Switch > 200-SMA 2007–2024)**: **9.10% CAGR**, **Max DD -19.40%**

---

## 9. The 3 Pre-Registered Experimental Variants

| Specification | Variant 1 (Wide Stock Stops) | Variant 2 (Medium Stock Stops) | Variant 3 (Tight Current Stops) |
| :--- | :--- | :--- | :--- |
| **Developing Positions** | Exit on daily close below **100-SMA** | Exit on daily close below **50-SMA** | Exit on daily close below **100-SMA** |
| **Proven Winners** | Gain $\ge +25\% \implies$ 150-SMA / -22% Peak Trail | Gain $\ge +15\% \implies$ 100-SMA / -15% Peak Trail | Gain $\ge +15\% \to -8\%$ Trail; $\ge +30\% \to -12\%$ Trail |
| **Fiduciary Hard Stop** | **-10.0%** | **-8.0%** | **-8.0%** |
| **Daily Portfolio Ladder**| Step-down at -10% / -18% / -24% | Step-down at -10% / -18% / -24% | Step-down at -10% / -18% / -24% |
| **Max Gross Exposure** | $\le \min(1.0, \text{ladder\_cap})$ | $\le \min(1.0, \text{ladder\_cap})$ | $\le \min(1.0, \text{ladder\_cap})$ |
| **Rebalance & Fill** | Weekly / Next-Day Open | Weekly / Next-Day Open | Weekly / Next-Day Open |

---

## 10. Complete Gate A Acceptance Criteria & Decision Rule

### Gate A Acceptance Criteria (Both Markets Must Pass)
1. **Stressed Pre-Tax CAGR**: $\ge 15.00\%$ (Stressed all-in costs: 20 bps one-way).
2. **Stressed Max Drawdown**: $\le -25.00\%$ (Target), Hard Failure Ceiling: $\le -30.00\%$.
3. **Stressed Annualized Sharpe**: $\ge 0.70$.
4. **Deflated Sharpe Ratio (DSR)**: $\ge 0.95$ (accounting for $N \ge 25$ total trials, skewness, and kurtosis).
5. **Monte Carlo 5th-Percentile Max DD**: $\le -25.00\%$ (Hard Ceiling: $\le -30.00\%$).
6. **Minimum Closed Trades**: $\ge 100$ trades over 2007–2024.
7. **Parameter Stability**: $\pm 20\%$ parameter variation degrades CAGR by $< 25\%$.
8. **Beats Base Strategy**: Outperforms the market's respective Base Strategy after all-in costs.

### Pre-Committed Decision Logic
1. **Dual-Market Pass**: A variant passes Gate A in **both India and US** $\implies$ Advance to Gate B (13-Week Paper Phase on Dhan for India, Alpaca for US).
2. **Single-Market Pass**: A variant passes Gate A in only one market $\implies$ Advance passing market to Gate B paper trial; quarantine failing market.
3. **Tie-Break Rule**: If multiple variants pass Gate A, select the variant with the highest **Calmar Ratio** ($\text{CAGR} / |\text{Max DD}|$). Selecting counts as a trial.
4. **All Fail**: If none of the 3 variants passes Gate A in both markets $\implies$ Accept that long-only large-cap momentum under an institutional $\le -25\%$ to $-30\%$ drawdown ceiling yields **10%–13% net CAGR**. Choose between:
   * Formally adjusting the target to 11%–13% (beating index with half the drawdown), OR
   * Pre-registering a separate trial on expanded liquid universes (Nifty 100/200, S&P Midcap 400) after constructing verified Point-in-Time membership datasets.
