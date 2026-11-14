"""
Execution Script: Run ETF & Gold Bot (Phase 1 Gate B Incubation)
================================================================
Executes daily cycle for Bot 1 (ETF & Gold Bot):
- Ingests latest live prices for GOLDBEES, MON100, NIFTYBEES, MID150BEES
- Deploys / rebalances portfolio
- Logs daily NAV and trades
- Prints incubation health and drawdown status
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
    print(f"Mandate  : Gold + Equity ETFs (GOLDBEES, MON100, NIFTYBEES, MID150BEES)")
    print(f"Capital  : INR 80,000.00 Starting Capital")
    print(f"Target   : 13-Week Paper Incubation Window")
    print("-" * 80)

    runner = ETFGoldsPaperRunner()
    result = runner.run_daily_cycle()

    if result.get("status") == "FAIL_CLOSED":
        print(f"[FAIL-CLOSED] Execution aborted safely. Missing quotes: {result.get('missing_quotes')}")
        sys.exit(0)

    print(f"Execution Status    : {result.get('status')}")
    print(f"Portfolio NAV       : INR {result.get('nav', 0.0):,.2f}")
    print(f"Cash Balance        : INR {result.get('cash', 0.0):,.2f}")
    print(f"Max Drawdown        : {result.get('drawdown_pct', 0.0):.2f}%")
    print(f"Incubation Progress : Day {result.get('days_incubated')} of 91 ({result.get('weeks_incubated')} / 13.0 weeks - {result.get('incubation_progress_pct')}% Complete)")
    print("-" * 80)
    print("Current Holdings:")
    for sym, pos in result.get("positions", {}).items():
        print(f"  - {sym:14s}: {pos['shares']:4d} shs @ INR {pos.get('last_price', 0.0):.2f} (Entry: INR {pos.get('entry_price', 0.0):.2f})")
    print("=" * 80)


if __name__ == "__main__":
    main()
