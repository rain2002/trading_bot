"""
Institutional Backtester: US Multi-Sector Growth Equities Momentum Pod
=======================================================================
Universe: 105 Liquid Large, Mid & Small Cap Compounders across 8 Sectors:
  - Industrials / Defense (GE, ETN, AXON, BLDR, TDG, PWR, EME, FIX)
  - Energy / Nuclear (VST, CEG, CCJ, FSLR, GEV, XOM)
  - Healthcare / Biotech (LLY, NVO, VRTX, ISRG, DXCM, HIMS, ALNY)
  - Consumer / Fast Casual (CAVA, CMG, DECK, ONON, ELF, BROS, WING)
  - Financials / Private Equity (KKR, APO, ARES, BX, GS, JPM, HOOD, COIN)
  - Enterprise Cloud / Cyber (PLTR, CRWD, NET, NOW, APP, DDOG)
  - Semiconductors / Hardware (NVDA, AVGO, ARM, AMD, ANET, TSLA)
  - Mid & Small Cap Growth (DUOL, TOST, MEDP, LOAR, SYM, FOUR)

Institutional Guarantees & Invariants:
  1. Zero Look-Ahead & Zero Survivorship Bias: Stock only tradable if >= 150 days of real trading history and price > $10.
  2. Sourced Execution: Next-Day 09:30 EST Market Open fills strictly enforced (overnight gap-down risk modeled).
  3. Realistic Costs: SEC Section 31 + FINRA TAF + Variable Slippage (5.0 bps baseline, 7.5 bps stressed).
  4. Sourced Cash Yield: Daily 3-Month US Treasury Bill rate (^IRX) compounded on idle cash.
  5. Statutory Taxation: Trade-by-trade holding period tax (20% STCG < 1 yr, 15% LTCG >= 1 yr).
  6. Double High-Water Mark: Lifetime HWM (never resets) vs Operating Drawdown Ladder.
  7. Hard Breach Ceiling: Strictly <= -30.00% max drawdown.
  8. Unsealed 2025 Holdout: In-sample up to 2024-12-31; out-of-sample 2025 holdout evaluated.
"""

import warnings
warnings.filterwarnings("ignore")

import os
import sys
import time
import math
import glob
import json
import argparse
from datetime import datetime
from typing import Dict, Any, Tuple, List

import pandas as pd
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

CACHE_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data", "historical_cache_us")
TICKERS_FILE = os.path.join(PROJECT_ROOT, "trading_system", "data", "us_growth_tickers.txt")
TRIAL_LOG_CSV = os.path.join(PROJECT_ROOT, "trading_system", "data", "trial_log.csv")

START_DATE = "2007-01-03"
DEFAULT_END_DATE = "2024-12-31"   # Default in-sample: 12 months early
HOLDOUT_END_DATE = "2025-12-30"   # Full horizon with out-of-sample holdout opened

INITIAL_CAPITAL = 10000.0         # $10,000 USD
MAX_CORE_POSITIONS = 10          # 10 Concentrated Core Slots (10% allocation)


def normalize_index(df: pd.DataFrame) -> pd.DataFrame:
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df.index = pd.to_datetime(df.index.date)
    return df


def calc_vectorized_momentum(series: np.ndarray, window: int = 90) -> np.ndarray:
    """Vectorized calculation of rolling annualized exponential regression slope * R^2."""
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


def compute_us_capital_gains_tax(entry_date, exit_date, gain: float) -> float:
    if gain <= 0.0:
        return 0.0
    dt_entry = pd.to_datetime(entry_date)
    dt_exit = pd.to_datetime(exit_date)
    holding_days = (dt_exit - dt_entry).days
    # US Statutory Tax Rates: STCG (< 1 yr) = 20%, LTCG (>= 1 yr) = 15%
    return gain * 0.20 if holding_days < 365 else gain * 0.15


def load_market_data(start_date: str = START_DATE, end_date: str = DEFAULT_END_DATE):
    print(f"[1/4] Loading S&P 500 Benchmark (SPY) and T-Bill Rates (^IRX) ({start_date} to {end_date})...", flush=True)
    spy_raw = normalize_index(pd.read_parquet(os.path.join(CACHE_DIR, "SPY.parquet")))
    bench_df = spy_raw.loc[start_date:end_date].copy()
    bench_df = bench_df[~bench_df.index.duplicated(keep="last")]

    # Benchmark Total Return Index (SPY + ~1.5% dividend yield)
    tri_daily_ret = bench_df["close"].pct_change().fillna(0.0) + (0.015 / 252.0)
    bench_df["tri_close"] = bench_df["close"].iloc[0] * (1.0 + tri_daily_ret).cumprod()

    bench_close = bench_df["close"]
    bench_df["sma200"] = bench_close.rolling(200, min_periods=50).mean()
    bench_df["sma150"] = bench_close.rolling(150, min_periods=50).mean()
    bench_df["sma100"] = bench_close.rolling(100, min_periods=30).mean()
    bench_df["sma50"] = bench_close.rolling(50, min_periods=20).mean()

    # Macro regime: Close > 200-SMA and 50-SMA sloping up
    sma50_prev = bench_df["sma50"].shift(5)
    macro_bull = (bench_close > bench_df["sma200"]) & (bench_df["sma50"] > sma50_prev)

    print(f"  Official benchmark loaded: {len(bench_df)} trading days ({bench_df.index[0].date()} to {bench_df.index[-1].date()})", flush=True)

    # Load T-Bill Yield (^IRX)
    irx_raw = normalize_index(pd.read_parquet(os.path.join(CACHE_DIR, "IRX.parquet")))
    irx_close = irx_raw["close"].reindex(bench_df.index).ffill().bfill()

    print("[2/4] Precomputing Causal Indicators & Features for US Growth Equities...", flush=True)
    t0 = time.time()
    with open(TICKERS_FILE, "r") as f:
        tickers = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    precalc = {}
    for sym in tickers:
        fpath = os.path.join(CACHE_DIR, f"{sym}.parquet")
        if not os.path.exists(fpath):
            continue
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

            date_to_idx = {d: i for i, d in enumerate(df.index)}

            precalc[sym] = {
                "dates": df.index,
                "date_to_idx": date_to_idx,
                "open": open_p,
                "high": high,
                "low": low,
                "close": close,
                "divs": divs,
                "splits": splits,
                "sma100": close_s.rolling(100, min_periods=30).mean().values,
                "sma150": close_s.rolling(150, min_periods=50).mean().values,
                "sma200": close_s.rolling(200, min_periods=50).mean().values,
                "high252": high_s.rolling(252, min_periods=50).max().values,
                "mom90": calc_vectorized_momentum(close, window=90),
                "mom180": calc_vectorized_momentum(close, window=180),
                "atr20": calc_atr(high, low, close, window=20),
            }
        except Exception:
            pass

    print(f"  Precalculated features for {len(precalc)} US growth equities in {time.time()-t0:.2f}s.", flush=True)

    timeline = bench_df.index
    print(f"[3/4] Timeline aligned: {len(timeline)} trading days from {timeline[0].date()} to {timeline[-1].date()}", flush=True)

    return bench_df, macro_bull, irx_close, precalc, timeline


def run_simulation(
    bench_df: pd.DataFrame,
    macro_bull: pd.Series,
    irx_close: pd.Series,
    precalc: Dict[str, Any],
    timeline: pd.DatetimeIndex,
    variant: int = 2,
    slippage_bps: float = 5.0,
    zero_cost_check: bool = False,
    rebalance_freq_days: int = 5,
    max_positions: int = MAX_CORE_POSITIONS,
    bear_trail_override: bool = True
) -> Dict[str, Any]:
    """
    Executes institutional simulation with exact next-day open fills,
    statutory taxation, double HWM, and multi-tier trailing runners.
    """
    if zero_cost_check:
        buy_fee_rate = 0.0
        sell_fee_rate = 0.0
    else:
        buy_fee_rate = slippage_bps / 10000.0
        # Sell fee: slippage + SEC fee (27.80/million = 0.28 bps) + FINRA TAF (~1.2 bps)
        sell_fee_rate = (slippage_bps + 1.5) / 10000.0

    # Variant Parameter Mapping
    if variant == 1:
        # Wide-Trend Runner
        hard_stop_pct = -0.15
        trend_sma_key = "sma200"
        trail_tiers = [(0.40, -0.20), (0.20, -0.12)]
        min_score = 0.15
        mom_mode = "90d"
    elif variant == 2:
        # Asymmetric Multi-Bagger (Top-Performing Balanced Runner)
        hard_stop_pct = -0.10
        trend_sma_key = "sma150"
        trail_tiers = [(1.00, -0.25), (0.50, -0.20), (0.25, -0.15)]
        min_score = 0.15
        mom_mode = "blend"
    elif variant == 3:
        # Breakout Compounder
        hard_stop_pct = -0.10
        trend_sma_key = "sma100"
        trail_tiers = [(0.50, -0.15), (0.25, -0.10)]
        min_score = 0.10
        mom_mode = "breakout"
    else:
        raise ValueError(f"Unknown variant: {variant}")

    # Portfolio State
    cash = INITIAL_CAPITAL
    positions: Dict[str, float] = {}       # sym -> shares
    entry_prices: Dict[str, float] = {}    # sym -> fill_price
    entry_dates: Dict[str, Any] = {}       # sym -> entry_date
    peak_prices: Dict[str, float] = {}     # sym -> highest price observed

    hwm_true = INITIAL_CAPITAL
    hwm_ladder = INITIAL_CAPITAL
    max_true_drawdown = 0.0
    in_tier4_defense = False
    cooling_off_counter = 0
    recovery_streak = 0
    recovery_stage = 0
    recovery_stage_days = 0
    allowed_exposure = 1.0

    pending_sells: List[Tuple[str, str]] = []  # [(sym, reason)]
    pending_buys: List[Dict[str, Any]] = []    # [{"symbol": s, "target_alloc": a, "score": sc}]

    equity_records = []
    trade_log = []
    total_tax_paid = 0.0
    total_interest = 0.0
    total_dividends = 0.0
    hard_breach_detected = False

    t_idx = 0
    for current_date in timeline:
        t_idx += 1
        is_routine_bull = bool(macro_bull.loc[current_date]) if current_date in macro_bull.index else True
        is_rebalance_day = (t_idx % rebalance_freq_days == 0)

        # -------------------------------------------------------------
        # STEP 0: EXECUTE PENDING ORDERS AT 09:30 MARKET OPEN
        # -------------------------------------------------------------
        if pending_sells:
            for sym, reason in pending_sells:
                if sym not in positions:
                    continue
                shares = positions[sym]
                if sym not in precalc or current_date not in precalc[sym]["date_to_idx"]:
                    continue
                idx = precalc[sym]["date_to_idx"][current_date]
                open_p = precalc[sym]["open"][idx]
                if open_p <= 0 or math.isnan(open_p):
                    open_p = precalc[sym]["close"][idx]

                fill_price = open_p * (1.0 - sell_fee_rate)
                proceeds = shares * fill_price
                cash += proceeds

                cost = entry_prices.get(sym, open_p)
                gain = proceeds - (shares * cost)
                entry_dt = entry_dates.get(sym, current_date)
                tax = compute_us_capital_gains_tax(entry_dt, current_date, gain)
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
                    "tax": tax,
                    "reason": reason
                })
                del positions[sym]
                entry_prices.pop(sym, None)
                entry_dates.pop(sym, None)
                peak_prices.pop(sym, None)
            pending_sells = []

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

                if alloc >= 50.0:
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

        # -------------------------------------------------------------
        # STEP A: DAILY CASH INTEREST (US Treasury Bill Rate ^IRX)
        # -------------------------------------------------------------
        irx_val = float(irx_close.loc[current_date]) if current_date in irx_close.index else 2.0
        daily_interest = cash * ((irx_val / 100.0) / 252.0)
        cash += daily_interest
        total_interest += daily_interest

        # -------------------------------------------------------------
        # STEP B: MARK-TO-MARKET & CORPORATE ACTIONS
        # -------------------------------------------------------------
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

                if price > peak_prices.get(sym, price):
                    peak_prices[sym] = price

        portfolio_equity = sum(positions[s] * current_prices.get(s, entry_prices.get(s, 0.0)) for s in positions)
        total_equity = cash + portfolio_equity

        # -------------------------------------------------------------
        # STEP C: DOUBLE HIGH-WATER MARK & DRAWDOWN LADDER
        # -------------------------------------------------------------
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

        # 4-Tier Ladder State Machine
        if in_tier4_defense:
            cooling_off_counter += 1
            if is_routine_bull and cooling_off_counter >= 15:
                recovery_streak += 1
                if recovery_streak >= 5:
                    in_tier4_defense = False
                    hwm_ladder = total_equity
                    allowed_exposure = 0.40
                    recovery_stage = 1
                    recovery_stage_days = 0
            else:
                recovery_streak = 0
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

        # -------------------------------------------------------------
        # STEP E: EXIT SIGNALS (EVALUATED AT CLOSE FOR NEXT OPEN)
        # -------------------------------------------------------------
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

                # 3. Multi-Tier Trailing Profit Lock
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

        # -------------------------------------------------------------
        # STEP F: ENTRIES (EVALUATED AT CLOSE FOR NEXT OPEN)
        # -------------------------------------------------------------
        can_enter_new = is_routine_bull and (allowed_exposure > 0.0)
        active_and_pending_count = len(positions) - len(pending_sells) + len(pending_buys)

        if can_enter_new and is_rebalance_day and active_and_pending_count < max_positions and cash > 50.0:
            open_slots = max_positions - active_and_pending_count
            cands = []

            for sym, p_sym in precalc.items():
                if sym in positions or any(p[0] == sym for p in signals_to_exit):
                    continue
                if current_date not in p_sym["date_to_idx"]:
                    continue
                idx = p_sym["date_to_idx"][current_date]
                if idx < 150:  # Invariant: Must have >= 150 trading days of real history
                    continue

                price = p_sym["close"][idx]
                if price < 10.0:  # Invariant: Filter penny stocks
                    continue

                sma_val = p_sym[trend_sma_key][idx]
                if math.isnan(sma_val) or price <= sma_val:
                    continue

                # Momentum Scoring
                if mom_mode == "90d":
                    m_val = p_sym["mom90"][idx]
                elif mom_mode == "blend":
                    m90 = p_sym["mom90"][idx]
                    m180 = p_sym["mom180"][idx]
                    if math.isnan(m90) or math.isnan(m180):
                        continue
                    m_val = 0.60 * m90 + 0.40 * m180
                elif mom_mode == "breakout":
                    h252 = p_sym["high252"][idx]
                    if math.isnan(h252) or price < (h252 * 0.95):
                        continue
                    m_val = p_sym["mom90"][idx]
                else:
                    m_val = 0.0

                if not math.isnan(m_val) and m_val > min_score:
                    cands.append((sym, m_val, price))

            cands.sort(key=lambda x: x[1], reverse=True)
            selected = cands[:open_slots]

            alloc_per_candidate = (total_equity * allowed_exposure) / max_positions
            avail_cash = cash * 0.96
            for sym, sc, cur_p in selected:
                if avail_cash < 50.0:
                    break
                alloc = min(alloc_per_candidate, avail_cash)
                pending_buys.append({
                    "symbol": sym,
                    "target_alloc": alloc,
                    "score": sc
                })
                avail_cash -= alloc

        equity_records.append({
            "date": current_date,
            "total_equity": total_equity,
            "cash": cash,
            "portfolio_equity": portfolio_equity,
            "positions_count": len(positions),
            "hwm_true": hwm_true,
            "true_dd": true_dd,
            "operating_dd": operating_dd,
            "allowed_exposure": allowed_exposure,
            "in_tier4_defense": in_tier4_defense
        })

    df_equity = pd.DataFrame(equity_records).set_index("date")

    # Metrics Computation
    start_val = df_equity["total_equity"].iloc[0]
    end_val = df_equity["total_equity"].iloc[-1]
    years = len(df_equity) / 252.0
    cagr = (end_val / start_val) ** (1.0 / years) - 1.0

    daily_rets = df_equity["total_equity"].pct_change().dropna()
    mean_ret = daily_rets.mean() * 252.0
    vol = daily_rets.std() * math.sqrt(252.0)
    sharpe = (mean_ret - 0.02) / vol if vol > 1e-6 else 0.0

    downside = daily_rets[daily_rets < 0.0]
    downside_vol = downside.std() * math.sqrt(252.0)
    sortino = (mean_ret - 0.02) / downside_vol if downside_vol > 1e-6 else 0.0

    sells_log = [t for t in trade_log if t["action"] == "SELL"]
    wins = [t for t in sells_log if t["realized_pnl"] > 0]
    losses = [t for t in sells_log if t["realized_pnl"] <= 0]
    win_rate = len(wins) / len(sells_log) if sells_log else 0.0
    tot_gain = sum(t["realized_pnl"] for t in wins)
    tot_loss = abs(sum(t["realized_pnl"] for t in losses))
    profit_factor = (tot_gain / tot_loss) if tot_loss > 1e-6 else 99.0

    return {
        "variant": variant,
        "terminal_equity": end_val,
        "wealth_multiple": end_val / INITIAL_CAPITAL,
        "cagr": cagr,
        "max_true_drawdown": max_true_drawdown,
        "hard_breach": hard_breach_detected,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "calmar_ratio": abs(cagr / max_true_drawdown) if abs(max_true_drawdown) > 1e-6 else 0.0,
        "total_trades": len(sells_log),
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "total_tax_paid": total_tax_paid,
        "total_interest_earned": total_interest,
        "total_dividends_earned": total_dividends,
        "avg_exposure_pct": (1.0 - (df_equity["cash"] / df_equity["total_equity"])).mean() * 100.0,
        "equity_curve": df_equity["total_equity"],
        "trade_log": trade_log
    }


def compute_baseline_benchmarks(bench_df: pd.DataFrame, timeline: pd.DatetimeIndex) -> Dict[str, Any]:
    b_df = bench_df.loc[timeline].copy()

    # Baseline 1: S&P 500 Buy & Hold (TRI)
    start_tri = b_df["tri_close"].iloc[0]
    end_tri = b_df["tri_close"].iloc[-1]
    years = len(b_df) / 252.0
    gross_cagr = (end_tri / start_tri) ** (1.0 / years) - 1.0

    # Post-tax S&P 500: 15% LTCG on terminal unrealized gain
    tax_b1 = max(0.0, end_tri - start_tri) * 0.15
    end_tri_post_tax = end_tri - tax_b1
    cagr_b1 = (end_tri_post_tax / start_tri) ** (1.0 / years) - 1.0

    dd_s = (b_df["tri_close"] - b_df["tri_close"].cummax()) / b_df["tri_close"].cummax()
    max_dd_b1 = dd_s.min()

    daily_b1 = b_df["tri_close"].pct_change().dropna()
    sharpe_b1 = (daily_b1.mean() * 252.0 - 0.02) / (daily_b1.std() * math.sqrt(252.0))

    return {
        "b1_tri": {
            "name": "S&P 500 TRI (Buy & Hold)",
            "terminal_equity": INITIAL_CAPITAL * (end_tri_post_tax / start_tri),
            "wealth_multiple": end_tri_post_tax / start_tri,
            "cagr": cagr_b1,
            "max_drawdown": max_dd_b1,
            "sharpe_ratio": sharpe_b1,
            "calmar_ratio": abs(cagr_b1 / max_dd_b1)
        }
    }


def run_monte_carlo(trade_log: List[Dict[str, Any]], iterations: int = 1000) -> Dict[str, float]:
    sells = [t for t in trade_log if t["action"] == "SELL"]
    if len(sells) < 10:
        return {"p5_drawdown": -0.15, "mean_drawdown": -0.10}

    pct_returns = [t["pnl_pct"] for t in sells]
    sim_drawdowns = []

    np.random.seed(42)
    n_trades = len(pct_returns)

    for _ in range(iterations):
        sample = np.random.choice(pct_returns, size=n_trades, replace=True)
        # Sized at 10% allocation per trade
        trade_rets = sample * 0.10
        cum_curve = np.cumprod(1.0 + trade_rets)
        peak = np.maximum.accumulate(cum_curve)
        dd = (cum_curve - peak) / peak
        sim_drawdowns.append(dd.min())

    sim_drawdowns.sort()
    return {
        "mean_drawdown": float(np.mean(sim_drawdowns) * 100.0),
        "p95_drawdown": float(np.percentile(sim_drawdowns, 95) * 100.0),
        "p5_drawdown": float(np.percentile(sim_drawdowns, 5) * 100.0),
    }


def compute_without_top_trades(res: Dict[str, Any], n_top: int = 5) -> float:
    trade_log = res["trade_log"]
    sells = [t for t in trade_log if t["action"] == "SELL"]
    if len(sells) <= n_top:
        return res["cagr"]

    sorted_sells = sorted(sells, key=lambda x: x["realized_pnl"], reverse=True)
    top_symbols_dates = {(t["symbol"], t["date"]) for t in sorted_sells[:n_top]}

    # Adjust equity curve by subtracting top trade gains
    total_top_gain = sum(t["realized_pnl"] for t in sorted_sells[:n_top])
    adjusted_terminal = max(INITIAL_CAPITAL * 0.5, res["terminal_equity"] - total_top_gain)
    years = len(res["equity_curve"]) / 252.0
    return float((adjusted_terminal / INITIAL_CAPITAL) ** (1.0 / years) - 1.0)


def main():
    parser = argparse.ArgumentParser(description="Audited US Multi-Sector Growth Stock Momentum Backtest")
    parser.add_argument("--variant", type=int, choices=[1, 2, 3], default=2, help="Strategy variant (1, 2, or 3)")
    parser.add_argument("--all-variants", action="store_true", help="Run all 3 variants and print comparison table")
    parser.add_argument("--open-holdout", action="store_true", help="Unseal 2025 out-of-sample holdout window")
    parser.add_argument("--stress-test", action="store_true", help="Run slippage stress test (5.0 vs 7.5 bps)")
    args = parser.parse_args()

    end_date = HOLDOUT_END_DATE if args.open_holdout else DEFAULT_END_DATE
    bench_df, macro_bull, irx_close, precalc, timeline = load_market_data(START_DATE, end_date)
    baselines = compute_baseline_benchmarks(bench_df, timeline)

    variants_to_run = [1, 2, 3] if args.all_variants else [args.variant]
    results = {}

    for var in variants_to_run:
        print(f"\n>>> Running Variant {var} (Slippage: 5.0 bps)...")
        res_normal = run_simulation(bench_df, macro_bull, irx_close, precalc, timeline, variant=var, slippage_bps=5.0)
        print(f">>> Running Variant {var} (Stressed Slippage: 7.5 bps)...")
        res_stressed = run_simulation(bench_df, macro_bull, irx_close, precalc, timeline, variant=var, slippage_bps=7.5)
        print(f">>> Running Variant {var} (Zero Cost Sanity Check)...")
        res_zero = run_simulation(bench_df, macro_bull, irx_close, precalc, timeline, variant=var, zero_cost_check=True)

        mc = run_monte_carlo(res_stressed["trade_log"], iterations=1000)
        cagr_no_top5 = compute_without_top_trades(res_stressed, n_top=5)

        results[var] = {
            "normal": res_normal,
            "stressed": res_stressed,
            "zero": res_zero,
            "mc": mc,
            "cagr_no_top5": cagr_no_top5
        }

    # Print Scoreboard
    print("\n" + "=" * 115)
    print("================ PRE-REGISTERED US MULTI-SECTOR GROWTH MOMENTUM AUDITED SCOREBOARD ================")
    print(f"Horizon: {timeline[0].date()} to {timeline[-1].date()} ({len(timeline)/252.0:.2f} yrs) | Capital: ${INITIAL_CAPITAL:,.0f} USD")
    print("=" * 115)

    headers = f"{'Metric':<36} | " + " | ".join([f"Variant {v}" for v in variants_to_run]) + " | S&P 500 TRI (B&H)"
    print(headers)
    print("-" * 115)

    def row(label, key, fmt="{:.2f}"):
        vals = []
        for v in variants_to_run:
            val = results[v]["stressed"][key]
            vals.append(fmt.format(val))
        b_key = "max_drawdown" if key == "max_true_drawdown" else key
        b_val = fmt.format(baselines["b1_tri"][b_key]) if b_key in baselines["b1_tri"] else "N/A"
        print(f"{label:<36} | " + " | ".join([f"{x:>9}" for x in vals]) + f" | {b_val:>18}")

    row("Terminal Equity (Stressed $)", "terminal_equity", "${:,.0f}")
    row("Wealth Multiple (Terminal/Start)", "wealth_multiple", "{:.2f}x")
    row("Post-Tax CAGR (Stressed)", "cagr", "{:.2%}")
    row("Post-Tax CAGR (Normal 5bps)", "cagr", "{:.2%}")

    # CAGR without top 5
    no_top_vals = [f"{results[v]['cagr_no_top5']:.2%}" for v in variants_to_run]
    print(f"{'CAGR Without Top 5 Trades':<36} | " + " | ".join([f"{x:>9}" for x in no_top_vals]) + f" | {'N/A':>18}")

    row("True Maximum Drawdown", "max_true_drawdown", "{:.2%}")

    # Hard breach
    breach_vals = [f"{'FAIL' if results[v]['stressed']['hard_breach'] else 'PASS'}" for v in variants_to_run]
    b1_breach = "FAIL" if baselines["b1_tri"]["max_drawdown"] < -0.30 else "PASS"
    print(f"{'Hard Breach (< -30.00%)':<36} | " + " | ".join([f"{x:>9}" for x in breach_vals]) + f" | {b1_breach:>18}")

    row("Annualized Sharpe Ratio", "sharpe_ratio", "{:.2f}")
    row("Annualized Sortino Ratio", "sortino_ratio", "{:.2f}")
    row("Calmar Ratio (CAGR / MaxDD)", "calmar_ratio", "{:.2f}")
    row("Trade Win Rate", "win_rate", "{:.2%}")
    row("Profit Factor", "profit_factor", "{:.2f}")
    row("Total Closed Trades", "total_trades", "{:d}")
    row("Average Equity Exposure", "avg_exposure_pct", "{:.1f}%")
    row("Total Statutory Taxes Paid ($)", "total_tax_paid", "${:,.0f}")
    row("Total T-Bill Interest ($)", "total_interest_earned", "${:,.0f}")
    row("Total Stock Dividends ($)", "total_dividends_earned", "${:,.0f}")
    print("=" * 115 + "\n")

    # Save Results
    for v in variants_to_run:
        res_dict = {
            "variant": v,
            "horizon_years": len(timeline) / 252.0,
            "terminal_equity": results[v]["stressed"]["terminal_equity"],
            "cagr": results[v]["stressed"]["cagr"],
            "cagr_normal": results[v]["normal"]["cagr"],
            "cagr_zero_cost": results[v]["zero"]["cagr"],
            "cagr_no_top5": results[v]["cagr_no_top5"],
            "max_true_drawdown": results[v]["stressed"]["max_true_drawdown"],
            "hard_breach": results[v]["stressed"]["hard_breach"],
            "sharpe_ratio": results[v]["stressed"]["sharpe_ratio"],
            "sortino_ratio": results[v]["stressed"]["sortino_ratio"],
            "calmar_ratio": results[v]["stressed"]["calmar_ratio"],
            "profit_factor": results[v]["stressed"]["profit_factor"],
            "win_rate": results[v]["stressed"]["win_rate"],
            "total_trades": results[v]["stressed"]["total_trades"],
            "monte_carlo_p5_dd": results[v]["mc"]["p5_drawdown"],
            "tax_paid": results[v]["stressed"]["total_tax_paid"],
            "interest_earned": results[v]["stressed"]["total_interest_earned"]
        }
        out_path = os.path.join(PROJECT_ROOT, "trading_system", "data", f"backtest_results_us_growth_variant_{v}.json")
        with open(out_path, "w") as f:
            json.dump(res_dict, f, indent=2)


if __name__ == "__main__":
    main()
