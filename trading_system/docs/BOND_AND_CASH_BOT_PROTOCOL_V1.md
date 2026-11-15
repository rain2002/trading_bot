# Protocol: Bond and Cash Bot & Safe Carry Management (V1.0)

**Document ID**: `PROTOCOL-BOND-AND-CASH-BOT-V1-20261114`  
**Classification**: Production Quantitative Trading Protocol & Safe Reserve Mandate  
**Author**: @Raja Nithin  
**Date**: 2026-11-14  
**Target Capital**: ₹20,000 (Dedicated Gate B Paper Incubation Balance)  
**Governance Authority**: Multi-Bot Trading System Master Plan (Phase 3: Bond and Cash Bot)  

---

## 1. Role, Mandate and Instruments

### Mandate
The Bond and Cash Bot holds the multi-bot system's safe reserves and earns systematic carry on idle capital. It serves two institutional functions:
1. **Idle Cash Parking**: Safely yields on incoming SIP top-ups and cash reserves waiting for market deployment.
2. **Capital Retreat Haven**: Receives defensive capital when the Central Portfolio Manager throttles or halts equity exposure during portfolio-level drawdowns.

The bot **never forecasts interest rates**, macro cycles, or inflation numbers. It is evaluated on a single governing question:
$$\text{Does it earn more than plain overnight cash without incurring a material drawdown?}$$

### Approved Instruments (NSE Cash Delivery Only)
| Leg | Ticker | Description | Inherent Risk |
| :--- | :--- | :--- | :--- |
| **Cash Leg** | `LIQUIDBEES.NS` | Overnight Collateralized Borrowing and Lending Obligations (TREPS) | Near Zero / Sovereign Backed |
| **Duration Leg** | `LTGILTBEES.NS` | 10-Year Benchmark Government of India Sovereign Gilts | Price volatility when bond yields rise |

### Liquidity & Safety Constraints
- **Liquidity Filter**: Any candidate debt ETF must maintain a median daily traded turnover of at least ₹25 lakh over the trailing 90 trading sessions and an average bid-ask spread under 10 bps.
- **Instrument Limits**: Long-only, delivery-only, whole shares only, zero leverage, zero credit-risk/corporate debt exposure, and zero speculative rate-forecasting models.
- **Friction Model**: Evaluated under identical statutory Indian friction as the Phase 1 runner (5.0 bps slippage, ₹14.75 flat DP sell fee, 0.00345% exchange fee, statutory debt capital gains tax, and 0.16% annual ETF TER drag).
- **Cash Yield**: Overnight cash earns the prevailing RBI repo / TREPS cash rate (6.0% annualized, compounded daily over 252 sessions).
- **Data Series**: As certified in `DATA_AUDIT_GILT10Y_SERIES.md`, the cached historical series (`GILT10Y`) is a Total Return Index (TRI) generating +7.43% CAGR; no additional yield adjustments are applied.

---

## 2. Pre-Registered Candidates & Gate A Validation

The trial family is declared up front as strictly **$N = 3$** candidates. Plain overnight cash (`B0`) is the default benchmark: it ships to production unless a candidate clearly earns its extra duration risk.

### Candidate Family ($N = 3$)
1. **`B0` (Benchmark & Default)**:
   - 100% `LIQUIDBEES.NS` (Overnight cash yield).
2. **`B1` (Static Fixed-Weight Sleeve)**:
   - 70% `LIQUIDBEES.NS`, 30% `LTGILTBEES.NS`.
   - Rebalanced annually on the final trading session of each calendar year, or if either sleeve drifts by more than $\pm 5.0\%$ absolute from target.
3. **`B2` (Trend-Gated Gilt Sleeve)**:
   - 70% `LIQUIDBEES.NS` + up to 30% `LTGILTBEES.NS`.
   - Held at 30% only while `LTGILTBEES.NS` closes above its 200-day Simple Moving Average (SMA), checked at each month end.
   - If below its 200-day SMA, the duration sleeve is de-allocated to 0% and 100% is parked in `LIQUIDBEES.NS`.

### Gate A Hurdles (2008–2024 In-Sample, 2025+ Holdout Opened Once for Winner Alone)
| Metric | Hurdle Threshold | Rationale |
| :--- | :--- | :--- |
| **Excess Net Return** | Mean annual return $\ge +0.50$ percentage points above `B0` net of costs, AND bottom 5th percentile of 1,000 monthly block-bootstrap resamples $> 0.0\%$ | Verifies statistically robust carry premium over overnight cash |
| **Maximum Drawdown** | No worse than **-4.0%** peak-to-trough | Hard ceiling on duration capital loss |
| **Worst Single Month** | No worse than **-2.0%** net return | Avoids painful monthly bond volatility |
| **Trade Frequency** | $\le 12$ trades per year | Strictly bounds turnover drag and depository charges |

> **Decision Rule**: `B0` (100% Cash) ships by default. `B1` or `B2` replaces `B0` only if it satisfies **every single hurdle**.

---

## 3. Gate B Paper Incubation & Manager Integration

### Capital Partitioning
- The Bond and Cash Bot receives a dedicated starting paper balance of **₹20,000.00**.
- This balance is completely partitioned from the ETF Bot's ₹80,000.00 capital and the Central Manager's primary equity valuation.
- The bot's real-money capital share is **0.0%** until formal Gate B clearance and boss sign-off.

### Central Portfolio Manager Linkage
- **Retreat Channel**: When the Central Manager triggers a risk throttle (-15%, -30%) or hard kill switch (-40%), retreat capital is routed exclusively to this bot's `LIQUIDBEES.NS` leg.
- **Duration Scale Override (`max_duration_scale`)**:
  - The bot ingests `max_duration_scale` from the Manager on every run.
  - Normal operations: `max_duration_scale = 1.0`.
  - Throttled or Halted operations: `max_duration_scale = 0.0`.
  - When `max_duration_scale == 0.0`, the bot is forced to hold 100% `LIQUIDBEES.NS`, regardless of its own signal.
- **Sequential Daily Pipeline**:
  - `Bot 1 (ETF & Gold Bot)` -> `Bot 2 (Bond & Cash Bot)` -> `Central Portfolio Manager`.

### Gate B Incubation Pass Conditions (13 Consecutive Weeks)
1. **Fiduciary Reconciliation**: Daily NAV recomputed independently from raw cash and positions times fresh quotes matches reported NAV within **0.1%**.
2. **Execution Integrity**: A shadow calculation of the strategy's theoretical return matches the bot's realized return within **0.1% per month**.
3. **Data Freshness**: Zero trades executed on stale, missing, or anomalous quotes.
4. **Retreat Drill**: Successfully execute a drill setting `max_duration_scale = 0.0` and confirming 100% allocation into `LIQUIDBEES.NS` within a single cycle.
5. **Operational Reliability**: Scheduled workflow runs reliably on $\ge 95\%$ of NSE trading days with zero manual state intervention.

---

## 4. Execution Governance & Sign-off

- **Protocol State**: Pre-registered and locked via SHA-256 prior to implementation of strategies or test runners.
- **Sign-off**: @Raja Nithin
