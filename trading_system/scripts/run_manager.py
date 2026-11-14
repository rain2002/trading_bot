"""
Execution Script: Central Portfolio Manager (Phase 2 Gate B Paper Trader)
========================================================================
Governed strictly by: PROTOCOL-MANAGER-BOT-CASH-SLEEVE-V1-20261113
Policy: FIXED_SHARES_PLUS_KILL_SWITCH (Determined by Test T1)

Core Responsibilities:
1. Ingest specialist bot state reports (ETF & Gold Bot).
2. Maintain Unitized NAV and true trading return ledger (protecting against SIP/bonus distortion).
3. Daily fiduciary reconciliation between Manager NAV and sum of Bot NAVs (gap <= 0.1%).
4. Enforce portfolio-level risk limits (Hard Kill Switch at -40% Drawdown -> 100% to LIQUIDBEES).
5. Persist manager state and equity log to disk for state branch sync.
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from trading_system.app.common.interfaces import BotReport
from trading_system.app.manager.manager import PortfolioManagerEngine, RECONCILIATION_MAX_GAP
from trading_system.app.accounting.unitized_nav import UnitizedNAVEngine


def is_bot_state_stale(last_run_timestamp_str: Optional[str], as_of: datetime) -> bool:
    """
    Checks if bot state is older than one full trading day (48h max threshold for weekdays).
    """
    if not last_run_timestamp_str:
        return False
    try:
        ts = datetime.fromisoformat(last_run_timestamp_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        diff = as_of - ts
        # Over weekend allow up to 72h, on weekdays 48h
        max_allowed_hours = 72 if as_of.weekday() in (0, 6) else 48
        return diff > timedelta(hours=max_allowed_hours)
    except Exception:
        return True


def execute_manager_cycle(
    etf_state_path: Optional[str] = None,
    manager_state_path: Optional[str] = None,
    ledger_path: Optional[str] = None,
    equity_log_path: Optional[str] = None,
    policy: str = "FIXED_SHARES_PLUS_KILL_SWITCH",
    initial_capital: float = 80000.0,
    as_of: Optional[datetime] = None
) -> Dict[str, Any]:
    data_dir = os.path.join(PROJECT_ROOT, "trading_system", "data")
    etf_state_path = etf_state_path or os.path.join(data_dir, "etf_gold_state.json")
    manager_state_path = manager_state_path or os.path.join(data_dir, "manager_state.json")
    ledger_path = ledger_path or os.path.join(data_dir, "unitized_nav_ledger.json")
    equity_log_path = equity_log_path or os.path.join(data_dir, "manager_equity_log.csv")

    current_time = as_of or datetime.now(timezone.utc)

    # 1. Ingest ETF & Gold Bot State
    if os.path.exists(etf_state_path):
        try:
            with open(etf_state_path, "r") as f:
                etf_state = json.load(f)
        except Exception as e:
            etf_state = {"nav": initial_capital, "status": f"READ_ERROR: {e}", "gate": "GATE_B_PAPER"}
    else:
        etf_state = {
            "nav": initial_capital,
            "cash": initial_capital,
            "status": "INITIAL_UNSEEDED",
            "gate": "GATE_B_PAPER",
            "last_run_timestamp": None,
            "current_drawdown_pct": 0.0,
            "max_drawdown_pct": 0.0
        }

    etf_nav = float(etf_state.get("nav", initial_capital))
    stale = is_bot_state_stale(etf_state.get("last_run_timestamp"), current_time)

    etf_report = BotReport(
        nav=etf_nav,
        risk_status={
            "current_drawdown_pct": etf_state.get("current_drawdown_pct", 0.0),
            "max_drawdown_pct": etf_state.get("max_drawdown_pct", 0.0),
            "status": etf_state.get("status", "UNKNOWN")
        },
        gate_status=etf_state.get("gate", "GATE_B_PAPER"),
        last_update=pd.Timestamp(etf_state.get("last_run_timestamp") or current_time),
        stale=stale
    )

    reports = {"ETF_AND_GOLD": etf_report}

    # 2. Maintain Unitized NAV Ledger
    nav_engine = UnitizedNAVEngine(ledger_path=ledger_path, initial_capital=initial_capital)
    nav_engine.update_portfolio_valuation(etf_nav, timestamp=current_time)
    nav_metrics = nav_engine.get_fund_performance_metrics()

    nav_state = {
        "total_portfolio_value": nav_metrics["total_portfolio_value"],
        "nav_per_unit": nav_metrics["nav_per_unit"]
    }

    # 3. Evaluate Portfolio Shares & Risk Controls
    manager = PortfolioManagerEngine(
        target_shares={"ETF_AND_GOLD": 1.0},
        initial_capital=initial_capital,
        state_file=manager_state_path,
        policy=policy
    )

    shares = manager.evaluate_shares(
        as_of=pd.Timestamp(current_time),
        reports=reports,
        nav_state=nav_state
    )

    status = manager.get_status()

    # 4. Append to Manager Equity Log
    os.makedirs(os.path.dirname(equity_log_path), exist_ok=True)
    log_entry = {
        "date": current_time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_portfolio_value": round(nav_metrics["total_portfolio_value"], 2),
        "nav_per_unit": round(nav_metrics["nav_per_unit"], 4),
        "true_trading_return_pct": round(nav_metrics["true_trading_return_pct"], 4),
        "current_drawdown_pct": round(status["current_drawdown"] * 100.0, 2),
        "throttle_level": status["throttle_level"],
        "is_halted": status["is_halted"],
        "halt_reason": status["halt_reason"] or "",
        "reconciliation_gap_pct": round(status["last_reconciliation_gap_pct"], 4),
        "share_etf_gold": shares.get("ETF_AND_GOLD", 0.0),
        "share_cash_sleeve": shares.get("CASH_SLEEVE", 0.0)
    }

    df_log = pd.DataFrame([log_entry])
    if not os.path.exists(equity_log_path):
        df_log.to_csv(equity_log_path, index=False)
    else:
        df_log.to_csv(equity_log_path, mode="a", header=False, index=False)

    return {
        "timestamp": current_time.isoformat(),
        "policy": policy,
        "shares": shares,
        "status": status,
        "nav_metrics": nav_metrics,
        "etf_report": {
            "nav": etf_report.nav,
            "stale": etf_report.stale,
            "gate_status": etf_report.gate_status
        }
    }


def main():
    parser = argparse.ArgumentParser(description="Central Portfolio Manager (Phase 2 Paper Trader)")
    parser.add_argument("--policy", default="FIXED_SHARES_PLUS_KILL_SWITCH", choices=["FIXED_SHARES_PLUS_KILL_SWITCH", "THROTTLE_AND_KILL_SWITCH"])
    parser.add_argument("--capital", type=float, default=80000.0)
    args = parser.parse_args()

    print("=" * 80)
    print(">>> CENTRAL PORTFOLIO MANAGER (PHASE 2 - GATE B PAPER INCUBATION) <<<")
    print("=" * 80)
    print(f"Timestamp        : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Production Policy: {args.policy} (Per Pre-registered Test T1 Verdict)")
    print(f"Active Universe  : Bot 1 (ETF & Gold Bot: 100%) + Cash Sleeve (LIQUIDBEES.NS: 0%)")
    print(f"Starting Capital : INR {args.capital:,.2f}")
    print("-" * 80)

    res = execute_manager_cycle(policy=args.policy, initial_capital=args.capital)

    metrics = res["nav_metrics"]
    status = res["status"]
    shares = res["shares"]

    print(f"Total Portfolio Value : INR {metrics['total_portfolio_value']:,.2f}")
    print(f"NAV Per Unit          : INR {metrics['nav_per_unit']:.4f} (Base: 100.0000)")
    print(f"True Trading Return   : {metrics['true_trading_return_pct']:+.2f}%")
    print(f"Current Drawdown      : {status['current_drawdown'] * 100.0:.2f}% (HWM Unit NAV: {status['hwm_unit_nav']:.4f})")
    print(f"Reconciliation Gap    : {status['last_reconciliation_gap_pct']:.4f}% (Max Permissible: {RECONCILIATION_MAX_GAP * 100.0:.1f}%)")
    print(f"Trading Halted        : {'YES - ' + str(status['halt_reason']) if status['is_halted'] else 'NO (Normal Operations)'}")
    print(f"Risk Throttle Level   : {status['throttle_level']} (0: Normal, 1: -15%, 2: -30%, 3: -40% Kill)")
    print("-" * 80)
    print("Allocated Capital Shares:")
    for sleeve, share in shares.items():
        val = metrics['total_portfolio_value'] * share
        print(f"  - {sleeve:15s}: {share * 100.0:5.1f}% (INR {val:,.2f})")
    print("=" * 80)

    if status["is_halted"]:
        print(f"[CRITICAL ALERT] Manager Trading Halted: {status['halt_reason']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
