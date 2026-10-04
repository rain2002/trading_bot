# V2 Institutional Architecture Master Plan

**Core Philosophy:** *The first milestone is not profitability. The first milestone is proving that the system can run an experiment without cheating.*

## 1. Strict Pipeline Architecture
1. **Vectorized Research** (Fast experimentation)
2. **Event-Driven Backtester** (Authoritative validation)
3. **Walk-Forward Validation** (Rolling out-of-sample testing)
4. **Untouched Final Holdout** (The "Surprise Exam")
5. **Paper Trading** (Live forward-testing)
6. **Live Canary** (Small live exposure)

## 2. Robust Data Integrity
- **Corporate Actions:** Move beyond relying solely on `adjusted_close`. System must natively support stock splits, cash dividends, and symbol changes to prevent historical pricing corruption.
- **Point-In-Time Provider:** Strategies must query a `PointInTimeDataProvider` ("What was known at 2024-06-15 16:00?") rather than receiving arbitrary DataFrames.
- **Leakage Test Suite:** A dedicated Pytest suite strictly for detecting future data leakage, survivorship bias, and timezone mistakes.

## 3. Engineering Hardening
- **Database:** Migrate from SQLite to PostgreSQL 16.
- **Order Idempotency:** Orders must use deterministic `client_order_id` hashes (e.g., `strategy_version + decision_id + symbol + side + sequence`) to prevent duplicate submissions on timeouts.
- **Experiment Registry:** Every backtest must record git commits, strategy versions, execution assumptions, seeds, and dataset versions to ensure 100% reproducibility.

## 4. Strategy & Regime Discipline
- **Strategy Tiers:** Established (Trend/Momentum), User Hypotheses, and Controlled Discovery.
- **No-Trade State:** Cash is a first-class position. The engine must never be forced to trade.
- **Crash Module:** Primary job is Risk Reduction (Cash/Defensive), not immediately shorting.
- **No LLM Autonomous Trading:** ML (like Random Forests) is used strictly for feature ranking, regime classification, and probability—never for autonomous strategy invention.

## 5. The Ultimate Proof
Before deploying any Alpha strategies, the system must run a **Random-Walk Strategy**.
If a random-walk strategy magically makes money in the backtester, the engine is leaking future data. The engine is only proven secure when random entries yield a statistical 0% edge (minus costs).
