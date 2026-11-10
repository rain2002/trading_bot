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
The official production trading champion is the **Dual-Pod Autonomous Cloud Trader with Macro Multi-Asset Trend**:
- **Pod C (Macro Trend Allocation - Core Anchor)**:
  - 40% India Trend (`NIFTYBEES.NS`)
  - 30% US Secular Tech (`MON100.NS`)
  - 20% Domestic Gold (`GOLDBEES.NS`)
  - 10% Sovereign Cash Yield (`LIQUIDBEES.NS`)
  - Regime Protection: Individual 200-SMA filters (assets below 200-SMA switch 100% to liquid cash yield).
- **Pod 1 (India Growth Momentum - Satellite)**:
  - Point-in-Time NSE 100 universe, 10 slots (10% allocation).
  - Volatility Radar dynamic exposure scaling + -12% hard stop + 150-SMA trailing exit.
- **Pod 2 (US Growth Momentum - Satellite)**:
  - Point-in-Time NASDAQ/NYSE universe, 10 slots.
  - Live Alpaca Paper API routing + -10% hard stop + 150-SMA trailing exit.

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
