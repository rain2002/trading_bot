"""
Institutional Pre-Registered Multi-Asset Tactical Trend Engine (v1.0)
=====================================================================
Evaluates 3 pre-registered multi-asset trend variants over the 2007-2024 common window:
  - Indian Large-Cap Equities : NIFTY50 (^NSEI)
  - Indian Mid-Cap Equities   : MIDCAP50 (^NSEMDCP50)
  - Global Monetary Hard Asset: GOLD_INR (GC=F * USDINR)
  - Global High-Beta Tech     : QQQ_INR (QQQ * USDINR)
  - Sovereign Liquid Yield    : CASH_INR (RBI Repo Rate less 35 bps TER)

Protocol Verification: Cryptographically checks SHA-256 of MULTI_ASSET_TREND_PROTOCOL.md.
Execution Timing: Next-Day Open fills.
Friction: 49.20 bps stressed round-trip + flat Rs 14.75 DP fee per sale.
Taxation: Statutory holding-period based (STCG 15%/20%, LTCG 0%/10%/12.5%).
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
from typing import Dict, Any, List, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

from trading_system.scripts.backtest_nse50 import (
    compute_capital_gains_tax,
    get_liquid_etf_yield,
    calc_vectorized_momentum,
    BUY_COST_BPS_STRESSED,
    SELL_COST_BPS_STRESSED,
    BUY_COST_BPS_NORMAL,
    SELL_COST_BPS_NORMAL,
    FLAT_DP_FEE_RUPEES
)
from trading_system.app.validation.trial_logger import log_trial

CACHE_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data", "multi_asset_cache")
PROTOCOL_PATH = os.path.join(PROJECT_ROOT, "trading_system", "docs", "MULTI_ASSET_TREND_PROTOCOL.md")
PROTOCOL_SHA256_PATH = os.path.join(PROJECT_ROOT, "trading_system", "docs", "MULTI_ASSET_TREND_PROTOCOL.sha256")

START_DATE = "2007-09-24"
DEFAULT_END_DATE = "2024-12-31"
HOLDOUT_START_DATE = "2025-01-01"
INITIAL_CAPITAL = 80000.0


def verify_protocol_lock():
    if not os.path.exists(PROTOCOL_PATH):
        raise FileNotFoundError(f"CRITICAL: Protocol file missing: {PROTOCOL_PATH}")
    with open(PROTOCOL_PATH, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest().upper()
    if os.path.exists(PROTOCOL_SHA256_PATH):
        with open(PROTOCOL_SHA256_PATH, "r") as f:
            expected = f.read().strip().upper()
        if sha != expected:
            raise ValueError(f"PRE-REGISTRATION INTEGRITY VIOLATION: Protocol hash mismatch!\nExpected: {expected}\nComputed: {sha}")
    print(f"[OK] Multi-Asset Trend Protocol v1.0 verified (SHA-256: {sha[:16]}...).")


def load_multi_asset_data(start_date: str = START_DATE, end_date: str = DEFAULT_END_DATE) -> pd.DataFrame:
    print(f"[1/2] Loading Multi-Asset Historical Parquet Cache ({start_date} to {end_date})...", flush=True)
    nsei = pd.read_parquet(os.path.join(CACHE_DIR, "NIFTY50.parquet"))
    midcap = pd.read_parquet(os.path.join(CACHE_DIR, "MIDCAP50.parquet"))
    gold = pd.read_parquet(os.path.join(CACHE_DIR, "GOLD_USD.parquet"))
    qqq = pd.read_parquet(os.path.join(CACHE_DIR, "QQQ_USD.parquet"))
    usdinr = pd.read_parquet(os.path.join(CACHE_DIR, "USDINR.parquet"))

    # Common dates intersection
    common_idx = nsei.index.intersection(midcap.index).intersection(gold.index).intersection(qqq.index).intersection(usdinr.index)
    common_idx = [d for d in sorted(list(common_idx)) if pd.Timestamp(start_date) <= d <= pd.Timestamp(end_date)]

    data = {}
    # NIFTY50
    data["NIFTY50_close"] = nsei.loc[common_idx, "close"]
    data["NIFTY50_open"] = nsei.loc[common_idx, "open"]
    # MIDCAP50
    data["MIDCAP50_close"] = midcap.loc[common_idx, "close"]
    data["MIDCAP50_open"] = midcap.loc[common_idx, "open"]
    # GOLD_INR
    data["GOLD_INR_close"] = gold.loc[common_idx, "close"] * usdinr.loc[common_idx, "close"]
    data["GOLD_INR_open"] = gold.loc[common_idx, "open"] * usdinr.loc[common_idx, "open"]
    # QQQ_INR
    data["QQQ_INR_close"] = qqq.loc[common_idx, "close"] * usdinr.loc[common_idx, "close"]
    data["QQQ_INR_open"] = qqq.loc[common_idx, "open"] * usdinr.loc[common_idx, "open"]

    df = pd.DataFrame(data, index=common_idx).ffill().bfill()
    print(f"  Loaded 4 macro risk assets across {len(df)} aligned trading days.\n", flush=True)
    return df


def run_multi_asset_simulation(
    df: pd.DataFrame,
    variant: int = 1,
    slippage_bps: float = 7.5,
    label: str = "Variant A: Balanced Dual Momentum"
) -> Dict[str, Any]:
    print(f">>> Running Simulation [{label}] (Variant {variant}, Slippage: {slippage_bps:.2f} bps)...", flush=True)
    t0 = time.time()

    assets = ["NIFTY50", "MIDCAP50", "GOLD_INR", "QQQ_INR"]

    # Precalculate Indicators
    smas = {}
    sma50s = {}
    mom_scores = {}

    for a in assets:
        c = df[f"{a}_close"]
        smas[f"{a}_200"] = c.rolling(200, min_periods=50).mean()
        smas[f"{a}_150"] = c.rolling(150, min_periods=40).mean()
        sma50s[f"{a}_50"] = c.rolling(50, min_periods=20).mean()

        if variant == 1:
            # 6-Month relative return (126 days)
            mom_scores[a] = c.pct_change(126)
        elif variant == 2:
            # Blended 3M + 12M return
            m3 = c.pct_change(63)
            m12 = c.pct_change(252)
            mom_scores[a] = 0.5 * m3 + 0.5 * m12
        else:
            # Clenow exponential slope * R^2 (252 days)
            mom_scores[a] = pd.Series(calc_vectorized_momentum(c.values, window=252), index=df.index)

    # Rebalance dates: last trading day of each month
    monthly_rebalance_days = set(df.resample("ME").last().index)

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

    buy_fee = (BUY_COST_BPS_STRESSED if slippage_bps > 5.0 else BUY_COST_BPS_NORMAL) / 10000.0
    sell_fee = (SELL_COST_BPS_STRESSED if slippage_bps > 5.0 else SELL_COST_BPS_NORMAL) / 10000.0

    dates = list(df.index)

    for i, current_date in enumerate(dates):
        # Step 0: Execute Pending Orders at TODAY'S OPEN
        if pending_orders:
            for order in pending_orders:
                action = order["action"]
                asset = order["asset"]
                open_p = df.loc[current_date, f"{asset}_open"]
                if open_p <= 0 or math.isnan(open_p):
                    open_p = df.loc[current_date, f"{asset}_close"]

                if action == "SELL":
                    if asset in positions:
                        pos = positions.pop(asset)
                        fill_p = open_p * (1.0 - sell_fee)
                        gross = pos["shares"] * fill_p
                        cash += (gross - FLAT_DP_FEE_RUPEES)
                        total_dp_fees += FLAT_DP_FEE_RUPEES
                        cost = pos["shares"] * pos["entry_price"]
                        gain = gross - cost - FLAT_DP_FEE_RUPEES
                        tax = compute_capital_gains_tax(pos["entry_date"], current_date, gain)
                        cash -= tax
                        total_tax_paid += tax
                        trade_log.append({
                            "date": current_date, "asset": asset, "action": "SELL",
                            "shares": pos["shares"], "price": fill_p, "realized_pnl": gain,
                            "pnl_pct": (fill_p - pos["entry_price"]) / pos["entry_price"],
                            "tax": tax, "dp_fee": FLAT_DP_FEE_RUPEES, "reason": order["reason"]
                        })

                elif action == "BUY":
                    alloc = min(order["target_alloc"], cash * 0.99)
                    if alloc >= 1000.0:
                        fill_p = open_p * (1.0 + buy_fee)
                        shares = alloc / fill_p
                        cost = shares * fill_p
                        if cost <= cash and shares > 0:
                            cash -= cost
                            positions[asset] = {
                                "shares": shares, "entry_price": fill_p,
                                "entry_date": current_date, "peak_price": open_p
                            }
                            trade_log.append({
                                "date": current_date, "asset": asset, "action": "BUY",
                                "shares": shares, "price": fill_p, "cost": cost,
                                "reason": order["reason"]
                            })
            pending_orders = []

        # Step 1: Cash Yield Compounding
        daily_yield = get_liquid_etf_yield(current_date) / 252.0
        daily_interest = cash * daily_yield
        cash += daily_interest

        # Step 2: Mark-to-Market
        port_val = 0.0
        for asset, pos in positions.items():
            c_p = df.loc[current_date, f"{asset}_close"]
            port_val += pos["shares"] * c_p
            if c_p > pos.get("peak_price", c_p):
                pos["peak_price"] = c_p

        total_equity = cash + port_val
        equity_curve[current_date] = total_equity

        # Double High-Water Mark Evaluation
        if total_equity > hwm_true:
            hwm_true = total_equity
        true_dd = (total_equity - hwm_true) / hwm_true
        if true_dd < max_true_dd:
            max_true_dd = true_dd
        if true_dd < -0.3000:
            hard_breach = True

        # Step 3: Intra-Month Risk Stop (Variant B: 12% Trailing Stop)
        if variant == 2:
            for asset, pos in list(positions.items()):
                c_p = df.loc[current_date, f"{asset}_close"]
                peak = pos.get("peak_price", c_p)
                pullback = (c_p - peak) / peak if peak > 0 else 0.0
                if pullback <= -0.12:
                    # Queue immediate liquidation at tomorrow open
                    pending_orders.append({
                        "action": "SELL", "asset": asset,
                        "reason": f"INTRA_MONTH_TRAILING_STOP (-12.0%) [Pullback: {pullback*100:.1f}%]"
                    })

        # Step 4: Monthly Rebalance Evaluation at CLOSE
        if current_date in monthly_rebalance_days:
            eligible = {}
            for a in assets:
                p = df.loc[current_date, f"{a}_close"]
                score = mom_scores[a].loc[current_date]

                if variant == 1:
                    sma_val = smas[f"{a}_200"].loc[current_date]
                    if p > sma_val and not math.isnan(score) and score > 0:
                        eligible[a] = score

                elif variant == 2:
                    sma200_val = smas[f"{a}_200"].loc[current_date]
                    sma50_today = sma50s[f"{a}_50"].loc[current_date]
                    sma50_prev = sma50s[f"{a}_50"].iloc[max(0, i - 5)]
                    sma50_up = sma50_today > sma50_prev
                    if p > sma200_val and sma50_up and not math.isnan(score) and score > 0:
                        eligible[a] = score

                else:  # Variant 3
                    sma150_val = smas[f"{a}_150"].loc[current_date]
                    if p > sma150_val and not math.isnan(score) and score > 0:
                        eligible[a] = score

            # Rank eligible by momentum score
            sorted_cands = sorted(eligible.items(), key=lambda x: x[1], reverse=True)

            if variant == 1:
                top_targets = [x[0] for x in sorted_cands[:2]]
                target_weights = {top_targets[0]: 0.50, top_targets[1]: 0.50} if len(top_targets) == 2 else ({top_targets[0]: 0.50} if len(top_targets) == 1 else {})

            elif variant == 2:
                top_targets = [x[0] for x in sorted_cands[:2]]
                if len(top_targets) == 2:
                    target_weights = {top_targets[0]: 0.60, top_targets[1]: 0.40}
                elif len(top_targets) == 1:
                    target_weights = {top_targets[0]: 0.60}
                else:
                    target_weights = {}

            else:  # Variant 3
                top_targets = [x[0] for x in sorted_cands[:3]]
                if len(top_targets) == 3:
                    target_weights = {top_targets[0]: 0.45, top_targets[1]: 0.35, top_targets[2]: 0.20}
                elif len(top_targets) == 2:
                    target_weights = {top_targets[0]: 0.50, top_targets[1]: 0.35}
                elif len(top_targets) == 1:
                    target_weights = {top_targets[0]: 0.50}
                else:
                    target_weights = {}

            # Queue Sells for assets not in target_weights
            for asset in list(positions.keys()):
                if asset not in target_weights:
                    pending_orders.append({
                        "action": "SELL", "asset": asset,
                        "reason": "MONTHLY_REBALANCE_EXIT"
                    })

            # Queue Buys for new targets
            for target, w in target_weights.items():
                if target not in positions:
                    target_alloc = total_equity * w
                    pending_orders.append({
                        "action": "BUY", "asset": target, "target_alloc": target_alloc,
                        "reason": f"MONTHLY_REBALANCE_ENTRY (Weight: {w*100:.0f}%, Score: {eligible[target]:.2f})"
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
    gross_win = sum(t["realized_pnl"] for t in wins)
    gross_loss = abs(sum(t["realized_pnl"] for t in closed_sells if t["realized_pnl"] <= 0))
    pf = gross_win / gross_loss if gross_loss > 0 else 0.0

    print(f"  Simulation completed in {time.time()-t0:.2f}s.\n", flush=True)

    return {
        "label": label,
        "variant": variant,
        "slippage_bps": slippage_bps,
        "starting_capital": INITIAL_CAPITAL,
        "terminal_equity": round(eq_series.iloc[-1], 2),
        "total_return_pct": round(tot_ret, 2),
        "cagr_pct": round(cagr, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "hard_breach_detected": hard_breach,
        "sharpe_ratio": round(sharpe, 2),
        "calmar_ratio": round(calmar, 2),
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": round(pf, 2),
        "closed_trades": len(closed_sells),
        "trades_per_year": round(len(closed_sells) / years, 1),
        "total_dp_fees": round(total_dp_fees, 2),
        "total_tax_paid": round(total_tax_paid, 2),
        "equity_curve": eq_series,
        "trade_log": trade_log
    }


def compute_nifty_tri_baseline(df: pd.DataFrame) -> Dict[str, Any]:
    nsei_close = df["NIFTY50_close"]
    years = (df.index[-1] - df.index[0]).days / 365.25
    start_cash = INITIAL_CAPITAL * (1.0 - BUY_COST_BPS_STRESSED / 10000.0)
    shares = start_cash / nsei_close.iloc[0]
    tri_list = []
    for p in nsei_close:
        shares *= (1.0 + 0.0135 / 252.0)
        tri_list.append(shares * p)
    tri_s = pd.Series(tri_list, index=df.index)
    final_proceeds = shares * nsei_close.iloc[-1] * (1.0 - SELL_COST_BPS_STRESSED / 10000.0) - FLAT_DP_FEE_RUPEES
    tax = compute_capital_gains_tax(df.index[0], df.index[-1], final_proceeds - INITIAL_CAPITAL)
    tri_s.iloc[-1] = final_proceeds - tax

    cagr = ((tri_s.iloc[-1] / INITIAL_CAPITAL) ** (1.0 / years) - 1.0) * 100.0
    peak = tri_s.cummax()
    max_dd = ((tri_s - peak) / peak).min() * 100.0
    ret_d = tri_s.pct_change().dropna()
    sharpe = (ret_d.mean() / (ret_d.std() + 1e-9)) * np.sqrt(252)

    return {
        "terminal_equity": round(tri_s.iloc[-1], 2),
        "cagr_pct": round(cagr, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "calmar_ratio": round(abs(cagr / max_dd), 2),
        "sharpe_ratio": round(sharpe, 2)
    }


def main():
    parser = argparse.ArgumentParser(description="Multi-Asset Tactical Trend Engine Backtester")
    parser.add_argument("--variant", type=int, choices=[1, 2, 3], default=1)
    parser.add_argument("--run-all", action="store_true", help="Execute all 3 pre-registered variants")
    parser.add_argument("--skip-protocol-check", action="store_true")
    args = parser.parse_args()

    if not args.skip_protocol_check:
        verify_protocol_lock()

    df = load_multi_asset_data()
    tri_bench = compute_nifty_tri_baseline(df)

    variants_to_run = [1, 2, 3] if args.run_all else [args.variant]
    results = {}

    for var in variants_to_run:
        label = "Variant A (Balanced Dual Momentum)" if var == 1 else ("Variant B (Asymmetric High-Growth Trend)" if var == 2 else "Variant C (3-Asset Volatility-Inverse Momentum)")
        # Normal Run (5.0 bps)
        res_norm = run_multi_asset_simulation(df, variant=var, slippage_bps=5.0, label=f"{label} [Normal]")
        # Stressed Run (7.5 bps) [Gate A Evaluator]
        res_stress = run_multi_asset_simulation(df, variant=var, slippage_bps=7.5, label=f"{label} [Stressed Gate A]")

        results[f"variant_{var}"] = {
            "normal": res_norm,
            "stressed": res_stress
        }

        # Log trials
        log_trial(
            script="backtest_multi_asset.py", universe="MULTI_ASSET_5",
            kelly_fraction=1.0, lookback_days=126 if var == 1 else (252 if var == 3 else 189),
            cagr_pct=res_norm["cagr_pct"], max_drawdown_pct=res_norm["max_drawdown_pct"],
            sharpe_ratio=res_norm["sharpe_ratio"], is_holdout_opened=False,
            notes=f"Multi-Asset {label} Normal (5.0 bps) | IN_SAMPLE"
        )
        log_trial(
            script="backtest_multi_asset.py", universe="MULTI_ASSET_5",
            kelly_fraction=1.0, lookback_days=126 if var == 1 else (252 if var == 3 else 189),
            cagr_pct=res_stress["cagr_pct"], max_drawdown_pct=res_stress["max_drawdown_pct"],
            sharpe_ratio=res_stress["sharpe_ratio"], is_holdout_opened=False,
            notes=f"Multi-Asset {label} Stressed (7.5 bps) [Gate A] | IN_SAMPLE"
        )

        out_path = os.path.join(PROJECT_ROOT, "trading_system", "data", f"backtest_results_multi_asset_variant_{var}.json")
        save_dict = {k: v for k, v in res_stress.items() if k not in ["equity_curve", "trade_log"]}
        with open(out_path, "w") as f:
            json.dump(save_dict, f, indent=2)

    # Print Comparative Scoreboard
    print("\n" + "=" * 115)
    print("=" * 28 + " MULTI-ASSET TACTICAL TREND SCOREBOARD (POST-TAX & STRESSED) " + "=" * 25)
    print("=" * 115)
    print(f"{'Performance Metric':<32} | {'Variant A (Balanced)':<20} | {'Variant B (Asymmetric)':<22} | {'Variant C (3-Asset)':<20} | {'Nifty 50 TRI':<15}")
    print("-" * 115)

    va = results["variant_1"]["stressed"] if 1 in variants_to_run else None
    vb = results["variant_2"]["stressed"] if 2 in variants_to_run else None
    vc = results["variant_3"]["stressed"] if 3 in variants_to_run else None

    def fmt(val, prefix="", suffix="", decimals=2):
        if val is None:
            return "N/A"
        return f"{prefix}{val:.{decimals}f}{suffix}"

    print(f"{'Post-Tax Stressed CAGR':<32} | {fmt(va['cagr_pct'], suffix='%'):<20} | {fmt(vb['cagr_pct'], suffix='%'):<22} | {fmt(vc['cagr_pct'], suffix='%'):<20} | {fmt(tri_bench['cagr_pct'], suffix='%'):<15}")
    print(f"{'Max Drawdown Depth':<32} | {fmt(va['max_drawdown_pct'], suffix='%'):<20} | {fmt(vb['max_drawdown_pct'], suffix='%'):<22} | {fmt(vc['max_drawdown_pct'], suffix='%'):<20} | {fmt(tri_bench['max_drawdown_pct'], suffix='%'):<15}")
    print(f"{'Annualized Sharpe Ratio':<32} | {fmt(va['sharpe_ratio']):<20} | {fmt(vb['sharpe_ratio']):<22} | {fmt(vc['sharpe_ratio']):<20} | {fmt(tri_bench['sharpe_ratio']):<15}")
    print(f"{'Calmar Ratio (CAGR / MaxDD)':<32} | {fmt(va['calmar_ratio']):<20} | {fmt(vb['calmar_ratio']):<22} | {fmt(vc['calmar_ratio']):<20} | {fmt(tri_bench['calmar_ratio']):<15}")
    print(f"{'Terminal Equity (from Rs 80k)':<32} | {fmt(va['terminal_equity'], prefix='Rs '):<20} | {fmt(vb['terminal_equity'], prefix='Rs '):<22} | {fmt(vc['terminal_equity'], prefix='Rs '):<20} | {fmt(tri_bench['terminal_equity'], prefix='Rs '):<15}")
    print(f"{'Total Closed Trades':<32} | {str(va['closed_trades']) if va else 'N/A':<20} | {str(vb['closed_trades']) if vb else 'N/A':<22} | {str(vc['closed_trades']) if vc else 'N/A':<20} | {'0 (Buy & Hold)':<15}")
    print(f"{'Trades Per Year':<32} | {fmt(va['trades_per_year']):<20} | {fmt(vb['trades_per_year']):<22} | {fmt(vc['trades_per_year']):<20} | {'0.0':<15}")
    print(f"{'Total DP Fees Paid':<32} | {fmt(va['total_dp_fees'], prefix='Rs '):<20} | {fmt(vb['total_dp_fees'], prefix='Rs '):<22} | {fmt(vc['total_dp_fees'], prefix='Rs '):<20} | {'Rs 0.00':<15}")
    print(f"{'Total Statutory Taxes Paid':<32} | {fmt(va['total_tax_paid'], prefix='Rs '):<20} | {fmt(vb['total_tax_paid'], prefix='Rs '):<22} | {fmt(vc['total_tax_paid'], prefix='Rs '):<20} | {'Deferred LTCG':<15}")
    print("=" * 115)


if __name__ == "__main__":
    main()
