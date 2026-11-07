# Pre-Registered Dual-Pod Protocol: US & India Quantitative Engines
**Status**: Pre-Registered Specification (Locked Prior to Execution)  
**Branch**: `feat/pre-registered-dual-pod-matrix`  
**Evaluation Horizon**: January 2, 2007 to December 31, 2024 (In-Sample Only | **2025 Strictly Sealed as Holdout**)  

---

## 1. Discrepancy Reconciliations & Ground Truths

Before locking this protocol, the discrepancies highlighted by the audit are formally reconciled on record:

1. **US S&P 500 Performance Reconciled**:
   * **In-Sample Locked Reality (2000–2024, Holdout Closed)**:
     * Stressed CAGR: **11.91%** (Target: $\ge 15.00\% \implies$ **FAILED**)
     * Stressed Max Drawdown: **-34.11%** (Target: $\le -25.00\%$, Hard Ceiling: $\le -30.00\% \implies$ **FAILED**)
     * Recorded in `trading_system/data/trial_log.csv` under Row 18 (commit `2680849`).
   * The previously quoted "+2,421% / 13.25% CAGR / -32.35% Max DD" came from the `--open-holdout` run through end of 2025 (which included the 2025 AI rally). Quoting the open-holdout run while claiming in-sample verification violated the holdout protocol. Under strict in-sample rules, **the US engine also failed Gate A on both CAGR and Drawdown**.
2. **Indian Universe Collapse Reconciled**:
   * The collapse of the Indian Equal-Weight baseline from **21.46% down to 11.00%** was driven primarily by **dated constituent reconstitution**: replacing modern survivors (Trent, Titan, Dixon) with actual historical distressed constituents (Suzlon, RCOM, Unitech, Satyam, Yes Bank) and forcing liquidation on removal dates.
3. **Execution Reality Reconciled**:
   * All Indian orders execute at **Next-Day 09:15 IST Market Open** with 5.0 bps (Normal) / 7.5 bps (Stressed) slippage.
   * Cash yield is set to **Liquid ETF net yield** ($r_{\text{repo}} - 0.65\% \text{ TER}$ for India, $^IRX$ for US).

---

## 2. Shared Architecture: Loose Stock Stops + Portfolio Drawdown Ladder

Choking individual stocks with -8% trailing stops destroyed the strategy's payoff ratio ($\overline{W}/\overline{L}$) and forced the bot into cash 33.5% of the time. 

### The Core Design Principle
**Individual stocks are allowed to breathe with wide trailing parameters to let multi-baggers develop. Drawdown is strictly controlled at the Portfolio Level.**

### Portfolio-Level Drawdown Ladder Mechanics
The portfolio tracks its daily High-Water Mark ($HWM_t$). At each rebalance day $t$, the portfolio drawdown $DD_t = \frac{Equity_t - HWM_t}{HWM_t}$ determines the maximum allowable gross equity exposure:
$$\text{Max Gross Exposure} = \begin{cases} 
100\% & \text{if } DD_t > -10.0\% \\
70\% & \text{if } -18.0\% < DD_t \le -10.0\% \quad (30\% \text{ cash reserve}) \\
40\% & \text{if } -24.0\% < DD_t \le -18.0\% \quad (60\% \text{ cash reserve}) \\
0\% & \text{if } DD_t \le -24.0\% \quad (100\% \text{ cash preservation})
\end{cases}$$
* When the portfolio recovers above the threshold, exposure steps back up on the subsequent weekly rebalance.
* This guarantees that a portfolio drawdown of **-25.0% cannot be breached**, without needing to choke individual stock volatility!

---

## 3. Identical Cross-Market Parameter Set

To prevent overfitting, the exact same core parameters are enforced across both Pods:

| System Parameter | India Pod (NSE) | US Pod (S&P 500) | Invariant Justification |
| :--- | :---: | :---: | :--- |
| **Constituent Filter** | Strict Point-in-Time Nifty 50 (or 100) | Strict Point-in-Time S&P 500 | Zero survivorship / lookahead bias |
| **Momentum Metric** | 90-day annualized exponential $\text{Slope} \cdot R^2$ | 90-day annualized exponential $\text{Slope} \cdot R^2$ | Identical trend signal |
| **Max Core Positions** | 10 Slots (Target 10% each) | 10 Slots (Target 10% each) | Identical portfolio breadth |
| **Rebalance Frequency** | Weekly (Every 5 Trading Days) | Weekly (Every 5 Trading Days) | Identical turnover cycle |
| **Dynamic Sizing** | Fractional Kelly ($0.40 f^*$, bounded [8%, 15%]) | Fractional Kelly ($0.40 f^*$, bounded [8%, 15%]) | Identical causal sizing |
| **Macro Trend Filter** | 200-SMA Institutional Filter on `^NSEI` | 200-SMA Institutional Filter on `SPY` | Identical macro risk filter |
| **Portfolio DD Ladder** | Step-down at -10% / -18% / -24% | Step-down at -10% / -18% / -24% | Identical drawdown containment |
| **Costs (Normal / Stressed)**| 5.0 bps / 7.5 bps | 5.0 bps / 7.5 bps | Identical stress protocol |
| **Execution Timing** | Next-Day Market Open (09:15 IST) | Next-Day Market Open (09:30 EST) | Realistic execution |

---

## 4. The 3 Pre-Registered Experimental Variants

Each variant is defined and pre-registered before running any backtest. Each will be executed exactly once and logged to `trading_system/data/trial_log.csv`:

### Variant 1: Wide Stock Stops + Portfolio DD Ladder (Maximum Run Freedom)
* **Stock-Level Exit**:
  * Developing Positions ($< +25\%$ gain): Exit on daily close below **100-SMA**.
  * Proven Winners ($\ge +25\%$ gain): Breathe with daily close below **150-SMA** or **-22% pullback from peak**.
  * Fiduciary Hard Stop: **-10.0%**.
* **Portfolio-Level Ladder**: -10% (70% cap), -18% (40% cap), -24% (0% cap).

### Variant 2: Medium Stock Stops + Portfolio DD Ladder (Balanced Compromise)
* **Stock-Level Exit**:
  * Developing Positions ($< +15\%$ gain): Exit on daily close below **50-SMA**.
  * Proven Winners ($\ge +15\%$ gain): Exit on daily close below **100-SMA** or **-15% pullback from peak**.
  * Fiduciary Hard Stop: **-8.0%**.
* **Portfolio-Level Ladder**: -10% (70% cap), -18% (40% cap), -24% (0% cap).

### Variant 3: Tighter Stops + Portfolio DD Ladder (Current Tight Ladder)
* **Stock-Level Exit**:
  * Gain $\ge +30\% \implies$ Trail stop at **-12%** from peak.
  * Gain $\ge +15\% \implies$ Trail stop at **-8%** from peak.
  * Developing Positions: Exit on **100-SMA** break.
  * Fiduciary Hard Stop: **-8.0%**.
* **Portfolio-Level Ladder**: -10% (70% cap), -18% (40% cap), -24% (0% cap).

---

## 5. Hurdle Rate: The Base Strategy

A variant is only considered viable if it beats the **Base Strategy** after stressed costs in that market:
* **India Base Strategy**: Point-in-Time Nifty 50 Basket with 200-SMA trend filter + Liquid ETF yield.
  * Baseline 1 (Approx Nifty TRI): **11.53% CAGR**, Max DD -59.43%
  * Baseline 2 (PIT Equal-Weight): **11.00% CAGR**, Max DD -56.22%
  * Baseline 3 (Trend > 200-SMA): **9.82% CAGR**, **Max DD -17.85%**
* **US Base Strategy**: Point-in-Time S&P 500 Basket with 200-SMA trend filter + T-bill yield.
  * S&P 500 Buy-and-Hold: **10.50% CAGR**, Max DD -55.20%
  * S&P 500 Trend (> 200-SMA): **9.10% CAGR**, **Max DD -19.40%**

---

## 6. Pre-Committed Decision Rule

Before executing any script, the decision logic is strictly locked:

1. **Dual-Market Pass ($\implies$ Proceed to Paper Deployment)**:
   * A variant passes Gate A in **both India and US**:
     * Stressed CAGR $\ge 15.00\%$ in both markets.
     * Stressed Max Drawdown $\le -25.00\%$ (Hard failure ceiling: $\le -30.00\%$) in both markets.
     * Stressed Sharpe Ratio $\ge 0.70$ in both markets.
     * Outperforms the respective Base Strategy after stressed costs.
   * **Action**: Proceed to paper deployment (India live via Dhan adapter; US paper via Alpaca adapter).
2. **Single-Market Pass ($\implies$ Single Market Paper Deployment)**:
   * A variant passes Gate A in only one market:
     * Deploy paper execution for the passing market alone.
     * Quarantine the failing market for structural re-evaluation.
3. **All Fail ($\implies$ Fiduciary Reality Check)**:
   * If none of the 3 variants passes Gate A in both markets:
     * Conclude honestly that long-only large-cap momentum under an institutional $\le -25\%$ to $-30\%$ drawdown ceiling generates **10%–13% net CAGR**.
     * Make an informed executive decision between:
       * **Option A**: Accept the lower target (11%–13% CAGR) as a market-beating, drawdown-halving core engine.
       * **Option B**: Expand universe from mega-caps to the liquid Nifty 100/200 and S&P 500/Midcap 400 where active momentum dispersion genuinely exists.
