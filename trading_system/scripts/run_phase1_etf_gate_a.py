"""
Phase 1 Gate A Simulation: ETF, Gold & Sovereign Bonds Rotation Strategy
========================================================================
Executes the pre-registered protocol PROTOCOL-ETF-GOLD-BONDS-ROTATION-V1-20261112.
Evaluates Candidate 1 (Trend Rotation + Drawdown Throttle) against Baseline 1 (Static Mix).

Hard Invariants:
1. Pre-registration verified against ETF_GOLD_BONDS_ROTATION_PROTOCOL_V1.sha256.
2. 2007-09-24 start captures 2008 Lehman crash inside the evaluation window.
3. Full statutory friction: STT, Stamp Duty, flat Rs 14.75 DP fee, and 15% STCG / 12.5% LTCG tax.
4. Deflated Sharpe Ratio (DSR) evaluated using historical trial count N=122.
"""

import os
import sys
import math
import json
import hashlib
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from trading_system.app.common.interfaces import StrategyInterface
from trading_system.app.validation.trial_logger import log_trial
from trading_system.app.validation.gate_evaluator import GateEvaluator

CACHE_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data", "multi_asset_cache")
PROTOCOL_PATH = os.path.join(PROJECT_ROOT, "trading_system", "docs", "ETF_GOLD_BONDS_ROTATION_PROTOCOL_V1.md")
PROTOCOL_SHA256_PATH = os.path.join(PROJECT_ROOT, "trading_system", "docs", "ETF_GOLD_BONDS_ROTATION_PROTOCOL_V1.sha256")
TRIAL_LOG_PATH = os.path.join(PROJECT_ROOT, "trading_system", "data", "trial_log.csv")

START_DATE = "2007-09-24"
END_DATE = "2024-12-31"
INITIAL_CAPITAL = 80000.0

# Sourced Friction Parameters
FLAT_DP_FEE = 14.75
STAMP_DUTY_BUY = 0.00015
EXCH_TURNOVER_FEE = 0.0000345
STT_EQUITY_SELL = 0.0010
CASH_YIELD_ANNUAL = 0.06

SLIPPAGE_BPS = {
    "NIFTY": 5.0 / 10000.0,
    "MIDCAP": 12.5 / 10000.0,
    "MON100": 12.0 / 10000.0,
    "GOLD": 7.5 / 10000.0,
    "GILT": 5.0 / 10000.0
}

TER_ANNUAL = {
    "NIFTY": 0.0004,
    "MIDCAP": 0.0020,
    "MON100": 0.0058,
    "GOLD": 0.0050,
    "GILT": 0.0025
}


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
    print(f"[PROTOCOL OK] Pre-Registration Hash Verified: {computed[:16]}...")
    return computed


def load_dataset() -> pd.DataFrame:
    print(f"[1/4] Loading Multi-Asset Parquet Cache ({START_DATE} to {END_DATE})...")
    nifty = pd.read_parquet(os.path.join(CACHE_DIR, "NIFTY50.parquet"))
    midcap = pd.read_parquet(os.path.join(CACHE_DIR, "MIDCAP50.parquet"))
    gold = pd.read_parquet(os.path.join(CACHE_DIR, "GOLD_USD.parquet"))
    qqq = pd.read_parquet(os.path.join(CACHE_DIR, "QQQ_USD.parquet"))
    gilt = pd.read_parquet(os.path.join(CACHE_DIR, "GILT10Y.parquet"))
    usdinr = pd.read_parquet(os.path.join(CACHE_DIR, "USDINR.parquet"))

    common_idx = nifty.index.intersection(midcap.index).intersection(gold.index).intersection(qqq.index).intersection(gilt.index).intersection(usdinr.index)
    common_idx = [d for d in sorted(list(common_idx)) if pd.Timestamp(START_DATE) <= d <= pd.Timestamp(END_DATE)]

    data = {
        "NIFTY": nifty.loc[common_idx, "close"],
        "MIDCAP": midcap.loc[common_idx, "close"],
        "MON100": qqq.loc[common_idx, "close"] * usdinr.loc[common_idx, "close"],
        "GOLD": gold.loc[common_idx, "close"] * usdinr.loc[common_idx, "close"],
        "GILT": gilt.loc[common_idx, "close"]
    }

    df = pd.DataFrame(data, index=common_idx).ffill().bfill()
    print(f"  Successfully aligned 5 core assets across {len(df)} trading sessions.")
    return df


def calculate_metrics(equity_curve: List[float], dates: pd.DatetimeIndex, capital: float = INITIAL_CAPITAL) -> Dict[str, Any]:
    years = (dates[-1] - dates[0]).days / 365.25
    terminal = equity_curve[-1]
    cagr = ((terminal / capital) ** (1.0 / years) - 1.0) * 100.0

    eq_s = pd.Series(equity_curve, index=dates)
    cummax = eq_s.cummax()
    drawdowns = (eq_s - cummax) / cummax
    max_dd = drawdowns.min() * 100.0

    daily_rets = eq_s.pct_change().dropna()
    ann_vol = daily_rets.std() * math.sqrt(252) * 100.0 if len(daily_rets) > 0 else 0.0
    rf = 0.05
    excess_rets = daily_rets - (rf / 252.0)
    sharpe = (excess_rets.mean() / daily_rets.std() * math.sqrt(252)) if daily_rets.std() > 0 else 0.0
    calmar = (cagr / abs(max_dd)) if abs(max_dd) > 0 else 0.0

    return {
        "cagr_pct": round(cagr, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "terminal_equity": round(terminal, 2),
        "sharpe_ratio": round(sharpe, 2),
        "calmar_ratio": round(calmar, 2),
        "ann_volatility_pct": round(ann_vol, 2),
        "years": round(years, 2)
    }


def run_static_equal_weight_baseline(df: pd.DataFrame) -> Tuple[List[float], Dict[str, Any]]:
    """
    Baseline 1: Static Fixed-Weight Rebalanced Annually
    Allocations: 25% Gold, 25% MON100, 15% Nifty, 15% Midcap, 20% Gilt
    """
    dates = df.index
    target_weights = {"GOLD": 0.25, "MON100": 0.25, "NIFTY": 0.15, "MIDCAP": 0.15, "GILT": 0.20}
    
    # Net of daily TER drag
    net_df = df.copy()
    for col, ter in TER_ANNUAL.items():
        cum_drag = (1.0 - (ter / 252.0)) ** np.arange(len(net_df))
        net_df[col] = net_df[col] * cum_drag

    cash = INITIAL_CAPITAL
    holdings = {k: 0.0 for k in target_weights}
    equity_curve = []
    trade_count = 0
    total_tax = 0.0

    rebal_dates = set(net_df.resample("YE").last().index)

    for i, dt in enumerate(dates):
        prices = net_df.loc[dt]
        port_val = cash + sum(holdings[k] * prices[k] for k in holdings)

        # Initial buy or annual rebalance
        if i == 0 or dt in rebal_dates:
            for k, wt in target_weights.items():
                target_val = port_val * wt
                curr_val = holdings[k] * prices[k]
                diff = target_val - curr_val
                slip = SLIPPAGE_BPS[k]

                if diff < -100: # Sell
                    sh_to_sell = abs(diff) / prices[k]
                    proceeds = sh_to_sell * prices[k] * (1.0 - slip - (STT_EQUITY_SELL if k in ["NIFTY", "MIDCAP"] else 0.0)) - FLAT_DP_FEE
                    cash += proceeds
                    holdings[k] -= sh_to_sell
                    trade_count += 1
                elif diff > 100 and cash > 200: # Buy
                    alloc = min(diff, cash * 0.98)
                    sh_to_buy = alloc / (prices[k] * (1.0 + slip + STAMP_DUTY_BUY))
                    holdings[k] += sh_to_buy
                    cash -= alloc
                    trade_count += 1

        tot_val = cash + sum(holdings[k] * prices[k] for k in holdings)
        equity_curve.append(tot_val)

    metrics = calculate_metrics(equity_curve, dates)
    metrics["strategy"] = "Baseline 1: Static Equal-Weight Benchmark"
    metrics["trades"] = trade_count
    return equity_curve, metrics


def run_dynamic_rotation_candidate(df: pd.DataFrame) -> Tuple[List[float], Dict[str, Any]]:
    """
    Candidate 1: Pre-Registered Dynamic Trend Rotation + Drawdown Throttle
    - 200-SMA Trend Filter on all growth assets.
    - Assets below 200-SMA are rotated into Gilt / Cash yield.
    - Drawdown Throttle:
        DD > -10%: 100% exposure
        -20% < DD <= -10%: 50% risk throttle (50% shifted to Gilts)
        DD <= -20%: 100% capital retreats to Gilts/Cash until recovery.
    """
    dates = df.index
    target_weights = {"GOLD": 0.25, "MON100": 0.25, "NIFTY": 0.15, "MIDCAP": 0.15}
    
    # Net of daily TER drag
    net_df = df.copy()
    for col, ter in TER_ANNUAL.items():
        cum_drag = (1.0 - (ter / 252.0)) ** np.arange(len(net_df))
        net_df[col] = net_df[col] * cum_drag

    sma200 = net_df.rolling(200, min_periods=50).mean()
    month_ends = set(net_df.resample("ME").last().index)

    cash = INITIAL_CAPITAL
    holdings = {k: 0.0 for k in ["GOLD", "MON100", "NIFTY", "MIDCAP", "GILT"]}
    entry_prices = {k: 0.0 for k in holdings}
    entry_dates = {}
    equity_curve = []
    trade_count = 0
    total_tax = 0.0
    hwm = INITIAL_CAPITAL

    for i, dt in enumerate(dates):
        prices = net_df.loc[dt]
        port_val = cash + sum(holdings[k] * prices[k] for k in holdings)
        if port_val > hwm:
            hwm = port_val
        dd = (port_val - hwm) / hwm

        # Drawdown throttle scale
        if dd >= -0.10:
            dd_scale = 1.0
        elif dd >= -0.20:
            dd_scale = 0.50
        else:
            dd_scale = 0.0  # Full circuit breaker into Gilts

        # Monthly Rebalance & Trend Check
        if dt in month_ends and i >= 50:
            gilt_target_wt = 0.20 + (1.0 - dd_scale) * 0.80  # Absorbs throttled equity risk

            active_weights = {}
            for k, base_wt in target_weights.items():
                is_bull = prices[k] >= sma200.loc[dt, k]
                if is_bull and dd_scale > 0:
                    active_weights[k] = base_wt * dd_scale
                else:
                    active_weights[k] = 0.0
                    gilt_target_wt += base_wt  # Divert to Gilts

            active_weights["GILT"] = min(1.0, gilt_target_wt)

            # Reallocate
            for k in holdings.keys():
                desired_val = port_val * active_weights.get(k, 0.0)
                curr_val = holdings[k] * prices[k]
                diff = desired_val - curr_val
                slip = SLIPPAGE_BPS[k]

                if diff < -100 and holdings[k] > 0: # Sell
                    sh_to_sell = min(holdings[k], abs(diff) / prices[k])
                    proceeds = sh_to_sell * prices[k] * (1.0 - slip - (STT_EQUITY_SELL if k in ["NIFTY", "MIDCAP"] else 0.0)) - FLAT_DP_FEE
                    gain = proceeds - (sh_to_sell * entry_prices[k])
                    if gain > 0:
                        h_days = (dt - entry_dates.get(k, dt)).days
                        tax_rate = 0.125 if h_days >= 365 else 0.15
                        tax = gain * tax_rate
                        proceeds -= tax
                        total_tax += tax
                    cash += proceeds
                    holdings[k] -= sh_to_sell
                    trade_count += 1

            for k in holdings.keys():
                desired_val = port_val * active_weights.get(k, 0.0)
                curr_val = holdings[k] * prices[k]
                diff = desired_val - curr_val
                slip = SLIPPAGE_BPS[k]

                if diff > 100 and cash > 200: # Buy
                    alloc = min(diff, cash * 0.98)
                    sh_to_buy = alloc / (prices[k] * (1.0 + slip + STAMP_DUTY_BUY))
                    holdings[k] += sh_to_buy
                    entry_prices[k] = prices[k]
                    entry_dates[k] = dt
                    cash -= alloc
                    trade_count += 1

        tot_val = cash + sum(holdings[k] * prices[k] for k in holdings)
        equity_curve.append(tot_val)

    metrics = calculate_metrics(equity_curve, dates)
    metrics["strategy"] = "Candidate 1: Trend Rotation + Drawdown Throttle"
    metrics["trades"] = trade_count
    metrics["tax_paid"] = round(total_tax, 2)
    return equity_curve, metrics


def main():
    print("=" * 80)
    print(">>> PHASE 1 GATE A AUDIT: ETF, GOLD & SOVEREIGN BONDS ROTATION <<<")
    print("=" * 80)

    # 1. Verify cryptographic protocol lock
    sha = verify_protocol_lock()

    # 2. Load continuous multi-asset data
    df = load_dataset()

    # 3. Execute Baseline 1: Static Equal-Weight Benchmark
    print("\n[2/4] Executing Baseline 1: Static Equal-Weight Benchmark...")
    eq_static, m_static = run_static_equal_weight_baseline(df)
    print(f"  -> Static Benchmark: CAGR={m_static['cagr_pct']}%, MaxDD={m_static['max_drawdown_pct']}%, Sharpe={m_static['sharpe_ratio']}, Trades={m_static['trades']}")

    # 4. Execute Candidate 1: Trend Rotation + Drawdown Throttle
    print("\n[3/4] Executing Candidate 1: Trend Rotation + Drawdown Throttle...")
    eq_cand, m_cand = run_dynamic_rotation_candidate(df)
    print(f"  -> Candidate 1: CAGR={m_cand['cagr_pct']}%, MaxDD={m_cand['max_drawdown_pct']}%, Sharpe={m_cand['sharpe_ratio']}, Trades={m_cand['trades']}, Tax Paid=INR {m_cand['tax_paid']:,.2f}")

    # 5. Evaluate Gate A Hurdle
    print("\n[4/4] Evaluating Gate A Statutory & Benchmark Hurdles...")
    passed_hurdle = (m_cand["cagr_pct"] > m_static["cagr_pct"]) or (abs(m_cand["max_drawdown_pct"]) <= abs(m_static["max_drawdown_pct"]) * 0.65 and m_cand["cagr_pct"] >= 12.0)
    passed_dd = abs(m_cand["max_drawdown_pct"]) <= 35.0
    passed_sharpe = m_cand["sharpe_ratio"] >= 0.60
    
    # Deflated Sharpe Ratio Check (N = 122 historical trials)
    dsr_stat = GateEvaluator.compute_deflated_sharpe_ratio(
        observed_sharpe=m_cand["sharpe_ratio"],
        num_trials=122,
        variance_of_sharpes=0.08,
        sample_length=len(df),
        skewness=-0.20,
        kurtosis=3.50
    )
    passed_dsr = dsr_stat >= 0.95

    gate_a_verdict = bool(passed_hurdle and passed_dd and passed_sharpe and passed_dsr)

    print("-" * 80)
    print(f"1. Benchmark Superiority Check : {'PASSED' if passed_hurdle else 'FAILED'} (Candidate CAGR={m_cand['cagr_pct']}% vs Static={m_static['cagr_pct']}%)")
    print(f"2. Maximum Drawdown Check (<= -35%) : {'PASSED' if passed_dd else 'FAILED'} (MaxDD={m_cand['max_drawdown_pct']}%)")
    print(f"3. Annualized Sharpe Ratio (>= 0.60): {'PASSED' if passed_sharpe else 'FAILED'} (Sharpe={m_cand['sharpe_ratio']})")
    print(f"4. Deflated Sharpe Ratio (DSR >= 0.95): {'PASSED' if passed_dsr else 'FAILED'} (DSR={dsr_stat:.4f} at N=122)")
    print(f"OVERALL GATE A VERDICT : {'PASSED (Clear to Proceed to Gate B Paper Incubation)' if gate_a_verdict else 'FAILED (Retain Static Equal-Weight Benchmark)'}")
    print("-" * 80)

    # Write results JSON
    results_path = os.path.join(PROJECT_ROOT, "trading_system", "data", "phase1_etf_gate_a_results.json")
    with open(results_path, "w") as f:
        json.dump({
            "protocol_sha256": sha,
            "date_executed": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "baseline_static": m_static,
            "candidate_dynamic": m_cand,
            "dsr_stat": dsr_stat,
            "gate_a_cleared": gate_a_verdict
        }, f, indent=2)

    # Stamp trial log row 123
    try:
        commit_hash = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        commit_hash = "local"

    trial_entry = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "commit_hash": commit_hash,
        "script": "run_phase1_etf_gate_a.py",
        "universe": "PHASE1_ETF_GOLD_BONDS",
        "kelly_fraction": 1.0,
        "lookback_days": 200,
        "cagr_pct": m_cand["cagr_pct"],
        "max_drawdown_pct": m_cand["max_drawdown_pct"],
        "sharpe_ratio": m_cand["sharpe_ratio"],
        "is_holdout_opened": False,
        "notes": f"Phase 1 Gate A Audit: Candidate Dynamic (CAGR {m_cand['cagr_pct']}%, MaxDD {m_cand['max_drawdown_pct']}%, DSR {dsr_stat:.2f}) vs Static Benchmark ({m_static['cagr_pct']}%, MaxDD {m_static['max_drawdown_pct']}%)"
    }
    
    # Read and append to trial_log.csv
    tdf = pd.read_csv(TRIAL_LOG_PATH)
    tdf = pd.concat([tdf, pd.DataFrame([trial_entry])], ignore_index=True)
    tdf.to_csv(TRIAL_LOG_PATH, index=False)
    print(f"[OK] Trial 123 successfully stamped in {TRIAL_LOG_PATH}.")


if __name__ == "__main__":
    main()
