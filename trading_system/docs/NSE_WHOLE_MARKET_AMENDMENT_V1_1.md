# Protocol Amendment V1.1: NSE Whole-Market Long-Only Strategy (Phase 5)

**Document ID**: `AMENDMENT-NSE-WHOLE-MARKET-LONG-ONLY-V1-1-20261115`  
**Classification**: Formal Protocol Amendment & Parameter Pre-Registration  
**Base Protocol**: [`NSE_WHOLE_MARKET_LONG_ONLY_PROTOCOL_V1.md`](NSE_WHOLE_MARKET_LONG_ONLY_PROTOCOL_V1.md) (`PROTOCOL-NSE-WHOLE-MARKET-LONG-ONLY-V1-20261115`)  
**Base Protocol SHA-256**: `8f536f131fada8185425f153ce060b50b7e34a5715e2aaaf6a409f0d6b24a5f2`  
**Author**: @Raja Nithin  
**Date**: 2026-11-15  
**Target Platform**: Live Paper Trading / Zerodha-Groww Paper Pipeline (`GATE_B_PAPER`)  
**Declared Candidate**: Candidate $S_2$ (Asymmetric Profit-Trail Compounder)  
**Cumulative Multi-Testing Count**: $N = 85$  
**Governance Authority**: Multi-Bot Trading System Master Plan (Phase 5: NSE Whole-Market Alpha Sleeve)  

---

## 1. Executive Summary & Amendment Scope

This amendment resolves three architectural ambiguities identified in Base Protocol V1 before the execution of the Gate A runner:
1. **Re-Entry State Machine**: Establishes the exact mathematical rules governing exit from Tier 4 emergency cash defense and defines the double high-water mark architecture ($HWM_{\text{true}}$ vs. $HWM_{\text{ladder}}$) to prevent permanent lockout.
2. **Surveillance & Circuit Treatment**: Defines causal circuit-lock inference from daily session OHLC data and explicitly declares historical SEBI/NSE ASM/GSM/ESM regulatory lists as unavailable point-in-time prior to 2018.
3. **Benchmark Series & Cost Schedule**: Specifies `INDEX_NSEI.parquet` as the institutional macro benchmark with a stated +1.35% annualized dividend yield adjustment for Total Return Index (TRI), and itemizes the exact baseline and $2\times$ stressed friction schedules.
4. **Single Dividend Accounting Rule**: Mandates that price data uses split-only adjustments to prevent double-counting dividends.
5. **Audited Trial Count**: Formally documents the exact accounting of all 84 prior NSE trials in `trial_log.csv`, fixing honest cumulative $N = 85$.

---

## 2. Double High-Water Mark Architecture & Emergency Re-Entry State Machine

### A. High-Water Mark Definitions
1. **$HWM_{\text{true}}$ (Lifetime Peak Equity)**:
   - Initialized to starting capital ($\text{INR } 80,000.00$).
   - Updated daily: $HWM_{\text{true}, t} = \max(HWM_{\text{true}, t-1}, \text{Total Equity}_t)$.
   - **Never resets under any circumstances**.
   - Governs strategy lifetime maximum drawdown ($\text{True Drawdown}_t = (\text{Total Equity}_t - HWM_{\text{true}, t}) / HWM_{\text{true}, t}$) and evaluates hard breach thresholds (Hurdle H3 $\ge -35.00\%$).
2. **$HWM_{\text{ladder}}$ (Operating Ladder Reference)**:
   - Initialized to starting capital ($\text{INR } 80,000.00$).
   - When not in Tier 4 Emergency Defense: updated daily when total equity hits a new operating peak:
     $$\text{If } \text{Total Equity}_t > HWM_{\text{ladder}, t-1} \implies HWM_{\text{ladder}, t} = \text{Total Equity}_t$$
   - Governs active drawdown ladder tier assignment:
     $$\text{Operating Drawdown}_t = \frac{\text{Total Equity}_t - HWM_{\text{ladder}, t}}{HWM_{\text{ladder}, t}}$$

### B. Four-Tier Drawdown Exposure Ladder
- **Tier 1**: $\text{Operating Drawdown}_t \in [0.0\%, -8.0\%] \implies 100\%$ target exposure.
- **Tier 2**: $\text{Operating Drawdown}_t \in (-8.0\%, -14.0\%] \implies 70\%$ target exposure.
- **Tier 3**: $\text{Operating Drawdown}_t \in (-14.0\%, -18.0\%] \implies 40\%$ target exposure.
- **Tier 4**: $\text{Operating Drawdown}_t < -18.0\% \implies 0\%$ target exposure (**Emergency Cash Defense**).

### C. Emergency State Machine & Re-Entry Protocol
When Tier 4 triggers:
1. **Immediate Liquidation**: All open stock positions are queued for execution at the next market open ($t+1$).
2. **Yield Accrual**: Portfolio capital is held 100% in idle cash compounding at the sovereign repo rate (`LIQUIDBEES` model @ 6.0% p.a.).
3. **Re-Entry Dual Conditions**: Re-entry is strictly prohibited until **both** of the following conditions are simultaneously satisfied:
   - **Condition 1 (Cool-Off)**: The strategy has remained continuously in Tier 4 100% cash defense for at least **15 consecutive trading sessions**.
   - **Condition 2 (Macro Confirmation)**: The benchmark index (`INDEX_NSEI.parquet`) has closed strictly above its 200-day Simple Moving Average (SMA) for at least **10 consecutive trading sessions**.
4. **Staged Recovery Re-Allocation**:
   Upon simultaneous satisfaction of Conditions 1 and 2:
   - Tier 4 defense is formally exited.
   - The operating reference is re-anchored to current cash: $HWM_{\text{ladder}} = \text{Total Equity}_t$.
   - Capital re-enters the market through a 3-stage exposure ramp:
     - **Recovery Stage 1**: Maximum 40% equity exposure for 10 trading sessions.
     - **Recovery Stage 2**: Maximum 70% equity exposure for 10 trading sessions.
     - **Recovery Stage 3**: 100% normal ladder operation restored (Tier 1).

---

## 3. Circuit Limit Inference & Exchange Surveillance Data Treatment

### A. Point-in-Time Circuit-Lock Inference
Official historical NSE Bhavcopy records do not include daily price band limits. To prevent unfillable execution on circuit-locked illiquid names, circuit status is causally inferred from daily session OHLC data on the rebalance signal date:
1. **Intraday Lock**: $\text{High}_t == \text{Low}_t$ on the signal session (zero price range indicating an open-to-close circuit freeze with blocked order matching).
2. **Band Hit**: Daily percentage return $| \frac{\text{Close}_t - \text{Close}_{t-1}}{\text{Close}_{t-1}} | \ge 19.50\%$ (approximating the standard NSE 20% equity price band with 50 bps tolerance).
- **Execution Rule**: Any prospective entry flagged with either condition on the signal date is strictly barred from entry. Any existing position flagged with either condition queues its exit until the first subsequent session where $\text{High}_t > \text{Low}_t$ and daily return $< 19.50\%$.

### B. Exchange Surveillance Measures (ASM / GSM / ESM)
- **Historical Availability**: Machine-readable point-in-time SEBI/NSE circulars for Additional Surveillance Measure (ASM), Graded Surveillance Measure (GSM), and Enhanced Surveillance Measure (ESM) lists do not exist prior to 2018 in the local dataset.
- **Explicit Declaration**: Historical surveillance lists are formally declared **unavailable point-in-time** for the historical backtest.
- **Backtest Protection**: The strategy relies on the strict ₹2.0 crore median daily turnover filter, 12-month listing seasoning, Rs 20 share price floor, and causal circuit-lock inference to exclude microcap manipulation and distressed shell entities.
- **Live Incubation Guard**: For forward paper trading (Gate B onwards), live daily ASM/GSM/ESM regulatory lists are ingested and enforced directly by `cro.check_exchange_surveillance_and_circuits()`.

---

## 4. Benchmark Series, Dividend Adjustment, and Itemized Cost Schedule

### A. Authoritative Benchmark & Macro Radar Series
- **Benchmark Series**: Sourced from `trading_system/data/historical_cache_nse/INDEX_NSEI.parquet` (Nifty 50 Index).
- **Rationale**: The local repository contains continuous historical data for `INDEX_NSEI.parquet` (2007 to Present). It serves as the authoritative institutional macro proxy for:
  1. The 200-day SMA Macro Volatility Radar.
  2. The Hurdle H1 excess CAGR benchmark.
  3. The Hurdle H7 multi-cycle sub-period consistency evaluation.
- **Stated Dividend Adjustment for Total Return Index (TRI)**:
  `INDEX_NSEI.parquet` represents a Price Return (PR) index. To establish an honest Total Return benchmark, an empirical annualized dividend yield of **+1.35% per annum** is added to benchmark daily returns:
  $$r_{\text{benchmark, TRI}, t} = r_{\text{benchmark, PR}, t} + \left[(1 + 0.0135)^{1/252} - 1\right]$$
  Hurdle H1 requires Candidate $S_2$ CAGR $\ge \text{Benchmark TRI CAGR} + 4.00\%$.

### B. Baseline Friction & Statutory Cost Schedule (per side)
All trades model statutory Indian equity taxes, exchange fees, and execution slippage:

| Cost Component | Buy Side | Sell Side | Regulatory / Commercial Basis |
|---|---|---|---|
| **Securities Transaction Tax (STT)** | 10.0 bps (0.10%) | 10.0 bps (0.10%) | Statutory delivery equity STT rate |
| **Stamp Duty** | 1.5 bps (0.015%) | 0.0 bps | Indian Stamp Act (state delivery schedule) |
| **Exchange Turnover + SEBI + GST** | 0.5 bps (0.005%) | 0.5 bps (0.005%) | NSE turnover charges + SEBI turnover fee + 18% GST |
| **Brokerage** | 0.0 bps | 0.0 bps | Zero brokerage on equity delivery (discount broker standard) |
| **Depository Participant (DP) Fee** | ₹0.00 | ₹15.93 flat | ₹13.50 + 18% GST per scrip per sell day deducted from cash |
| **Execution Slippage** | 15.0 bps (0.15%) | 15.0 bps (0.15%) | Baseline conservative market impact on liquid names |
| **Total Baseline Friction** | **27.0 bps** | **25.5 bps + ₹15.93 DP Fee** | Baseline transaction friction |

### C. Hurdle H9 Stressed Cost Schedule ($2\times$ Multiplier)
To clear Hurdle H9, the strategy must pass all Gate A criteria under severe liquidity friction:
- **Execution Slippage**: Doubled from 15.0 bps to **30.0 bps per side** (0.30% per side, matching the reviewer's small-cap stress assumption).
- **Statutory & Exchange Costs**: Doubled to **24.0 bps on buy** and **21.0 bps on sell**.
- **Flat DP Fee**: Doubled to **₹31.86 per sell leg**.
- **Total Stressed Friction**: **54.0 bps on buy** and **51.0 bps on sell + ₹31.86 DP fee**.

---

## 5. Single Dividend Accounting Rule (Double-Counting Prevention)

To maintain absolute quantitative integrity and eliminate dividend double-counting:
1. **Split-Only Price Adjustment**: Stock price matrices loaded by the runner are backward-adjusted **EXCLUSIVELY for verified stock splits and bonus issues** using `build_verified_split_adjustment_matrix()` and `nse_corporate_actions_audited.csv`.
2. **Zero Price Dividend Adjustment**: Price series are **not** scaled for cash dividends.
3. **Cash Credit on Ex-Date**: Cash dividends are credited once as realized cash to portfolio equity on confirmed corporate action ex-dates.

---

## 6. Honest Multi-Testing Accounting ($N = 85$)

A forensic audit of `trading_system/data/trial_log.csv` (139 total entries) identifies exactly **84 prior NSE-related trials**:
- `NSE_NIFTY50`: 31 trials
- `NSE_GROWTH_EQUITIES`: 20 trials
- `NIFTY_500_SURVIVOR_BIASED_TODAY_LIST`: 6 trials
- Causal Bhavcopy variants (`NSE_BHAVCOPY_CAUSAL_TOP500`, `TOP300`, `TOP50_EQUAL_WEIGHT`, `PLAIN_MOMENTUM`): 8 trials
- Point-in-time Nifty 100/50 baseline runs: 4 trials
- Exploratory and dual-pod trials: 4 trials
- Hybrid satellite and decile spread runs: 4 trials
- NSE debt and cash baseline runs (`NSE_DEBT_CASH_B0`, `B1`, `B2`): 3 trials
- Other non-NSE entries (US S&P 500 [13], Multi-Asset [29], Factor ETFs [5], Phase 1/2 ETFs [8]): 55 trials

Adding Candidate $S_2$ yields:
$$N = N_{\text{prior}} + 1 = 84 + 1 = 85$$

**Hurdle H4 Mandate**: The Deflated Sharpe Ratio (DSR) must evaluate against **$N = 85$**, rigorously penalizing the full history of exploratory experimentation.
