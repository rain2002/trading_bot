"""
Execution Script: Run Bond and Cash Bot (Phase 3 Gate B Incubation)
===================================================================
Executes daily cycle for Bot 2 (Bond and Cash Bot):
- Ingests latest market quotes for LIQUIDBEES.NS and LTGILTBEES.NS.
- Ingests Manager's `max_duration_scale` (1.0 = normal, 0.0 = retreat/halt).
  * Note on Retreat Lag: Ingests `max_duration_scale` from the previous session's Manager state
    (1-day EOD lag), which is standard for sequential end-of-day paper trading.
- Enforces stale-price and missing-quote fail-closed safety.
- Executes Champion strategy (B0: 100% Overnight Cash Yield) with dedicated INR 20,000 paper capital.
- Logs daily NAV, trades, and 13-week incubation progress.
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from trading_system.app.bots.bond_cash_bot import BondCashPaperRunner

logger = logging.getLogger("RunBondCashBot")


def get_manager_duration_scale() -> float:
    """Reads max_duration_scale from manager_state.json if available."""
    manager_path = os.path.join(PROJECT_ROOT, "trading_system", "data", "manager_state.json")
    if os.path.exists(manager_path):
        try:
            with open(manager_path, "r") as f:
                data = json.load(f)
                if data.get("is_halted", False) or data.get("throttle_level", 0) >= 3:
                    return 0.0
                return float(data.get("max_duration_scale", 1.0))
        except Exception:
            pass
    return 1.0


def main():
    print("=" * 80)
    print(">>> BOT 2: BOND AND CASH BOT (PHASE 3 - GATE B PAPER INCUBATION) <<<")
    print("=" * 80)
    print(f"Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("Mandate  : Safe Carry & Overnight Capital Parking (Champion B0)")
    print("Universe : LIQUIDBEES.NS (100%), LTGILTBEES.NS (0% Duration)")
    print("Capital  : INR 20,000.00 Dedicated Gate B Incubation Capital")
    print("Target   : 13-Week Paper Incubation Window")
    print("-" * 80)

    duration_scale = get_manager_duration_scale()
    print(f"Manager Duration Scale : {duration_scale:.2f}")

    runner = BondCashPaperRunner()
    result = runner.run_daily_cycle(max_duration_scale=duration_scale)

    if result.get("status") == "FAIL_CLOSED":
        print(f"[FAIL-CLOSED] Execution aborted safely. Missing: {result.get('missing_quotes')} | Stale: {result.get('stale_quotes')}")
        sys.exit(0)

    days = runner.state.get("days_incubated", 0)
    weeks = round(days / 7.0, 1)
    progress_pct = round(min(100.0, (days / 91.0) * 100.0), 1)

    print(f"Execution Status    : {result.get('status')}")
    print(f"Portfolio NAV       : INR {result.get('nav', 0.0):,.2f}")
    print(f"Cash Balance        : INR {result.get('cash', 0.0):,.2f}")
    print(f"Current Drawdown    : {result.get('drawdown_pct', 0.0):.2f}% (Max: {runner.state.get('max_drawdown_pct', 0.0):.2f}%)")
    print(f"Rebalance Status    : {'EXECUTED' if result.get('rebalance_executed') else 'HOLD'} ({result.get('rebalance_reason')})")
    print(f"Incubation Progress : Day {days} of 91 ({weeks} / 13.0 weeks - {progress_pct}% Complete)")
    print("-" * 80)
    print("Current Positions:")
    if runner.state.get("positions"):
        for sym, pos in runner.state["positions"].items():
            val = pos["shares"] * pos.get("last_price", 0.0)
            w = (val / runner.state["nav"]) * 100.0 if runner.state["nav"] > 0 else 0.0
            print(f"  - {sym:14s}: {pos['shares']:4d} shs @ INR {pos.get('last_price', 0.0):.2f} = INR {val:,.2f} ({w:.1f}%)")
    else:
        print("  - [No active positions; 100% parked in unallocated overnight cash]")
    print("=" * 80)


if __name__ == "__main__":
    main()
