# Institutional Specification: US Forward Shadow Paper Trading Pod

## 1. Executive Summary & Fiduciary Status
This specification establishes the formal, frozen operating parameters for the **US Forward Shadow Paper Trading Pod** (Pod 2 - US Momentum Compounders).

> [!CAUTION]
> **Fiduciary Status & Regulatory Disclaimer:**
> **Zero-capital forward paper run; NOT evidence for Gate A (universe suffers from survivorship bias toward 2014-2024 winners).**
> Under no circumstances may forward paper results from this exploratory pod be submitted as evidence for Gate A algorithmic capital certification or used to justify live capital allocation without independent point-in-time constituent reconstruction and full unadjusted-split audit verification.

---

## 2. In-Sample Retrospective Performance (Optimized on Survivor-Biased List; N Unbounded)
Retrospective simulation run across 2007–2024 (18.0 years, 4,530 sessions) on the static list of 123 contemporary US growth stocks. This is an in-sample exploratory parameter search on past survivors with multiple trials tested (N=33). It is NOT an out-of-sample validation or proof of alpha.

| Metric | Old Variant 2 | SPY Benchmark (Buy & Hold) | Tuned Candidate (Best of N=33 In-Sample Grid Search) | Delta vs SPY |
| :--- | :--- | :--- | :--- | :--- |
| **CAGR (Annualized Return)** | 9.50% | 11.97% | **13.77%** | **+1.80% / yr** |
| **Sharpe Ratio (Rf=2%)** | 0.51 | 0.57 | **0.61** | **+0.04** |
| **Sortino Ratio** | 0.56 | 0.62 | **0.69** | **+0.07** |
| **Wealth Multiple ($100k start)**| 5.11x ($511k) | 7.63x ($763k) | **10.17x ($1,017k)** | **+2.54x (+$254k)** |
| **Trade Win Rate** | 44.4% | N/A | **54.8%** | **+10.4%** |
| **Profit Factor** | 1.38 | N/A | **1.82** | **+0.44** |

### Parameter Changes Deployed (Exploratory Grid Search):
1. **Concentration from 12 to 8 Slots**: Allocating 12.5% per position in top momentum leaders eliminates performance dilution.
2. **6M-1M Skip-Month Momentum (126d - 21d skip)**: Eliminates buying the peak of 1-month mean-reversion spikes.
3. **4.0x ATR Trailing Stops**: Replaces blunt -10% stop whipsaws, giving winning compounders room to breathe.
4. **Macro Bear Defense (SPY 200-SMA Filter)**: When SPY falls below its 200-SMA, new buys are halted and capital preserves 100% principal compounding daily in risk-free yield.

---

## 3. Frozen Operational Baseline

| Parameter | Specification | Institutional Constraint |
| :--- | :--- | :--- |
| **Fund Capital Allocation** | **$0.00 (Zero Capital)** | Strictly zero fund capital. Zero draw against Central Portfolio Manager. |
| **Broker Desk** | **Alpaca Paper API** | Hardcoded endpoint: `https://paper-api.alpaca.markets` |
| **API Credentials** | `PAPER_API_KEY`, `PAPER_API_SECRET` | Strictly restricted to paper keys. All production/live fallbacks stripped. |
| **Active Portfolio Capacity** | **8 Slots (12.5% per position)** | Concentrated momentum allocation. |
| **Momentum Metric** | 126-day slope * $R^2$ with 21-day skip | 6-month momentum excluding immediate 1-month lookback. |
| **Trailing Stop Loss** | **4.0x 20-Day ATR from Peak** | Dynamic volatility trailing lock. |
| **Hard Stop Loss** | **-12.0% from Entry Fill Price** | Catastrophic gap protection. |
| **Trend Exit** | **150-Day Simple Moving Average** | Exit when daily close breaches 150-SMA. |
| **Macro Regime Filter** | **SPY 200-Day SMA** | SPY < 200-SMA triggers full `BEAR_DEFENSE` into cash yield. |
| **Traded Universe File** | [`trading_system/data/us_growth_tickers.txt`](file:///d:/paper_trading_bot/trading_system/data/us_growth_tickers.txt) | 123 US compounders. |
| **Execution Schedule** | **Autonomous Two-Phase Daily** | 09:30 EST (14:30 UTC) Open Fills + 16:15 EST (21:15 UTC) Close Scan |
| **GitHub Actions Runner** | [`.github/workflows/shadow_us_alpaca.yml`](file:///d:/paper_trading_bot/.github/workflows/shadow_us_alpaca.yml) | Scheduled via cron + manual `workflow_dispatch`. |
| **Concurrency Group** | `shadow-us-alpaca` | Fully isolated; zero collision with Indian Gate B pipeline (`trading-state`). |
| **State Persistence Branch** | `state-shadow-us` | Zero write permissions to `main` or production `state`. |
| **Logged Provenance** | Short commit hash recorded per row | Every equity log row in `paper_equity_log.csv` records exact git commit hash. |

---

## 4. Mandatory Invalidation & Restart Clause
- **Frozen Rule**: The strategy logic in [`trading_system/scripts/run_dual_pod_paper.py`](file:///d:/paper_trading_bot/trading_system/scripts/run_dual_pod_paper.py), the universe in [`trading_system/data/us_growth_tickers.txt`](file:///d:/paper_trading_bot/trading_system/data/us_growth_tickers.txt), and the risk parameters (8 slots, 4.0x ATR trailing stop, -12% hard stop, 150-SMA trend exit, 200-SMA macro filter) are strictly frozen.
- **Strict Parameter Freeze Contract**: **No parameter changes during the 12-month window; any change restarts the clock.**
- **Restart Condition**: Any code change, universe adjustment, or model modification invalidates the current incubation track, requiring an explicit new shadow sequence, labelled and restarted from Day 0.

---

## 5. Evaluation Horizon & Gate Criteria
The exploratory shadow pod will be monitored in background isolation under the following formal evaluation protocol:
1. **Horizon**: **12 months minimum** continuous forward operation.
2. **Benchmark**: Compared strictly against **Buy-and-Hold SPY** over the identical 12-month calendar window.
3. **Success Criteria**:
   - **Annualized Sharpe Ratio**: Pod Sharpe must equal or exceed SPY Sharpe over the same period net of all simulated costs and fees.
   - **Maximum Drawdown**: Pod Max Drawdown must not exceed SPY Max Drawdown during any market correction.
   - **Cost Drag & Slippage**: Empirical slippage and SEC/FINRA fees on Alpaca paper fills must remain within pre-registered friction bounds ($\le$ 6.5 bps round-trip).
