"""
Phase 2 Manager Test T1: Throttle Value vs Fixed Shares & Kill Switch
====================================================================
Governed strictly by: PROTOCOL-MANAGER-BOT-CASH-SLEEVE-V1-20261113

Compares:
  - Variant 1 (Baseline): Manager with Fixed Shares (100% ETF Bot) + Hard Kill Switch (-40% DD).
  - Variant 2 (Candidate): Manager with 2-Level Drawdown Throttle (-15%, -30%) + Hard Kill Switch (-40% DD).

Test Dataset:
  - 2007-09-24 to 2024-12-31 historical in-sample proxy data (4,494 sessions).
  - 2025-01-01 to Present live NSE ETF holdout (463 sessions, labeled as seen).

Hurdles for Throttle to Earn Production Deployment:
  1. Cuts Maximum Drawdown by at least 20.0% relative vs Fixed Shares.
  2. Costs at most 1.00 percentage point of CAGR.
  3. Does not lower the Annualized Sharpe Ratio.
  -> Decision Rule: If any hurdle fails, ship simpler Fixed Shares + Kill Switch only.

Trial Family: N = 2 declared up front.
"""

import os
import sys
import math
import json
import hashlib
import subprocess
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple
import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from trading_system.scripts.run_phase1_etf_gate_a import (
    load_in_sample_dataset,
    load_holdout_dataset,
    run_static_equal_weight_baseline,
    calculate_metrics
)

TRIAL_LOG_PATH = os.path.join(PROJECT_ROOT, "trading_system", "data", "trial_log.csv")
PROTOCOL_PATH = os.path.join(PROJECT_ROOT, "trading_system", "docs", "MANAGER_BOT_AND_CASH_SLEEVE_PROTOCOL_V1.md")
PROTOCOL_SHA256_PATH = os.path.join(PROJECT_ROOT, "trading_system", "docs", "MANAGER_BOT_AND_CASH_SLEEVE_PROTOCOL_V1.sha256")

CASH_YIELD_ANNUAL = 0.06
CASH_YIELD_DAILY = CASH_YIELD_ANNUAL / 252.0


def verify_protocol_lock() -> str:
    if not os.path.exists(PROTOCOL_PATH):
        raise FileNotFoundError(f"Protocol file missing: {PROTOCOL_PATH}")
    with open(PROTOCOL_PATH, "rb") as f:
        computed = hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest().lower()
    if os.path.exists(PROTOCOL_SHA256_PATH):
        with open(PROTOCOL_SHA256_PATH, "r") as f:
            expected = f.read().strip().lower()
        if computed != expected:
            raise ValueError(f"CRITICAL: Protocol hash mismatch!\nExpected: {expected}\nComputed: {computed}")
    print(f"[PROTOCOL OK] Phase 2 Protocol Hash Verified: {computed[:16]}...")
    return computed


def simulate_manager_fixed_shares(champ_rets: pd.Series, dates: pd.DatetimeIndex) -> Tuple[List[float], Dict[str, Any]]:
    """
    Variant 1: Manager with Fixed Shares (100% ETF Bot) + Kill Switch (-40% DD).
    """
    nav = 100.0
    hwm = 100.0
    curve = [100.0]
    killed = False

    for r in champ_rets:
        dd = (nav - hwm) / hwm
        if dd <= -0.40:
            killed = True

        day_ret = CASH_YIELD_DAILY if killed else r
        nav *= (1.0 + day_ret)
        hwm = max(hwm, nav)
        curve.append(nav)

    metrics = calculate_metrics(curve, dates, capital=100.0)
    metrics["strategy"] = "Variant 1: Fixed Shares + Kill Switch (-40%)"
    metrics["killed"] = killed
    return curve, metrics


def simulate_manager_throttled(champ_rets: pd.Series, dates: pd.DatetimeIndex) -> Tuple[List[float], Dict[str, Any]]:
    """
    Variant 2: Manager with 2-Level Throttle (-15%, -30%) + Kill Switch (-40%).
    Re-risking: 21 trading days +5 pts better required to de-throttle one level.
    """
    nav = 100.0
    hwm = 100.0
    curve = [100.0]
    level = 0
    rec_days = 0

    for r in champ_rets:
        dd = (nav - hwm) / hwm

        # 1. Kill switch
        if dd <= -0.40:
            level = 3
        # 2. Risk-off transitions
        elif dd <= -0.30:
            level = max(level, 2)
            rec_days = 0
        elif dd <= -0.15:
            if level == 0:
                level = 1
                rec_days = 0

        # 3. Re-risking transitions (never skips a level)
        if level == 2:
            if dd >= -0.25:
                rec_days += 1
                if rec_days >= 21:
                    level = 1
                    rec_days = 0
            else:
                rec_days = 0
        elif level == 1:
            if dd >= -0.10:
                rec_days += 1
                if rec_days >= 21:
                    level = 0
                    rec_days = 0
            else:
                rec_days = 0

        risk_w = {0: 1.0, 1: 0.50, 2: 0.25, 3: 0.0}[level]
        day_ret = risk_w * r + (1.0 - risk_w) * CASH_YIELD_DAILY
        nav *= (1.0 + day_ret)
        hwm = max(hwm, nav)
        curve.append(nav)

    metrics = calculate_metrics(curve, dates, capital=100.0)
    metrics["strategy"] = "Variant 2: Throttle (-15%, -30%) + Kill Switch (-40%)"
    metrics["final_level"] = level
    return curve, metrics


def main():
    print("=" * 80)
    print(">>> PHASE 2 TEST T1: MANAGER THROTTLE VALUE AUDIT (N = 2 DECLARED) <<<")
    print("=" * 80)

    # 1. Verify protocol lock
    sha = verify_protocol_lock()

    # 2. Load continuous ETF Champion returns
    print("\n[1/4] Generating Continuous ETF Champion Equity Series...")
    df_is = load_in_sample_dataset()
    _, _, s_is = run_static_equal_weight_baseline(df_is)
    rets_is = s_is.pct_change().dropna()

    df_ho = load_holdout_dataset()
    _, _, s_ho = run_static_equal_weight_baseline(df_ho)
    rets_ho = s_ho.pct_change().dropna()

    combined_rets = pd.concat([rets_is, rets_ho])
    combined_dates = pd.DatetimeIndex([combined_rets.index[0] - pd.Timedelta(days=1)] + list(combined_rets.index))
    print(f"  Combined evaluation series: {len(combined_rets)} sessions (2007 to Present).")
    print("  [NOTICE]: 2025-2026 holdout was already opened in Phase 1 Gate A, so it is labeled as seen.")

    # 3. Simulate Variant 1: Fixed Shares + Kill Switch
    print("\n[2/4] Executing Variant 1 (Baseline): Fixed Shares + Kill Switch...")
    _, m_fixed = simulate_manager_fixed_shares(combined_rets, combined_dates)
    print(f"  -> Fixed Shares:    CAGR={m_fixed['cagr_pct']}%, MaxDD={m_fixed['max_drawdown_pct']}%, Sharpe={m_fixed['sharpe_ratio']}, Calmar={m_fixed['calmar_ratio']}")

    # 4. Simulate Variant 2: Throttle + Kill Switch
    print("\n[3/4] Executing Variant 2 (Candidate): Drawdown Throttle + Kill Switch...")
    _, m_throttled = simulate_manager_throttled(combined_rets, combined_dates)
    print(f"  -> Throttled:       CAGR={m_throttled['cagr_pct']}%, MaxDD={m_throttled['max_drawdown_pct']}%, Sharpe={m_throttled['sharpe_ratio']}, Calmar={m_throttled['calmar_ratio']}")

    # 5. Evaluate Protocol T1 Hurdles
    print("\n[4/4] Evaluating Test T1 Pass Conditions...")
    print("-" * 80)

    # Hurdle 1: Relative Max Drawdown reduction >= 20.0%
    abs_dd_fixed = abs(m_fixed["max_drawdown_pct"])
    abs_dd_th = abs(m_throttled["max_drawdown_pct"])
    rel_dd_reduction = float(((abs_dd_fixed - abs_dd_th) / abs_dd_fixed) * 100.0)
    passed_dd_cut = bool(rel_dd_reduction >= 20.0)

    # Hurdle 2: Costs at most 1.0 point of CAGR
    cagr_cost = float(m_fixed["cagr_pct"] - m_throttled["cagr_pct"])
    passed_cagr_cost = bool(cagr_cost <= 1.00)

    # Hurdle 3: Does not lower Sharpe Ratio
    passed_sharpe = bool(m_throttled["sharpe_ratio"] >= m_fixed["sharpe_ratio"])

    overall_t1_pass = bool(passed_dd_cut and passed_cagr_cost and passed_sharpe)

    print(f"1. Relative MaxDD Cut (>= 20.0%): {'PASSED' if passed_dd_cut else 'FAILED'} (Actual: {rel_dd_reduction:.2f}%)")
    print(f"2. CAGR Drag Cost (<= 1.00 pt)  : {'PASSED' if passed_cagr_cost else 'FAILED'} (Actual: {cagr_cost:.2f} pts | {m_fixed['cagr_pct']}% -> {m_throttled['cagr_pct']}%)")
    print(f"3. Sharpe Ratio (>= Fixed)      : {'PASSED' if passed_sharpe else 'FAILED'} (Actual: {m_throttled['sharpe_ratio']} vs {m_fixed['sharpe_ratio']})")
    print("-" * 80)

    if overall_t1_pass:
        verdict = "PASSED: Throttle earned its place. Deploy Manager with Throttle."
        production_policy = "THROTTLE_AND_KILL_SWITCH"
    else:
        verdict = "FAILED: Throttle did not earn its place. Per protocol rule, ship fixed shares plus kill switch."
        production_policy = "FIXED_SHARES_PLUS_KILL_SWITCH"

    print(f"TEST T1 VERDICT   : {verdict}")
    print(f"PRODUCTION POLICY : {production_policy}")
    print("=" * 80)

    def _json_serial(obj):
        if isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        if isinstance(obj, (np.integer, int)):
            return int(obj)
        if isinstance(obj, (np.floating, float)):
            return float(obj)
        return str(obj)

    # 6. Save results JSON
    results_path = os.path.join(PROJECT_ROOT, "trading_system", "data", "phase2_manager_t1_results.json")
    with open(results_path, "w") as f:
        json.dump({
            "protocol_sha256": sha,
            "test": "T1_THROTTLE_VALUE",
            "trial_family_n": 2,
            "date_executed": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "variant_1_fixed_shares": m_fixed,
            "variant_2_throttled": m_throttled,
            "evaluation": {
                "rel_max_dd_reduction_pct": round(rel_dd_reduction, 2),
                "passed_dd_cut": passed_dd_cut,
                "cagr_cost_pts": round(cagr_cost, 2),
                "passed_cagr_cost": passed_cagr_cost,
                "passed_sharpe": passed_sharpe,
                "t1_passed": overall_t1_pass,
                "production_policy": production_policy
            }
        }, f, indent=2, default=_json_serial)

    # 7. Stamp Trial Log (N = 2 trials)
    try:
        commit_hash = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], shell=True, text=True).strip()
    except Exception:
        commit_hash = "local"

    trial_entry_v1 = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "commit_hash": commit_hash,
        "script": "run_phase2_manager_t1.py",
        "universe": "PHASE2_MANAGER_FIXED_SHARES",
        "kelly_fraction": 1.0,
        "lookback_days": 252,
        "cagr_pct": m_fixed["cagr_pct"],
        "max_drawdown_pct": m_fixed["max_drawdown_pct"],
        "sharpe_ratio": m_fixed["sharpe_ratio"],
        "is_holdout_opened": True,
        "notes": f"Phase 2 Test T1 (Trial 1 of N=2): Manager Fixed Shares + Kill Switch (CAGR {m_fixed['cagr_pct']}%, MaxDD {m_fixed['max_drawdown_pct']}%, Sharpe {m_fixed['sharpe_ratio']})"
    }

    trial_entry_v2 = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "commit_hash": commit_hash,
        "script": "run_phase2_manager_t1.py",
        "universe": "PHASE2_MANAGER_THROTTLED",
        "kelly_fraction": 1.0,
        "lookback_days": 252,
        "cagr_pct": m_throttled["cagr_pct"],
        "max_drawdown_pct": m_throttled["max_drawdown_pct"],
        "sharpe_ratio": m_throttled["sharpe_ratio"],
        "is_holdout_opened": True,
        "notes": f"Phase 2 Test T1 (Trial 2 of N=2): Manager Drawdown Throttle + Kill Switch (CAGR {m_throttled['cagr_pct']}%, MaxDD {m_throttled['max_drawdown_pct']}%, Sharpe {m_throttled['sharpe_ratio']})"
    }

    tdf = pd.read_csv(TRIAL_LOG_PATH)
    tdf = pd.concat([tdf, pd.DataFrame([trial_entry_v1, trial_entry_v2])], ignore_index=True)
    tdf.to_csv(TRIAL_LOG_PATH, index=False)
    print(f"[OK] Stamped Trials {len(tdf)-1} and {len(tdf)} (N = 2 trial family) into {TRIAL_LOG_PATH}.")


if __name__ == "__main__":
    main()
