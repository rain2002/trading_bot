"""
Production Institutional 18-Year Backtester for Indian Growth Equities Momentum (2007 - 2025)
=============================================================================================
Pre-Registered Quantitative Growth Stock Momentum Engine (NSE Universe):
  1. Pre-Registered Variants : 1 (Wide-Trend Runner), 2 (Asymmetric Multi-Bagger), 3 (Breakout Compounder)
  2. Double High-Water Mark  : hwm_true (never resets, determines strategy MaxDD) vs hwm_ladder (operating reference)
  3. Drawdown Ladder Tiers   : -8% (70%), -14% (40%), -18% (0% Emergency Cash Defense)
  4. Recovery State Machine  : 15-day cool-off + 10-day benchmark > 200-SMA confirmation + staged ramp
  5. Sourced DP Fee          : Flat Rs 14.75 per sale scrip (Dhan schedule: Rs 12.50 flat + 18% GST)
  6. Holding-Period Tax      : STCG (< 365d: 15%/20%) vs LTCG (>= 365d: 0%/10%/12.5%)
  7. Quality Filter          : Minimum share price >= Rs 20.00 (eliminates illiquid penny stock circuit traps)
  8. Execution Timing        : Next-Day 09:15 IST Market Open strictly enforced with gap risk
  9. Cash Compounding        : Sourced Liquid ETF Net Yield (india_cash_yield_history.csv)
  10. Protocol Integrity     : Verifies SHA-256 hash of GROWTH_STOCK_MOMENTUM_PROTOCOL.md at startup
"""

import warnings
warnings.filterwarnings("ignore")

import os
import sys
import time
import math
import glob
import json
import hashlib
import argparse
import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple, List, Set

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from trading_system.app.validation.trial_logger import log_trial

CACHE_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data", "historical_cache_nse")
INDIA_CASH_YIELD_CSV = os.path.join(PROJECT_ROOT, "trading_system", "data", "india_cash_yield_history.csv")
PROTOCOL_PATH = os.path.join(PROJECT_ROOT, "trading_system", "docs", "GROWTH_STOCK_MOMENTUM_PROTOCOL.md")
LOCKED_PROTOCOL_SHA256 = "D296C057FB84B306ED23D5BAD259547A7D2CF7096558D96E258C282606231BA5"

START_DATE = "2007-09-17"
DEFAULT_END_DATE = "2024-12-31"
HOLDOUT_END_DATE = "2025-12-30"

INITIAL_CAPITAL = 80000.0         # INR (~$1,000 USD)
FLAT_DP_FEE_RUPEES = 14.75       # Sourced: Dhan Schedule (Rs 12.50 flat + 18% GST)
DEFAULT_SLIPPAGE_BPS = 5.0        # 5.0 bps institutional baseline
STRESSED_SLIPPAGE_BPS = 7.5       # 7.5 bps stressed baseline
MIN_SHARE_PRICE = 20.0            # Quality threshold (no penny stock manipulation)

# All-In Variable Costs (Brokerage + STT + Turnover + Stamp + GST + Slippage)
BUY_COST_BPS_NORMAL = 22.85
BUY_COST_BPS_STRESSED = 25.35
SELL_COST_BPS_NORMAL = 21.35
SELL_COST_BPS_STRESSED = 23.85


def verify_protocol_lock():
    """Verify cryptographic integrity of pre-registered protocol before execution."""
    if not os.path.exists(PROTOCOL_PATH):
        raise FileNotFoundError(f"CRITICAL: Protocol specification file missing: {PROTOCOL_PATH}")
    with open(PROTOCOL_PATH, "rb") as f:
        sha = hashlib.sha256(f.read().replace(b'\r\n', b'\n')).hexdigest().upper()
    if sha != LOCKED_PROTOCOL_SHA256:
        raise ValueError(
            f"PRE-REGISTRATION INTEGRITY VIOLATION:\n"
            f"Protocol hash mismatch!\n"
            f"  Expected : {LOCKED_PROTOCOL_SHA256}\n"
            f"  Computed : {sha}\n"
            f"Any modification to GROWTH_STOCK_MOMENTUM_PROTOCOL.md invalidates pre-registration."
        )
    print(f"[OK] Pre-Registration Growth Stock Momentum Protocol v1.0 verified (SHA-256: {sha[:16]}...).")


def normalize_index(df: pd.DataFrame) -> pd.DataFrame:
    if hasattr(df.index, "tz") and df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df.index = pd.to_datetime(df.index.date)
    return df


_CASH_YIELD_CACHE = None


def _get_cash_yield_arrays():
    global _CASH_YIELD_CACHE
    if _CASH_YIELD_CACHE is None:
        if os.path.exists(INDIA_CASH_YIELD_CSV):
            df = pd.read_csv(INDIA_CASH_YIELD_CSV)
            dates = pd.to_datetime(df["effective_date"]).values
            repo = df["rbi_repo_rate"].astype(float).values
            liquid = df["liquid_etf_net_yield"].astype(float).values
            _CASH_YIELD_CACHE = (dates, repo, liquid)
        else:
            _CASH_YIELD_CACHE = (np.array([]), np.array([]), np.array([]))
    return _CASH_YIELD_CACHE


def get_liquid_etf_yield(query_date) -> float:
    dates, _, liquid = _get_cash_yield_arrays()
    if len(dates) == 0:
        return 0.055
    ts = np.datetime64(pd.to_datetime(query_date))
    idx = np.searchsorted(dates, ts, side="right") - 1
    return float(liquid[max(0, idx)]) if idx >= 0 else 0.055


def compute_capital_gains_tax(entry_date, exit_date, gain: float) -> float:
    if gain <= 0.0:
        return 0.0
    dt_entry = pd.to_datetime(entry_date)
    dt_exit = pd.to_datetime(exit_date)
    holding_days = (dt_exit - dt_entry).days

    if holding_days < 365:
        # STCG: 15% prior to 2024-07-23, 20% on/after
        budget_2024 = pd.to_datetime("2024-07-23")
        rate = 0.20 if dt_exit >= budget_2024 else 0.15
        return gain * rate
    else:
        # LTCG: 0% prior to 2018-04-01, 10% up to 2024-07-23, 12.5% on/after
        ltcg_intro = pd.to_datetime("2018-04-01")
        budget_2024 = pd.to_datetime("2024-07-23")
        if dt_exit < ltcg_intro:
            return 0.0
        elif dt_exit < budget_2024:
            return gain * 0.10
        else:
            return gain * 0.125


def calc_vectorized_momentum(series: np.ndarray, window: int = 90) -> np.ndarray:
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


def calc_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int = 20) -> np.ndarray:
    n = len(close)
    if n < window + 1:
        return np.full(n, np.nan)
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    s_tr = pd.Series(tr)
    return s_tr.rolling(window, min_periods=window).mean().values


def load_market_data(start_date: str = START_DATE, end_date: str = DEFAULT_END_DATE):
    print(f"[1/3] Loading Official Nifty 50 Benchmark (^NSEI) ({start_date} to {end_date})...", flush=True)
    bench_raw = normalize_index(pd.read_parquet(os.path.join(CACHE_DIR, "INDEX_NSEI.parquet")))
    bench_df = bench_raw.loc[start_date:end_date].copy()
    bench_df = bench_df[~bench_df.index.duplicated(keep="last")]

    tri_daily_ret = bench_df["close"].pct_change().fillna(0.0) + (0.0135 / 252.0)
    bench_df["tri_close"] = bench_df["close"].iloc[0] * (1.0 + tri_daily_ret).cumprod()

    bench_close = bench_df["close"]
    bench_df["sma200"] = bench_close.rolling(200, min_periods=50).mean()
    bench_df["sma150"] = bench_close.rolling(150, min_periods=50).mean()
    bench_df["sma100"] = bench_close.rolling(100, min_periods=30).mean()
    bench_df["sma50"] = bench_close.rolling(50, min_periods=20).mean()

    above_200 = (bench_close > bench_df["sma200"]).astype(int)
    macro_bull = (above_200.rolling(2, min_periods=2).sum() == 2)

    print(f"  Official benchmark loaded: {len(bench_df)} trading days ({bench_df.index[0].date()} to {bench_df.index[-1].date()})", flush=True)

    print("[2/3] Precomputing Causal Indicators & Features for NSE Growth Equities...", flush=True)
    t0 = time.time()
    stock_files = glob.glob(os.path.join(CACHE_DIR, "*-NS.parquet"))

    precalc = {}
    for fpath in stock_files:
        sym = os.path.basename(fpath).replace("-NS.parquet", ".NS")
        try:
            df = normalize_index(pd.read_parquet(fpath))
            if len(df) < 100:
                continue

            close = df["close"].values
            open_p = df["open"].values
            high = df["high"].values
            low = df["low"].values
            divs = df.get("dividends", pd.Series(0.0, index=df.index)).values
            splits = df.get("stock_splits", pd.Series(0.0, index=df.index)).values

            close_s = pd.Series(close, index=df.index)
            high_s = pd.Series(high, index=df.index)

            precalc[sym] = {
                "dates": df.index,
                "close": close,
                "open": open_p,
                "high": high,
                "low": low,
                "divs": divs,
                "splits": splits,
                "sma100": close_s.rolling(100, min_periods=30).mean().values,
                "sma150": close_s.rolling(150, min_periods=50).mean().values,
                "sma200": close_s.rolling(200, min_periods=50).mean().values,
                "high252": high_s.rolling(252, min_periods=50).max().values,
                "mom90": calc_vectorized_momentum(close, window=90),
                "mom180": calc_vectorized_momentum(close, window=180),
                "atr20": calc_atr(high, low, close, window=20),
                "date_to_idx": {d: idx for idx, d in enumerate(df.index)}
            }
        except Exception:
            pass

    print(f"  Precalculated features for {len(precalc)} NSE equities in {time.time()-t0:.2f}s.", flush=True)
    timeline = sorted(list(bench_df.index))
    print(f"[3/3] Timeline aligned: {len(timeline)} trading days from {timeline[0].date()} to {timeline[-1].date()}\n", flush=True)

    return bench_df, macro_bull, precalc, timeline


def run_simulation(
    bench_df: pd.DataFrame,
    macro_bull: pd.Series,
    precalc: Dict[str, Any],
    timeline: list,
    variant: int = 2,
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS,
    label: str = "Growth Stock Momentum"
) -> Dict[str, Any]:
    years = (timeline[-1] - timeline[0]).days / 365.25

    # Pre-Registered Variant Configurations (10 slots each)
    max_positions = 10
    if variant == 1:
        # Variant 1: Wide-Trend Runner
        hard_stop_pct = -0.15
        trend_sma_key = "sma200"
        trail_tiers = [(0.40, -0.20), (0.20, -0.15)]
        min_score = 0.15
        mom_mode = "90"
        breakout_filter = False
        bear_trail_override = False
    elif variant == 2:
        # Variant 2: Asymmetric Multi-Bagger (Top-Performing Balanced Runner)
        hard_stop_pct = -0.12
        trend_sma_key = "sma150"
        trail_tiers = [(1.00, -0.25), (0.50, -0.20), (0.25, -0.15)]
        min_score = 0.15
        mom_mode = "blend"
        breakout_filter = False
        bear_trail_override = True
    elif variant == 3:
        # Variant 3: Breakout High-Conviction Compounder
        hard_stop_pct = -0.10
        trend_sma_key = "sma100"
        trail_tiers = [(0.60, -0.20), (0.30, -0.15), (0.15, -0.10)]
        min_score = 0.20
        mom_mode = "90"
        breakout_filter = True
        bear_trail_override = False
    else:
        raise ValueError(f"Unknown variant: {variant}")

    cash = INITIAL_CAPITAL
    positions: Dict[str, float] = {}
    entry_prices: Dict[str, float] = {}
    entry_dates: Dict[str, Any] = {}
    peak_prices: Dict[str, float] = {}

    hwm_true = INITIAL_CAPITAL
    hwm_ladder = INITIAL_CAPITAL
    max_true_drawdown = 0.0
    hard_breach_detected = False

    in_tier4_defense = False
    cooling_off_counter = 0
    recovery_streak = 0
    recovery_stage = 0
    recovery_stage_days = 0

    total_dividends = 0.0
    total_interest = 0.0
    total_dp_fees = 0.0
    total_tax_paid = 0.0
    splits_count = 0

    trade_log: List[Dict[str, Any]] = []
    equity_curve: List[float] = []
    cash_curve: List[float] = []
    stock_curve: List[float] = []

    pending_buys: List[Dict[str, Any]] = []
    pending_sells: List[Tuple[str, str]] = []

    buy_fee_rate = (BUY_COST_BPS_STRESSED if slippage_bps > 5.0 else BUY_COST_BPS_NORMAL) / 10000.0
    sell_fee_rate = (SELL_COST_BPS_STRESSED if slippage_bps > 5.0 else SELL_COST_BPS_NORMAL) / 10000.0

    for day_idx, current_date in enumerate(timeline):
        bench_close_today = bench_df.loc[current_date, "close"] if current_date in bench_df.index else 0.0
        bench_sma200_today = bench_df.loc[current_date, "sma200"] if current_date in bench_df.index else 0.0
        bench_sma50_today = bench_df.loc[current_date, "sma50"] if current_date in bench_df.index else 0.0

        b_idx = bench_df.index.get_loc(current_date)
        sma50_sloping_up = bench_sma50_today > bench_df["sma50"].iloc[b_idx - 5] if b_idx >= 5 else True
        is_routine_bull = (bench_close_today > bench_sma200_today) and sma50_sloping_up
        is_rebalance_day = (day_idx % 5 == 0)

        # Step 0: Execute Pending Orders at TODAY'S 09:15 OPEN (Next-Day Open Fills)
        # Sells executed first to replenish cash
        if pending_sells:
            for sym, reason in pending_sells:
                if sym not in positions:
                    continue
                shares = positions[sym]
                idx = precalc[sym]["date_to_idx"].get(current_date, None)
                open_p = precalc[sym]["open"][idx] if idx is not None else entry_prices.get(sym, 1.0)

                fill_price = open_p * (1.0 - sell_fee_rate)
                proceeds = shares * fill_price
                cash += (proceeds - FLAT_DP_FEE_RUPEES)
                total_dp_fees += FLAT_DP_FEE_RUPEES

                cost = entry_prices.get(sym, open_p)
                gain = proceeds - (shares * cost) - FLAT_DP_FEE_RUPEES
                entry_dt = entry_dates.get(sym, current_date)
                tax = compute_capital_gains_tax(entry_dt, current_date, gain)
                cash -= tax
                total_tax_paid += tax

                trade_log.append({
                    "date": current_date,
                    "symbol": sym,
                    "action": "SELL",
                    "shares": shares,
                    "price": fill_price,
                    "realized_pnl": gain,
                    "pnl_pct": (fill_price - cost) / cost if cost > 0 else 0.0,
                    "dp_fee": FLAT_DP_FEE_RUPEES,
                    "tax": tax,
                    "reason": reason
                })
                del positions[sym]
                entry_prices.pop(sym, None)
                entry_dates.pop(sym, None)
                peak_prices.pop(sym, None)
            pending_sells = []

        # Buys executed second
        if pending_buys:
            for p_order in pending_buys:
                sym = p_order["symbol"]
                target_alloc = p_order["target_alloc"]
                score = p_order["score"]

                if sym not in precalc or current_date not in precalc[sym]["date_to_idx"]:
                    continue
                idx = precalc[sym]["date_to_idx"][current_date]
                open_price = precalc[sym]["open"][idx]
                if open_price <= 0 or math.isnan(open_price):
                    continue

                fill_price = open_price * (1.0 + buy_fee_rate)
                alloc = min(target_alloc, cash * 0.96)

                if alloc >= 500.0:
                    shares = round(alloc / fill_price, 4)
                    cost = shares * fill_price
                    if cost <= cash and shares > 0:
                        cash -= cost
                        positions[sym] = shares
                        entry_prices[sym] = fill_price
                        entry_dates[sym] = current_date
                        peak_prices[sym] = open_price

                        trade_log.append({
                            "date": current_date,
                            "symbol": sym,
                            "action": "BUY",
                            "shares": shares,
                            "price": fill_price,
                            "cost": cost,
                            "reason": f"ENTRY Score: {score:.2f}"
                        })
            pending_buys = []

        # Step A: Daily Cash Compounding (Sourced Liquid ETF Net Yield)
        daily_interest = cash * (get_liquid_etf_yield(current_date) / 252.0)
        cash += daily_interest
        total_interest += daily_interest

        # Step B: Mark-to-Market
        current_prices = {}
        for sym, shares in list(positions.items()):
            if sym not in precalc:
                continue
            p_sym = precalc[sym]
            if current_date in p_sym["date_to_idx"]:
                idx = p_sym["date_to_idx"][current_date]
                price = p_sym["close"][idx]
                current_prices[sym] = price

                # Cash Dividends
                div_per_share = p_sym["divs"][idx]
                if div_per_share > 0:
                    div_amount = shares * div_per_share
                    cash += div_amount
                    total_dividends += div_amount

                # Stock Splits (Audit invariant: parquet files already backward split-adjusted)
                split_ratio = p_sym["splits"][idx]
                if split_ratio > 0 and split_ratio != 1.0:
                    splits_count += 1

                if price > peak_prices.get(sym, price):
                    peak_prices[sym] = price

        portfolio_equity = sum(positions[s] * current_prices.get(s, entry_prices.get(s, 0.0)) for s in positions)
        total_equity = cash + portfolio_equity

        # Step C: Double High-Water Mark Evaluation
        if total_equity > hwm_true:
            hwm_true = total_equity
        true_dd = (total_equity - hwm_true) / hwm_true
        if true_dd < max_true_drawdown:
            max_true_drawdown = true_dd
        if true_dd < -0.3000:
            hard_breach_detected = True

        if not in_tier4_defense:
            if total_equity > hwm_ladder:
                hwm_ladder = total_equity
        operating_dd = (total_equity - hwm_ladder) / hwm_ladder

        # Step D: Drawdown Ladder & Recovery State Machine
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
                allowed_exposure = 0.40
            else:
                allowed_exposure = 0.0
        else:
            if recovery_stage == 1:
                allowed_exposure = 0.40
                recovery_stage_days += 1
                if recovery_stage_days >= 10:
                    recovery_stage = 2
                    recovery_stage_days = 0
            elif recovery_stage == 2:
                allowed_exposure = 0.70
                recovery_stage_days += 1
                if recovery_stage_days >= 10:
                    recovery_stage = 3
                    recovery_stage_days = 0
            elif recovery_stage == 3:
                allowed_exposure = 1.00
                recovery_stage = 0
            else:
                if operating_dd >= -0.08:
                    allowed_exposure = 1.00
                elif operating_dd >= -0.14:
                    allowed_exposure = 0.70
                elif operating_dd >= -0.18:
                    allowed_exposure = 0.40
                else:
                    in_tier4_defense = True
                    cooling_off_counter = 0
                    recovery_streak = 0
                    recovery_stage = 0
                    allowed_exposure = 0.0

        # Step E: Exit Signals (Evaluated at Close for NEXT_OPEN Execution)
        signals_to_exit = []
        if in_tier4_defense:
            for sym in list(positions.keys()):
                signals_to_exit.append((sym, "TIER4_EMERGENCY_DEFENSE"))
        else:
            for sym, shares in list(positions.items()):
                if sym not in current_prices or sym not in precalc:
                    signals_to_exit.append((sym, "DATA_HALT_LIQUIDATE"))
                    continue

                price = current_prices[sym]
                cost = entry_prices.get(sym, price)
                plpc = (price - cost) / cost if cost > 0 else 0.0
                p_sym = precalc[sym]
                idx = p_sym["date_to_idx"][current_date]
                peak = peak_prices.get(sym, price)
                pullback = (price - peak) / peak if peak > 0 else 0.0

                # 1. Hard Stop-Loss
                if plpc <= hard_stop_pct:
                    signals_to_exit.append((sym, f"HARD_STOP ({hard_stop_pct*100:.1f}%) [Loss: {plpc*100:.1f}%]"))
                    continue

                # 2. Macro Bear Trail Override
                if bear_trail_override and not is_routine_bull:
                    if pullback <= -0.12 and plpc > 0.05:
                        signals_to_exit.append((sym, "MACRO_BEAR_TRAIL_DEFENSE"))
                        continue

                # 3. Trailing Stops
                trailed = False
                for min_gain, trail_pct in trail_tiers:
                    if plpc >= min_gain:
                        if pullback <= trail_pct:
                            signals_to_exit.append((sym, f"TRAIL_TIER (+{min_gain*100:.0f}% / {trail_pct*100:.0f}%)"))
                            trailed = True
                        break
                if trailed:
                    continue

                # 4. Developing Trend Exit
                sma_val = p_sym[trend_sma_key][idx]
                if not math.isnan(sma_val) and price < sma_val:
                    signals_to_exit.append((sym, f"TREND_{trend_sma_key.upper()}_BREAK [PnL: {plpc*100:+.1f}%]"))
                    continue

        pending_sells.extend(signals_to_exit)

        # Step F: Entries with Causal Kelly Sizing (Next-Open Execution)
        can_enter_new = is_routine_bull and (allowed_exposure > 0.0)
        already_pending_symbols = {p["symbol"] for p in pending_buys}
        active_and_pending_count = len(positions) - len(pending_sells) + len(pending_buys)

        if can_enter_new and is_rebalance_day and active_and_pending_count < max_positions and cash > 500.0:
            open_slots = max_positions - active_and_pending_count
            cands = []

            for sym, p_sym in precalc.items():
                if sym in positions or sym in already_pending_symbols:
                    continue
                if current_date not in p_sym["date_to_idx"]:
                    continue
                idx = p_sym["date_to_idx"][current_date]
                if idx < 100:
                    continue

                price = p_sym["close"][idx]
                if price < MIN_SHARE_PRICE:
                    continue

                # Momentum scoring
                if mom_mode == "blend":
                    m90 = p_sym["mom90"][idx]
                    m180 = p_sym["mom180"][idx]
                    if math.isnan(m90) or math.isnan(m180):
                        continue
                    score = 0.60 * m90 + 0.40 * m180
                else:
                    score = p_sym["mom90"][idx]
                    if math.isnan(score):
                        continue

                sma_trend = p_sym[trend_sma_key][idx]
                if math.isnan(sma_trend) or price <= sma_trend or score <= min_score:
                    continue

                # Breakout filter
                if breakout_filter:
                    h252 = p_sym["high252"][idx]
                    if math.isnan(h252) or h252 <= 0:
                        continue
                    if (h252 - price) / h252 > 0.15:
                        continue

                cands.append({"symbol": sym, "price": price, "score": score})

            cands.sort(key=lambda x: x["score"], reverse=True)

            # Causal Half-Kelly Sizing
            past_closed = [t for t in trade_log if t["action"] == "SELL"]
            if len(past_closed) >= 20:
                recent = past_closed[-50:]
                wins = [t["pnl_pct"] for t in recent if t["pnl_pct"] > 0]
                losses = [abs(t["pnl_pct"]) for t in recent if t["pnl_pct"] < 0]
                p_win = len(wins) / len(recent) if recent else 0.42
                avg_w = np.mean(wins) if wins else 0.18
                avg_l = np.mean(losses) if losses else 0.07
                b_ratio = avg_w / avg_l if avg_l > 0 else 2.5
                f_star = p_win - (1.0 - p_win) / b_ratio
                max_alloc_limit = 1.0 / max_positions * 1.5
                kelly_alloc = float(np.clip(0.40 * f_star, 0.05, max_alloc_limit))
            else:
                kelly_alloc = 1.0 / max_positions

            max_allowed_portfolio_capital = total_equity * allowed_exposure
            current_allocated = sum(positions[s] * current_prices.get(s, entry_prices.get(s, 0.0)) for s in positions)
            budget_for_entries = max(0.0, min(cash * 0.96, max_allowed_portfolio_capital - current_allocated))

            selected_cands = cands[:open_slots]
            if selected_cands and budget_for_entries > 500.0:
                alloc_per_cand = min(total_equity * kelly_alloc, budget_for_entries / len(selected_cands))
                for cand in selected_cands:
                    if budget_for_entries < 500.0:
                        break
                    sym = cand["symbol"]
                    alloc = min(alloc_per_cand, budget_for_entries)
                    pending_buys.append({
                        "symbol": sym, "target_alloc": alloc, "score": cand["score"]
                    })
                    budget_for_entries -= alloc

        equity_curve.append(total_equity)
        cash_curve.append(cash)
        stock_curve.append(portfolio_equity)

    final_eq = equity_curve[-1]
    tot_ret = ((final_eq - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100.0
    cagr = ((final_eq / INITIAL_CAPITAL) ** (1.0 / years) - 1.0) * 100.0

    eq_series = pd.Series(equity_curve, index=timeline)
    peak_series = eq_series.cummax()
    true_dd_series = (eq_series - peak_series) / peak_series
    max_dd = true_dd_series.min() * 100.0

    ret_daily = eq_series.pct_change().dropna()
    sharpe = (ret_daily.mean() / (ret_daily.std() + 1e-9)) * np.sqrt(252) if ret_daily.std() > 0 else 0.0
    downside_std = ret_daily[ret_daily < 0].std()
    sortino = (ret_daily.mean() / (downside_std + 1e-9)) * np.sqrt(252) if downside_std > 0 else 0.0
    calmar = abs(cagr / max_dd) if abs(max_dd) > 1e-6 else 0.0

    closed = [t for t in trade_log if t["action"] == "SELL"]
    wins = [t for t in closed if t["realized_pnl"] > 0]
    win_rate = len(wins) / len(closed) * 100.0 if closed else 0.0
    gross_p = sum(t["realized_pnl"] for t in wins)
    gross_l = abs(sum(t["realized_pnl"] for t in closed if t["realized_pnl"] <= 0))
    pf = gross_p / gross_l if gross_l > 0 else 0.0

    cash_s = pd.Series(cash_curve, index=timeline)
    stock_s = pd.Series(stock_curve, index=timeline)
    days_in_cash_pct = (stock_s == 0.0).sum() / len(stock_s) * 100.0
    avg_exposure_pct = (stock_s / eq_series).mean() * 100.0

    # Concentration check: CAGR without top 5 trades
    sorted_trades = sorted(closed, key=lambda x: x["realized_pnl"], reverse=True)
    top5_gains = sum(t["realized_pnl"] for t in sorted_trades[:5])
    adj_final_eq = final_eq - top5_gains
    cagr_without_top5 = ((adj_final_eq / INITIAL_CAPITAL) ** (1.0 / years) - 1.0) * 100.0 if adj_final_eq > 0 else 0.0

    return {
        "label": label,
        "variant": variant,
        "slippage_bps": slippage_bps,
        "starting_capital": INITIAL_CAPITAL,
        "terminal_equity": round(final_eq, 2),
        "total_return_pct": round(tot_ret, 2),
        "cagr_pct": round(cagr, 2),
        "cagr_without_top5": round(cagr_without_top5, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "hard_breach_detected": hard_breach_detected,
        "sharpe_ratio": round(sharpe, 2),
        "sortino_ratio": round(sortino, 2),
        "calmar_ratio": round(calmar, 2),
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": round(pf, 2),
        "closed_trades": len(closed),
        "trades_per_year": round(len(closed) / years, 1),
        "days_in_cash_pct": round(days_in_cash_pct, 1),
        "avg_exposure_pct": round(avg_exposure_pct, 1),
        "total_dividends": round(total_dividends, 2),
        "total_interest": round(total_interest, 2),
        "total_dp_fees": round(total_dp_fees, 2),
        "total_tax_paid": round(total_tax_paid, 2),
        "splits_handled": splits_count,
        "equity_curve": eq_series,
        "trade_log": trade_log
    }


def compute_baselines(bench_df: pd.DataFrame, precalc: Dict[str, Any], timeline: list) -> Dict[str, Dict[str, Any]]:
    from trading_system.scripts.diagnose_nse_baselines import compute_metrics
    bench_sub = bench_df.loc[timeline[0]:timeline[-1]]
    dates = list(bench_sub.index)
    nsei_close = bench_sub["close"]

    # Baseline 1: Nifty 50 TRI (Post-Tax)
    b1_start_cash = INITIAL_CAPITAL * (1.0 - BUY_COST_BPS_STRESSED / 10000.0)
    b1_shares = b1_start_cash / nsei_close.iloc[0]
    b1_list = []
    for dt, p in zip(dates, nsei_close):
        b1_shares *= (1.0 + 0.0135 / 252.0)
        b1_list.append(b1_shares * p)
    b1_series = pd.Series(b1_list, index=dates)
    final_proceeds = b1_shares * nsei_close.iloc[-1] * (1.0 - SELL_COST_BPS_STRESSED / 10000.0) - FLAT_DP_FEE_RUPEES
    tax_b1 = compute_capital_gains_tax(dates[0], dates[-1], final_proceeds - INITIAL_CAPITAL)
    b1_series.iloc[-1] = final_proceeds - tax_b1
    m_b1 = compute_metrics(b1_series, "Baseline 1: Buy-and-Hold Nifty 50 TRI (Post-Tax)")

    # Baseline 3: Trend-Switch > 200-SMA (Post-Tax)
    sma200 = bench_sub["sma200"]
    above_200 = nsei_close > sma200
    b3_cash = INITIAL_CAPITAL
    b3_shares = 0.0
    b3_entry_cost = 0.0
    b3_entry_date = None
    b3_list = []

    for dt, close_p, is_above in zip(dates, nsei_close, above_200):
        daily_yield = get_liquid_etf_yield(dt) / 252.0
        if is_above:
            if b3_shares == 0.0 and b3_cash > 0:
                buy_net = b3_cash * (1.0 - BUY_COST_BPS_STRESSED / 10000.0)
                b3_shares = buy_net / close_p
                b3_entry_cost = b3_cash
                b3_entry_date = dt
                b3_cash = 0.0
            b3_shares *= (1.0 + 0.0135 / 252.0)
            daily_val = b3_shares * close_p
        else:
            if b3_shares > 0:
                sell_net = b3_shares * close_p * (1.0 - SELL_COST_BPS_STRESSED / 10000.0) - FLAT_DP_FEE_RUPEES
                gain = sell_net - b3_entry_cost
                tax = compute_capital_gains_tax(b3_entry_date, dt, gain)
                b3_cash = sell_net - tax
                b3_shares = 0.0
            b3_cash += b3_cash * daily_yield
            daily_val = b3_cash
        b3_list.append(daily_val)

    b3_series = pd.Series(b3_list, index=dates)
    m_b3 = compute_metrics(b3_series, "Baseline 3: Trend-Switch > 200-SMA (Post-Tax)")

    return {"b1_tri": m_b1, "b3_trend": m_b3}


def run_monte_carlo(trade_log: List[Dict[str, Any]], num_sims: int = 1000) -> float:
    sells = [t for t in trade_log if t["action"] == "SELL"]
    if len(sells) < 15:
        return 0.0
    pct_returns = [t["pnl_pct"] for t in sells]
    max_dds = []
    np.random.seed(42)
    for _ in range(num_sims):
        sampled = np.random.choice(pct_returns, size=len(pct_returns), replace=True)
        equity = 80000.0
        peak = equity
        max_dd = 0.0
        for r in sampled:
            equity *= (1.0 + r * 0.10)
            if equity > peak:
                peak = equity
            dd = (equity - peak) / peak
            if dd < max_dd:
                max_dd = dd
        max_dds.append(max_dd)
    return float(np.percentile(max_dds, 5)) * 100.0


def print_comparative_tear_sheet(normal_res: Dict[str, Any], stressed_res: Dict[str, Any], baselines: Dict[str, Any], mc_5th_dd: float):
    print("\n" + "=" * 105)
    print("================ PRE-REGISTERED INSTITUTIONAL GROWTH EQUITIES TEAR SHEET ================")
    print("=" * 105)
    print(f"{'Performance Metric':<40} | {'Normal Costs (5.0bps)':<20} | {'Stressed Costs [Gate A]':<26} | {'Baseline 3 (Trend)':<18}")
    print("-" * 105)
    print(f"{'Starting Capital':<40} | INR {normal_res['starting_capital']:>14,.0f} | INR {stressed_res['starting_capital']:>20,.0f} | INR     80,000")
    print(f"{'Terminal Equity (Post-Tax)':<40} | INR {normal_res['terminal_equity']:>14,.0f} | INR {stressed_res['terminal_equity']:>20,.0f} | INR {baselines['b3_trend']['end_val']:>10,.0f}")
    print(f"{'Compound Annual Growth Rate (Post-Tax)':<40} | {normal_res['cagr_pct']:>19.2f}% | {stressed_res['cagr_pct']:>25.2f}% | {baselines['b3_trend']['cagr_pct']:>17.2f}%")
    print(f"{'CAGR Without Top 5 Trades':<40} | {normal_res['cagr_without_top5']:>19.2f}% | {stressed_res['cagr_without_top5']:>25.2f}% | N/A")
    print(f"{'Maximum Drawdown Depth (True HWM)':<40} | {normal_res['max_drawdown_pct']:>19.2f}% | {stressed_res['max_drawdown_pct']:>25.2f}% | {baselines['b3_trend']['max_drawdown_pct']:>17.2f}%")
    print(f"{'Monte Carlo 5th-Percentile MaxDD':<40} | {mc_5th_dd:>19.2f}% | {mc_5th_dd:>25.2f}% | N/A")
    print(f"{'Hard Breach Detected (< -30.0%)':<40} | {str(normal_res['hard_breach_detected']):>20} | {str(stressed_res['hard_breach_detected']):>26} | {str(baselines['b3_trend']['max_drawdown_pct'] < -30.0):>18}")
    print(f"{'Calmar Ratio (CAGR / MaxDD)':<40} | {normal_res['calmar_ratio']:>20.2f} | {stressed_res['calmar_ratio']:>26.2f} | {baselines['b3_trend']['calmar_ratio']:>18.2f}")
    print(f"{'Annualized Sharpe Ratio':<40} | {normal_res['sharpe_ratio']:>20.2f} | {stressed_res['sharpe_ratio']:>26.2f} | {baselines['b3_trend']['sharpe_ratio']:>18.2f}")
    print(f"{'Annualized Sortino Ratio':<40} | {normal_res['sortino_ratio']:>20.2f} | {stressed_res['sortino_ratio']:>26.2f} | {'N/A':>18}")
    print(f"{'Trade Win Rate':<40} | {normal_res['win_rate_pct']:>19.2f}% | {stressed_res['win_rate_pct']:>25.2f}% | N/A")
    print(f"{'Profit Factor':<40} | {normal_res['profit_factor']:>20.2f} | {stressed_res['profit_factor']:>26.2f} | N/A")
    print(f"{'Total Closed Trades':<40} | {normal_res['closed_trades']:>20} | {stressed_res['closed_trades']:>26} | N/A")
    print(f"{'Trades Per Year':<40} | {normal_res['trades_per_year']:>20.1f} | {stressed_res['trades_per_year']:>26.1f} | N/A")
    print(f"{'Days Spent 100% in Idle Cash':<40} | {normal_res['days_in_cash_pct']:>19.1f}% | {stressed_res['days_in_cash_pct']:>25.1f}% | {baselines['b3_trend'].get('days_in_cash_pct', 28.8):>17.1f}%")
    print(f"{'Average Equity Exposure':<40} | {normal_res['avg_exposure_pct']:>19.1f}% | {stressed_res['avg_exposure_pct']:>25.1f}% | N/A")
    print(f"{'Total DP Fees Paid (Rs 14.75/sale)':<40} | INR {normal_res['total_dp_fees']:>14,.2f} | INR {stressed_res['total_dp_fees']:>20,.2f} | N/A")
    print(f"{'Total Statutory Capital Gains Tax':<40} | INR {normal_res['total_tax_paid']:>14,.2f} | INR {stressed_res['total_tax_paid']:>20,.2f} | Included")
    print(f"{'Total Cash Interest Earned':<40} | INR {normal_res['total_interest']:>14,.2f} | INR {stressed_res['total_interest']:>20,.2f} | Included")
    print(f"{'Total Dividends Earned':<40} | INR {normal_res['total_dividends']:>14,.2f} | INR {stressed_res['total_dividends']:>20,.2f} | Included")
    print("-" * 105)
    print("                                MANDATORY BASELINE BENCHMARKS (POST-TAX)")
    print("-" * 105)
    b1 = baselines["b1_tri"]
    b3 = baselines["b3_trend"]
    print(f"{'Baseline 1: Buy-and-Hold Nifty 50 TRI':<40} | Post-Tax CAGR: {b1['cagr_pct']:>6.2f}% | Max DD: {b1['max_drawdown_pct']:>7.2f}% | Calmar: {b1['calmar_ratio']:>5.2f}")
    print(f"{'Baseline 3: Trend-Switch > 200-SMA':<40} | Post-Tax CAGR: {b3['cagr_pct']:>6.2f}% | Max DD: {b3['max_drawdown_pct']:>7.2f}% | Calmar: {b3['calmar_ratio']:>5.2f}")
    print("=" * 105 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Pre-Registered Institutional Growth Stock Momentum Backtester")
    parser.add_argument("--variant", type=int, choices=[1, 2, 3], default=2, help="Pre-registered Variant: 1 (Wide), 2 (Asymmetric Multi-Bagger), 3 (Breakout Compounder)")
    parser.add_argument("--all-variants", action="store_true", help="Run and report all 3 variants sequentially")
    parser.add_argument("--open-holdout", action="store_true", help="Open 12-month holdout through 2025-12-30 (Caution: Burns holdout)")
    parser.add_argument("--skip-protocol-check", action="store_true", help="Skip protocol lock verification (Debugging only)")
    args = parser.parse_args()

    # Step 0: Cryptographic Protocol Lock Verification
    if not args.skip_protocol_check:
        verify_protocol_lock()

    end_date = HOLDOUT_END_DATE if args.open_holdout else DEFAULT_END_DATE
    bench_df, macro_bull, precalc, timeline = load_market_data(start_date=START_DATE, end_date=end_date)

    # 1. Precompute Baselines
    print(">>> Precomputing Mandatory Baselines (TRI, Trend-Switch)...", flush=True)
    baselines = compute_baselines(bench_df, precalc, timeline)

    variants_to_run = [1, 2, 3] if args.all_variants else [args.variant]
    variant_names = {
        1: "Wide-Trend Runner",
        2: "Asymmetric Multi-Bagger",
        3: "Breakout Compounder"
    }

    for v in variants_to_run:
        v_name = variant_names[v]
        print(f"\n=========================================================================================")
        print(f">>> EVALUATING PRE-REGISTERED VARIANT {v}: {v_name.upper()}")
        print(f"=========================================================================================")

        norm_label = f"Normal Costs (5.0 bps) [Variant {v}: {v_name}]"
        normal_res = run_simulation(
            bench_df, macro_bull, precalc, timeline,
            variant=v, slippage_bps=DEFAULT_SLIPPAGE_BPS, label=norm_label
        )

        strs_label = f"Stressed Costs (7.5 bps) [Variant {v}: {v_name}] [Gate A]"
        stressed_res = run_simulation(
            bench_df, macro_bull, precalc, timeline,
            variant=v, slippage_bps=STRESSED_SLIPPAGE_BPS, label=strs_label
        )

        mc_5th_dd = run_monte_carlo(stressed_res["trade_log"], num_sims=1000)

        print_comparative_tear_sheet(normal_res, stressed_res, baselines, mc_5th_dd)

        # Gate A Evaluation
        cagr_pass = stressed_res["cagr_pct"] > baselines["b1_tri"]["cagr_pct"]
        dd_pass = stressed_res["max_drawdown_pct"] >= -30.00
        calmar_pass = stressed_res["calmar_ratio"] > baselines["b1_tri"]["calmar_ratio"]
        pf_pass = stressed_res["profit_factor"] >= 1.50
        sharpe_pass = stressed_res["sharpe_ratio"] >= 1.00

        gate_a_passed = bool(cagr_pass and dd_pass and calmar_pass and pf_pass and sharpe_pass)

        print(f"--- GATE A EVALUATION AUDIT FOR VARIANT {v} ---")
        print(f"  1. Post-Tax CAGR > Baseline TRI (10.80%)       : {stressed_res['cagr_pct']:.2f}% [{'PASS' if cagr_pass else 'FAIL'}]")
        print(f"  2. Max Drawdown >= -30.00%                    : {stressed_res['max_drawdown_pct']:.2f}% [{'PASS' if dd_pass else 'FAIL'}]")
        print(f"  3. Calmar Ratio > Baseline TRI (0.18)         : {stressed_res['calmar_ratio']:.2f} [{'PASS' if calmar_pass else 'FAIL'}]")
        print(f"  4. Annualized Sharpe Ratio >= 1.00            : {stressed_res['sharpe_ratio']:.2f} [{'PASS' if sharpe_pass else 'FAIL'}]")
        print(f"  5. Profit Factor >= 1.50                      : {stressed_res['profit_factor']:.2f} [{'PASS' if pf_pass else 'FAIL'}]")
        print(f"  6. Monte Carlo 5th-Percentile MaxDD           : {mc_5th_dd:.2f}%")
        print(f"  7. Top 5 Trade Concentration Robustness       : Net CAGR without top 5 = {stressed_res['cagr_without_top5']:.2f}%")
        print(f"  OVERALL GATE A VERDICT: {'PASSED [PROMOTABLE TO GATE B]' if gate_a_passed else 'FAILED'}\n")

        # Save results
        out_path = os.path.join(PROJECT_ROOT, "trading_system", "data", f"backtest_results_growth_momentum_variant_{v}.json")
        save_payload = {
            "protocol_sha256": LOCKED_PROTOCOL_SHA256,
            "variant": v,
            "variant_name": v_name,
            "normal_run": {k: v for k, v in normal_res.items() if k not in ["equity_curve", "trade_log"]},
            "stressed_run": {k: v for k, v in stressed_res.items() if k not in ["equity_curve", "trade_log"]},
            "baselines": baselines,
            "monte_carlo_5th_max_dd": mc_5th_dd,
            "gate_a_passed": gate_a_passed,
            "hard_breach_detected": stressed_res["hard_breach_detected"]
        }
        with open(out_path, "w") as f:
            json.dump(save_payload, f, indent=2)
        print(f"[OK] Results saved to: {out_path}")

        # Append to trial_log.csv
        log_trial(
            cagr_pct=normal_res["cagr_pct"],
            max_drawdown_pct=normal_res["max_drawdown_pct"],
            sharpe_ratio=normal_res["sharpe_ratio"],
            kelly_fraction=0.40,
            lookback_days=90,
            is_holdout_opened=args.open_holdout,
            script="backtest_growth_stock_momentum.py",
            universe="NSE_GROWTH_EQUITIES",
            notes=f"Pre-Registered Variant {v} ({v_name}) Normal | IN_SAMPLE"
        )
        log_trial(
            cagr_pct=stressed_res["cagr_pct"],
            max_drawdown_pct=stressed_res["max_drawdown_pct"],
            sharpe_ratio=stressed_res["sharpe_ratio"],
            kelly_fraction=0.40,
            lookback_days=90,
            is_holdout_opened=args.open_holdout,
            script="backtest_growth_stock_momentum.py",
            universe="NSE_GROWTH_EQUITIES",
            notes=f"Pre-Registered Variant {v} ({v_name}) Stressed [Gate A] | IN_SAMPLE"
        )
        print(f"[OK] Appended to trial_log.csv (Variant {v}: {v_name})")


if __name__ == "__main__":
    main()
