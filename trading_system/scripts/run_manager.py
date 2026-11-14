"""
Execution Script: Central Portfolio Manager (Phase 2 Gate B Paper Trader)
========================================================================
Governed strictly by: PROTOCOL-MANAGER-BOT-CASH-SLEEVE-V1-20261113
Policy: FIXED_SHARES_PLUS_KILL_SWITCH (Determined by Test T1)

Core Responsibilities:
1. Ingest specialist bot state reports (ETF & Gold Bot).
2. Compute bot NAV independently from cash + positions times fresh market quotes.
3. Daily fiduciary reconciliation between independent bot NAV and reported bot NAV (gap <= 0.1%).
4. Maintain Unitized NAV and true trading return ledger (protecting against SIP/bonus distortion).
5. Enforce portfolio-level risk limits (Hard Kill Switch at -40% Drawdown -> 100% to LIQUIDBEES).
6. Support PAPER vs LIVE execution modes (LIVE mode enforces strictly LIVE_APPROVED gate clearance).
7. Persist manager state and equity log to disk for state branch sync.
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from trading_system.app.common.interfaces import BotReport
from trading_system.app.manager.manager import PortfolioManagerEngine, RECONCILIATION_MAX_GAP
from trading_system.app.accounting.unitized_nav import UnitizedNAVEngine

logger = logging.getLogger("CentralPortfolioManager")


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


def compute_independent_bot_nav(
    etf_state: Dict[str, Any],
    quotes_override: Optional[Dict[str, float]] = None
) -> Tuple[float, Dict[str, float]]:
    """
    Computes ETF Bot NAV independently from raw cash balance and active positions,
    evaluated against fresh quotes (or quotes_override, falling back to position last_price).
    Returns (independent_nav, prices_used).
    """
    positions = etf_state.get("positions", {})
    if not positions:
        # If no positions are held, bot NAV is its cash balance (or reported NAV if cash not explicitly set)
        cash = float(etf_state.get("cash", etf_state.get("nav", 0.0)))
        return round(cash, 2), {}

    cash = float(etf_state.get("cash", 0.0))
    prices = dict(quotes_override or {})
    # If not supplied, attempt to fetch fresh market quotes for missing symbols
    missing = [sym for sym in positions.keys() if sym not in prices]
    if missing:
        try:
            import yfinance as yf
            tickers = yf.Tickers(" ".join(missing))
            for sym in missing:
                try:
                    hist = tickers.tickers[sym].history(period="5d")
                    if not hist.empty:
                        prices[sym] = float(hist["Close"].iloc[-1])
                except Exception:
                    pass
        except Exception:
            pass

    holdings_val = 0.0
    for sym, pos in positions.items():
        shs = int(pos.get("shares", 0))
        # Use fresh quote if available, fallback to position last_price
        px = prices.get(sym)
        if px is None:
            px = float(pos.get("last_price", 0.0))
        prices[sym] = px
        holdings_val += shs * px

    independent_nav = cash + holdings_val
    return round(independent_nav, 2), prices


def execute_manager_cycle(
    etf_state_path: Optional[str] = None,
    manager_state_path: Optional[str] = None,
    ledger_path: Optional[str] = None,
    equity_log_path: Optional[str] = None,
    policy: str = "FIXED_SHARES_PLUS_KILL_SWITCH",
    mode: str = "PAPER",
    initial_capital: float = 80000.0,
    quotes_override: Optional[Dict[str, float]] = None,
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
            etf_state = {"nav": initial_capital, "cash": initial_capital, "status": f"READ_ERROR: {e}", "gate": "GATE_B_PAPER"}
    else:
        etf_state = {
            "nav": initial_capital,
            "cash": initial_capital,
            "positions": {},
            "status": "INITIAL_UNSEEDED",
            "gate": "GATE_B_PAPER",
            "last_run_timestamp": None,
            "current_drawdown_pct": 0.0,
            "max_drawdown_pct": 0.0
        }

    reported_nav = float(etf_state.get("nav", initial_capital))
    stale = is_bot_state_stale(etf_state.get("last_run_timestamp"), current_time)

    # 2. Independent Bot NAV Calculation (from raw cash + positions * fresh quotes)
    independent_nav, quotes_used = compute_independent_bot_nav(etf_state, quotes_override=quotes_override)

    # 3. Maintain Unitized NAV Ledger based on Verified Independent NAV
    nav_engine = UnitizedNAVEngine(ledger_path=ledger_path, initial_capital=initial_capital)
    nav_engine.update_portfolio_valuation(independent_nav, timestamp=current_time)
    nav_metrics = nav_engine.get_fund_performance_metrics()

    # Manager Portfolio Total Value is the verified independent NAV
    nav_state = {
        "total_portfolio_value": independent_nav,
        "nav_per_unit": nav_metrics["nav_per_unit"]
    }

    # 4. Construct Bot Report using Reported NAV to Test State File Integrity
    etf_report = BotReport(
        nav=reported_nav,
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

    # 5. Evaluate Portfolio Shares, Fiduciary Reconciliation & Risk Controls
    manager = PortfolioManagerEngine(
        target_shares={"ETF_AND_GOLD": 1.0},
        initial_capital=initial_capital,
        state_file=manager_state_path,
        policy=policy,
        mode=mode
    )

    shares = manager.evaluate_shares(
        as_of=pd.Timestamp(current_time),
        reports=reports,
        nav_state=nav_state
    )

    status = manager.get_status()

    # 6. Append to Manager Equity Log
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
        "share_cash_sleeve": shares.get("CASH_SLEEVE", 0.0),
        "execution_mode": mode
    }

    df_log = pd.DataFrame([log_entry])
    if not os.path.exists(equity_log_path):
        df_log.to_csv(equity_log_path, index=False)
    else:
        df_log.to_csv(equity_log_path, mode="a", header=False, index=False)

    return {
        "timestamp": current_time.isoformat(),
        "policy": policy,
        "mode": mode,
        "shares": shares,
        "status": status,
        "nav_metrics": nav_metrics,
        "independent_nav": independent_nav,
        "reported_nav": reported_nav,
        "quotes_used": quotes_used,
        "etf_report": {
            "nav": etf_report.nav,
            "stale": etf_report.stale,
            "gate_status": etf_report.gate_status
        }
    }


def main():
    parser = argparse.ArgumentParser(description="Central Portfolio Manager (Phase 2 Paper Trader)")
    parser.add_argument("--policy", default="FIXED_SHARES_PLUS_KILL_SWITCH", choices=["FIXED_SHARES_PLUS_KILL_SWITCH", "THROTTLE_AND_KILL_SWITCH"])
    parser.add_argument("--mode", default="PAPER", choices=["PAPER", "LIVE"], help="Execution mode (PAPER: GATE_B_PAPER eligible; LIVE: strictly LIVE_APPROVED)")
    parser.add_argument("--capital", type=float, default=80000.0)
    args = parser.parse_args()

    print("=" * 80)
    print(">>> CENTRAL PORTFOLIO MANAGER (PHASE 2 - GATE B PAPER INCUBATION) <<<")
    print("=" * 80)
    print(f"Timestamp        : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Execution Mode   : {args.mode.upper()}")
    print(f"Production Policy: {args.policy} (Per Pre-registered Test T1 Verdict)")
    print(f"Active Universe  : Bot 1 (ETF & Gold Bot: 100%) + Cash Sleeve (LIQUIDBEES.NS: 0%)")
    print(f"Starting Capital : INR {args.capital:,.2f}")
    print("-" * 80)

    res = execute_manager_cycle(policy=args.policy, mode=args.mode, initial_capital=args.capital)

    metrics = res["nav_metrics"]
    status = res["status"]
    shares = res["shares"]

    print(f"Total Portfolio Value : INR {metrics['total_portfolio_value']:,.2f} (Independent: INR {res['independent_nav']:,.2f} | Reported: INR {res['reported_nav']:,.2f})")
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
