# Institutional Specification: US Forward Shadow Paper Trading Pod

## 1. Executive Summary & Fiduciary Status
This specification establishes the formal, frozen operating parameters for the **US Forward Shadow Paper Trading Pod** (Pod 2 - US Momentum Compounders). 

> [!CAUTION]
> **Fiduciary Status & Regulatory Disclaimer:**
> **Zero-capital forward paper run; NOT evidence for Gate A (universe suffers from survivorship bias toward 2014-2024 winners).**
> Under no circumstances may forward paper results from this exploratory pod be submitted as evidence for Gate A algorithmic capital certification or used to justify live capital allocation without independent point-in-time constituent reconstruction and full unadjusted-split audit verification.

---

## 2. Frozen Operational Baseline

| Parameter | Specification | Institutional Constraint |
| :--- | :--- | :--- |
| **Fund Capital Allocation** | **$0.00 (Zero Capital)** | Strictly zero fund capital. Zero draw against Central Portfolio Manager. |
| **Broker Desk** | **Alpaca Paper API** | Hardcoded endpoint: `https://paper-api.alpaca.markets` |
| **API Credentials** | `PAPER_API_KEY`, `PAPER_API_SECRET` | Strictly restricted to paper keys. All production/live fallbacks stripped. |
| **Traded Universe File** | [`trading_system/data/us_growth_tickers.txt`](file:///d:/paper_trading_bot/trading_system/data/us_growth_tickers.txt) | 123 US compounders (Industrials, Power, Healthcare, Consumer, Tech). |
| **Execution Cadence** | Daily post-market close (16:15 EST / 21:15 UTC) | Autonomous GitHub Actions runner: [`.github/workflows/shadow_us_alpaca.yml`](file:///d:/paper_trading_bot/.github/workflows/shadow_us_alpaca.yml) |
| **Concurrency Group** | `shadow-us-alpaca` | Fully isolated; zero collision with Indian Gate B pipeline (`trading-state`). |
| **State Persistence Branch** | `state-shadow-us` | Zero write permissions to `main` or production `state`. |
| **Logged Provenance** | Short commit hash recorded per row | Every equity log row in `paper_equity_log.csv` records exact git commit hash. |

---

## 3. Mandatory Invalidation & Restart Clause
- **Frozen Rule**: The strategy logic in [`trading_system/scripts/run_dual_pod_paper.py`](file:///d:/paper_trading_bot/trading_system/scripts/run_dual_pod_paper.py), the universe in [`trading_system/data/us_growth_tickers.txt`](file:///d:/paper_trading_bot/trading_system/data/us_growth_tickers.txt), and the risk parameters (10-position max, 10% hard stop, 150-SMA trend exit, 200-SMA macro filter) are strictly frozen.
- **Restart Condition**: Any code change, universe adjustment, or model modification invalidates the current incubation track, requiring an explicit new shadow sequence, labelled and restarted from Day 0.

---

## 4. Evaluation Horizon & Gate Criteria
The exploratory shadow pod will be monitored in background isolation under the following formal evaluation protocol:
1. **Horizon**: **12 months minimum** continuous forward operation.
2. **Benchmark**: Compared strictly against **Buy-and-Hold SPY** over the identical 12-month calendar window.
3. **Success Criteria**:
   - **Annualized Sharpe Ratio**: Pod Sharpe must equal or exceed SPY Sharpe over the same period net of all simulated costs and fees.
   - **Maximum Drawdown**: Pod Max Drawdown must not exceed SPY Max Drawdown during any market correction.
   - **Cost Drag & Slippage**: Empirical slippage and SEC/FINRA fees on Alpaca paper fills must remain within pre-registered friction bounds ($\le$ 6.5 bps round-trip).
