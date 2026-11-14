"""
Execution Script: Run ETF & Gold Bot (Phase 1 Gate B Incubation)
================================================================
Executes daily cycle for Bot 1 (ETF & Gold Bot):
- Ingests latest live prices for GOLDBEES, MON100, NIFTYBEES, MID150BEES, LTGILTBEES
- Enforces stale-price and missing-quote fail-closed safety
- Manages yearly rebalancing and 5% drift-band tolerance rebalances
- Logs daily NAV, trades, and incubation health
"""

import os
import sys
import json
from datetime import datetime, timezone

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from trading_system.app.bots.etf_gold_bot import ETFGoldsPaperRunner, ETFGoldsStrategy


def main():
    print("=" * 80)
    print(">>> BOT 1: ETF & GOLD BOT (PHASE 1 - GATE B PAPER INCUBATION) <<<")
    print("=" * 80)
    print(f"Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Mandate  : Static 5-Asset Mix with Sovereign Gilts (Champion)")
    print(f"Universe : GOLDBEES (25%), MON100 (25%), NIFTYBEES (15%), MID150BEES (15%), LTGILTBEES (20%)")
    print(f"Capital  : INR 80,000.00 Starting Capital")
    print(f"Target   : 13-Week Paper Incubation Window")
    print("-" * 80)

    runner = ETFGoldsPaperRunner()
    result = runner.run_daily_cycle()

    if result.get("status") == "FAIL_CLOSED":
        print(f"[FAIL-CLOSED] Execution aborted safely. Missing: {result.get('missing_quotes')} | Stale: {result.get('stale_quotes')}")
        sys.exit(0)

    print(f"Execution Status    : {result.get('status')}")
    print(f"Portfolio NAV       : INR {result.get('nav', 0.0):,.2f}")
    print(f"Cash Balance        : INR {result.get('cash', 0.0):,.2f}")
    print(f"Current Drawdown    : {result.get('current_drawdown_pct', 0.0):.2f}% (Max: {result.get('max_drawdown_pct', 0.0):.2f}%)")
    print(f"Rebalance Status    : {'EXECUTED' if result.get('rebalance_executed') else 'HOLD'} ({result.get('rebalance_reason')})")
    print(f"Incubation Progress : Day {result.get('days_incubated')} of 91 ({result.get('weeks_incubated')} / 13.0 weeks - {result.get('incubation_progress_pct')}% Complete)")
    print("-" * 80)
    print("Current Holdings:")
    for sym, pos in result.get("positions", {}).items():
        curr_w = result.get("current_weights", {}).get(sym, 0.0) * 100.0
        val = pos['shares'] * pos.get('last_price', 0.0)
        print(f"  - {sym:14s}: {pos['shares']:4d} shs @ INR {pos.get('last_price', 0.0):.2f} = INR {val:,.2f} ({curr_w:.1f}%)")
    print("=" * 80)


if __name__ == "__main__":
    main()
