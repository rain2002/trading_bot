"""
Emergency Kill-Switch & Boss Command Console
Document Classification: Master Fiduciary Blueprint & Final Architecture
Strictly Governed by: FINAL_MASTER_HEDGE_FUND_ROADMAP.md (Section 2, Item 2 & Chapter 2)

Usage:
  python trading_system/scripts/emergency_kill_switch.py --action status
  python trading_system/scripts/emergency_kill_switch.py --action trigger --reason "Manual Boss halt"
  python trading_system/scripts/emergency_kill_switch.py --action reset
  python trading_system/scripts/emergency_kill_switch.py --action drill
  python trading_system/scripts/emergency_kill_switch.py --action ping
"""

import sys
import os
import argparse
import json
from datetime import datetime, timezone

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from trading_system.app.risk.cro import ChiefRiskOfficer
from trading_system.app.notifications.notifier import QuantNotifier


def main():
    parser = argparse.ArgumentParser(description="Chief Risk Officer (CRO) Emergency Kill-Switch Desk")
    parser.add_argument(
        "--action",
        choices=["status", "trigger", "reset", "drill", "ping"],
        default="status",
        help="Action to execute on the CRO supervisor engine"
    )
    parser.add_argument(
        "--reason",
        type=str,
        default="Manual Boss emergency intervention",
        help="Reason string when triggering emergency kill switch"
    )

    args = parser.parse_args()
    notifier = QuantNotifier()
    cro = ChiefRiskOfficer(notifier=notifier)

    print("=" * 65)
    print(">>> CHIEF RISK OFFICER (CRO) EMERGENCY COMMAND CONSOLE <<<")
    print("=" * 65)

    if args.action == "status":
        state = cro.state
        is_halted = state.get("emergency_halt_active", False)
        drill_done = state.get("kill_switch_drill_verified", False)
        hwm = state.get("high_water_mark", 0.0)
        regime = state.get("confirmed_regime", "UNKNOWN")
        last_ping = state.get("last_boss_ping", "None")

        status_tag = "🚨 EMERGENCY HALT ACTIVE" if is_halted else "🟢 NORMAL OPERATIONS"
        drill_tag = "✅ VERIFIED" if drill_done else "⏳ PENDING"

        print(f"  Fiduciary State:        {status_tag}")
        print(f"  High-Water Mark:        ${hwm:,.2f}")
        print(f"  Confirmed Regime:       {regime}")
        print(f"  Last Boss Check-In:     {last_ping}")
        print(f"  Gate B Drill Status:    {drill_tag}")
        print("=" * 65)

    elif args.action == "trigger":
        print(f"\n[CRITICAL] Activating Emergency Kill Switch: {args.reason}")
        cro.trigger_emergency_kill_switch(reason=args.reason)
        print(" -> Kill switch activated. All live order placement quarantined.")
        print(" -> Urgent Discord alert dispatched.")

    elif args.action == "reset":
        print("\n[BOSS AUTH] Resetting emergency halt authorization...")
        cro.reset_emergency_halt()
        print(" -> Emergency halt cleared. CRO supervisor restored to normal monitoring.")

    elif args.action == "drill":
        print("\n[GATE B DRILL] Executing simulated emergency kill-switch drill...")
        drill_rec = cro.verify_kill_switch_drill()
        print(f" -> Drill verified at {drill_rec['timestamp']}.")
        print(" -> Gate B Criterion 5 verification receipt generated.")
        print(" -> Confirmation dispatched to Discord.")

    elif args.action == "ping":
        print("\n[WATCHDOG PING] Registering Boss handshake ping...")
        cro.register_boss_ping()
        print(" -> 14-day Boss-away watchdog reset to full window.")


if __name__ == "__main__":
    main()
