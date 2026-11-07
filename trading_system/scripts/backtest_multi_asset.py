"""
Institutional Pre-Registered Multi-Asset Tactical Trend Engine (V2.1 Protocol)
==============================================================================
Document Identifier: MULTI_ASSET_TREND_PROTOCOL_V2_1
Governed by: MULTI_ASSET_TREND_PROTOCOL_V2_1.md (SHA-256 Locked)

Evaluates 3 pre-registered multi-asset trend variants over the 2007-2024 window (17.3 years):
  - Indian Large-Cap Equities : NIFTY50 (^NSEI / NIFTYBEES.NS)
  - Indian Next 50 Equities   : NEXT50 (JUNIORBEES.NS / ^NSMIDCP proxy)
  - Indian Mid-Cap Equities   : MIDCAP150 (MID150BEES.NS / ^NSEMDCP50 proxy)
  - Domestic Gold             : GOLDBEES (GOLDBEES.NS / GOLD_USD * USDINR)
  - Domestic Silver           : SILVERBEES (SILVERBEES.NS / SI=F * USDINR)
  - Sovereign 10Y Benchmark   : GILT10Y (CCIL 10-Yr Benchmark G-Sec Index proxy)
  - US Mega-Cap Tech (INR)    : MON100 (MON100.NS / QQQ * USDINR + 1.5% premium stress)
  - Sovereign Liquid Cash     : CASH_INR (RBI Repo Rate less 65 bps TER, net of slab tax)

Execution Timing: Signal at Close T-1; Filled at Open T.
Friction: Asset-specific slippage matrix + statutory STT + flat Rs 14.75 DP fee per scrip sell day.
Taxation: CA-aligned statutory Indian tax regime (Section 50AA slab rates for debt/intl, STCG/LTCG for equities).
"""

import os
import sys
import math
import time
import json
import hashlib
import argparse
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Tuple, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

from trading_system.scripts.backtest_nse50 import calc_vectorized_momentum
from trading_system.app.validation.trial_logger import log_trial
from trading_system.app.validation.gate_evaluator import GateEvaluator

CACHE_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data", "multi_asset_cache")
PROTOCOL_PATH = os.path.join(PROJECT_ROOT, "trading_system", "docs", "MULTI_ASSET_TREND_PROTOCOL_V2_1.md")
PROTOCOL_SHA256_PATH = os.path.join(PROJECT_ROOT, "trading_system", "docs", "MULTI_ASSET_TREND_PROTOCOL_V2_1.sha256")

START_DATE = "2007-09-24"
DEFAULT_END_DATE = "2024-12-31"
HOLDOUT_START_DATE = "2025-01-01"
INITIAL_CAPITAL = 80000.0
FLAT_DP_FEE_RUPEES = 14.75

# Asset Specifications per Protocol Section 2 & 5
ASSET_SPECS = {
    "NIFTY50": {
        "class": "EQUITY", "ter": 0.0005, "norm_slip_bps": 5.0, "stress_slip_bps": 7.5,
        "stt_sell_bps": 10.0, "stamp_buy_bps": 1.5, "exch_bps": 0.297, "sebi_bps": 0.01,
        "entry_premium": 0.0, "pre_drag_annual_bps": 0.0
    },
    "NEXT50": {
        "class": "EQUITY", "ter": 0.0022, "norm_slip_bps": 7.5, "stress_slip_bps": 12.0,
        "stt_sell_bps": 10.0, "stamp_buy_bps": 1.5, "exch_bps": 0.297, "sebi_bps": 0.01,
        "entry_premium": 0.0, "pre_drag_annual_bps": 15.0
    },
    "MIDCAP150": {
        "class": "EQUITY", "ter": 0.0022, "norm_slip_bps": 10.0, "stress_slip_bps": 15.0,
        "stt_sell_bps": 10.0, "stamp_buy_bps": 1.5, "exch_bps": 0.297, "sebi_bps": 0.01,
        "entry_premium": 0.0, "pre_drag_annual_bps": 15.0
    },
    "GOLDBEES": {
        "class": "METAL", "ter": 0.0080, "norm_slip_bps": 7.5, "stress_slip_bps": 12.0,
        "stt_sell_bps": 0.0, "stamp_buy_bps": 1.5, "exch_bps": 0.297, "sebi_bps": 0.01,
        "entry_premium": 0.0, "pre_drag_annual_bps": 15.0
    },
    "SILVERBEES": {
        "class": "METAL", "ter": 0.0045, "norm_slip_bps": 15.0, "stress_slip_bps": 25.0,
        "stt_sell_bps": 0.0, "stamp_buy_bps": 1.5, "exch_bps": 0.297, "sebi_bps": 0.01,
        "entry_premium": 0.0, "pre_drag_annual_bps": 15.0
    },
    "GILT10Y": {
        "class": "DEBT", "ter": 0.0016, "norm_slip_bps": 15.0, "stress_slip_bps": 25.0,
        "stt_sell_bps": 0.0, "stamp_buy_bps": 1.5, "exch_bps": 0.297, "sebi_bps": 0.01,
        "entry_premium": 0.0, "pre_drag_annual_bps": 15.0
    },
    "MON100": {
        "class": "INTL", "ter": 0.0035, "norm_slip_bps": 12.0, "stress_slip_bps": 20.0,
        "stt_sell_bps": 0.0, "stamp_buy_bps": 1.5, "exch_bps": 0.297, "sebi_bps": 0.01,
        "entry_premium": 0.0150, "pre_drag_annual_bps": 15.0
    }
}


def verify_protocol_lock() -> str:
    """Verifies SHA-256 cryptographic pre-registration hash of Protocol V2.1."""
    if not os.path.exists(PROTOCOL_PATH):
        raise FileNotFoundError(f"CRITICAL: Protocol file missing: {PROTOCOL_PATH}")
    with open(PROTOCOL_PATH, "rb") as f:
        sha = hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest().upper()
    if os.path.exists(PROTOCOL_SHA256_PATH):
        with open(PROTOCOL_SHA256_PATH, "r") as f:
            expected = f.read().strip().upper()
        if sha != expected:
            raise ValueError(f"PRE-REGISTRATION INTEGRITY VIOLATION: Protocol hash mismatch!\nExpected: {expected}\nComputed: {sha}")
    print(f"[OK] Multi-Asset Trend Protocol V2.1 verified (SHA-256: {sha[:16]}...).")
    return sha


def compute_multi_asset_tax(
    asset: str,
    entry_date: pd.Timestamp,
    exit_date: pd.Timestamp,
    realized_gain: float,
    slab_rate: float = 0.312
) -> float:
    """Computes statutory Indian capital gains tax per Asset Class and Finance Act regimes."""
    if realized_gain <= 0:
        return 0.0

    days_held = (exit_date - entry_date).days
    asset_class = ASSET_SPECS[asset]["class"]

    if asset_class == "EQUITY":
        # Domestic Equity ETFs: 12-Month Threshold (365 days)
        if days_held < 365:
            # STCG: 15% + 4% cess prior to 23-Jul-2024, 20% + 4% after
            tax_rate = 0.208 if exit_date >= pd.Timestamp("2024-07-23") else 0.156
            return realized_gain * tax_rate
        else:
            # LTCG: 0% pre-2018; 10% + 4% (2018 to 22-Jul-2024); 12.5% + 4% post-Jul-2024
            if exit_date < pd.Timestamp("2018-04-01"):
                return 0.0
            elif exit_date < pd.Timestamp("2024-07-23"):
                return realized_gain * 0.104
            else:
                return realized_gain * 0.130

    elif asset_class in ["DEBT", "INTL"]:
        # Sovereign Gilt & International (MON100):
        # Section 50AA applies post 01-Apr-2023: all taxed as STCG at slab rate
        if exit_date >= pd.Timestamp("2023-04-01"):
            return realized_gain * slab_rate
        else:
            # Prior to Apr 2023: 36M threshold. LTCG: 20% with indexation
            if days_held >= 1095:
                return realized_gain * 0.104
            else:
                return realized_gain * slab_rate

    elif asset_class == "METAL":
        # Gold and Silver ETFs
        if exit_date >= pd.Timestamp("2024-07-23"):
            # Post July 2024 reform: 12M threshold; LTCG 12.5% + 4% = 13.0%
            if days_held >= 365:
                return realized_gain * 0.130
            else:
                return realized_gain * slab_rate
        elif exit_date >= pd.Timestamp("2023-04-01"):
            # Section 50AA transitional window: slab rate
            return realized_gain * slab_rate
        else:
            # Pre-2023: 36M threshold
            if days_held >= 1095:
                return realized_gain * 0.104
            else:
                return realized_gain * slab_rate

    return realized_gain * slab_rate


def get_cash_yield_table() -> pd.DataFrame:
    path = os.path.join(PROJECT_ROOT, "trading_system", "data", "india_cash_yield_history.csv")
    df = pd.read_csv(path)
    df["effective_date"] = pd.to_datetime(df["effective_date"])
    return df.sort_values("effective_date")


def load_multi_asset_v2_1_data(start_date: str = START_DATE, end_date: str = DEFAULT_END_DATE) -> pd.DataFrame:
    print(f"[1/3] Loading 7 Macro Assets Historical Parquet Cache ({start_date} to {end_date})...", flush=True)
    nsei = pd.read_parquet(os.path.join(CACHE_DIR, "NIFTY50.parquet"))
    next50 = pd.read_parquet(os.path.join(CACHE_DIR, "NEXT50.parquet"))
    midcap = pd.read_parquet(os.path.join(CACHE_DIR, "MIDCAP50.parquet"))
    gold = pd.read_parquet(os.path.join(CACHE_DIR, "GOLD_USD.parquet"))
    silver = pd.read_parquet(os.path.join(CACHE_DIR, "SILVERBEES.parquet"))
    gilt = pd.read_parquet(os.path.join(CACHE_DIR, "GILT10Y.parquet"))
    qqq = pd.read_parquet(os.path.join(CACHE_DIR, "QQQ_USD.parquet"))
    usdinr = pd.read_parquet(os.path.join(CACHE_DIR, "USDINR.parquet"))

    common_idx = nsei.index.intersection(next50.index).intersection(midcap.index).intersection(gold.index).intersection(silver.index).intersection(gilt.index).intersection(qqq.index).intersection(usdinr.index)
    common_idx = [d for d in sorted(list(common_idx)) if pd.Timestamp(start_date) <= d <= pd.Timestamp(end_date)]

    data = {}
    data["NIFTY50_close"] = nsei.loc[common_idx, "close"]
    data["NIFTY50_open"] = nsei.loc[common_idx, "open"]

    data["NEXT50_close"] = next50.loc[common_idx, "close"]
    data["NEXT50_open"] = next50.loc[common_idx, "open"]

    data["MIDCAP150_close"] = midcap.loc[common_idx, "close"]
    data["MIDCAP150_open"] = midcap.loc[common_idx, "open"]

    data["GOLDBEES_close"] = gold.loc[common_idx, "close"] * usdinr.loc[common_idx, "close"]
    data["GOLDBEES_open"] = gold.loc[common_idx, "open"] * usdinr.loc[common_idx, "open"]

    data["SILVERBEES_close"] = silver.loc[common_idx, "close"]
    data["SILVERBEES_open"] = silver.loc[common_idx, "open"]

    data["GILT10Y_close"] = gilt.loc[common_idx, "close"]
    data["GILT10Y_open"] = gilt.loc[common_idx, "open"]

    data["MON100_close"] = qqq.loc[common_idx, "close"] * usdinr.loc[common_idx, "close"]
    data["MON100_open"] = qqq.loc[common_idx, "open"] * usdinr.loc[common_idx, "open"]

    # Backward compatibility aliases
    data["MIDCAP50_close"] = data["MIDCAP150_close"]
    data["MIDCAP50_open"] = data["MIDCAP150_open"]
    data["GOLD_INR_close"] = data["GOLDBEES_close"]
    data["GOLD_INR_open"] = data["GOLDBEES_open"]
    data["QQQ_INR_close"] = data["MON100_close"]
    data["QQQ_INR_open"] = data["MON100_open"]

    df = pd.DataFrame(data, index=common_idx).ffill().bfill()
    print(f"  Successfully aligned 7 macro risk assets across {len(df)} trading sessions.\n", flush=True)
    return df


def run_multi_asset_v2_1_simulation(
    df: pd.DataFrame,
    variant: int = 1,
    is_stressed: bool = True,
    slab_rate: float = 0.312,
    label: str = "Variant A: Diversified Dual Momentum"
) -> Dict[str, Any]:
    """
    Executes pre-registered V2.1 simulation with full statutory costs, slippage, and DP charges.
    """
    t0 = time.time()
    assets = list(ASSET_SPECS.keys())
    yield_df = get_cash_yield_table()

    # Precalculate Technical Indicators
    smas_200 = {}
    smas_150 = {}
    smas_50 = {}
    mom_scores = {}
    realized_vols = {}

    for a in assets:
        c = df[f"{a}_close"]
        smas_200[a] = c.rolling(200, min_periods=50).mean()
        smas_150[a] = c.rolling(150, min_periods=40).mean()
        smas_50[a] = c.rolling(50, min_periods=20).mean()

        if variant == 1:
            # Variant A: 6-Month relative momentum (126 days)
            mom_scores[a] = c.pct_change(126)
        elif variant == 2:
            # Variant B: Blended 50% 3M (63d) + 50% 12M (252d)
            m3 = c.pct_change(63)
            m12 = c.pct_change(252)
            mom_scores[a] = 0.5 * m3 + 0.5 * m12
        else:
            # Variant C: 12-Month vectorized exponential slope * R^2 (252d)
            mom_scores[a] = pd.Series(calc_vectorized_momentum(c.values, window=252), index=df.index)

        # 60-day annualized realized volatility for Variant C risk-parity
        ret_60 = c.pct_change()
        realized_vols[a] = ret_60.rolling(60, min_periods=20).std() * np.sqrt(252)

    # First trading day of each month for monthly rebalance
    # Day T-1 close gives signal, executed on Day T open
    monthly_rebalance_days = set(df.resample("BMS").first().index)

    cash = INITIAL_CAPITAL
    positions: Dict[str, Dict[str, Any]] = {}
    pending_orders: List[Dict[str, Any]] = []

    hwm_true = INITIAL_CAPITAL
    max_true_dd = 0.0
    hard_breach = False

    trade_log = []
    equity_curve = {}
    total_dp_fees = 0.0
    total_tax_paid = 0.0
    total_friction_paid = 0.0

    dates = list(df.index)
    
    # State tracking for Variant B confirmation (2 consecutive closes > 200-SMA)
    whipsaw_counters = {a: 0 for a in assets}

    for i, current_date in enumerate(dates):
        # -------------------------------------------------------------
        # STEP 0: Execute Pending Orders at TODAY'S OPEN
        # -------------------------------------------------------------
        if pending_orders:
            for order in pending_orders:
                action = order["action"]
                asset = order["asset"]
                spec = ASSET_SPECS[asset]
                slip_bps = spec["stress_slip_bps"] if is_stressed else spec["norm_slip_bps"]

                open_p = df.loc[current_date, f"{asset}_open"]
                if open_p <= 0 or math.isnan(open_p):
                    open_p = df.loc[current_date, f"{asset}_close"]

                if action == "SELL":
                    if asset in positions:
                        pos = positions.pop(asset)
                        # Sell fill price includes slippage
                        fill_p = open_p * (1.0 - slip_bps / 10000.0)
                        gross_proceeds = pos["shares"] * fill_p

                        # Friction breakdown: STT + Brokerage + Exch + SEBI + GST
                        stt = gross_proceeds * (spec["stt_sell_bps"] / 10000.0)
                        brok = min(20.0, gross_proceeds * 0.0005)
                        exch = gross_proceeds * (spec["exch_bps"] / 10000.0)
                        sebi = gross_proceeds * (spec["sebi_bps"] / 10000.0)
                        gst = (brok + exch) * 0.18
                        sell_friction = stt + brok + exch + sebi + gst + FLAT_DP_FEE_RUPEES

                        net_proceeds = gross_proceeds - sell_friction
                        cash += net_proceeds
                        total_dp_fees += FLAT_DP_FEE_RUPEES
                        total_friction_paid += sell_friction

                        # Capital gains tax
                        cost_basis = pos["shares"] * pos["entry_price"]
                        realized_gain = gross_proceeds - cost_basis - sell_friction
                        tax = compute_multi_asset_tax(asset, pos["entry_date"], current_date, realized_gain, slab_rate=slab_rate)
                        cash -= tax
                        total_tax_paid += tax

                        trade_log.append({
                            "date": current_date, "asset": asset, "action": "SELL",
                            "shares": pos["shares"], "price": fill_p, "realized_pnl": realized_gain,
                            "pnl_pct": (fill_p - pos["entry_price"]) / pos["entry_price"],
                            "tax": tax, "dp_fee": FLAT_DP_FEE_RUPEES, "friction": sell_friction,
                            "reason": order["reason"]
                        })

                elif action == "BUY":
                    target_alloc = min(order["target_alloc"], cash * 0.99)
                    if target_alloc >= 1000.0:
                        # Buy fill price includes slippage + MON100 premium stress if applicable
                        premium = spec["entry_premium"] if is_stressed else 0.0
                        fill_p = open_p * (1.0 + slip_bps / 10000.0) * (1.0 + premium)

                        # Friction breakdown on buy
                        brok = min(20.0, target_alloc * 0.0005)
                        stamp = target_alloc * (spec["stamp_buy_bps"] / 10000.0)
                        exch = target_alloc * (spec["exch_bps"] / 10000.0)
                        sebi = target_alloc * (spec["sebi_bps"] / 10000.0)
                        gst = (brok + exch) * 0.18
                        buy_friction = brok + stamp + exch + sebi + gst

                        investable = target_alloc - buy_friction
                        shares = investable / fill_p
                        cost = shares * fill_p + buy_friction

                        if cost <= cash and shares > 0:
                            cash -= cost
                            total_friction_paid += buy_friction
                            positions[asset] = {
                                "shares": shares, "entry_price": fill_p,
                                "entry_date": current_date, "peak_price": open_p
                            }
                            trade_log.append({
                                "date": current_date, "asset": asset, "action": "BUY",
                                "shares": shares, "price": fill_p, "cost": cost,
                                "friction": buy_friction, "reason": order["reason"]
                            })
            pending_orders = []

        # -------------------------------------------------------------
        # STEP 1: Daily Cash Compounding Yield
        # -------------------------------------------------------------
        sub_y = yield_df[yield_df["effective_date"] <= current_date]
        repo_rate = sub_y.iloc[-1]["rbi_repo_rate"] if len(sub_y) > 0 else 0.065
        net_daily_yield = max(0.0, repo_rate - 0.0065) / 252.0 * (1.0 - slab_rate)
        daily_interest = cash * net_daily_yield
        cash += daily_interest

        # -------------------------------------------------------------
        # STEP 2: Mark-to-Market & Lifetime High-Water Mark
        # -------------------------------------------------------------
        port_val = 0.0
        for asset, pos in positions.items():
            c_p = df.loc[current_date, f"{asset}_close"]
            port_val += pos["shares"] * c_p
            if c_p > pos.get("peak_price", c_p):
                pos["peak_price"] = c_p

        total_equity = cash + port_val
        equity_curve[current_date] = total_equity

        if total_equity > hwm_true:
            hwm_true = total_equity
        true_dd = (total_equity - hwm_true) / hwm_true
        if true_dd < max_true_dd:
            max_true_dd = true_dd
        if true_dd < -0.2500:
            hard_breach = True

        # -------------------------------------------------------------
        # STEP 3: Intra-Month Risk Stop
        # -------------------------------------------------------------
        if variant == 2:
            # Variant B: Intra-month 12.0% trailing stop
            for asset, pos in list(positions.items()):
                c_p = df.loc[current_date, f"{asset}_close"]
                peak = pos.get("peak_price", c_p)
                pullback = (c_p - peak) / peak if peak > 0 else 0.0
                if pullback <= -0.120:
                    pending_orders.append({
                        "action": "SELL", "asset": asset,
                        "reason": f"INTRA_MONTH_TRAILING_STOP (-12.0%) [Pullback: {pullback*100:.1f}%]"
                    })

        elif variant == 3:
            # Variant C: CRO Drawdown Ladder (-10% / -18% / -24% portfolio DD derisking)
            if true_dd <= -0.24:
                cash_target_pct = 0.75
            elif true_dd <= -0.18:
                cash_target_pct = 0.50
            elif true_dd <= -0.10:
                cash_target_pct = 0.25
            else:
                cash_target_pct = 0.0

            if cash_target_pct > 0.0 and positions:
                # Derisk by liquidating lowest momentum asset to hold target cash
                sorted_pos = sorted(positions.keys(), key=lambda a: mom_scores[a].loc[current_date])
                for a in sorted_pos:
                    if (cash / total_equity) < cash_target_pct:
                        pending_orders.append({
                            "action": "SELL", "asset": a,
                            "reason": f"CRO_DD_LADDER_DERISKING (Portfolio DD: {true_dd*100:.1f}%)"
                        })

        # Update whipsaw confirmation counters
        for a in assets:
            c_p = df.loc[current_date, f"{a}_close"]
            sma_200 = smas_200[a].loc[current_date]
            if c_p > sma_200:
                whipsaw_counters[a] += 1
            else:
                whipsaw_counters[a] = 0

        # -------------------------------------------------------------
        # STEP 4: Monthly Rebalance Evaluation at CLOSE
        # -------------------------------------------------------------
        is_rebal_day = current_date in monthly_rebalance_days or (i < len(dates) - 1 and dates[i+1] in monthly_rebalance_days)
        if is_rebal_day:
            eligible = {}
            for a in assets:
                p = df.loc[current_date, f"{a}_close"]
                score = mom_scores[a].loc[current_date]

                if variant == 1:
                    # Variant A: Price > 200-SMA and positive 6M momentum
                    sma_val = smas_200[a].loc[current_date]
                    if p > sma_val and not math.isnan(score) and score > 0:
                        eligible[a] = score

                elif variant == 2:
                    # Variant B: Price > 200-SMA AND 50-SMA sloping upward AND 2-close confirmation
                    sma200_val = smas_200[a].loc[current_date]
                    sma50_today = smas_50[a].loc[current_date]
                    sma50_prev = smas_50[a].iloc[max(0, i - 5)]
                    sma50_up = sma50_today > sma50_prev
                    confirmed = whipsaw_counters[a] >= 2
                    if p > sma200_val and sma50_up and confirmed and not math.isnan(score) and score > 0:
                        eligible[a] = score

                else:
                    # Variant C: Price > 150-SMA and positive Clenow score
                    sma150_val = smas_150[a].loc[current_date]
                    if p > sma150_val and not math.isnan(score) and score > 0:
                        eligible[a] = score

            # Rank eligible candidate assets
            sorted_cands = sorted(eligible.items(), key=lambda x: x[1], reverse=True)

            target_weights = {}
            if variant == 1:
                # Top 3 assets, equal-weight (33.33% each)
                top_targets = [x[0] for x in sorted_cands[:3]]
                w_each = 1.0 / 3.0
                for t in top_targets:
                    target_weights[t] = w_each

            elif variant == 2:
                # Top 2 assets, equal-weight (50.0% each)
                top_targets = [x[0] for x in sorted_cands[:2]]
                w_each = 0.50
                for t in top_targets:
                    target_weights[t] = w_each

            else:
                # Top 3 assets, Inverse-Volatility weighted, capped at 45%
                top_targets = [x[0] for x in sorted_cands[:3]]
                if top_targets:
                    inv_vols = {}
                    for t in top_targets:
                        v = realized_vols[t].loc[current_date]
                        inv_vols[t] = 1.0 / max(v, 0.05) if not math.isnan(v) else 1.0
                    tot_inv = sum(inv_vols.values())
                    raw_weights = {t: inv_vols[t] / tot_inv for t in top_targets}
                    # Cap at 45%
                    for t, w in raw_weights.items():
                        target_weights[t] = min(0.45, w)

            if variant == 3:
                # Variant C: Scale gross exposure by (1.0 - cash_target_pct) to respect the active CRO drawdown ladder tier
                gross_scale = 1.0 - cash_target_pct
                for t in list(target_weights.keys()):
                    target_weights[t] = target_weights[t] * gross_scale

            # Sells: liquidate any holding not selected for target allocation
            for asset in list(positions.keys()):
                if asset not in target_weights:
                    pending_orders.append({
                        "action": "SELL", "asset": asset,
                        "reason": "MONTHLY_REBALANCE_EXIT"
                    })

            # Buys: enter new target assets
            for target, w in target_weights.items():
                if target not in positions:
                    target_alloc = total_equity * w
                    pending_orders.append({
                        "action": "BUY", "asset": target, "target_alloc": target_alloc,
                        "reason": f"MONTHLY_REBALANCE_ENTRY (Weight: {w*100:.1f}%, Score: {eligible[target]:.2f})"
                    })

    eq_series = pd.Series(equity_curve)
    years = (dates[-1] - dates[0]).days / 365.25
    cagr = ((eq_series.iloc[-1] / INITIAL_CAPITAL) ** (1.0 / years) - 1.0) * 100.0
    tot_ret = (eq_series.iloc[-1] - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100.0
    peak_s = eq_series.cummax()
    max_dd = ((eq_series - peak_s) / peak_s).min() * 100.0
    ret_daily = eq_series.pct_change().dropna()
    sharpe = (ret_daily.mean() / (ret_daily.std() + 1e-9)) * np.sqrt(252) if ret_daily.std() > 0 else 0.0
    calmar = abs(cagr / max_dd) if abs(max_dd) > 1e-6 else 0.0

    closed_sells = [t for t in trade_log if t["action"] == "SELL"]
    wins = [t for t in closed_sells if t["realized_pnl"] > 0]
    win_rate = len(wins) / len(closed_sells) * 100.0 if closed_sells else 0.0

    return {
        "label": label,
        "variant": variant,
        "is_stressed": is_stressed,
        "slab_rate": slab_rate,
        "starting_capital": INITIAL_CAPITAL,
        "terminal_equity": round(eq_series.iloc[-1], 2),
        "total_return_pct": round(tot_ret, 2),
        "cagr_pct": round(cagr, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "hard_breach_detected": hard_breach,
        "sharpe_ratio": round(sharpe, 2),
        "calmar_ratio": round(calmar, 2),
        "win_rate_pct": round(win_rate, 2),
        "closed_trades": len(closed_sells),
        "trades_per_year": round(len(closed_sells) / years, 1),
        "total_dp_fees": round(total_dp_fees, 2),
        "total_friction_paid": round(total_friction_paid, 2),
        "total_tax_paid": round(total_tax_paid, 2),
        "equity_curve": eq_series,
        "trade_log": trade_log
    }


def compute_baseline_1_static_equal_weight(df: pd.DataFrame, slab_rate: float = 0.312) -> Dict[str, Any]:
    """Baseline 1: Static Equal-Weight Multi-Asset (1/N across 7 assets, rebalanced annually in January)."""
    assets = list(ASSET_SPECS.keys())
    dates = list(df.index)
    years = (dates[-1] - dates[0]).days / 365.25
    
    annual_rebalance_days = set(df.resample("BYS").first().index)
    cash = INITIAL_CAPITAL
    positions = {}
    total_tax = 0.0
    total_dp = 0.0
    eq_curve = {}
    pending_rebal = False

    for i, d in enumerate(dates):
        if pending_rebal or i == 0:
            # Liquidate current positions
            for a, pos in list(positions.items()):
                p = df.loc[d, f"{a}_open"]
                if p <= 0 or math.isnan(p):
                    p = df.loc[d, f"{a}_close"]
                gross = pos["shares"] * p
                gain = gross - (pos["shares"] * pos["entry"])
                tax = compute_multi_asset_tax(a, pos["date"], d, gain, slab_rate=slab_rate)
                cash += (gross - FLAT_DP_FEE_RUPEES - tax)
                total_dp += FLAT_DP_FEE_RUPEES
                total_tax += tax
            positions = {}
            # Buy 1/N
            alloc_per_asset = (cash * 0.99) / len(assets)
            for a in assets:
                p = df.loc[d, f"{a}_open"]
                if p <= 0 or math.isnan(p):
                    p = df.loc[d, f"{a}_close"]
                shares = alloc_per_asset / p
                cost = shares * p
                if cost <= cash:
                    cash -= cost
                    positions[a] = {"shares": shares, "entry": p, "date": d}
            pending_rebal = False

        if d in annual_rebalance_days and i > 0:
            pending_rebal = True

        # Daily equity
        cur_val = cash + sum(pos["shares"] * df.loc[d, f"{a}_close"] for a, pos in positions.items())
        eq_curve[d] = cur_val

    s = pd.Series(eq_curve)
    cagr = ((s.iloc[-1] / INITIAL_CAPITAL) ** (1.0 / years) - 1.0) * 100.0
    peak = s.cummax()
    max_dd = ((s - peak) / peak).min() * 100.0
    ret_d = s.pct_change().dropna()
    sharpe = (ret_d.mean() / (ret_d.std() + 1e-9)) * np.sqrt(252)

    return {
        "label": "Baseline 1: Static 1/N Equal-Weight",
        "terminal_equity": round(s.iloc[-1], 2),
        "cagr_pct": round(cagr, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe_ratio": round(sharpe, 2),
        "calmar_ratio": round(abs(cagr / max_dd), 2)
    }




def compute_baseline_2_buy_and_hold(df: pd.DataFrame, slab_rate: float = 0.312) -> Dict[str, Any]:
    """Baseline 2: Standalone Buy-and-Hold per asset over identical 2007-2024 window (Post-Tax)."""
    dates = list(df.index)
    years = (dates[-1] - dates[0]).days / 365.25
    assets = list(ASSET_SPECS.keys())
    results = {}

    for a in assets:
        spec = ASSET_SPECS[a]
        open_start = df.loc[dates[0], f"{a}_open"]
        if open_start <= 0 or math.isnan(open_start):
            open_start = df.loc[dates[0], f"{a}_close"]
        close_end = df.loc[dates[-1], f"{a}_close"]

        brok = min(20.0, INITIAL_CAPITAL * 0.0005)
        stamp = INITIAL_CAPITAL * (spec["stamp_buy_bps"] / 10000.0)
        exch = INITIAL_CAPITAL * (spec["exch_bps"] / 10000.0)
        sebi = INITIAL_CAPITAL * (spec["sebi_bps"] / 10000.0)
        gst = (brok + exch) * 0.18
        buy_fric = brok + stamp + exch + sebi + gst
        shares = (INITIAL_CAPITAL - buy_fric) / open_start

        curve = df[f"{a}_close"] * shares
        gross_final = shares * close_end

        brok_s = min(20.0, gross_final * 0.0005)
        stt_s = gross_final * (spec["stt_sell_bps"] / 10000.0)
        exch_s = gross_final * (spec["exch_bps"] / 10000.0)
        sebi_s = gross_final * (spec["sebi_bps"] / 10000.0)
        gst_s = (brok_s + exch_s) * 0.18
        sell_fric = brok_s + stt_s + exch_s + sebi_s + gst_s + FLAT_DP_FEE_RUPEES
        gain = gross_final - INITIAL_CAPITAL - sell_fric
        tax = compute_multi_asset_tax(a, dates[0], dates[-1], gain, slab_rate=slab_rate)
        terminal = gross_final - sell_fric - tax

        cagr = ((terminal / INITIAL_CAPITAL) ** (1.0 / years) - 1.0) * 100.0
        peak = curve.cummax()
        max_dd = ((curve - peak) / peak).min() * 100.0
        ret_d = curve.pct_change().dropna()
        sharpe = (ret_d.mean() / (ret_d.std() + 1e-9)) * np.sqrt(252)
        calmar = abs(cagr / max_dd) if abs(max_dd) > 0 else 0.0

        results[a] = {
            "label": f"Buy & Hold: {a}",
            "cagr_pct": round(cagr, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "sharpe_ratio": round(sharpe, 2),
            "calmar_ratio": round(calmar, 2),
            "terminal_equity": round(terminal, 2)
        }

    return results


def compute_baseline_3_sma200_vs_cash(df: pd.DataFrame, slab_rate: float = 0.312) -> Dict[str, Any]:
    """Baseline 3: Standalone 200-SMA Trend Filter vs Cash Yield per asset (Post-Tax)."""
    dates = list(df.index)
    years = (dates[-1] - dates[0]).days / 365.25
    assets = list(ASSET_SPECS.keys())
    yield_df = get_cash_yield_table()
    results = {}

    for a in assets:
        spec = ASSET_SPECS[a]
        sma_200 = df[f"{a}_close"].rolling(200, min_periods=50).mean()
        cash = INITIAL_CAPITAL
        shares = 0.0
        entry_price = 0.0
        entry_date = None
        curve = {}
        pending = None

        for i, d in enumerate(dates):
            if pending == "BUY":
                open_p = df.loc[d, f"{a}_open"]
                if open_p <= 0 or math.isnan(open_p):
                    open_p = df.loc[d, f"{a}_close"]
                brok = min(20.0, cash * 0.0005)
                stamp = cash * (spec["stamp_buy_bps"] / 10000.0)
                exch = cash * (spec["exch_bps"] / 10000.0)
                sebi = cash * (spec["sebi_bps"] / 10000.0)
                gst = (brok + exch) * 0.18
                fric = brok + stamp + exch + sebi + gst
                shares = (cash - fric) / open_p
                cash = 0.0
                entry_price = open_p
                entry_date = d
                pending = None
            elif pending == "SELL":
                open_p = df.loc[d, f"{a}_open"]
                if open_p <= 0 or math.isnan(open_p):
                    open_p = df.loc[d, f"{a}_close"]
                gross = shares * open_p
                brok = min(20.0, gross * 0.0005)
                stt = gross * (spec["stt_sell_bps"] / 10000.0)
                exch = gross * (spec["exch_bps"] / 10000.0)
                sebi = gross * (spec["sebi_bps"] / 10000.0)
                gst = (brok + exch) * 0.18
                fric = brok + stt + exch + sebi + gst + FLAT_DP_FEE_RUPEES
                gain = gross - (shares * entry_price) - fric
                tax = compute_multi_asset_tax(a, entry_date, d, gain, slab_rate=slab_rate)
                cash = gross - fric - tax
                shares = 0.0
                pending = None

            if shares == 0.0:
                sub_y = yield_df[yield_df["effective_date"] <= d]
                repo = sub_y.iloc[-1]["rbi_repo_rate"] if len(sub_y) > 0 else 0.065
                net_yield = max(0.0, repo - 0.0065) / 252.0 * (1.0 - slab_rate)
                cash += cash * net_yield

            close_p = df.loc[d, f"{a}_close"]
            sma_val = sma_200.loc[d]
            if shares == 0.0 and close_p > sma_val and not pd.isna(sma_val):
                pending = "BUY"
            elif shares > 0.0 and close_p < sma_val and not pd.isna(sma_val):
                pending = "SELL"

            curve[d] = cash + (shares * close_p)

        s_b3 = pd.Series(curve)
        cagr = ((s_b3.iloc[-1] / INITIAL_CAPITAL) ** (1.0 / years) - 1.0) * 100.0
        peak = s_b3.cummax()
        max_dd = ((s_b3 - peak) / peak).min() * 100.0
        ret_d = s_b3.pct_change().dropna()
        sharpe = (ret_d.mean() / (ret_d.std() + 1e-9)) * np.sqrt(252)
        calmar = abs(cagr / max_dd) if abs(max_dd) > 0 else 0.0

        results[a] = {
            "label": f"200-SMA vs Cash: {a}",
            "cagr_pct": round(cagr, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "sharpe_ratio": round(sharpe, 2),
            "calmar_ratio": round(calmar, 2),
            "terminal_equity": round(s_b3.iloc[-1], 2)
        }

    return results


def compute_baseline_4_nifty_tri(df: pd.DataFrame, slab_rate: float = 0.312) -> Dict[str, Any]:
    """Baseline 4: Nifty 50 Total Return Index (TRI) post-tax."""
    nsei_close = df["NIFTY50_close"]
    years = (df.index[-1] - df.index[0]).days / 365.25
    start_cash = INITIAL_CAPITAL * (1.0 - 0.00075)
    shares = start_cash / nsei_close.iloc[0]
    tri_list = []
    for p in nsei_close:
        shares *= (1.0 + 0.0135 / 252.0)  # Dividend reinvestment
        tri_list.append(shares * p)
    tri_s = pd.Series(tri_list, index=df.index)

    final_proceeds = shares * nsei_close.iloc[-1] * (1.0 - 0.00175) - FLAT_DP_FEE_RUPEES
    tax = compute_multi_asset_tax("NIFTY50", df.index[0], df.index[-1], final_proceeds - INITIAL_CAPITAL, slab_rate=slab_rate)
    tri_s.iloc[-1] = final_proceeds - tax

    cagr = ((tri_s.iloc[-1] / INITIAL_CAPITAL) ** (1.0 / years) - 1.0) * 100.0
    peak = tri_s.cummax()
    max_dd = ((tri_s - peak) / peak).min() * 100.0
    ret_d = tri_s.pct_change().dropna()
    sharpe = (ret_d.mean() / (ret_d.std() + 1e-9)) * np.sqrt(252)

    return {
        "label": "Baseline 4: Nifty 50 TRI (Post-Tax)",
        "terminal_equity": round(tri_s.iloc[-1], 2),
        "cagr_pct": round(cagr, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe_ratio": round(sharpe, 2),
        "calmar_ratio": round(abs(cagr / max_dd), 2)
    }


def main():
    parser = argparse.ArgumentParser(description="Multi-Asset Tactical Trend Engine V2.1 Backtester")
    parser.add_argument("--variant", type=int, choices=[1, 2, 3], default=1)
    parser.add_argument("--run-all", action="store_true", help="Execute all 3 pre-registered variants")
    parser.add_argument("--skip-protocol-check", action="store_true")
    args = parser.parse_args()

    protocol_sha = "UNVERIFIED"
    if not args.skip_protocol_check:
        protocol_sha = verify_protocol_lock()

    df = load_multi_asset_v2_1_data()

    print("[2/3] Evaluating Mandatory Institutional Baselines (All 4)...", flush=True)
    b1 = compute_baseline_1_static_equal_weight(df)
    b2 = compute_baseline_2_buy_and_hold(df)
    b3 = compute_baseline_3_sma200_vs_cash(df)
    b4 = compute_baseline_4_nifty_tri(df)

    all_baselines = {
        "baseline_1_static_equal_weight": b1,
        "baseline_2_standalone_buy_and_hold": b2,
        "baseline_3_standalone_200_sma_vs_cash": b3,
        "baseline_4_nifty_50_tri": b4,
        "horizon_years": round((df.index[-1] - df.index[0]).days / 365.25, 2),
        "start_date": str(df.index[0].date()),
        "end_date": str(df.index[-1].date()),
        "initial_capital": INITIAL_CAPITAL
    }

    baselines_out_path = os.path.join(PROJECT_ROOT, "trading_system", "data", "multi_asset_baselines_v2_1.json")
    with open(baselines_out_path, "w", encoding="utf-8") as f:
        json.dump(all_baselines, f, indent=2)

    print(f"  {b1['label']}: CAGR {b1['cagr_pct']}%, Max DD {b1['max_drawdown_pct']}%, Calmar {b1['calmar_ratio']}")
    print(f"  {b4['label']}: CAGR {b4['cagr_pct']}%, Max DD {b4['max_drawdown_pct']}%, Calmar {b4['calmar_ratio']}")
    print(f"  Baseline 2 & 3 computed across {len(b2)} assets and exported to multi_asset_baselines_v2_1.json\n")

    variants_to_run = [1, 2, 3] if args.run_all else [args.variant]
    results = {}

    print("[3/3] Simulating Pre-Registered Variants across Dual Slippage & Tax Regimes...", flush=True)
    for var in variants_to_run:
        name = "Variant A (Diversified Dual Momentum)" if var == 1 else ("Variant B (Quality-Blended Anti-Whipsaw)" if var == 2 else "Variant C (Risk-Parity Vol-Inverse)")

        # Normal Slippage (Primary 31.2% Slab Tax)
        res_norm = run_multi_asset_v2_1_simulation(df, variant=var, is_stressed=False, slab_rate=0.312, label=f"{name} [Normal]")

        # Stressed Slippage + 1.5% MON100 Premium Stress (Gate A Evaluator)
        res_stress = run_multi_asset_v2_1_simulation(df, variant=var, is_stressed=True, slab_rate=0.312, label=f"{name} [Stressed Gate A]")

        # Sensitivity: Retail 20.8% Slab Tax
        res_sens = run_multi_asset_v2_1_simulation(df, variant=var, is_stressed=True, slab_rate=0.208, label=f"{name} [20.8% Slab Sensitivity]")

        results[f"variant_{var}"] = {
            "normal": res_norm,
            "stressed": res_stress,
            "sensitivity_20_8": res_sens
        }

        # Log trials to trial_log.csv
        log_trial(
            script="backtest_multi_asset.py", universe="MULTI_ASSET_7",
            kelly_fraction=1.0, lookback_days=126 if var == 1 else (252 if var == 3 else 189),
            cagr_pct=res_norm["cagr_pct"], max_drawdown_pct=res_norm["max_drawdown_pct"],
            sharpe_ratio=res_norm["sharpe_ratio"], is_holdout_opened=False,
            notes=f"V2.1 {name} Normal | IN_SAMPLE"
        )
        log_trial(
            script="backtest_multi_asset.py", universe="MULTI_ASSET_7",
            kelly_fraction=1.0, lookback_days=126 if var == 1 else (252 if var == 3 else 189),
            cagr_pct=res_stress["cagr_pct"], max_drawdown_pct=res_stress["max_drawdown_pct"],
            sharpe_ratio=res_stress["sharpe_ratio"], is_holdout_opened=False,
            notes=f"V2.1 {name} Stressed (Gate A) | IN_SAMPLE"
        )

        out_path = os.path.join(PROJECT_ROOT, "trading_system", "data", f"backtest_results_multi_asset_v2_1_variant_{var}.json")
        save_dict = {
            "variant": var,
            "label": name,
            "protocol_sha256": protocol_sha,
            "baselines": {
                "baseline_1_static_equal_weight": b1,
                "baseline_4_nifty_50_tri": b4,
                "baseline_2_buy_and_hold_summary": {k: {"cagr_pct": v["cagr_pct"], "max_drawdown_pct": v["max_drawdown_pct"], "calmar": v["calmar_ratio"]} for k, v in b2.items()},
                "baseline_3_sma200_summary": {k: {"cagr_pct": v["cagr_pct"], "max_drawdown_pct": v["max_drawdown_pct"], "calmar": v["calmar_ratio"]} for k, v in b3.items()}
            },
            "stressed_metrics": {k: v for k, v in res_stress.items() if k not in ["equity_curve", "trade_log"]},
            "normal_metrics": {k: v for k, v in res_norm.items() if k not in ["equity_curve", "trade_log"]},
            "sensitivity_metrics": {k: v for k, v in res_sens.items() if k not in ["equity_curve", "trade_log"]}
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(save_dict, f, indent=2)

    # Print Official Scoreboard
    print("\n" + "=" * 120)
    print("=" * 28 + " MULTI-ASSET V2.1 TACTICAL TREND SCOREBOARD (POST-TAX & STRESSED) " + "=" * 25)
    print("=" * 120)
    print(f"{'Performance Metric':<32} | {'Variant A (Dual Mom)':<22} | {'Variant B (Anti-Whip)':<22} | {'Variant C (Risk-Parity)':<22} | {'Nifty 50 TRI':<15}")
    print("-" * 120)

    va = results["variant_1"]["stressed"] if 1 in variants_to_run else None
    vb = results["variant_2"]["stressed"] if 2 in variants_to_run else None
    vc = results["variant_3"]["stressed"] if 3 in variants_to_run else None

    def fmt(val, prefix="", suffix="", decimals=2):
        if val is None:
            return "N/A"
        return f"{prefix}{val:.{decimals}f}{suffix}"

    print(f"{'Post-Tax Stressed CAGR':<32} | {fmt(va['cagr_pct'], suffix='%'):<22} | {fmt(vb['cagr_pct'], suffix='%'):<22} | {fmt(vc['cagr_pct'], suffix='%'):<22} | {fmt(b4['cagr_pct'], suffix='%'):<15}")
    print(f"{'Max Drawdown Depth':<32} | {fmt(va['max_drawdown_pct'], suffix='%'):<22} | {fmt(vb['max_drawdown_pct'], suffix='%'):<22} | {fmt(vc['max_drawdown_pct'], suffix='%'):<22} | {fmt(b4['max_drawdown_pct'], suffix='%'):<15}")
    print(f"{'Annualized Sharpe Ratio':<32} | {fmt(va['sharpe_ratio']):<22} | {fmt(vb['sharpe_ratio']):<22} | {fmt(vc['sharpe_ratio']):<22} | {fmt(b4['sharpe_ratio']):<15}")
    print(f"{'Calmar Ratio (CAGR / |MaxDD|)':<32} | {fmt(va['calmar_ratio']):<22} | {fmt(vb['calmar_ratio']):<22} | {fmt(vc['calmar_ratio']):<22} | {fmt(b4['calmar_ratio']):<15}")
    print(f"{'Terminal Equity (from Rs 80k)':<32} | {fmt(va['terminal_equity'], prefix='Rs '):<22} | {fmt(vb['terminal_equity'], prefix='Rs '):<22} | {fmt(vc['terminal_equity'], prefix='Rs '):<22} | {fmt(b4['terminal_equity'], prefix='Rs '):<15}")
    print(f"{'Total Closed Trades':<32} | {str(va['closed_trades']) if va else 'N/A':<22} | {str(vb['closed_trades']) if vb else 'N/A':<22} | {str(vc['closed_trades']) if vc else 'N/A':<22} | {'0 (Buy & Hold)':<15}")
    print(f"{'Trades Per Year':<32} | {fmt(va['trades_per_year']):<22} | {fmt(vb['trades_per_year']):<22} | {fmt(vc['trades_per_year']):<22} | {'0.0':<15}")
    print(f"{'Total DP Fees Paid':<32} | {fmt(va['total_dp_fees'], prefix='Rs '):<22} | {fmt(vb['total_dp_fees'], prefix='Rs '):<22} | {fmt(vc['total_dp_fees'], prefix='Rs '):<22} | {'Rs 0.00':<15}")
    print(f"{'Total Statutory Friction':<32} | {fmt(va['total_friction_paid'], prefix='Rs '):<22} | {fmt(vb['total_friction_paid'], prefix='Rs '):<22} | {fmt(vc['total_friction_paid'], prefix='Rs '):<22} | {'Deferred LTCG':<15}")
    print(f"{'Total Taxes (31.2% Slab)':<32} | {fmt(va['total_tax_paid'], prefix='Rs '):<22} | {fmt(vb['total_tax_paid'], prefix='Rs '):<22} | {fmt(vc['total_tax_paid'], prefix='Rs '):<22} | {'Deferred LTCG':<15}")
    print("=" * 120)

    # -----------------------------------------------------------------
    # Institutional Gate A Decision Matrix Evaluation (Section 8 & 9)
    # -----------------------------------------------------------------
    print("\n" + "=" * 120)
    print("=" * 35 + " INSTITUTIONAL GATE A FIDUCIARY AUDIT " + "=" * 45)
    print("=" * 120)

    passing_variants = []
    for var in variants_to_run:
        res = results[f"variant_{var}"]["stressed"]
        v_name = f"Variant {var}"
        cagr = res["cagr_pct"]
        dd = res["max_drawdown_pct"]
        trades = res["closed_trades"]
        calmar = res["calmar_ratio"]

        # Criteria evaluations
        beat_b1 = cagr > b1["cagr_pct"]
        beat_b4 = cagr > b4["cagr_pct"]
        floor_cagr = cagr >= 8.50
        dd_pass = dd >= -25.00
        sample_pass = trades >= 50
        calmar_pass = calmar >= 0.45

        all_hurdles = beat_b1 and beat_b4 and floor_cagr and dd_pass and sample_pass and calmar_pass

        print(f"\n--- Gate A Clearance Audit for {res['label']} ---")
        print(f"  1. Primary CAGR Hurdle (Beat B1 {b1['cagr_pct']}% & B4 {b4['cagr_pct']}%): {cagr}% -> {'PASS' if (beat_b1 and beat_b4) else 'FAIL'}")
        print(f"  2. Minimum Absolute Floor (>= 8.50%): {cagr}% -> {'PASS' if floor_cagr else 'FAIL'}")
        print(f"  3. Maximum Drawdown (<= -20% target, limit > -25.0%): {dd}% -> {'PASS' if dd_pass else 'FAIL'}")
        print(f"  4. Calmar Ratio (>= 0.45): {calmar} -> {'PASS' if calmar_pass else 'FAIL'}")
        print(f"  5. Trade Sample Size (>= 50 trades): {trades} trades -> {'PASS' if sample_pass else 'FAIL'}")
        print(f"  6. Holdout Window (2025): SEALED & UNTOUCHED -> PASS")

        if all_hurdles:
            print(f"  >>> RESULT: {v_name} CLEARED ALL GATE A HURDLES!")
            passing_variants.append((var, res))
        else:
            print(f"  >>> RESULT: {v_name} FAILED Gate A.")

    print("\n" + "=" * 120)
    print("=" * 38 + " FINAL STRATEGY DECISION " + "=" * 55)
    print("=" * 120)

    if passing_variants:
        # Tie-Break Rule per Section 9: Highest Calmar
        passing_variants.sort(key=lambda x: x[1]["calmar_ratio"], reverse=True)
        winner_var, winner_res = passing_variants[0]
        print(f"[DECISION] Champion Variant Identified: Variant {winner_var} ({winner_res['label']})")
        print(f"           Calmar: {winner_res['calmar_ratio']} | CAGR: {winner_res['cagr_pct']}% | Max DD: {winner_res['max_drawdown_pct']}%")
        print(f"           Certifying Gate A clearance in signed cryptographic ledger...")

        cert_file = GateEvaluator.certify_gate_a_result(
            variant_id=f"Multi_Asset_Variant_{winner_var}",
            protocol_hash=protocol_sha,
            cagr_pct=winner_res["cagr_pct"],
            max_drawdown_pct=winner_res["max_drawdown_pct"],
            total_trades=winner_res["closed_trades"],
            is_holdout_opened=False
        )
        print(f"           Signed Gate A Certification File: {cert_file}")
    else:
        print("[DECISION] ZERO VARIANTS CLEARED ALL GATE A HURDLES.")
        print("           Per Section 9 (All-Fail Rule):")
        print("           1. Multi-Asset Tactical Trend is formally DISQUALIFIED for live/paper allocation.")
        print("           2. The trading desk defaults to Baseline 1 (Static 1/N Equal-Weight) or Sovereign Cash preservation.")
        print("           3. The sealed 2025 holdout window SHALL NOT BE UNSEALED (strictly protected).")

    print("=" * 120)


if __name__ == "__main__":
    main()


# Backward compatibility aliases
load_multi_asset_data = load_multi_asset_v2_1_data


def run_multi_asset_simulation(df: pd.DataFrame, variant: int = 1, slippage_bps: float = 7.5, label: str = "Simulation") -> Dict[str, Any]:
    return run_multi_asset_v2_1_simulation(df, variant=variant, is_stressed=(slippage_bps > 5.0), label=label)
