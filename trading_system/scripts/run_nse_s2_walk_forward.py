"""
Stage 2: NSE S2 Walk-Forward Runner (Pre-Registered Protocol V1.0)
==================================================================
Verifies Protocol V1 SHA-256 and NSE_PANEL_V2 SHA-256 before running.
Executes 10 rolling folds (5y train with longest-hold embargo -> 1y blind OOS test,
2013 to 2022), 3x3x3 plateau grid selection, 4 baselines, 13 checks (H1-H9, W1-W4),
and logs N=88 rows to trial_log.csv.
"""

import os
import sys
import json
import math
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import trading_system.app.data.corporate_actions as ca_mod
import trading_system.scripts.run_phase5_nse_whole_market_gate_a as p5
from trading_system.app.validation.gate_evaluator import GateEvaluator
from trading_system.app.validation.trial_logger import log_trial

DATA_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data")
DOCS_DIR = os.path.join(PROJECT_ROOT, "trading_system", "docs")

WF_PROTOCOL_PATH = os.path.join(DOCS_DIR, "NSE_S2_WALK_FORWARD_PROTOCOL_V1.md")
WF_PROTOCOL_SHA_PATH = os.path.join(DOCS_DIR, "NSE_S2_WALK_FORWARD_PROTOCOL_V1.sha256")
PANEL_SHA_PATH = os.path.join(DATA_DIR, "nse_panel_v2.sha256")
CA_V2_CSV = os.path.join(DATA_DIR, "nse_corporate_actions_v2.csv")
WF_RESULTS_JSON = os.path.join(DATA_DIR, "nse_s2_walk_forward_results.json")

EXPECTED_WF_PROTOCOL_SHA = "03ea0ad375cf30792952a7add7eb184c1c611a77561a6eaffca9888c84de7cf6"
EXPECTED_PANEL_SHA = "d2806b81342339edcd6debf60a8dfcac7042ab7b9f630db1795b925cb68a2156"

# 3x3x3 Grid
GRID_LB90 = [72, 90, 108]
GRID_SMA = [120, 150, 180]
GRID_TRAIL_SCALE = [0.8, 1.0, 1.2]
TEST_YEARS = list(range(2013, 2023))  # 10 test years: 2013..2022


def verify_seals() -> Tuple[str, str]:
    raw_proto = open(WF_PROTOCOL_PATH, "rb").read().replace(b"\r\n", b"\n")
    proto_sha = hashlib.sha256(raw_proto).hexdigest()
    seal_proto = open(WF_PROTOCOL_SHA_PATH, "r", encoding="utf-8").read().strip()
    if proto_sha != EXPECTED_WF_PROTOCOL_SHA or proto_sha != seal_proto:
        raise ValueError(f"Walk-Forward Protocol SHA mismatch: {proto_sha} != {EXPECTED_WF_PROTOCOL_SHA}")

    panel_line = open(PANEL_SHA_PATH, "r", encoding="utf-8").readline().strip().split()[0]
    if panel_line != EXPECTED_PANEL_SHA:
        raise ValueError(f"Panel V2 SHA mismatch: {panel_line} != {EXPECTED_PANEL_SHA}")
    return proto_sha, panel_line


def simulate_s2_window(
    close_df: pd.DataFrame,
    open_df: pd.DataFrame,
    turnover_df: pd.DataFrame,
    bench_df: pd.DataFrame,
    mult_df: pd.DataFrame,
    adj_close: pd.DataFrame,
    med_turnover: pd.DataFrame,
    seasoning: pd.DataFrame,
    sim_start: str,
    sim_end: str,
    lookback_90: int = 90,
    exit_sma_window: int = 150,
    trail_scale: float = 1.0,
    buy_friction_bps: float = p5.BUY_FRICTION_BPS_BASE,
    sell_friction_bps: float = p5.SELL_FRICTION_BPS_BASE,
    dp_fee_rupees: float = p5.FLAT_DP_FEE_BASE,
    blocked_entries: Optional[Set[Tuple[str, str]]] = None,
    exit_sma_cache: Optional[Dict[int, pd.DataFrame]] = None,
    mom_cache: Optional[Dict[Tuple[int, pd.Timestamp, str], float]] = None,
) -> Dict[str, Any]:
    """
    Causal S2 simulation over [sim_start, sim_end] using full historical warmup
    from close_df.index[0] so 1-year OOS folds have full 252d seasoning & 180d/150d indicators.
    """
    lookback_180 = 2 * lookback_90
    trail_t1_stop = 0.15 * trail_scale
    trail_t2_stop = 0.20 * trail_scale
    trail_t3_stop = 0.25 * trail_scale

    dates = close_df.loc[sim_start:sim_end].index
    if len(dates) < 20:
        raise ValueError(f"Insufficient trading days in [{sim_start}, {sim_end}]: {len(dates)}")

    bench_close = bench_df["close"].loc[dates]
    bench_sma200 = bench_df["sma200"].loc[dates]
    if exit_sma_cache is not None and exit_sma_window in exit_sma_cache:
        exit_sma = exit_sma_cache[exit_sma_window]
    else:
        exit_sma = adj_close.rolling(exit_sma_window, min_periods=int(exit_sma_window * 0.75)).mean()

    df_d = pd.DataFrame({"date": dates}, index=dates)
    df_d["month"] = df_d["date"].dt.to_period("M")
    rebalance_dates = set(df_d.groupby("month")["date"].max())

    cash = p5.INITIAL_CAPITAL
    hwm_true = p5.INITIAL_CAPITAL
    hwm_ladder = p5.INITIAL_CAPITAL
    holdings: Dict[str, Dict[str, Any]] = {}
    equity_curve: List[float] = []
    trade_log: List[Dict[str, Any]] = []

    in_tier4_defense = False
    cooling_off_counter = 0
    recovery_streak = 0
    recovery_stage = 0
    recovery_stage_days = 0
    daily_cash_yield = (1.0 + p5.CASH_YIELD_PA) ** (1.0 / 252.0) - 1.0

    for i, current_date in enumerate(dates):
        for sym in list(holdings.keys()):
            if sym in mult_df.columns:
                mult = mult_df.loc[current_date, sym]
                if mult > 1.0001 or mult < 0.9999:
                    holdings[sym]["shares"] *= mult
                    holdings[sym]["fill_price"] /= mult
                    holdings[sym]["peak_price"] /= mult

        current_close = close_df.loc[current_date]
        portfolio_stock_value = 0.0
        for sym, pos in holdings.items():
            price = current_close.get(sym, np.nan)
            if not math.isnan(price) and price > 0.0:
                pos["current_price"] = price
                if price > pos["peak_price"]:
                    pos["peak_price"] = price
                portfolio_stock_value += pos["shares"] * price
            else:
                portfolio_stock_value += pos["shares"] * pos.get("current_price", pos["fill_price"])

        total_equity = cash + portfolio_stock_value
        if total_equity > hwm_true:
            hwm_true = total_equity
        if not in_tier4_defense and total_equity > hwm_ladder:
            hwm_ladder = total_equity

        current_dd = (total_equity - hwm_ladder) / hwm_ladder if hwm_ladder > 0 else 0.0
        b_c = bench_close.iloc[i]
        b_s = bench_sma200.iloc[i]
        macro_bullish = True if math.isnan(b_s) else (b_c >= b_s)

        if in_tier4_defense:
            if cooling_off_counter > 0:
                cooling_off_counter -= 1
            elif macro_bullish:
                recovery_streak += 1
                if recovery_streak >= 3:
                    in_tier4_defense = False
                    hwm_ladder = total_equity
                    recovery_stage = 1
                    recovery_stage_days = 0
            else:
                recovery_streak = 0

        if not in_tier4_defense:
            if recovery_stage == 1:
                recovery_stage_days += 1
                if recovery_stage_days > 20:
                    recovery_stage = 2
                    recovery_stage_days = 0
            elif recovery_stage == 2:
                recovery_stage_days += 1
                if recovery_stage_days > 20:
                    recovery_stage = 0
                    recovery_stage_days = 0

        effective_exposure_cap = 1.0
        if not macro_bullish:
            effective_exposure_cap = 0.25

        if current_dd <= -0.15 and not in_tier4_defense:
            in_tier4_defense = True
            cooling_off_counter = 20
            recovery_streak = 0
            effective_exposure_cap = 0.0
        elif current_dd <= -0.10:
            effective_exposure_cap = min(effective_exposure_cap, 0.25)
        elif current_dd <= -0.05:
            effective_exposure_cap = min(effective_exposure_cap, 0.60)

        if in_tier4_defense:
            effective_exposure_cap = 0.0
        elif recovery_stage == 1:
            effective_exposure_cap = min(effective_exposure_cap, 0.25)
        elif recovery_stage == 2:
            effective_exposure_cap = min(effective_exposure_cap, 0.50)

        cash *= (1.0 + daily_cash_yield)
        equity_curve.append(total_equity)

        if i == len(dates) - 1:
            # Close out open positions on final day for holding-period accounting
            for sym, pos in list(holdings.items()):
                exit_p = pos.get("current_price", pos["fill_price"]) * (1.0 - sell_friction_bps / 10000.0)
                ret_pct = (exit_p - pos["fill_price"]) / max(pos["fill_price"], 1e-4)
                hold_days = (current_date - pd.to_datetime(pos["entry_date"])).days
                trade_log.append({
                    "symbol": sym,
                    "entry_date": pos["entry_date"],
                    "exit_date": str(current_date.date()),
                    "holding_days": max(1, hold_days),
                    "return_pct": ret_pct,
                    "reason": "END_OF_WINDOW",
                })
            break

        next_date = dates[i + 1]
        next_open = open_df.loc[next_date]

        exits_to_execute: List[Tuple[str, str]] = []
        if effective_exposure_cap == 0.0 and len(holdings) > 0:
            for sym in list(holdings.keys()):
                exits_to_execute.append((sym, "TIER4_LIQUIDATION"))
        else:
            prev_date = dates[i - 1] if i > 0 else current_date
            prev_close = close_df.loc[prev_date]
            for sym, pos in list(holdings.items()):
                c_p = current_close.get(sym, np.nan)
                p_p = prev_close.get(sym, np.nan)
                is_circuit = False
                if not (math.isnan(c_p) or math.isnan(p_p) or p_p <= 0.0):
                    if abs((c_p - p_p) / p_p) >= 0.1950:
                        is_circuit = True

                curr_p = pos.get("current_price", pos["fill_price"])
                fill_p = pos["fill_price"]
                peak_p = pos["peak_price"]

                if (curr_p - fill_p) / fill_p <= -0.12:
                    if not is_circuit:
                        exits_to_execute.append((sym, "HARD_STOP_12"))
                    continue

                peak_gain = (peak_p - fill_p) / fill_p
                dd_from_peak = (curr_p - peak_p) / peak_p
                trail_hit = False
                if peak_gain >= 1.00 and dd_from_peak <= -trail_t3_stop:
                    trail_hit = True
                elif peak_gain >= 0.50 and dd_from_peak <= -trail_t2_stop:
                    trail_hit = True
                elif peak_gain >= 0.25 and dd_from_peak <= -trail_t1_stop:
                    trail_hit = True

                if trail_hit:
                    if not is_circuit:
                        exits_to_execute.append((sym, "PROFIT_TRAIL_STOP"))
                    continue

                sym_sma = exit_sma.loc[current_date, sym] if sym in exit_sma.columns else np.nan
                adj_c = adj_close.loc[current_date, sym]
                if not math.isnan(sym_sma) and adj_c < sym_sma:
                    if not is_circuit:
                        exits_to_execute.append((sym, "TREND_EXIT_150SMA"))
                    continue

        for sym, reason in exits_to_execute:
            if sym not in holdings:
                continue
            fill_open = next_open.get(sym, np.nan)
            if math.isnan(fill_open) or fill_open <= 0.0:
                fill_open = holdings[sym]["current_price"]

            eff_sell_price = fill_open * (1.0 - sell_friction_bps / 10000.0)
            gross_proceeds = holdings[sym]["shares"] * eff_sell_price
            net_proceeds = max(0.0, gross_proceeds - dp_fee_rupees)
            cash += net_proceeds

            ret_pct = (eff_sell_price - holdings[sym]["fill_price"]) / max(holdings[sym]["fill_price"], 1e-4)
            hold_days = (next_date - pd.to_datetime(holdings[sym]["entry_date"])).days
            trade_log.append({
                "symbol": sym,
                "entry_date": holdings[sym]["entry_date"],
                "exit_date": str(next_date.date()),
                "holding_days": max(1, hold_days),
                "return_pct": ret_pct,
                "reason": reason,
            })
            del holdings[sym]

        if (current_date in rebalance_dates) and (not in_tier4_defense) and (effective_exposure_cap > 0.05):
            available_slots = p5.CORE_SLOTS - len(holdings)
            if available_slots > 0:
                turnover_60d = med_turnover.loc[current_date]
                p_c = current_close
                p_season = seasoning.loc[current_date]
                prev_d = dates[i - 1] if i > 0 else current_date
                p_prev = close_df.loc[prev_d]
                pct_chg_day = ((p_c - p_prev) / p_prev.replace(0.0, np.nan)).abs()

                eligible_mask = (
                    (turnover_60d >= p5.MIN_MEDIAN_TURNOVER) &
                    (p_c >= p5.MIN_SHARE_PRICE) &
                    (p_season >= p5.MIN_SEASONING_DAYS) &
                    (pct_chg_day < 0.1950) &
                    (~close_df.columns.isin(list(holdings.keys())))
                )
                eligible_syms = close_df.columns[eligible_mask].tolist()

                if eligible_syms:
                    scores_dict = {}
                    window_slice = None
                    for s in eligible_syms:
                        if mom_cache is not None and (lookback_90, current_date, s) in mom_cache:
                            blended = mom_cache[(lookback_90, current_date, s)]
                            if blended is not None and blended > 0.15:
                                scores_dict[s] = blended
                            continue
                        if window_slice is None:
                            window_slice = adj_close.loc[:current_date].iloc[-(lookback_180 + 20):]
                        p_arr = window_slice[s].dropna().values
                        blended_val = None
                        if len(p_arr) >= lookback_180:
                            s90 = p5.calc_vectorized_momentum(p_arr, lookback_90)[-1]
                            s180 = p5.calc_vectorized_momentum(p_arr, lookback_180)[-1]
                            if not (math.isnan(s90) or math.isnan(s180)):
                                blended_val = 0.60 * s90 + 0.40 * s180
                        if mom_cache is not None:
                            mom_cache[(lookback_90, current_date, s)] = blended_val
                        if blended_val is not None and blended_val > 0.15:
                            scores_dict[s] = blended_val

                    sorted_candidates = sorted(scores_dict.items(), key=lambda x: x[1], reverse=True)
                    if blocked_entries:
                        next_d_str = str(next_date.date())
                        sorted_candidates = [(s, sc) for s, sc in sorted_candidates if (s, next_d_str) not in blocked_entries]
                    picks = [s for s, _ in sorted_candidates[:available_slots]]

                    target_equity_exposure = total_equity * effective_exposure_cap
                    current_invested = sum(pos["shares"] * pos.get("current_price", pos["fill_price"]) for pos in holdings.values())
                    allocatable_cash = max(0.0, min(cash, target_equity_exposure - current_invested))

                    if allocatable_cash > 1000.0 and picks:
                        target_per_slot = min(allocatable_cash / len(picks), total_equity * p5.MAX_ALLOC_PER_STOCK)
                        for sym in picks:
                            open_p = next_open.get(sym, np.nan)
                            if math.isnan(open_p) or open_p <= 0.0:
                                open_p = current_close.get(sym, np.nan)
                            if math.isnan(open_p) or open_p <= 0.0:
                                continue

                            eff_buy_price = open_p * (1.0 + buy_friction_bps / 10000.0)
                            shares = math.floor(target_per_slot / eff_buy_price)
                            if shares > 0 and cash >= (shares * eff_buy_price):
                                cash -= shares * eff_buy_price
                                holdings[sym] = {
                                    "shares": shares,
                                    "fill_price": eff_buy_price,
                                    "peak_price": eff_buy_price,
                                    "entry_date": str(next_date.date()),
                                    "current_price": eff_buy_price,
                                }

    eq_series = pd.Series(equity_curve, index=dates)
    years = max((dates[-1] - dates[0]).days / 365.25, 0.1)
    cagr = (eq_series.iloc[-1] / eq_series.iloc[0]) ** (1.0 / years) - 1.0
    daily_ret = eq_series.pct_change().dropna()
    mean_d = daily_ret.mean()
    std_d = daily_ret.std()
    sharpe = (mean_d / std_d * math.sqrt(252.0)) if std_d > 1e-6 else 0.0
    cummax = eq_series.cummax()
    max_dd = float(((eq_series - cummax) / cummax).min())

    return {
        "cagr_pct": round(cagr * 100.0, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_pct": round(max_dd * 100.0, 2),
        "daily_returns": daily_ret,
        "equity_curve": eq_series,
        "trade_log": trade_log,
    }


def metrics_from_daily_returns(daily_ret: pd.Series) -> Dict[str, Any]:
    eq = (1.0 + daily_ret).cumprod() * p5.INITIAL_CAPITAL
    years = max((daily_ret.index[-1] - daily_ret.index[0]).days / 365.25, 0.1)
    cagr = (eq.iloc[-1] / p5.INITIAL_CAPITAL) ** (1.0 / years) - 1.0
    m = daily_ret.mean()
    s = daily_ret.std()
    sharpe = (m / s * math.sqrt(252.0)) if s > 1e-6 else 0.0
    cummax = eq.cummax()
    max_dd = float(((eq - cummax) / cummax).min())
    skew = float(daily_ret.skew()) if len(daily_ret) > 10 else 0.0
    kurt = float(daily_ret.kurtosis() + 3.0) if len(daily_ret) > 10 else 3.0
    return {
        "cagr_pct": round(float(cagr * 100.0), 2),
        "sharpe_ratio": round(float(sharpe), 2),
        "max_drawdown_pct": round(float(max_dd * 100.0), 2),
        "skewness": round(skew, 2),
        "kurtosis": round(kurt, 2),
        "years": round(years, 2),
        "equity_curve": eq,
    }


def select_plateau_grid(sharpe_grid: Dict[Tuple[int, int, int], float]) -> Tuple[Tuple[int, int, int], float]:
    best_idx = (1, 1, 1)
    best_plateau = -1e9
    for i in range(3):
        for j in range(3):
            for k in range(3):
                nbrs = []
                for ni in range(3):
                    for nj in range(3):
                        for nk in range(3):
                            if abs(i - ni) + abs(j - nj) + abs(k - nk) <= 1:
                                nbrs.append(sharpe_grid[(ni, nj, nk)])
                avg_s = float(np.mean(nbrs))
                if avg_s > best_plateau:
                    best_plateau = avg_s
                    best_idx = (i, j, k)
    return best_idx, round(best_plateau, 3)


def main():
    print("=" * 85)
    print("STAGE 2: NSE S2 WALK-FORWARD VALIDATION (PROTOCOL V1.0, N=88)")
    print("=" * 85)

    proto_sha, panel_sha = verify_seals()
    print(f"  Protocol SHA-256 : {proto_sha}")
    print(f"  Panel V2 SHA-256 : {panel_sha}")

    ca_mod.CORPORATE_ACTIONS_CSV = CA_V2_CSV
    ca_mod._ACTIONS_CACHE = None
    close_df, open_df, turnover_df, bench_df, _ = p5.load_all_data()
    mult_df, adj_factors = ca_mod.build_verified_split_adjustment_matrix(close_df, csv_path=CA_V2_CSV)
    adj_close = close_df * adj_factors
    med_turnover = turnover_df.rolling(60, min_periods=5).median()
    seasoning = (close_df.notna() & (close_df > 0.0)).cumsum()
    exit_sma_cache = {w: adj_close.rolling(w, min_periods=int(w * 0.75)).mean() for w in GRID_SMA}
    mom_cache: Dict[Tuple[int, pd.Timestamp, str], Optional[float]] = {}

    # 1. Run 10 Rolling Walk-Forward Folds (2013..2022)
    fold_rows: List[Dict[str, Any]] = []
    oos_daily_rets: List[pd.Series] = []
    oos_daily_rets_2x: List[pd.Series] = []
    oos_trades_all: List[Dict[str, Any]] = []
    chosen_indices: List[Tuple[int, int, int]] = []

    for test_yr in TEST_YEARS:
        raw_train_start = max("2007-09-17", f"{test_yr - 5}-01-01")
        raw_train_end = f"{test_yr - 1}-12-31"
        test_start = f"{test_yr}-01-01"
        test_end = f"{test_yr}-12-31"

        # Determine embargo = longest completed holding period in raw training window (base S2)
        base_train = simulate_s2_window(
            close_df, open_df, turnover_df, bench_df, mult_df, adj_close, med_turnover, seasoning,
            raw_train_start, raw_train_end, 90, 150, 1.0,
            exit_sma_cache=exit_sma_cache, mom_cache=mom_cache,
        )
        completed_holds = [t["holding_days"] for t in base_train["trade_log"] if t["reason"] != "END_OF_WINDOW"]
        embargo_cal_days = max(completed_holds) if completed_holds else 90
        # Cap embargo so at least 2.5 years of training remain
        max_embargo = max(90, (pd.to_datetime(raw_train_end) - pd.to_datetime(raw_train_start)).days - 900)
        embargo_cal_days = min(embargo_cal_days, max_embargo)
        embargo_end_dt = (pd.to_datetime(raw_train_end) - pd.Timedelta(days=embargo_cal_days)).strftime("%Y-%m-%d")

        # Evaluate 27 grid points on [raw_train_start, embargo_end_dt]
        sharpe_grid: Dict[Tuple[int, int, int], float] = {}
        for ii, lb90 in enumerate(GRID_LB90):
            for jj, sma_w in enumerate(GRID_SMA):
                for kk, t_sc in enumerate(GRID_TRAIL_SCALE):
                    r_tr = simulate_s2_window(
                        close_df, open_df, turnover_df, bench_df, mult_df, adj_close, med_turnover, seasoning,
                        raw_train_start, embargo_end_dt, lb90, sma_w, t_sc,
                        exit_sma_cache=exit_sma_cache, mom_cache=mom_cache,
                    )
                    sharpe_grid[(ii, jj, kk)] = float(r_tr["sharpe_ratio"])

        best_idx, best_plateau = select_plateau_grid(sharpe_grid)
        chosen_indices.append(best_idx)
        sel_lb90 = GRID_LB90[best_idx[0]]
        sel_sma = GRID_SMA[best_idx[1]]
        sel_tscale = GRID_TRAIL_SCALE[best_idx[2]]
        is_sharpe = sharpe_grid[best_idx]

        # Blind OOS test year (1x and 2x costs)
        oos_1x = simulate_s2_window(
            close_df, open_df, turnover_df, bench_df, mult_df, adj_close, med_turnover, seasoning,
            test_start, test_end, sel_lb90, sel_sma, sel_tscale,
            p5.BUY_FRICTION_BPS_BASE, p5.SELL_FRICTION_BPS_BASE, p5.FLAT_DP_FEE_BASE,
            exit_sma_cache=exit_sma_cache, mom_cache=mom_cache,
        )
        oos_2x = simulate_s2_window(
            close_df, open_df, turnover_df, bench_df, mult_df, adj_close, med_turnover, seasoning,
            test_start, test_end, sel_lb90, sel_sma, sel_tscale,
            p5.BUY_FRICTION_BPS_STRESSED, p5.SELL_FRICTION_BPS_STRESSED, p5.FLAT_DP_FEE_STRESSED,
            exit_sma_cache=exit_sma_cache, mom_cache=mom_cache,
        )
        oos_sharpe = float(oos_1x["sharpe_ratio"])
        wf_eff = round(oos_sharpe / is_sharpe, 2) if abs(is_sharpe) > 1e-4 else 0.0

        oos_daily_rets.append(oos_1x["daily_returns"])
        oos_daily_rets_2x.append(oos_2x["daily_returns"])
        oos_trades_all.extend(oos_1x["trade_log"])

        row = {
            "test_year": test_yr,
            "train_window": f"{raw_train_start}..{embargo_end_dt}",
            "embargo_days": int(embargo_cal_days),
            "chosen_lb90": sel_lb90,
            "chosen_sma": sel_sma,
            "chosen_trail_scale": sel_tscale,
            "plateau_sharpe": best_plateau,
            "is_sharpe": round(is_sharpe, 2),
            "oos_cagr_pct": float(oos_1x["cagr_pct"]),
            "oos_sharpe": oos_sharpe,
            "oos_max_dd_pct": float(oos_1x["max_drawdown_pct"]),
            "wf_efficiency": wf_eff,
        }
        fold_rows.append(row)
        print(f"  Fold {test_yr}: ({sel_lb90}/{sel_sma}/{sel_tscale}) | IS_Sh={is_sharpe:.2f} | OOS_CAGR={row['oos_cagr_pct']:6.2f}% | OOS_Sh={oos_sharpe:5.2f} | Eff={wf_eff:.2f}")

    # 2. Stitch 10-year OOS curves
    stitched_ret_1x = pd.concat(oos_daily_rets).sort_index()
    stitched_ret_2x = pd.concat(oos_daily_rets_2x).sort_index()
    wf_1x = metrics_from_daily_returns(stitched_ret_1x)
    wf_2x = metrics_from_daily_returns(stitched_ret_2x)

    # 3. Baselines over 2013-01-01..2022-12-31
    oos_start, oos_end = "2013-01-01", "2022-12-31"
    fixed_s2 = simulate_s2_window(
        close_df, open_df, turnover_df, bench_df, mult_df, adj_close, med_turnover, seasoning,
        oos_start, oos_end, 90, 150, 1.0,
        exit_sma_cache=exit_sma_cache, mom_cache=mom_cache,
    )
    ctrl_b = p5.simulate_control_b_equal_weight_top100(adj_close, turnover_df, oos_start, oos_end)
    ctrl_a = p5.simulate_control_a_monte_carlo(close_df, turnover_df, bench_df, oos_start, oos_end, n_iterations=1000)

    b_tri = bench_df.loc[oos_start:oos_end, "tri_close"]
    b_years = max((b_tri.index[-1] - b_tri.index[0]).days / 365.25, 0.1)
    b_cagr = round(((b_tri.iloc[-1] / b_tri.iloc[0]) ** (1.0 / b_years) - 1.0) * 100.0, 2)

    # 4. H4 DSR (N=88)
    dsr = GateEvaluator.compute_deflated_sharpe(
        sharpe=wf_1x["sharpe_ratio"],
        num_trials=88,
        num_observations=len(stitched_ret_1x),
        skewness=wf_1x["skewness"],
        kurtosis=wf_1x["kurtosis"],
        var_sharpe=0.15,
        annualized=True,
    )

    # 5. H7 Subperiod Stability (4 equal segments of 2013-2022)
    eq_wf = wf_1x["equity_curve"]
    seg_len = len(eq_wf) // 4
    pos_segs = 0
    for s_idx in range(4):
        seg = eq_wf.iloc[s_idx * seg_len : (s_idx + 1) * seg_len if s_idx < 3 else len(eq_wf)]
        b_seg = b_tri.loc[seg.index[0]:seg.index[-1]]
        s_ret = (seg.iloc[-1] / seg.iloc[0]) - 1.0
        b_ret = (b_seg.iloc[-1] / b_seg.iloc[0]) - 1.0
        if s_ret > b_ret:
            pos_segs += 1

    # 6. H8 Plateau at +-20% on 2013-2022
    h8_all_pass = True
    for lb90, sma_w, t_sc in [
        (72, 150, 1.0), (108, 150, 1.0),
        (90, 120, 1.0), (90, 180, 1.0),
        (90, 150, 0.8), (90, 150, 1.2),
    ]:
        r_p = simulate_s2_window(
            close_df, open_df, turnover_df, bench_df, mult_df, adj_close, med_turnover, seasoning,
            oos_start, oos_end, lb90, sma_w, t_sc,
            exit_sma_cache=exit_sma_cache, mom_cache=mom_cache,
        )
        if r_p["sharpe_ratio"] < 0.70:
            h8_all_pass = False

    # 7. W3 Top-5 OOS Trades Removed
    top5_oos = sorted(oos_trades_all, key=lambda x: x["return_pct"], reverse=True)[:5]
    top5_oos_keys = {(t["symbol"], t["entry_date"]) for t in top5_oos}
    # Re-run each fold with top5_oos_keys blocked
    oos_no_top5_rets = []
    for f_row in fold_rows:
        yr = f_row["test_year"]
        r_nt5 = simulate_s2_window(
            close_df, open_df, turnover_df, bench_df, mult_df, adj_close, med_turnover, seasoning,
            f"{yr}-01-01", f"{yr}-12-31",
            f_row["chosen_lb90"], f_row["chosen_sma"], f_row["chosen_trail_scale"],
            blocked_entries=top5_oos_keys,
        )
        oos_no_top5_rets.append(r_nt5["daily_returns"])
    wf_no_top5 = metrics_from_daily_returns(pd.concat(oos_no_top5_rets).sort_index())

    # 8. W4 Settings Stability (each knob moves > 1 step in < 3 of 10 folds)
    big_jumps = [0, 0, 0]
    for idx_t in range(1, len(chosen_indices)):
        for k in range(3):
            if abs(chosen_indices[idx_t][k] - chosen_indices[idx_t - 1][k]) > 1:
                big_jumps[k] += 1
    w4_pass = all(j < 3 for j in big_jumps)

    # 9. Evaluate 13 Checks
    w1_count = sum(1 for r in fold_rows if r["wf_efficiency"] >= 0.50)
    checks = {
        "H1_Return": {"passed": bool(wf_1x["cagr_pct"] >= b_cagr + 4.0), "val": f"{wf_1x['cagr_pct']}% vs {b_cagr+4.0:.2f}%"},
        "H2_Sharpe": {"passed": bool(wf_1x["sharpe_ratio"] >= 0.80), "val": wf_1x["sharpe_ratio"]},
        "H3_Drawdown": {"passed": bool(wf_1x["max_drawdown_pct"] >= -35.0), "val": f"{wf_1x['max_drawdown_pct']}%"},
        "H4_DSR_N88": {"passed": bool(dsr >= 0.95), "val": round(dsr, 4)},
        "H5_Control_A": {"passed": bool(wf_1x["sharpe_ratio"] > ctrl_a["p95_sharpe"]), "val": f"{wf_1x['sharpe_ratio']} > {ctrl_a['p95_sharpe']}"},
        "H6_Control_B": {"passed": bool(wf_1x["cagr_pct"] > ctrl_b["cagr_pct"] and wf_1x["sharpe_ratio"] > ctrl_b["sharpe_ratio"]), "val": f"{wf_1x['cagr_pct']}%/{wf_1x['sharpe_ratio']} vs {ctrl_b['cagr_pct']}%/{ctrl_b['sharpe_ratio']}"},
        "H7_Stability": {"passed": bool(pos_segs >= 3), "val": f"{pos_segs}/4"},
        "H8_Plateau": {"passed": bool(h8_all_pass), "val": h8_all_pass},
        "H9_Cost_Stress_2x": {"passed": bool(wf_2x["cagr_pct"] >= b_cagr + 2.0 and wf_2x["sharpe_ratio"] >= 0.70), "val": f"{wf_2x['cagr_pct']}% / Sh={wf_2x['sharpe_ratio']}"},
        "W1_Efficiency": {"passed": bool(w1_count >= 7), "val": f"{w1_count}/10"},
        "W2_Beats_Fixed": {"passed": bool(wf_1x["sharpe_ratio"] >= fixed_s2["sharpe_ratio"]), "val": f"{wf_1x['sharpe_ratio']} vs {fixed_s2['sharpe_ratio']}"},
        "W3_Top5_Removed": {"passed": bool(wf_no_top5["cagr_pct"] >= b_cagr + 4.0), "val": f"{wf_no_top5['cagr_pct']}% vs {b_cagr+4.0:.2f}%"},
        "W4_Settings_Stability": {"passed": bool(w4_pass), "val": f"jumps={big_jumps}"},
    }

    all_passed = all(c["passed"] for c in checks.values())
    only_h4_failed = (not checks["H4_DSR_N88"]["passed"]) and all(v["passed"] for k, v in checks.items() if k != "H4_DSR_N88")

    # 10. Holdout rule: ONLY open once if all_passed!
    holdout_res = {"status": "SEALED", "reason": "All 13 checks did not pass."}
    if all_passed:
        ho = simulate_s2_window(
            close_df, open_df, turnover_df, bench_df, mult_df, adj_close, med_turnover, seasoning,
            "2023-01-01", "2024-07-05", 90, 150, 1.0
        )
        holdout_res = {
            "status": "OPENED_ONCE_ALL_PASS",
            "cagr_pct": float(ho["cagr_pct"]),
            "sharpe_ratio": float(ho["sharpe_ratio"]),
            "max_drawdown_pct": float(ho["max_drawdown_pct"]),
        }

    out = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "protocol_sha256": proto_sha,
        "panel_version": "NSE_PANEL_V2",
        "panel_sha256": panel_sha,
        "multi_testing_n": 88,
        "stitched_oos_2013_2022": {k: v for k, v in wf_1x.items() if k != "equity_curve"},
        "stitched_oos_2x_costs": {k: v for k, v in wf_2x.items() if k != "equity_curve"},
        "stitched_oos_top5_removed": {k: v for k, v in wf_no_top5.items() if k != "equity_curve"},
        "baselines_2013_2022": {
            "fixed_s2": {k: v for k, v in fixed_s2.items() if k not in ("daily_returns", "equity_curve", "trade_log")},
            "control_a": {"p95_sharpe": ctrl_a["p95_sharpe"], "median_sharpe": ctrl_a["median_sharpe"]},
            "control_b_adj": ctrl_b,
            "benchmark_tri_cagr_pct": b_cagr,
        },
        "per_fold_table": fold_rows,
        "checks_13": checks,
        "all_13_passed": all_passed,
        "only_h4_failed": only_h4_failed,
        "holdout": holdout_res,
    }
    with open(WF_RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    # Log N=88 trial rows
    commit_hash = p5.get_git_commit_hash()[:7]
    log_trial(
        commit_hash=commit_hash,
        script="run_nse_s2_walk_forward.py",
        universe="NSE_WHOLE_MARKET_WF_2013_2022",
        kelly_fraction=0.08,
        lookback_days=90,
        cagr_pct=float(fixed_s2["cagr_pct"]),
        max_drawdown_pct=float(fixed_s2["max_drawdown_pct"]),
        sharpe_ratio=float(fixed_s2["sharpe_ratio"]),
        is_holdout_opened=False,
        notes=f"WF Baseline Fixed S2 (2013-2022, N=87, PanelSHA={panel_sha[:12]}, ProtoSHA={proto_sha[:12]})",
    )
    log_trial(
        commit_hash=commit_hash,
        script="run_nse_s2_walk_forward.py",
        universe="NSE_WHOLE_MARKET_WF_2013_2022",
        kelly_fraction=0.08,
        lookback_days=90,
        cagr_pct=wf_1x["cagr_pct"],
        max_drawdown_pct=wf_1x["max_drawdown_pct"],
        sharpe_ratio=wf_1x["sharpe_ratio"],
        is_holdout_opened=all_passed,
        notes=f"WF Stitched OOS S2 (2013-2022, N=88, DSR={dsr:.4f}, PanelSHA={panel_sha[:12]}, ProtoSHA={proto_sha[:12]})",
    )

    print("\n--- 13 CHECKS SUMMARY ---")
    for k, v in checks.items():
        print(f"  {k:22s}: {'PASS' if v['passed'] else 'FAIL'} ({v['val']})")
    print(f"\nSaved Walk-Forward results to {WF_RESULTS_JSON}")


if __name__ == "__main__":
    main()
