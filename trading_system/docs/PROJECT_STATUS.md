# V2 Project Status

We have officially transitioned to the **V2 Institutional Hardening Phase**.
The baseline execution architecture (V1 Phases 1-14) is complete. The following phases represent the strict transition to institutional-grade security, data integrity, and Walk-Forward optimization as defined in the V2 Master Plan.

## PHASE 0: Infrastructure Foundation
**STATUS: IN PROGRESS**
- [x] Docker Compose Setup
- [x] PostgreSQL 16 Migration
- [x] Alembic setup
- [x] PointInTimeDataProvider interface
- [x] Explicit Experiment Registry

## PHASE 1: Trustworthy Data
**STATUS: COMPLETE**
- [x] Leakage tests (Random-Walk Anti-Cheating Strategy)
- [x] Explicit Corporate Actions layer (Splits, Reverse Splits, Cash Dividends)
- [x] Raw daily bars processing
- [x] Point-in-time database access (fetching from DB instead of API)
- [x] Small controlled universe ingestion

## PHASE 2: Core Event Engine & Validation
**STATUS: COMPLETE**
- [x] Walk-Forward Validation Engine
- [x] Random-Walk end-to-end integration test
- [x] Order Idempotency (Deterministic client_order_ids)

## PHASE 3: Strategy Registry & Discovery
**STATUS: COMPLETE**
- [x] Categorized Strategy Library
- [x] Explicit "NO TRADE" state integration
- [x] Crash / Crisis Risk Module

## PHASE 4: Untouched Final Holdout Testing
**STATUS: COMPLETE**
- [x] Freeze Strategy candidates
- [x] Execute strict, single-run holdout test

## PHASE 5: Paper Canary
**STATUS: COMPLETE**
- [x] Connect validated strategies to Live Bot

---

# MAIN PLAN CONTINUATION (PHASE 15-18)

## PHASE 15: Live Execution Adapter (Initially Disabled)
**STATUS: COMPLETE**
- [x] Build Live execution adapter (Alpaca)
- [x] Ensure it is completely decoupled from Paper execution
- [x] Ensure it requires explicit configuration to run (Disabled by default)

## PHASE 16: Canary/Live Validation
**STATUS: COMPLETE**
- [x] Create divergence analysis tool (Paper vs Live)
- [x] Track spread, slippage, latency, partial fills, and timing differences
- [x] Generate Canary Execution Report

## PHASE 17: Capacity/Scaling Tools
**STATUS: COMPLETE**
- [x] Build Capacity Analysis Module
- [x] Model average daily volume, liquidity participation rate, and market impact
- [x] Calculate the capital threshold where execution degrades

## PHASE 18: Future ML Framework
**STATUS: COMPLETE**
- [x] Time-aware ML validation (Purging/Embargo)
- [x] Versioning for features, labels, and hyperparameters
- [x] Champion vs Challenger model infrastructure


---

# PRODUCTION CHAMPION DESIGNATION (v1.0.0-champion)
**Tag**: `v1.0.0-champion` | **Canonical Commit**: `10ed8d3` | **Date**: 2026-11-10  
**Status**: **ACTIVE IN PRODUCTION (GATE B FORWARD INCUBATION)**

### 1. Active Champion Architecture
The official production Gate B trading fund (`origin/state`, Day 5/91, NAV ₹98,082.80) is partitioned into two specialist sleeves supervised by the Central Portfolio Manager:
- **Sleeve 1: Specialist Bot 1 (ETF and Gold Bot - Phase 1 Champion)**:
  - Governed by `PROTOCOL-ETF-GOLD-BONDS-ROTATION-V1-20261112` and `AMENDMENT-ETF-GOLD-BONDS-V1-1-20261114`.
  - Target Capital: ₹80,000.
  - Allocation: Static 5-Asset Mix (25% `GOLDBEES.NS`, 25% `MON100.NS`, 15% `NIFTYBEES.NS`, 15% `MID150BEES.NS`, 20% `LTGILTBEES.NS`).
  - Audited Gate A Result: CAGR 15.15%, MaxDD -25.59%, Sharpe 0.75, DSR = 0.9957.
  - **Fiduciary Clarification**: This is the **Static Multi-Asset Allocation**. It is **NOT** the failed active switching `MULTI_ASSET_TREND_PROTOCOL_V2_1` family (which failed Gate A hurdles due to Section 50AA turnover tax and is formally killed).
- **Sleeve 2: Specialist Bot 2 (Bond and Cash Bot - Phase 3 Champion B0)**:
  - Governed by `PROTOCOL-BOND-AND-CASH-BOT-V1-20261114`.
  - Target Capital: ₹20,000.
  - Allocation: 100% `LIQUIDBEES.NS` (Overnight MIBOR repo carry, ~6.0% net).
  - Audited Gate A Result: CAGR 5.64%, MaxDD 0.00%, Worst Month +0.09%, DSR = 0.9999.
- **Central Portfolio Manager (Phase 2)**:
  - Reconciles sleeve NAVs daily within 0.1% tolerance; enforces 5% drift-band rebalance.
  - Drawdown throttle ladder: -15% (50% risk), -30% (25% risk), -40% (hard kill switch to 100% cash).
  - 21-day anti-whipsaw recovery cooldown before re-risking.

### 2. Operational Automation (GitHub Actions)
- Automated execution across 6 daily sessions:
  - India Open (`03:46 UTC / 09:16 IST`)
  - India Mid-Session (`06:30 UTC / 12:00 IST`)
  - India Close Scan (`10:05 UTC / 15:35 IST`)
  - US Open (`14:31 UTC / 09:31 EST`)
  - US Mid-Session (`18:00 UTC / 13:00 EST`)
  - US Close Scan (`21:05 UTC / 16:05 EST`)
- Automated state isolation: All live fills, NAV changes, and HTML dashboards persist directly to the dedicated `origin/state` branch without dirtying code.

### 3. Challenger Governance Rules
- Hyperparameters are permanently frozen for `v1.0.0-champion`.
- Any candidate strategy (Challenger) must be tested on causal survivor-free data with pre-registered protocols.
- To replace the Champion, a Challenger must achieve a Deflated Sharpe Ratio (DSR) $\ge 0.95$ over an audited out-of-sample incubation period.

---

# UPDATE 2026-11-27: NSE S2 V1 ARCHIVED & FUND TARGET RESET

- **Decision**: Accepted archiving **NSE S2 V1** as research, resetting the whole-fund target to **11–13% CAGR**, and capping S2 near **30%** (pending live shadow evidence) instead of ramping to 70%.
- **Walk-Forward Evidence (`2013–2022`, `N=88`, `NSE_PANEL_V2`)**:
  - Protocol `NSE_S2_WALK_FORWARD_PROTOCOL_V1.md` (`03ea0ad3...`, committed alone in `b0c5901`).
  - Walk-Forward S2: `11.46%` CAGR, `0.86` Sharpe, `-22.99%` MaxDD (`5/13` checks passed; failed `H1`, `H4`, `H7`, `H9`, `W1`, `W2`, `W3`, `W4`).
  - Fixed S2 (`90/150/1.0`): `14.85%` CAGR, `1.15` Sharpe, `-20.79%` MaxDD vs Nifty 50 TRI `13.17%` CAGR (`H1` required `17.17%`).
  - The `2023-01-01` to `2024-07-05` holdout remains **strictly sealed**.
- **Active Posture**:
  - **Core Fund (ETF + Gold + Bond)** stays untouched through Gate B.
  - **NSE S2 Shadow** remains at **zero capital** on `state-shadow-nse` with weekly Friday fidelity replay (`run_nse_s2_shadow_replay.py`), with no further re-tuning.
  - **US price-only stock research** remains closed (US shadow retired in `f1162f1`).
  - **Next Research Track** (when initiated): uncorrelated edges such as point-in-time fundamentals-based stock selection or F&O premium strategies, each subject to pre-registered protocol + single run + trial log + forward shadow.
