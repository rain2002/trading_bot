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
import csv
import json
import math
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
    bot_state: Dict[str, Any],
    quotes_override: Optional[Dict[str, float]] = None
) -> Tuple[float, Dict[str, float], bool]:
    """
    Computes Bot NAV independently from raw cash balance and active positions,
    evaluated against fresh quotes (or quotes_override, falling back to position last_price).
    Returns (independent_nav, prices_used, all_quotes_verified).
    If any position relies on unverified last_price fallback due to missing live quote,
    all_quotes_verified is False (counted as UNVERIFIED, not as a confirmed reconciliation pass).
    """
    positions = bot_state.get("positions", {})
    if not positions:
        # If no positions are held, bot NAV is its cash balance
        cash = float(bot_state.get("cash", bot_state.get("nav", 0.0)))
        return round(cash, 2), {}, True

    cash = float(bot_state.get("cash", 0.0))
    prices = dict(quotes_override or {})
    all_quotes_verified = True

    # If not supplied, attempt to fetch fresh market quotes for missing symbols
    missing = [sym for sym in positions.keys() if sym not in prices]
    if missing:
        try:
            import yfinance as yf
            now_dt = datetime.now(timezone.utc)
            for sym in missing:
                try:
                    t = yf.Ticker(sym)
                    hist = t.history(period="10d")
                    valid_hist = hist.dropna(subset=["Close"]) if not hist.empty else pd.DataFrame()
                    if not valid_hist.empty:
                        bar_dt = valid_hist.index[-1].to_pydatetime()
                        if bar_dt.tzinfo is None:
                            bar_dt = bar_dt.replace(tzinfo=timezone.utc)
                        days_old = (now_dt - bar_dt).days
                        # Only accept quotes if within max price staleness threshold (5 days)
                        if days_old <= 5:
                            cand_price = float(valid_hist.iloc[-1]["Close"])
                            try:
                                fi_px = getattr(t.fast_info, "last_price", None)
                                if fi_px is not None and not pd.isna(fi_px):
                                    fi_val = float(fi_px)
                                    if fi_val > 0 and (cand_price <= 0 or abs(fi_val - cand_price) / cand_price <= 0.20):
                                        cand_price = fi_val
                            except Exception:
                                pass
                            if cand_price > 0 and not pd.isna(cand_price):
                                prices[sym] = cand_price
                except Exception:
                    pass
        except Exception:
            pass

    holdings_val = 0.0
    for sym, pos in positions.items():
        shs = int(pos.get("shares", 0))
        # Use fresh quote if available (>0 and non-NaN), fallback to position last_price
        px = prices.get(sym)
        if px is None or pd.isna(px) or px <= 0:
            px = float(pos.get("last_price", 0.0))
            all_quotes_verified = False  # Price was unverified against live market
            logger.warning(f"Unverified quote fallback used for {sym}: last_price={px:.2f}")
        prices[sym] = px
        holdings_val += shs * px

    independent_nav = cash + holdings_val
    if pd.isna(independent_nav) or independent_nav <= 0:
        logger.error(f"Non-positive or NaN independent NAV: {independent_nav}. Falling back to reported NAV.")
        independent_nav = float(bot_state.get("nav", cash))
        all_quotes_verified = False

    return round(independent_nav, 2), prices, all_quotes_verified


def append_manager_equity_log(
    equity_log_path: str,
    log_entry: Dict[str, Any],
    session_date: Optional[str] = None
):
    """
    Appends manager equity record to CSV safely, ensuring canonical schema alignment:
    - Automatically initializes header on new file.
    - If existing file has legacy/ragged header (e.g. 11-column pre-sleeve format, or 15-column pre-session_date format),
      transparently migrates historical rows into the canonical 16-column schema
      before appending, preventing column misalignment.
    - Uses csv.reader to safely handle any quoted fields with commas.
    - For historical rows predating multi-sleeve logging, reserve_sleeve_nav and
      combined_fund_nav are left blank (never populated with invented/guessed values).
    - Session date is keyed on the exchange bar date (session_date), ensuring that delayed runs
      past midnight UTC or same-session re-runs are idempotently replaced rather than duplicated or erring.
    """
    os.makedirs(os.path.dirname(equity_log_path), exist_ok=True)
    canonical_columns = [
        "date", "session_date", "total_portfolio_value", "primary_sleeve_nav", "reserve_sleeve_nav",
        "combined_fund_nav", "nav_per_unit", "true_trading_return_pct", "current_drawdown_pct",
        "throttle_level", "is_halted", "halt_reason", "reconciliation_gap_pct",
        "share_etf_gold", "share_cash_sleeve", "execution_mode"
    ]

    if not session_date:
        session_date = log_entry.get("session_date") or str(log_entry.get("date", ""))[:10]
    log_entry["session_date"] = str(session_date)

    if not os.path.exists(equity_log_path) or os.path.getsize(equity_log_path) == 0:
        df = pd.DataFrame([log_entry])
        for col in canonical_columns:
            if col not in df.columns:
                df[col] = ""
        df[canonical_columns].to_csv(equity_log_path, index=False)
        return

    with open(equity_log_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header_row = next(reader, None)
    existing_cols = [c.strip() for c in header_row if c.strip()] if header_row else []

    if existing_cols == canonical_columns:
        # Idempotent logging: replace existing row for this session date on re-run, otherwise append
        try:
            existing_df = pd.read_csv(equity_log_path, dtype=str)
            if "session_date" in existing_df.columns:
                mask = existing_df["session_date"].astype(str) == str(session_date)
                if mask.any():
                    existing_df = existing_df[~mask]
                    new_df = pd.concat([existing_df, pd.DataFrame([log_entry])], ignore_index=True)
                    for col in canonical_columns:
                        if col not in new_df.columns:
                            new_df[col] = ""
                    new_df[canonical_columns].to_csv(equity_log_path, index=False)
                    return
        except Exception as e:
            logger.warning(f"Error checking manager equity log for deduplication: {e}")

        df = pd.DataFrame([log_entry])
        for col in canonical_columns:
            if col not in df.columns:
                df[col] = ""
        df[canonical_columns].to_csv(equity_log_path, mode="a", header=False, index=False)
    else:
        # Migrate legacy rows into canonical 16-column schema
        migrated_rows = []
        with open(equity_log_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            _ = next(reader, None)  # Skip header
            for parts in reader:
                if not parts:
                    continue
                # Case 1: 15-column schema (missing session_date)
                if len(parts) == 15 and "primary_sleeve_nav" in existing_cols:
                    dt = parts[0].strip()
                    row_dict = {
                        "date": dt,
                        "session_date": dt[:10],
                        "total_portfolio_value": parts[1].strip(),
                        "primary_sleeve_nav": parts[2].strip(),
                        "reserve_sleeve_nav": parts[3].strip(),
                        "combined_fund_nav": parts[4].strip(),
                        "nav_per_unit": parts[5].strip(),
                        "true_trading_return_pct": parts[6].strip(),
                        "current_drawdown_pct": parts[7].strip(),
                        "throttle_level": parts[8].strip(),
                        "is_halted": parts[9].strip(),
                        "halt_reason": parts[10].strip(),
                        "reconciliation_gap_pct": parts[11].strip(),
                        "share_etf_gold": parts[12].strip(),
                        "share_cash_sleeve": parts[13].strip(),
                        "execution_mode": parts[14].strip()
                    }
                    migrated_rows.append(row_dict)
                # Case 2: Legacy 11-12 column schema
                elif len(parts) >= 11 and parts[1].replace(".", "", 1).isdigit():
                    dt = parts[0].strip()
                    tot_val = float(parts[1].strip()) if parts[1].strip() else 80000.0
                    nav_u = float(parts[2].strip()) if parts[2].strip() else 100.0
                    ret_pct = float(parts[3].strip()) if parts[3].strip() else 0.0
                    dd_pct = float(parts[4].strip()) if parts[4].strip() else 0.0
                    th_lvl = int(parts[5].strip()) if parts[5].strip() else 0
                    halted = parts[6].strip().lower() == "true"
                    h_reason = parts[7].strip()
                    rec_gap = float(parts[8].strip()) if parts[8].strip() else 0.0
                    s_etf = float(parts[9].strip()) if parts[9].strip() else 1.0
                    s_cash = float(parts[10].strip()) if parts[10].strip() else 0.0
                    exec_m = parts[11].strip() if len(parts) > 11 and parts[11].strip() else "PAPER"

                    row_dict = {
                        "date": dt,
                        "session_date": dt[:10],
                        "total_portfolio_value": tot_val,
                        "primary_sleeve_nav": tot_val,
                        "reserve_sleeve_nav": "",
                        "combined_fund_nav": "",
                        "nav_per_unit": nav_u,
                        "true_trading_return_pct": ret_pct,
                        "current_drawdown_pct": dd_pct,
                        "throttle_level": th_lvl,
                        "is_halted": halted,
                        "halt_reason": h_reason,
                        "reconciliation_gap_pct": rec_gap,
                        "share_etf_gold": s_etf,
                        "share_cash_sleeve": s_cash,
                        "execution_mode": exec_m
                    }
                    migrated_rows.append(row_dict)

        migrated_rows = [r for r in migrated_rows if str(r.get("session_date", "")) != str(session_date)]
        migrated_rows.append(log_entry)
        df_migrated = pd.DataFrame(migrated_rows)
        for col in canonical_columns:
            if col not in df_migrated.columns:
                df_migrated[col] = ""
        df_migrated[canonical_columns].to_csv(equity_log_path, index=False)


def execute_manager_cycle(
    etf_state_path: Optional[str] = None,
    bond_cash_state_path: Optional[str] = None,
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
    bond_cash_state_path = bond_cash_state_path or os.path.join(data_dir, "bond_cash_state.json")
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
    etf_status = etf_state.get("status", "UNKNOWN")
    stale = is_bot_state_stale(etf_state.get("last_run_timestamp"), current_time)

    # Load prior manager state if present to check 1-day jump and retain prior state on DATA_FAULT
    prior_manager_state = None
    prior_nav = initial_capital
    if os.path.exists(manager_state_path):
        try:
            with open(manager_state_path, "r") as f:
                prior_manager_state = json.load(f)
            u_nav = float(prior_manager_state.get("unitized_nav", 100.0))
            if u_nav > 0:
                prior_nav = u_nav * (initial_capital / 100.0)
            elif prior_manager_state.get("total_portfolio_value"):
                p_val = float(prior_manager_state["total_portfolio_value"])
                if p_val > 0 and not math.isnan(p_val):
                    prior_nav = p_val
        except Exception:
            prior_nav = initial_capital

    # 2. Independent Bot NAV Calculation (from raw cash + positions * fresh quotes)
    independent_nav, quotes_used, etf_quotes_verified = compute_independent_bot_nav(etf_state, quotes_override=quotes_override)

    # Sanity checks for DATA_FAULT (Reviewer Requirement 2 & 3):
    # - If ETF step fails (FAIL_CLOSED, FAILED, ERROR)
    # - If independent NAV is NaN, non-positive (<=0), or moves > 25% in a single day
    is_data_fault = False
    data_fault_reasons = []

    # 1. Check if ETF bot ran in today's session (Reviewer Gap 1)
    last_run_str = etf_state.get("last_run_timestamp")
    etf_ran_today = False
    if last_run_str:
        try:
            last_run_dt = datetime.fromisoformat(last_run_str)
            if last_run_dt.tzinfo is None:
                last_run_dt = last_run_dt.replace(tzinfo=timezone.utc)
            # Valid session window: same calendar date, or within last 6 hours
            hours_diff = (current_time - last_run_dt).total_seconds() / 3600.0
            if last_run_dt.date() == current_time.date() or (0 <= hours_diff <= 6.0):
                etf_ran_today = True
        except Exception:
            etf_ran_today = False

    # Allow initial unseeded state on day 0
    if etf_state.get("status") == "INITIAL_UNSEEDED":
        etf_ran_today = True

    if not etf_ran_today:
        is_data_fault = True
        data_fault_reasons.append(
            f"ETF Bot did not execute in today's session (last run: {last_run_str}, session: {current_time.strftime('%Y-%m-%d')})"
        )
    elif etf_status in ["FAILED", "ERROR", "FAIL_CLOSED"]:
        is_data_fault = True
        data_fault_reasons.append(f"ETF Bot execution step failed (status: {etf_status})")

    if math.isnan(independent_nav) or math.isinf(independent_nav) or pd.isna(independent_nav):
        is_data_fault = True
        data_fault_reasons.append(f"Non-finite independent NAV: {independent_nav}")
    elif independent_nav <= 0:
        is_data_fault = True
        data_fault_reasons.append(f"Non-positive independent NAV: {independent_nav}")
    elif prior_nav > 0:
        pct_jump = abs(independent_nav - prior_nav) / prior_nav
        if pct_jump > 0.25:
            is_data_fault = True
            data_fault_reasons.append(f"Extreme single-day NAV jump of {pct_jump*100:.1f}% exceeds 25.0% sanity threshold (Prior: {prior_nav:.2f}, Indep: {independent_nav:.2f})")

    if is_data_fault:
        fault_msg = "DATA_FAULT: " + "; ".join(data_fault_reasons)
        logger.error(f"[DATA FAULT DETECTED] {fault_msg}. Retaining prior manager state, skipping ledger update, and bypassing kill switch.")

        # Retain prior manager state safely
        state = dict(prior_manager_state or {})
        if not state:
            state = {
                "manager_name": "CENTRAL_PORTFOLIO_MANAGER",
                "phase": "PHASE_2",
                "policy": policy,
                "unitized_nav": 100.0,
                "hwm_unit_nav": 100.0,
                "current_drawdown": 0.0,
                "max_drawdown": 0.0,
                "throttle_level": 0,
                "consecutive_recovery_days": 0,
                "is_halted": False,
                "halt_reason": None,
                "human_override_required": False,
                "last_reconciliation_gap_pct": 0.0,
                "last_rebalance_date": None,
                "current_shares": {"ETF_AND_GOLD": 1.0, "BOND_AND_CASH": 0.0, "CASH_SLEEVE": 0.0},
                "mode": mode,
                "max_duration_scale": 1.0
            }

        state["last_cycle_status"] = fault_msg
        state["last_update"] = current_time.isoformat()
        os.makedirs(os.path.dirname(manager_state_path), exist_ok=True)
        with open(manager_state_path, "w") as f:
            json.dump(state, f, indent=2)

        # Skip ledger update & skip equity log append
        return {
            "policy": policy,
            "mode": mode,
            "shares": state.get("current_shares", {"ETF_AND_GOLD": 1.0}),
            "status": {
                "is_halted": state.get("is_halted", False),
                "halt_reason": state.get("halt_reason"),
                "throttle_level": state.get("throttle_level", 0),
                "current_drawdown": state.get("current_drawdown", 0.0),
                "max_drawdown": state.get("max_drawdown", 0.0),
                "last_reconciliation_gap_pct": state.get("last_reconciliation_gap_pct", 0.0),
                "is_data_fault": True,
                "data_fault_reason": fault_msg
            },
            "nav_metrics": {
                "nav_per_unit": state.get("unitized_nav", 100.0),
                "total_portfolio_value": prior_nav
            },
            "independent_nav": prior_nav,
            "reported_nav": reported_nav,
            "combined_fund_nav": state.get("combined_fund_nav", prior_nav),
            "sleeves": state.get("sleeves", {}),
            "etf_report": {
                "nav": reported_nav,
                "stale": stale,
                "gate_status": etf_state.get("gate", "GATE_B_PAPER")
            },
            "bond_cash_report": None,
            "quotes_used": quotes_used,
            "max_duration_scale": state.get("max_duration_scale", 1.0),
            "consecutive_unverified_quote_days": state.get("consecutive_unverified_quote_days", 0),
            "unverified_quotes_warning": state.get("unverified_quotes_warning")
        }

    etf_gap = abs(independent_nav - reported_nav) / reported_nav if reported_nav > 0 else 0.0
    etf_rec_passed = (etf_gap <= RECONCILIATION_MAX_GAP and etf_quotes_verified)
    etf_rec_status = "PASSED" if etf_rec_passed else ("UNVERIFIED_FALLBACK_PRICE" if not etf_quotes_verified else "RECONCILIATION_BREACH")

    # 3. Ingest Bond and Cash Bot State (Dedicated INR 20,000 Paper Capital Partition)
    bond_state = None
    independent_bond_nav = 0.0
    bond_reported_nav = 0.0
    bond_stale = False
    bond_rec_passed = True
    bond_quotes_verified = True
    bond_rec_status = "PASSED"
    bond_gap = 0.0
    bond_report = None

    if os.path.exists(bond_cash_state_path):
        try:
            with open(bond_cash_state_path, "r") as f:
                bond_state = json.load(f)
            bond_reported_nav = float(bond_state.get("nav", 20000.0))
            bond_stale = is_bot_state_stale(bond_state.get("last_run_timestamp"), current_time)
            independent_bond_nav, bond_quotes, bond_quotes_verified = compute_independent_bot_nav(bond_state, quotes_override=quotes_override)
            quotes_used.update(bond_quotes)

            # Independent reconciliation of Bond & Cash Bot
            if bond_reported_nav > 0:
                bond_gap = abs(independent_bond_nav - bond_reported_nav) / bond_reported_nav
                bond_rec_passed = (bond_gap <= RECONCILIATION_MAX_GAP and bond_quotes_verified)
                bond_rec_status = "PASSED" if bond_rec_passed else ("UNVERIFIED_FALLBACK_PRICE" if not bond_quotes_verified else "RECONCILIATION_BREACH")
                if bond_gap > RECONCILIATION_MAX_GAP:
                    logger.error(f"BOND & CASH BOT RECONCILIATION GAP: {bond_gap*100:.3f}% > 0.1%")
                elif not bond_quotes_verified:
                    logger.warning("BOND & CASH BOT RECONCILIATION UNVERIFIED: Missing live quote; fell back to last_price.")

            bond_report = BotReport(
                nav=bond_reported_nav,
                risk_status={
                    "current_drawdown_pct": bond_state.get("current_drawdown_pct", 0.0),
                    "max_drawdown_pct": bond_state.get("max_drawdown_pct", 0.0),
                    "strategy_id": bond_state.get("strategy_id", "B0"),
                    "status": bond_state.get("status", "HEALTHY_ACTIVE")
                },
                gate_status=bond_state.get("gate", "GATE_B_PAPER"),
                last_update=pd.Timestamp(bond_state.get("last_run_timestamp") or current_time),
                stale=bond_stale
            )
        except Exception as e:
            logger.error(f"Error reading bond cash state: {e}")

    # 4. Maintain Unitized NAV Ledger based on Verified Independent Primary Portfolio NAV
    nav_engine = UnitizedNAVEngine(ledger_path=ledger_path, initial_capital=initial_capital)
    nav_engine.update_portfolio_valuation(independent_nav, timestamp=current_time)
    nav_metrics = nav_engine.get_fund_performance_metrics()

    # Manager Portfolio Total Value is the verified independent NAV
    nav_state = {
        "total_portfolio_value": independent_nav,
        "nav_per_unit": nav_metrics["nav_per_unit"]
    }

    # 5. Construct Bot Reports
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
    if bond_report is not None:
        reports["BOND_AND_CASH"] = bond_report

    # Target shares: ETF Bot holds 100% of deployable capital; Bond Bot holds dedicated partitioned paper capital (0.0% real share)
    target_shares = {"ETF_AND_GOLD": 1.0}
    if bond_report is not None:
        target_shares["BOND_AND_CASH"] = 0.0

    # 6. Evaluate Portfolio Shares, Fiduciary Reconciliation & Risk Controls
    manager = PortfolioManagerEngine(
        target_shares=target_shares,
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

    # Record explicit multi-sleeve architecture and independent per-sleeve reconciliation
    combined_fund_nav = round(independent_nav + independent_bond_nav, 2)
    max_reconciliation_gap = max(etf_gap, bond_gap)

    manager.state["sleeves"] = {
        "primary_sleeve": {
            "bot_name": "ETF_AND_GOLD_BOT",
            "mandate": "Active Multi-Asset Equity & Gold Growth (Phase 1)",
            "target_capital": 80000.0,
            "reported_nav": reported_nav,
            "independent_nav": independent_nav,
            "reconciliation_gap_pct": round(etf_gap * 100.0, 4),
            "reconciliation_passed": etf_rec_passed,
            "reconciliation_status": etf_rec_status,
            "quotes_verified": etf_quotes_verified,
            "stale": stale
        },
        "reserve_sleeve": {
            "bot_name": "BOND_AND_CASH_BOT",
            "mandate": "Dedicated Safe Carry & Retreat Haven Partition (Phase 3 Champion B0)",
            "target_capital": 20000.0,
            "reported_nav": bond_reported_nav,
            "independent_nav": independent_bond_nav,
            "reconciliation_gap_pct": round(bond_gap * 100.0, 4),
            "reconciliation_passed": bond_rec_passed,
            "reconciliation_status": bond_rec_status,
            "quotes_verified": bond_quotes_verified,
            "stale": bond_stale
        }
    }
    manager.state["combined_fund_nav"] = combined_fund_nav
    manager.state["combined_target_capital"] = 100000.0
    manager.state["last_reconciliation_gap_pct"] = round(max_reconciliation_gap * 100.0, 4)

    # Hard reconciliation gap breach (> 0.1%) triggers trading halt
    if etf_gap > RECONCILIATION_MAX_GAP:
        manager.state["is_halted"] = True
        manager.state["halt_reason"] = f"RECONCILIATION_GAP_BREACH (ETF Bot): {etf_gap*100:.3f}% > 0.1%"
    elif bond_gap > RECONCILIATION_MAX_GAP:
        manager.state["is_halted"] = True
        manager.state["halt_reason"] = f"BOND_CASH_BOT_RECONCILIATION_BREACH: {bond_gap*100:.3f}% > 0.1%"

    # Track consecutive unverified quote sessions and warn after 3 consecutive days
    quotes_all_verified = (etf_quotes_verified and bond_quotes_verified)
    consecutive_unverified = int(manager.state.get("consecutive_unverified_quote_days", 0))

    if not quotes_all_verified:
        consecutive_unverified += 1
        manager.state["consecutive_unverified_quote_days"] = consecutive_unverified
        if consecutive_unverified >= 3:
            logger.warning(
                f"[ALERT] UNVERIFIED QUOTES PERSISTENCE: Live market quotes have failed verification for "
                f"{consecutive_unverified} consecutive sessions! Relying on unverified fallback prices."
            )
            manager.state["unverified_quotes_warning"] = (
                f"UNVERIFIED_QUOTES_WARNING: {consecutive_unverified} consecutive sessions with unverified fallback quotes"
            )
    else:
        manager.state["consecutive_unverified_quote_days"] = 0
        manager.state["unverified_quotes_warning"] = None

    manager._save_state()

    status = manager.get_status()

    session_date = etf_state.get("last_bar_date") or (bond_state.get("last_bar_date") if bond_state else None) or current_time.strftime("%Y-%m-%d")

    # 6. Append to Manager Equity Log (with canonical schema migration & alignment guard)
    log_entry = {
        "date": current_time.strftime("%Y-%m-%d %H:%M:%S"),
        "session_date": str(session_date),
        "total_portfolio_value": round(nav_metrics["total_portfolio_value"], 2),
        "primary_sleeve_nav": independent_nav,
        "reserve_sleeve_nav": independent_bond_nav,
        "combined_fund_nav": combined_fund_nav,
        "nav_per_unit": round(nav_metrics["nav_per_unit"], 4),
        "true_trading_return_pct": round(nav_metrics["true_trading_return_pct"], 4),
        "current_drawdown_pct": round(status["current_drawdown"] * 100.0, 2),
        "throttle_level": status["throttle_level"],
        "is_halted": status["is_halted"],
        "halt_reason": status["halt_reason"] or "",
        "reconciliation_gap_pct": round(manager.state["last_reconciliation_gap_pct"], 4),
        "share_etf_gold": shares.get("ETF_AND_GOLD", 0.0),
        "share_cash_sleeve": shares.get("CASH_SLEEVE", 0.0),
        "execution_mode": mode
    }

    append_manager_equity_log(equity_log_path, log_entry, session_date=session_date)

    return {
        "timestamp": current_time.isoformat(),
        "policy": policy,
        "mode": mode,
        "shares": shares,
        "status": status,
        "nav_metrics": nav_metrics,
        "independent_nav": independent_nav,
        "reported_nav": reported_nav,
        "combined_fund_nav": combined_fund_nav,
        "sleeves": manager.state["sleeves"],
        "consecutive_unverified_quote_days": manager.state.get("consecutive_unverified_quote_days", 0),
        "unverified_quotes_warning": manager.state.get("unverified_quotes_warning"),
        "quotes_used": quotes_used,
        "max_duration_scale": status.get("max_duration_scale", 1.0),
        "etf_report": {
            "nav": etf_report.nav,
            "stale": etf_report.stale,
            "gate_status": etf_report.gate_status
        },
        "bond_cash_report": {
            "nav": bond_reported_nav,
            "independent_nav": independent_bond_nav,
            "stale": bond_stale,
            "reconciliation_passed": bond_rec_passed,
            "reconciliation_status": bond_rec_status,
            "quotes_verified": bond_quotes_verified
        } if bond_report is not None else None
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
    print(f"Starting Capital : INR {args.capital:,.2f}")
    print("-" * 80)

    res = execute_manager_cycle(policy=args.policy, mode=args.mode, initial_capital=args.capital)

    status = res["status"]
    if status.get("is_data_fault"):
        print(f"[DATA FAULT DETECTED] {status['data_fault_reason']}")
        print("Cycle bypassed safely: Prior manager state retained, ledger unchanged, kill switch avoided.")
        print("=" * 80)
        sys.exit(1)

    metrics = res["nav_metrics"]
    shares = res["shares"]

    p_sleeve = res["sleeves"]["primary_sleeve"]
    r_sleeve = res["sleeves"]["reserve_sleeve"]

    print(f"Primary Sleeve (ETF & Gold)   : Reported INR {p_sleeve['reported_nav']:,.2f} | Indep INR {p_sleeve['independent_nav']:,.2f} | Gap: {p_sleeve['reconciliation_gap_pct']:.4f}% ({p_sleeve['reconciliation_status']})")
    print(f"Reserve Sleeve (Bond & Cash)  : Reported INR {r_sleeve['reported_nav']:,.2f} | Indep INR {r_sleeve['independent_nav']:,.2f} | Gap: {r_sleeve['reconciliation_gap_pct']:.4f}% ({r_sleeve['reconciliation_status']})")
    print(f"Combined Multi-Bot Fund NAV   : INR {res['combined_fund_nav']:,.2f} (Target: INR 100,000.00)")
    print(f"Primary Unitized NAV (Active) : INR {metrics['nav_per_unit']:.4f} (Base: 100.0000 | Drawdown: {status['current_drawdown'] * 100.0:.2f}%)")
    print(f"Worst Reconciliation Gap      : {status['last_reconciliation_gap_pct']:.4f}% (Max Permissible: {RECONCILIATION_MAX_GAP * 100.0:.1f}%)")
    if res.get("consecutive_unverified_quote_days", 0) >= 3:
        print(f"[PERSISTENCE WARNING] Live quotes unverified for {res['consecutive_unverified_quote_days']} consecutive sessions! Review yfinance/broker data feed.")
    print(f"Trading Halted                : {'YES - ' + str(status['halt_reason']) if status['is_halted'] else 'NO (Normal Operations)'}")
    print(f"Risk Throttle Level           : {status['throttle_level']} (0: Normal, 1: -15%, 2: -30%, 3: -40% Kill)")
    print(f"Max Duration Scale            : {status.get('max_duration_scale', 1.0):.2f} (1.0 = Normal, 0.0 = Retreat/Throttled)")
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
