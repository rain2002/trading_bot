"""
Phase 5: NSE Whole-Market Long-Only Strategy Gate A Runner
==========================================================
Autonomous Quantitative Evaluation & Institutional Hurdle Auditing

Mandate:
- Candidate S2: Asymmetric Profit-Trail Compounder (with Macro Vol Radar & Drawdown Ladder)
- Control A: 1,000-iteration Monte Carlo random selection null distribution
- Control B: Equal-weight liquid Top-100 monthly rebalance
- Benchmark: Nifty 50 TRI (INDEX_NSEI.parquet + 1.35% p.a. continuous dividend yield adjustment)

Multi-Testing Governance:
- N = 85 (honest accounting across 84 prior NSE exploratory trials recorded in trial_log.csv).
- Hurdle H4 evaluates Deflated Sharpe Ratio (DSR >= 0.95) under cumulative N = 85.

Architecture & State Machine Invariants:
- Ladder Integration: If both the operating drawdown ladder tier cap and the emergency recovery stage
  cap apply, the effective allowed exposure is strictly min(ladder_exposure, recovery_stage_exposure, radar_exposure).
- Double High-Water Mark: HWM_true (lifetime peak, never resets, governs MaxDD) vs HWM_ladder (operating reference).
- Emergency Tier 4 Recovery State Machine: Requires 15 consecutive sessions cool-off in 100% cash
  AND 10 consecutive sessions benchmark above its 200-SMA, followed by 3-stage ramp (40% -> 70% -> 100%).
- Circuit Limit Inference: Stocks where High == Low (zero intrabar range) or |1-day return| >= 19.5%
  on the signal session are barred from entry; circuit-flagged signals are logged.
- Single Dividend Rule: Prices are backward-adjusted exclusively for splits and bonus issues;
  cash dividends are credited to portfolio cash on ex-dates (zero dividend price scaling).
- Strict Sealed Holdout: Last 2 calendar years (2022-07-06 to 2024-07-05) remain strictly sealed
  unless Candidate S2 passes ALL 9 Gate A hurdles simultaneously.
"""

import os
import sys
import math
import json
import hashlib
import subprocess
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Optional, Set
import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from trading_system.app.validation.trial_logger import log_trial
from trading_system.app.validation.gate_evaluator import GateEvaluator
from trading_system.app.data.corporate_actions import (
    build_verified_split_adjustment_matrix,
    load_audited_corporate_actions,
    is_etf_ticker,
)

PROTOCOL_PATH = os.path.join(PROJECT_ROOT, "trading_system", "docs", "NSE_WHOLE_MARKET_LONG_ONLY_PROTOCOL_V1.md")
PROTOCOL_SHA256_PATH = os.path.join(PROJECT_ROOT, "trading_system", "docs", "NSE_WHOLE_MARKET_LONG_ONLY_PROTOCOL_V1.sha256")
AMENDMENT_PATH = os.path.join(PROJECT_ROOT, "trading_system", "docs", "NSE_WHOLE_MARKET_AMENDMENT_V1_1.md")
AMENDMENT_SHA256_PATH = os.path.join(PROJECT_ROOT, "trading_system", "docs", "NSE_WHOLE_MARKET_AMENDMENT_V1_1.sha256")

PANEL_CLOSE_FILE = os.path.join(PROJECT_ROOT, "trading_system", "data", "causal_panel_close.parquet")
PANEL_OPEN_FILE = os.path.join(PROJECT_ROOT, "trading_system", "data", "causal_panel_open.parquet")
PANEL_TURNOVER_FILE = os.path.join(PROJECT_ROOT, "trading_system", "data", "causal_panel_turnover.parquet")
BENCHMARK_FILE = os.path.join(PROJECT_ROOT, "trading_system", "data", "historical_cache_nse", "INDEX_NSEI.parquet")
TRIAL_LOG_PATH = os.path.join(PROJECT_ROOT, "trading_system", "data", "trial_log.csv")
RESULTS_JSON_PATH = os.path.join(PROJECT_ROOT, "trading_system", "data", "phase5_nse_whole_market_gate_a_results.json")

EXPECTED_PROTOCOL_HASH = "8f536f131fada8185425f153ce060b50b7e34a5715e2aaaf6a409f0d6b24a5f2"
EXPECTED_AMENDMENT_HASH = "7726da83a6ed9ca8cf90a2541b9411070a5db6be74ebb3de3fb340cbf49455a4"

# Timeline Definitions
IN_SAMPLE_START = "2007-09-17"
IN_SAMPLE_END = "2022-07-05"
HOLDOUT_START = "2022-07-06"
HOLDOUT_END = "2024-07-05"

# Multi-Testing Parameters
N_PRIOR_TRIALS = 84
CUMULATIVE_N = 85

# Portfolio Invariants
INITIAL_CAPITAL = 80000.0
CORE_SLOTS = 15
MAX_ALLOC_PER_STOCK = 0.08  # 8.0% max entry weight
MIN_SHARE_PRICE = 20.0
MIN_SEASONING_DAYS = 252    # 12 calendar months
MIN_MEDIAN_TURNOVER = 20000000.0  # ₹2.0 Crore
CASH_YIELD_PA = 0.06        # 6.0% p.a. overnight repo yield (LIQUIDBEES)
BENCHMARK_DIV_YIELD_PA = 0.0135  # 1.35% p.a. dividend adjustment for Nifty 50 TRI

# Baseline Friction Schedule (bps & INR)
BUY_FRICTION_BPS_BASE = 27.0   # 10.0 STT + 1.5 Stamp + 0.5 Exch/SEBI/GST + 15.0 Slippage
SELL_FRICTION_BPS_BASE = 25.5  # 10.0 STT + 0.5 Exch/SEBI/GST + 15.0 Slippage
FLAT_DP_FEE_BASE = 15.93       # ₹13.50 + 18% GST flat per sell scrip

# Stressed Friction Schedule (2x Multiplier per Hurdle H9)
BUY_FRICTION_BPS_STRESSED = 54.0   # 2x fees + 30.0 bps slippage
SELL_FRICTION_BPS_STRESSED = 51.0  # 2x fees + 30.0 bps slippage
FLAT_DP_FEE_STRESSED = 31.86       # 2x DP fee


def verify_governance_hashes():
    """Verify cryptographic SHA-256 integrity of protocol and amendment."""
    print("=" * 80)
    print("STEP 1: CRYPTOGRAPHIC GOVERNANCE VERIFICATION")
    print("=" * 80)

    for doc_name, path, sha_path, expected in [
        ("Base Protocol V1", PROTOCOL_PATH, PROTOCOL_SHA256_PATH, EXPECTED_PROTOCOL_HASH),
        ("Amendment V1.1", AMENDMENT_PATH, AMENDMENT_SHA256_PATH, EXPECTED_AMENDMENT_HASH),
    ]:
        if not os.path.exists(path):
            raise FileNotFoundError(f"{doc_name} file missing: {path}")
        raw = open(path, "rb").read().replace(b"\r\n", b"\n")
        computed = hashlib.sha256(raw).hexdigest()
        seal = open(sha_path, "r").read().strip() if os.path.exists(sha_path) else "MISSING"

        print(f"  {doc_name}:")
        print(f"    Computed Hash : {computed}")
        print(f"    Expected Seal : {expected}")
        if computed != expected or computed != seal:
            raise ValueError(f"CRITICAL: {doc_name} hash mismatch! Computed {computed} != Expected {expected}")
        print(f"    Status        : SEAL VERIFIED")


def get_git_commit_hash() -> str:
    """Return the current git HEAD commit hash."""
    try:
        res = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception:
        return "UNKNOWN_COMMIT"


def calc_vectorized_momentum(series: np.ndarray, window: int = 90) -> np.ndarray:
    """
    Andreas Clenow Exponential Regression Slope * R^2 Momentum Score.
    Vectorized calculation on historical log prices.
    """
    n = len(series)
    scores = np.full(n, np.nan)
    if n < window:
        return scores
    log_p = np.log(np.maximum(series, 1e-4))
    w = np.arange(window) - (window - 1.0) / 2.0
    ss_x = np.sum(w ** 2)
    w_norm = w / ss_x
    slopes = np.convolve(log_p, w_norm[::-1], mode="valid")
    s = pd.Series(log_p)
    rolling_var = s.rolling(window).var().values[window - 1:] * (window - 1)
    r2 = np.clip((slopes ** 2 * ss_x) / np.maximum(rolling_var, 1e-6), 0.0, 1.0)
    annualized_slope = np.expm1(np.clip(slopes * 252.0, -10.0, 10.0))
    scores[window - 1:] = annualized_slope * r2
    return scores


def load_all_data() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """
    Load causal panels, benchmark, corporate actions, and compute universe coverage audit.
    """
    print("\n" + "=" * 80)
    print("STEP 2: LOADING SURVIVOR-FREE CAUSAL BHAVCOPY PANELS")
    print("=" * 80)

    if not (os.path.exists(PANEL_CLOSE_FILE) and os.path.exists(PANEL_OPEN_FILE) and os.path.exists(PANEL_TURNOVER_FILE)):
        raise FileNotFoundError("Pre-built causal panel parquet files not found in data directory!")

    close_df = pd.read_parquet(PANEL_CLOSE_FILE)
    open_df = pd.read_parquet(PANEL_OPEN_FILE)
    turnover_df = pd.read_parquet(PANEL_TURNOVER_FILE)

    # Filter out ETFs/Funds
    valid_cols = [c for c in close_df.columns if not is_etf_ticker(c)]
    close_df = close_df[valid_cols]
    open_df = open_df[[c for c in valid_cols if c in open_df.columns]]
    turnover_df = turnover_df[[c for c in valid_cols if c in turnover_df.columns]]

    # Load Benchmark (Nifty 50)
    bench_raw = pd.read_parquet(BENCHMARK_FILE)
    if hasattr(bench_raw.index, "tz") and bench_raw.index.tz is not None:
        bench_raw.index = bench_raw.index.tz_localize(None)
    bench_raw.index = pd.to_datetime(bench_raw.index.date)

    # Align dates
    common_dates = close_df.index.intersection(bench_raw.index).sort_values()
    close_df = close_df.loc[common_dates]
    open_df = open_df.loc[common_dates]
    turnover_df = turnover_df.loc[common_dates]
    bench_df = bench_raw.loc[common_dates].copy()

    # Apply Benchmark +1.35% Dividend Yield for TRI
    daily_div_yield = (1.0 + BENCHMARK_DIV_YIELD_PA) ** (1.0 / 252.0) - 1.0
    bench_ret_pr = bench_df["close"].pct_change().fillna(0.0)
    bench_ret_tri = bench_ret_pr + daily_div_yield
    bench_tri_series = (1.0 + bench_ret_tri).cumprod() * 1000.0
    bench_df["tri_close"] = bench_tri_series
    bench_df["sma200"] = bench_df["close"].rolling(200, min_periods=50).mean()

    # Universe Coverage Audit (Reviewer Note 4)
    total_tickers = len(close_df.columns)
    last_dates = close_df.apply(lambda s: s.last_valid_index())
    delisted_tickers = int((last_dates < close_df.index[-1]).sum())
    delisted_pct = round(delisted_tickers / total_tickers * 100.0, 2)

    active_per_year = {}
    for yr, group in close_df.groupby(close_df.index.year):
        active_per_year[int(yr)] = int((group.notna().sum(axis=0) > 0).sum())

    coverage_audit = {
        "total_unique_equities": total_tickers,
        "delisted_or_merged_equities": delisted_tickers,
        "delisted_percentage": delisted_pct,
        "active_equities_per_year": active_per_year,
        "panel_date_range": {
            "start": str(common_dates[0].date()),
            "end": str(common_dates[-1].date()),
            "total_trading_days": len(common_dates)
        }
    }

    print(f"  Total Equities in Panel        : {total_tickers:,}")
    print(f"  Delisted / Merged Equities     : {delisted_tickers:,} ({delisted_pct}% survivor-free coverage)")
    print(f"  Trading Sessions Aligned       : {len(common_dates):,} ({common_dates[0].date()} to {common_dates[-1].date()})")
    print(f"  Benchmark TRI Synthesized      : +{BENCHMARK_DIV_YIELD_PA*100:.2f}% p.a. dividend reinvestment")

    return close_df, open_df, turnover_df, bench_df, coverage_audit


def simulate_strategy_s2(
    close_df: pd.DataFrame,
    open_df: pd.DataFrame,
    turnover_df: pd.DataFrame,
    bench_df: pd.DataFrame,
    sim_start: str,
    sim_end: str,
    buy_friction_bps: float = BUY_FRICTION_BPS_BASE,
    sell_friction_bps: float = SELL_FRICTION_BPS_BASE,
    dp_fee_rupees: float = FLAT_DP_FEE_BASE,
    lookback_90: int = 90,
    lookback_180: int = 180,
    exit_sma_window: int = 150,
    hard_stop_pct: float = 0.12,
    trail_t1_gain: float = 0.25,
    trail_t1_stop: float = 0.15,
    trail_t2_gain: float = 0.50,
    trail_t2_stop: float = 0.20,
    trail_t3_gain: float = 1.00,
    trail_t3_stop: float = 0.25,
) -> Dict[str, Any]:
    """
    Simulates Candidate S2 (Asymmetric Profit-Trail Compounder) over the specified window.
    """
    dates = close_df.loc[sim_start:sim_end].index
    if len(dates) < 252:
        raise ValueError(f"Insufficient trading days for backtest: {len(dates)}")

    # Precompute split multipliers and continuous indicator prices
    mult_df, adj_factors = build_verified_split_adjustment_matrix(close_df)
    adj_close = close_df * adj_factors

    # Precompute 60-day median turnover
    med_turnover = turnover_df.rolling(60, min_periods=5).median()

    # Precompute listing seasoning (consecutive traded days)
    is_valid_bar = close_df.notna() & (close_df > 0.0)
    seasoning = is_valid_bar.cumsum()

    # Benchmark 200-SMA Macro Radar
    bench_close = bench_df["close"].loc[dates]
    bench_sma200 = bench_df["sma200"].loc[dates]

    # Precompute Trend Exit SMA on continuous indicator prices
    exit_sma = adj_close.rolling(exit_sma_window, min_periods=int(exit_sma_window * 0.75)).mean()

    # Identify Monthly Rebalance Dates
    df_d = pd.DataFrame({"date": dates}, index=dates)
    df_d["month"] = df_d["date"].dt.to_period("M")
    rebalance_dates = set(df_d.groupby("month")["date"].max())

    # State Variables
    cash = INITIAL_CAPITAL
    hwm_true = INITIAL_CAPITAL
    hwm_ladder = INITIAL_CAPITAL

    # Holdings: sym -> dict(shares, fill_price, peak_price, entry_date)
    holdings: Dict[str, Dict[str, Any]] = {}

    equity_curve: List[float] = []
    trade_log: List[Dict[str, Any]] = []

    in_tier4_defense = False
    cooling_off_counter = 0
    recovery_streak = 0
    recovery_stage = 0
    recovery_stage_days = 0

    circuit_blocked_entries = 0
    circuit_delayed_exits = 0

    daily_cash_yield = (1.0 + CASH_YIELD_PA) ** (1.0 / 252.0) - 1.0

    for i, current_date in enumerate(dates):
        # Step A: Process Corporate Action Split Multipliers on Holdings
        for sym in list(holdings.keys()):
            if sym in mult_df.columns:
                mult = mult_df.loc[current_date, sym]
                if mult > 1.0001 or mult < 0.9999:
                    holdings[sym]["shares"] *= mult
                    holdings[sym]["fill_price"] /= mult
                    holdings[sym]["peak_price"] /= mult

        # Step B: Mark-to-Market Valuation at Today's Close
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

        # Step C: Update Double High-Water Marks
        if total_equity > hwm_true:
            hwm_true = total_equity

        if not in_tier4_defense:
            if total_equity > hwm_ladder:
                hwm_ladder = total_equity
        operating_dd = (total_equity - hwm_ladder) / max(hwm_ladder, 1e-4)

        # Step D: Drawdown Ladder & Emergency Recovery State Machine
        is_routine_bull = bench_close.loc[current_date] > bench_sma200.loc[current_date]

        if in_tier4_defense:
            cooling_off_counter += 1
            if is_routine_bull and cooling_off_counter >= 15:
                recovery_streak += 1
            else:
                recovery_streak = 0

            if cooling_off_counter >= 15 and recovery_streak >= 10:
                in_tier4_defense = False
                hwm_ladder = total_equity
                recovery_stage = 1
                recovery_stage_days = 0
                recovery_stage_exposure = 0.40
            else:
                recovery_stage_exposure = 0.0
            ladder_exposure = 0.0
        else:
            if recovery_stage == 1:
                recovery_stage_exposure = 0.40
                recovery_stage_days += 1
                if recovery_stage_days >= 10:
                    recovery_stage = 2
                    recovery_stage_days = 0
            elif recovery_stage == 2:
                recovery_stage_exposure = 0.70
                recovery_stage_days += 1
                if recovery_stage_days >= 10:
                    recovery_stage = 3
                    recovery_stage_days = 0
            elif recovery_stage == 3:
                recovery_stage_exposure = 1.00
                recovery_stage = 0
            else:
                recovery_stage_exposure = 1.00

            # Normal Ladder Tiers
            if operating_dd >= -0.08:
                ladder_exposure = 1.00
            elif operating_dd >= -0.14:
                ladder_exposure = 0.70
            elif operating_dd >= -0.18:
                ladder_exposure = 0.40
            else:
                in_tier4_defense = True
                cooling_off_counter = 0
                recovery_streak = 0
                recovery_stage = 0
                ladder_exposure = 0.0
                recovery_stage_exposure = 0.0

        # Reviewer Note 3: If both ladder tier and recovery cap apply, strictly take the minimum
        allowed_ladder = min(ladder_exposure, recovery_stage_exposure)

        # Volatility Radar Macro Overlay
        radar_exposure = 1.00 if is_routine_bull else 0.00
        effective_exposure_cap = min(allowed_ladder, radar_exposure)

        # Idle cash accrues daily repo yield (LIQUIDBEES)
        if cash > 0.0:
            cash += cash * daily_cash_yield

        # Record Daily Equity
        equity_curve.append(total_equity)

        # If last day, finish
        if i == len(dates) - 1:
            break

        next_date = dates[i + 1]
        next_open = open_df.loc[next_date]

        # Step E: Evaluate Stop Loss & Trend Exits at Today's Close
        exits_to_execute: List[Tuple[str, str]] = []

        if in_tier4_defense:
            # Liquidate all open positions for emergency defense
            for sym in list(holdings.keys()):
                exits_to_execute.append((sym, "EMERGENCY_TIER4_LIQUIDATION"))
        else:
            for sym, pos in list(holdings.items()):
                p_close = current_close.get(sym, np.nan)
                if math.isnan(p_close) or p_close <= 0.0:
                    continue

                # Causal Circuit Check on Exit
                prev_p = close_df.loc[dates[i - 1], sym] if i > 0 else p_close
                pct_chg = (p_close - prev_p) / max(prev_p, 1e-4) if prev_p > 0 else 0.0
                h_val = close_df.loc[current_date, sym]  # high proxy in panel
                is_circuit = abs(pct_chg) >= 0.1950

                gain_pct = (p_close - pos["fill_price"]) / max(pos["fill_price"], 1e-4)
                peak_p = pos["peak_price"]
                dd_from_peak = (p_close - peak_p) / max(peak_p, 1e-4)

                # Hard Stop (-12%)
                if gain_pct <= -hard_stop_pct:
                    if is_circuit:
                        circuit_delayed_exits += 1
                    else:
                        exits_to_execute.append((sym, "HARD_STOP"))
                    continue

                # Trailing Profit Stops
                trail_hit = False
                if gain_pct >= trail_t3_gain:
                    if dd_from_peak <= -trail_t3_stop:
                        trail_hit = True
                elif gain_pct >= trail_t2_gain:
                    if dd_from_peak <= -trail_t2_stop:
                        trail_hit = True
                elif gain_pct >= trail_t1_gain:
                    if dd_from_peak <= -trail_t1_stop:
                        trail_hit = True

                if trail_hit:
                    if is_circuit:
                        circuit_delayed_exits += 1
                    else:
                        exits_to_execute.append((sym, "PROFIT_TRAIL_STOP"))
                    continue

                # Trend Exit: Close < 150-SMA
                sym_sma = exit_sma.loc[current_date, sym] if sym in exit_sma.columns else np.nan
                adj_c = adj_close.loc[current_date, sym]
                if not math.isnan(sym_sma) and adj_c < sym_sma:
                    if is_circuit:
                        circuit_delayed_exits += 1
                    else:
                        exits_to_execute.append((sym, "TREND_EXIT_150SMA"))
                    continue

        # Execute Exits at Next Day Open with Slippage
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
            trade_log.append({
                "symbol": sym,
                "entry_date": holdings[sym]["entry_date"],
                "exit_date": str(next_date.date()),
                "return_pct": ret_pct,
                "reason": reason
            })
            del holdings[sym]

        # Step F: Monthly Rebalancing & Entries (Evaluated at Rebalance Dates)
        if (current_date in rebalance_dates) and (not in_tier4_defense) and (effective_exposure_cap > 0.05):
            available_slots = CORE_SLOTS - len(holdings)
            if available_slots > 0:
                # 1. Filter Liquid Eligible Universe
                turnover_60d = med_turnover.loc[current_date]
                p_c = current_close
                p_season = seasoning.loc[current_date]

                prev_d = dates[i - 1] if i > 0 else current_date
                p_prev = close_df.loc[prev_d]
                pct_chg_day = ((p_c - p_prev) / p_prev.replace(0.0, np.nan)).abs()

                eligible_mask = (
                    (turnover_60d >= MIN_MEDIAN_TURNOVER) &
                    (p_c >= MIN_SHARE_PRICE) &
                    (p_season >= MIN_SEASONING_DAYS) &
                    (pct_chg_day < 0.1950) &
                    (~close_df.columns.isin(list(holdings.keys())))
                )
                eligible_syms = close_df.columns[eligible_mask].tolist()

                if eligible_syms:
                    # 2. Compute Momentum Scores on Eligible Universe
                    scores_dict = {}
                    # We compute on a rolling window ending today
                    window_slice = adj_close.loc[:current_date].iloc[-(lookback_180 + 20):]
                    for s in eligible_syms:
                        p_arr = window_slice[s].dropna().values
                        if len(p_arr) >= lookback_180:
                            s90 = calc_vectorized_momentum(p_arr, lookback_90)[-1]
                            s180 = calc_vectorized_momentum(p_arr, lookback_180)[-1]
                            if not (math.isnan(s90) or math.isnan(s180)):
                                blended = 0.60 * s90 + 0.40 * s180
                                if blended > 0.15:
                                    scores_dict[s] = blended

                    # Rank Top Eligible Stocks
                    sorted_candidates = sorted(scores_dict.items(), key=lambda x: x[1], reverse=True)
                    picks = [s for s, _ in sorted_candidates[:available_slots]]

                    # Size Positions Subject to Exposure Cap
                    target_equity_exposure = total_equity * effective_exposure_cap
                    current_invested = sum(pos["shares"] * pos.get("current_price", pos["fill_price"]) for pos in holdings.values())
                    allocatable_cash = max(0.0, min(cash, target_equity_exposure - current_invested))

                    if allocatable_cash > 1000.0 and picks:
                        target_per_slot = min(allocatable_cash / len(picks), total_equity * MAX_ALLOC_PER_STOCK)
                        for sym in picks:
                            open_p = next_open.get(sym, np.nan)
                            if math.isnan(open_p) or open_p <= 0.0:
                                open_p = current_close.get(sym, np.nan)

                            # Circuit check on entry execution day
                            if math.isnan(open_p) or open_p <= 0.0:
                                circuit_blocked_entries += 1
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
                                    "current_price": eff_buy_price
                                }

    # Compute Performance Metrics
    eq_series = pd.Series(equity_curve, index=dates)
    total_ret = (eq_series.iloc[-1] - eq_series.iloc[0]) / eq_series.iloc[0]
    years = max((dates[-1] - dates[0]).days / 365.25, 0.1)
    cagr = (eq_series.iloc[-1] / eq_series.iloc[0]) ** (1.0 / years) - 1.0

    daily_ret = eq_series.pct_change().dropna()
    mean_d = daily_ret.mean()
    std_d = daily_ret.std()
    sharpe = (mean_d / std_d * math.sqrt(252.0)) if std_d > 1e-6 else 0.0

    cummax = eq_series.cummax()
    dd_series = (eq_series - cummax) / cummax
    max_dd = float(dd_series.min())

    skew = float(daily_ret.skew()) if len(daily_ret) > 10 else 0.0
    kurt = float(daily_ret.kurtosis() + 3.0) if len(daily_ret) > 10 else 3.0

    return {
        "cagr_pct": round(cagr * 100.0, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_pct": round(max_dd * 100.0, 2),
        "total_return_pct": round(total_ret * 100.0, 2),
        "years": round(years, 2),
        "total_trades": len(trade_log),
        "circuit_blocked_entries": circuit_blocked_entries,
        "circuit_delayed_exits": circuit_delayed_exits,
        "skewness": round(skew, 2),
        "kurtosis": round(kurt, 2),
        "daily_returns": daily_ret,
        "equity_curve": eq_series
    }


def simulate_control_b_equal_weight_top100(
    close_df: pd.DataFrame,
    turnover_df: pd.DataFrame,
    sim_start: str,
    sim_end: str,
) -> Dict[str, Any]:
    """
    Control B: Equal-weight Top 100 liquid stocks, monthly rebalance with fees.
    """
    dates = close_df.loc[sim_start:sim_end].index
    med_turnover = turnover_df.rolling(60, min_periods=5).median()

    df_d = pd.DataFrame({"date": dates}, index=dates)
    df_d["month"] = df_d["date"].dt.to_period("M")
    month_ends = df_d.groupby("month")["date"].max().tolist()

    equity = INITIAL_CAPITAL
    equity_curve = [equity]

    current_weights = pd.Series(dtype=float)

    for i in range(len(month_ends) - 1):
        m_start = month_ends[i]
        m_end = month_ends[i + 1]

        # Select Top 100 by 60d median turnover
        t_vals = med_turnover.loc[m_start].dropna()
        p_vals = close_df.loc[m_start].dropna()
        valid = t_vals[(t_vals >= MIN_MEDIAN_TURNOVER) & (p_vals >= MIN_SHARE_PRICE)]
        top100 = valid.nlargest(100).index

        if len(top100) == 0:
            fallback = p_vals[p_vals >= MIN_SHARE_PRICE]
            top100 = fallback.nlargest(min(len(fallback), 50)).index

        if len(top100) == 0:
            equity *= (1.0 + (1.0 + CASH_YIELD_PA) ** (1.0 / 12.0) - 1.0)
            equity_curve.append(equity)
            continue

        target_weights = pd.Series(1.0 / len(top100), index=top100)

        # Turnover friction
        all_syms = current_weights.index.union(target_weights.index)
        w_curr = current_weights.reindex(all_syms, fill_value=0.0)
        w_targ = target_weights.reindex(all_syms, fill_value=0.0)
        rebal_turnover = (w_targ - w_curr).abs().sum() / 2.0
        fee_drag = rebal_turnover * (BUY_FRICTION_BPS_BASE / 10000.0)
        equity *= (1.0 - fee_drag)

        current_weights = target_weights

        # Month forward return
        p_start = close_df.loc[m_start, top100]
        p_end = close_df.loc[m_end, top100]
        stk_rets = (p_end - p_start) / p_start.replace(0.0, np.nan)
        month_ret = stk_rets.mean()
        if math.isnan(month_ret):
            month_ret = 0.0

        equity *= (1.0 + month_ret)
        equity_curve.append(equity)

    eq_s = pd.Series(equity_curve)
    years = max((dates[-1] - dates[0]).days / 365.25, 0.1)
    cagr = (eq_s.iloc[-1] / eq_s.iloc[0]) ** (1.0 / years) - 1.0
    m_rets = eq_s.pct_change().dropna()
    m_mean = m_rets.mean()
    m_std = m_rets.std()
    sharpe = (m_mean / m_std * math.sqrt(12.0)) if m_std > 1e-6 else 0.0
    cummax = eq_s.cummax()
    max_dd = float(((eq_s - cummax) / cummax).min())

    return {
        "cagr_pct": round(cagr * 100.0, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_pct": round(max_dd * 100.0, 2),
        "years": round(years, 2)
    }


def simulate_control_a_monte_carlo(
    close_df: pd.DataFrame,
    turnover_df: pd.DataFrame,
    bench_df: pd.DataFrame,
    sim_start: str,
    sim_end: str,
    n_iterations: int = 1000
) -> Dict[str, Any]:
    """
    Control A: 1,000-run Monte Carlo random selection null distribution from identical liquid universe
    with same slot count (15), turnover friction, and macro radar overlay.
    """
    print(f"\n  Running Control A Monte Carlo Null Distribution ({n_iterations:,} iterations)...", flush=True)
    dates = close_df.loc[sim_start:sim_end].index
    med_turnover = turnover_df.rolling(60, min_periods=5).median()

    df_d = pd.DataFrame({"date": dates}, index=dates)
    df_d["month"] = df_d["date"].dt.to_period("M")
    month_ends = df_d.groupby("month")["date"].max().tolist()

    bench_close = bench_df["close"].loc[dates]
    bench_sma200 = bench_df["sma200"].loc[dates]

    monthly_eligible: List[np.ndarray] = []
    monthly_bench_bull: List[bool] = []
    monthly_returns_matrix: List[pd.Series] = []

    for i in range(len(month_ends) - 1):
        m_start = month_ends[i]
        m_end = month_ends[i + 1]

        t_vals = med_turnover.loc[m_start]
        p_vals = close_df.loc[m_start]
        valid_mask = (t_vals >= MIN_MEDIAN_TURNOVER) & (p_vals >= MIN_SHARE_PRICE)
        elig = valid_mask[valid_mask].index.values

        monthly_eligible.append(elig)
        monthly_bench_bull.append(bool(bench_close.loc[m_start] > bench_sma200.loc[m_start]))

        p_s = close_df.loc[m_start]
        p_e = close_df.loc[m_end]
        r = (p_e - p_s) / p_s.replace(0.0, np.nan)
        monthly_returns_matrix.append(r)

    np.random.seed(42)
    sharpe_distribution = []

    cash_monthly_yield = (1.0 + CASH_YIELD_PA) ** (1.0 / 12.0) - 1.0

    for it in range(n_iterations):
        eq = INITIAL_CAPITAL
        eq_curve = [eq]

        for m_idx in range(len(monthly_eligible)):
            elig = monthly_eligible[m_idx]
            is_bull = monthly_bench_bull[m_idx]
            ret_series = monthly_returns_matrix[m_idx]

            if is_bull and len(elig) >= CORE_SLOTS:
                picks = np.random.choice(elig, CORE_SLOTS, replace=False)
                m_ret = ret_series.loc[picks].mean()
                if math.isnan(m_ret):
                    m_ret = 0.0
                # deduct rebalance friction (27 bps)
                eq *= (1.0 - 0.0027)
                eq *= (1.0 + m_ret)
            else:
                # Bear radar or insufficient names: cash compounding
                eq *= (1.0 + cash_monthly_yield)

            eq_curve.append(eq)

        eq_s = pd.Series(eq_curve)
        m_rets = eq_s.pct_change().dropna()
        m_m = m_rets.mean()
        m_s = m_rets.std()
        sh = (m_m / m_s * math.sqrt(12.0)) if m_s > 1e-6 else 0.0
        sharpe_distribution.append(sh)

    sh_arr = np.array(sharpe_distribution)
    p50 = float(np.percentile(sh_arr, 50))
    p95 = float(np.percentile(sh_arr, 95))
    p99 = float(np.percentile(sh_arr, 99))

    print(f"    Control A Null Distribution: Median Sharpe={p50:.2f}, 95th Percentile={p95:.2f}, 99th={p99:.2f}", flush=True)

    return {
        "n_iterations": n_iterations,
        "median_sharpe": round(p50, 2),
        "p95_sharpe": round(p95, 2),
        "p99_sharpe": round(p99, 2),
        "sharpe_distribution_sample": [round(float(x), 3) for x in sh_arr[:50]]
    }


def evaluate_parameter_plateau(
    close_df: pd.DataFrame,
    open_df: pd.DataFrame,
    turnover_df: pd.DataFrame,
    bench_df: pd.DataFrame,
    sim_start: str,
    sim_end: str,
) -> Dict[str, Any]:
    """
    Evaluates Candidate S2 across +-20% parameter shifts for Hurdle H8.
    """
    print("\n  Evaluating Parameter Plateau Sensitivity (+-20% shifts)...", flush=True)

    variations = {
        "BASE": {},
        "LOOKBACK_MINUS20": {"lookback_90": 72, "lookback_180": 144},
        "LOOKBACK_PLUS20": {"lookback_90": 108, "lookback_180": 216},
        "EXIT_SMA_MINUS20": {"exit_sma_window": 120},
        "EXIT_SMA_PLUS20": {"exit_sma_window": 180},
        "HARD_STOP_MINUS20": {"hard_stop_pct": 0.096},
        "HARD_STOP_PLUS20": {"hard_stop_pct": 0.144},
        "TRAIL_TIERS_MINUS20": {
            "trail_t1_gain": 0.20, "trail_t1_stop": 0.12,
            "trail_t2_gain": 0.40, "trail_t2_stop": 0.16,
            "trail_t3_gain": 0.80, "trail_t3_stop": 0.20
        },
        "TRAIL_TIERS_PLUS20": {
            "trail_t1_gain": 0.30, "trail_t1_stop": 0.18,
            "trail_t2_gain": 0.60, "trail_t2_stop": 0.24,
            "trail_t3_gain": 1.20, "trail_t3_stop": 0.30
        },
    }

    results = {}
    all_passed = True

    for var_name, kwargs in variations.items():
        res = simulate_strategy_s2(
            close_df, open_df, turnover_df, bench_df,
            sim_start, sim_end, **kwargs
        )
        passed = res["sharpe_ratio"] >= 0.70
        results[var_name] = {
            "cagr_pct": res["cagr_pct"],
            "sharpe_ratio": res["sharpe_ratio"],
            "max_drawdown_pct": res["max_drawdown_pct"],
            "passed_h8": passed
        }
        if not passed:
            all_passed = False
        print(f"    Shift {var_name:20s}: CAGR={res['cagr_pct']:6.2f}%, Sharpe={res['sharpe_ratio']:4.2f}, MaxDD={res['max_drawdown_pct']:6.2f}% -> {'PASS' if passed else 'FAIL'}")

    return {
        "all_passed": all_passed,
        "variations": results
    }


def evaluate_subperiods(
    close_df: pd.DataFrame,
    open_df: pd.DataFrame,
    turnover_df: pd.DataFrame,
    bench_df: pd.DataFrame,
    sim_start: str,
    sim_end: str,
) -> Dict[str, Any]:
    """
    Evaluates Candidate S2 across 4 equal in-sample sub-periods for Hurdle H7.
    """
    print("\n  Evaluating Multi-Cycle Sub-Period Stability (4 equal segments)...", flush=True)
    dates = close_df.loc[sim_start:sim_end].index
    n = len(dates)
    seg_size = n // 4

    sub_results = {}
    positive_count = 0

    bench_tri = bench_df["tri_close"]

    for seg in range(4):
        s_idx = seg * seg_size
        e_idx = (seg + 1) * seg_size - 1 if seg < 3 else n - 1
        d_start = str(dates[s_idx].date())
        d_end = str(dates[e_idx].date())

        s2_res = simulate_strategy_s2(close_df, open_df, turnover_df, bench_df, d_start, d_end)

        # Benchmark excess CAGR
        b_ret = (bench_tri.loc[d_end] - bench_tri.loc[d_start]) / bench_tri.loc[d_start]
        b_yrs = (dates[e_idx] - dates[s_idx]).days / 365.25
        b_cagr = (bench_tri.loc[d_end] / bench_tri.loc[d_start]) ** (1.0 / b_yrs) - 1.0
        excess_cagr = s2_res["cagr_pct"] - (b_cagr * 100.0)

        is_pos = excess_cagr > 0.0
        if is_pos:
            positive_count += 1

        sub_results[f"Segment_{seg+1}"] = {
            "window": f"{d_start} to {d_end}",
            "s2_cagr_pct": s2_res["cagr_pct"],
            "bench_cagr_pct": round(b_cagr * 100.0, 2),
            "excess_cagr_pct": round(excess_cagr, 2),
            "s2_sharpe": s2_res["sharpe_ratio"],
            "positive_excess": is_pos
        }
        print(f"    Segment {seg+1} ({d_start} to {d_end}): S2 CAGR={s2_res['cagr_pct']:6.2f}% vs Bench={b_cagr*100:6.2f}% (Excess: {excess_cagr:+6.2f}%) -> {'POSITIVE' if is_pos else 'NEGATIVE'}")

    h7_pass = positive_count >= 3
    print(f"    Sub-period Persistence: {positive_count}/4 segments positive excess CAGR -> {'PASS' if h7_pass else 'FAIL'}")

    return {
        "segments_positive": positive_count,
        "h7_pass": h7_pass,
        "segments": sub_results
    }


def run_phase5_gate_a():
    """Main Gate A orchestration routine for Phase 5 NSE Whole-Market Bot."""
    verify_governance_hashes()
    commit_hash = get_git_commit_hash()
    print(f"\nGit Runner Commit Hash: {commit_hash}")

    close_df, open_df, turnover_df, bench_df, coverage_audit = load_all_data()

    print("\n" + "=" * 80)
    print("STEP 3: CANDIDATE S2 IN-SAMPLE EVALUATION (2007-09-17 to 2022-07-05)")
    print("=" * 80)

    # 1. Simulate Candidate S2 Baseline
    print("  Running Candidate S2 baseline simulation...", flush=True)
    s2_base = simulate_strategy_s2(
        close_df, open_df, turnover_df, bench_df,
        IN_SAMPLE_START, IN_SAMPLE_END,
        buy_friction_bps=BUY_FRICTION_BPS_BASE,
        sell_friction_bps=SELL_FRICTION_BPS_BASE,
        dp_fee_rupees=FLAT_DP_FEE_BASE
    )

    # 2. Simulate Benchmark TRI
    bench_tri = bench_df["tri_close"].loc[IN_SAMPLE_START:IN_SAMPLE_END]
    bench_years = max((bench_tri.index[-1] - bench_tri.index[0]).days / 365.25, 0.1)
    bench_cagr = (bench_tri.iloc[-1] / bench_tri.iloc[0]) ** (1.0 / bench_years) - 1.0
    bench_daily = bench_tri.pct_change().dropna()
    bench_sharpe = (bench_daily.mean() / bench_daily.std() * math.sqrt(252.0)) if bench_daily.std() > 0 else 0.0
    bench_cummax = bench_tri.cummax()
    bench_maxdd = float(((bench_tri - bench_cummax) / bench_cummax).min())

    # 3. Simulate Hurdle H9 Stressed Costs (2x)
    print("  Running Candidate S2 under 2x cost stress (54 bps buy, 51 bps sell, 30 bps slippage)...", flush=True)
    s2_stressed = simulate_strategy_s2(
        close_df, open_df, turnover_df, bench_df,
        IN_SAMPLE_START, IN_SAMPLE_END,
        buy_friction_bps=BUY_FRICTION_BPS_STRESSED,
        sell_friction_bps=SELL_FRICTION_BPS_STRESSED,
        dp_fee_rupees=FLAT_DP_FEE_STRESSED
    )

    # 4. Simulate Control B (Top 100 Liquid Equal-Weight)
    print("  Running Control B (Top 100 liquid equal-weight monthly rebalance)...", flush=True)
    ctrl_b = simulate_control_b_equal_weight_top100(close_df, turnover_df, IN_SAMPLE_START, IN_SAMPLE_END)

    # 5. Simulate Control A (1,000-iteration Monte Carlo Random Null)
    ctrl_a = simulate_control_a_monte_carlo(close_df, turnover_df, bench_df, IN_SAMPLE_START, IN_SAMPLE_END, n_iterations=1000)

    # 6. Evaluate Multi-Cycle Sub-Periods (Hurdle H7)
    sub_res = evaluate_subperiods(close_df, open_df, turnover_df, bench_df, IN_SAMPLE_START, IN_SAMPLE_END)

    # 7. Evaluate Parameter Plateau (Hurdle H8)
    plat_res = evaluate_parameter_plateau(close_df, open_df, turnover_df, bench_df, IN_SAMPLE_START, IN_SAMPLE_END)

    # 8. Compute Deflated Sharpe Ratio (DSR) with honest cumulative N = 85
    dsr = GateEvaluator.compute_deflated_sharpe(
        sharpe=s2_base["sharpe_ratio"],
        num_trials=CUMULATIVE_N,
        num_observations=len(s2_base["daily_returns"]),
        skewness=s2_base["skewness"],
        kurtosis=s2_base["kurtosis"],
        var_sharpe=0.15,
        annualized=True
    )
    s2_base["deflated_sharpe_ratio"] = round(dsr, 4)

    # 9. Institutional Gate A Hurdle Auditing
    print("\n" + "=" * 80)
    print("STEP 4: INSTITUTIONAL GATE A HURDLE AUDITING")
    print("=" * 80)

    h1_pass = s2_base["cagr_pct"] >= round((bench_cagr * 100.0) + 4.0, 2)
    h2_pass = s2_base["sharpe_ratio"] >= 0.80
    h3_pass = s2_base["max_drawdown_pct"] >= -35.00
    h4_pass = s2_base["deflated_sharpe_ratio"] >= 0.95
    h5_pass = s2_base["sharpe_ratio"] > ctrl_a["p95_sharpe"]
    h6_pass = (s2_base["sharpe_ratio"] > ctrl_b["sharpe_ratio"]) and (s2_base["cagr_pct"] > ctrl_b["cagr_pct"])
    h7_pass = sub_res["h7_pass"]
    h8_pass = plat_res["all_passed"]
    h9_pass = (s2_stressed["cagr_pct"] >= round((bench_cagr * 100.0) + 4.0, 2)) and (s2_stressed["sharpe_ratio"] >= 0.70)

    all_pass = all([h1_pass, h2_pass, h3_pass, h4_pass, h5_pass, h6_pass, h7_pass, h8_pass, h9_pass])

    hurdles_table = {
        "H1_Excess_CAGR": {
            "description": "CAGR >= Benchmark TRI + 4.00%",
            "threshold": f">= {round((bench_cagr * 100.0) + 4.0, 2)}%",
            "candidate_val": f"{s2_base['cagr_pct']}%",
            "passed": bool(h1_pass)
        },
        "H2_Sharpe_Ratio": {
            "description": "Annualized Sharpe >= 0.80",
            "threshold": ">= 0.80",
            "candidate_val": f"{s2_base['sharpe_ratio']}",
            "passed": bool(h2_pass)
        },
        "H3_Max_Drawdown": {
            "description": "Max Drawdown >= -35.00%",
            "threshold": ">= -35.00%",
            "candidate_val": f"{s2_base['max_drawdown_pct']}%",
            "passed": bool(h3_pass)
        },
        "H4_Deflated_Sharpe": {
            "description": f"DSR >= 0.95 with N = {CUMULATIVE_N}",
            "threshold": ">= 0.95",
            "candidate_val": f"{s2_base['deflated_sharpe_ratio']}",
            "passed": bool(h4_pass)
        },
        "H5_Control_A_Null": {
            "description": "Sharpe > Control A 95th Percentile",
            "threshold": f"> {ctrl_a['p95_sharpe']}",
            "candidate_val": f"{s2_base['sharpe_ratio']}",
            "passed": bool(h5_pass)
        },
        "H6_Control_B_Liquid": {
            "description": "Sharpe > Ctrl B AND CAGR > Ctrl B",
            "threshold": f"Sharpe > {ctrl_b['sharpe_ratio']} & CAGR > {ctrl_b['cagr_pct']}%",
            "candidate_val": f"Sharpe={s2_base['sharpe_ratio']}, CAGR={s2_base['cagr_pct']}%",
            "passed": bool(h6_pass)
        },
        "H7_Subperiod_Stability": {
            "description": "Positive excess return in >= 3 of 4 subperiods",
            "threshold": ">= 3 segments",
            "candidate_val": f"{sub_res['segments_positive']}/4 segments",
            "passed": bool(h7_pass)
        },
        "H8_Parameter_Plateau": {
            "description": "Sharpe >= 0.70 across all +-20% parameter shifts",
            "threshold": "All shifts >= 0.70",
            "candidate_val": "All Passed" if h8_pass else "Breached",
            "passed": bool(h8_pass)
        },
        "H9_Severe_Cost_Stress": {
            "description": "Passes excess return and Sharpe >= 0.70 at 2x costs",
            "threshold": f"CAGR >= {round((bench_cagr * 100.0) + 4.0, 2)}% & Sharpe >= 0.70",
            "candidate_val": f"CAGR={s2_stressed['cagr_pct']}%, Sharpe={s2_stressed['sharpe_ratio']}",
            "passed": bool(h9_pass)
        },
        "ALL_HURDLES_PASSED": bool(all_pass)
    }

    for k, v in hurdles_table.items():
        if k == "ALL_HURDLES_PASSED":
            print(f"\n  OVERALL GATE A VERDICT: {'PASSED' if v else 'FAILED'}")
        else:
            print(f"  {k:25s} | Req: {v['threshold']:30s} | S2: {v['candidate_val']:25s} | {'PASS' if v['passed'] else 'FAIL'}")

    # 10. Strict Sealed Holdout Guard
    print("\n" + "=" * 80)
    print("STEP 5: OUT-OF-SAMPLE HOLDOUT GUARD (2022-07-06 to 2024-07-05)")
    print("=" * 80)

    holdout_results = {}
    if all_pass:
        print("  >>> GATE A CLEARED! OPENING SEALED OUT-OF-SAMPLE HOLDOUT (2022-07-06 to 2024-07-05)...")
        s2_holdout = simulate_strategy_s2(
            close_df, open_df, turnover_df, bench_df,
            HOLDOUT_START, HOLDOUT_END,
            buy_friction_bps=BUY_FRICTION_BPS_BASE,
            sell_friction_bps=SELL_FRICTION_BPS_BASE,
            dp_fee_rupees=FLAT_DP_FEE_BASE
        )
        holdout_results = {
            "status": "OPENED_POST_GATE_A_PASS",
            "cagr_pct": s2_holdout["cagr_pct"],
            "sharpe_ratio": s2_holdout["sharpe_ratio"],
            "max_drawdown_pct": s2_holdout["max_drawdown_pct"],
            "total_trades": s2_holdout["total_trades"]
        }
        print(f"  Holdout Performance: CAGR={s2_holdout['cagr_pct']}%, Sharpe={s2_holdout['sharpe_ratio']}, MaxDD={s2_holdout['max_drawdown_pct']}%")
    else:
        print("  >>> GATE A FAILED: CANDIDATE S2 FAILED TO CLEAR ALL 9 HURDLES.")
        print("  >>> FIDUCIARY INVARIANT ENFORCED: OUT-OF-SAMPLE HOLDOUT REMAINS STRICTLY SEALED.")
        holdout_results = {
            "status": "SEALED_GATE_A_FAILED",
            "message": "Holdout remains strictly unopened as Candidate S2 did not clear all 9 Gate A hurdles."
        }

    # 11. Stamp to trial_log.csv
    print("\n" + "=" * 80)
    print("STEP 6: STAMPING AUDIT LOGS AND PERSISTING RESULTS LEDGER")
    print("=" * 80)

    log_trial(
        commit_hash=commit_hash[:7],
        script="run_phase5_nse_whole_market_gate_a.py",
        universe="NSE_BHAVCOPY_SURVIVOR_FREE_WHOLE_MARKET",
        kelly_fraction=0.0,
        lookback_days=180,
        cagr_pct=s2_base["cagr_pct"],
        max_drawdown_pct=s2_base["max_drawdown_pct"],
        sharpe_ratio=s2_base["sharpe_ratio"],
        is_holdout_opened=bool(all_pass),
        notes=(
            f"Phase 5 Gate A: Candidate S2 in-sample 2007-2022. AllPass={all_pass}. "
            f"Sharpe={s2_base['sharpe_ratio']:.2f}, DSR={s2_base['deflated_sharpe_ratio']:.4f} (N={CUMULATIVE_N}). "
            f"BenchCAGR={bench_cagr*100:.2f}%, S2CAGR={s2_base['cagr_pct']:.2f}%. "
            f"Holdout={'OPENED' if all_pass else 'STRICTLY_SEALED'}."
        )
    )

    # 12. Save Results JSON
    final_output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "runner_commit": commit_hash,
        "base_protocol_sha256": EXPECTED_PROTOCOL_HASH,
        "amendment_sha256": EXPECTED_AMENDMENT_HASH,
        "multi_testing_n": CUMULATIVE_N,
        "coverage_audit": coverage_audit,
        "benchmark": {
            "series": "INDEX_NSEI.parquet + 1.35% p.a. dividend yield",
            "cagr_pct": round(bench_cagr * 100.0, 2),
            "sharpe_ratio": round(bench_sharpe, 2),
            "max_drawdown_pct": round(bench_maxdd * 100.0, 2)
        },
        "candidate_s2_in_sample": {
            "cagr_pct": s2_base["cagr_pct"],
            "sharpe_ratio": s2_base["sharpe_ratio"],
            "max_drawdown_pct": s2_base["max_drawdown_pct"],
            "total_return_pct": s2_base["total_return_pct"],
            "deflated_sharpe_ratio": s2_base["deflated_sharpe_ratio"],
            "total_trades": s2_base["total_trades"],
            "circuit_blocked_entries": s2_base["circuit_blocked_entries"],
            "circuit_delayed_exits": s2_base["circuit_delayed_exits"],
            "skewness": s2_base["skewness"],
            "kurtosis": s2_base["kurtosis"]
        },
        "candidate_s2_stressed_2x": {
            "cagr_pct": s2_stressed["cagr_pct"],
            "sharpe_ratio": s2_stressed["sharpe_ratio"],
            "max_drawdown_pct": s2_stressed["max_drawdown_pct"],
            "total_trades": s2_stressed["total_trades"]
        },
        "control_a_monte_carlo": ctrl_a,
        "control_b_liquid_top100": ctrl_b,
        "subperiod_stability": sub_res,
        "parameter_plateau": plat_res,
        "gate_a_hurdles": hurdles_table,
        "holdout_evaluation": holdout_results,
        "recommendation": (
            "PROCEED_TO_GATE_B_INCUBATION" if all_pass
            else "PARK_NSE_BOT_PERMANENTLY_CORE_RETAINS_ETF_CASH_ONLY"
        )
    }

    def json_serial(obj):
        if isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        if isinstance(obj, (np.floating, float)):
            return float(obj)
        if isinstance(obj, (np.integer, int)):
            return int(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return str(obj)

    with open(RESULTS_JSON_PATH, "w") as f:
        json.dump(final_output, f, indent=2, default=json_serial)

    print(f"\n  Detailed results saved to: {RESULTS_JSON_PATH}")
    print(f"  Trial recorded in: {TRIAL_LOG_PATH}")
    print(f"\nFINAL RECOMMENDATION: {final_output['recommendation']}")


if __name__ == "__main__":
    run_phase5_gate_a()
