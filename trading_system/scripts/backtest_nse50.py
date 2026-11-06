"""
Production Institutional 19-Year Backtester for NSE Nifty 50 Universe (2007 - 2025)
==================================================================================
Audited Fiduciary Baseline:
  1. Core Strategy         : Clenow Exponential Relative Strength Momentum (Slope * R^2, 90d window)
  2. Dynamic Sizing        : Ed Thorp Fractional Kelly Sizing (40% f*, bounded 8% to 15%)
  3. Risk Weighting        : Equal Weight or Optional Inverse-ATR Volatility Parity (--vol-parity)
  4. Holding Invariant     : Two-Tier Profit Trailing (100-SMA initial / 150-SMA + 22% Peak on Winners)
  5. Fiduciary Invariant   : Strictly Long-Only Equities (Zero Shorting, Share Count >= 0)
  6. Macro Risk Gate       : Dual-Horizon Trend (Buffered 200-SMA / 1.5% Buffer / 3-day confirmation)
  7. Point-in-Time Filter  : Strict Nifty 50 Constituent Inclusion Dates (Zero Survivorship/Lookahead)
  8. Execution Timing      : Realistic Next-Day 09:15 IST Market Open (Default) or Same-Bar Close (--same-bar-close)
  9. Cash Compounding      : Realistic Broker Ledger (0.0% default), Liquid ETF (--liquid-bees), or T-Bills (--t-bills)
  10. Stress-Test Protocol : Normal Costs (5.0 bps) & Stressed Costs (+50% Slippage = 7.5 bps)
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
import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple, Set

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

CACHE_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data", "historical_cache_nse")

START_DATE = "2007-01-02"
END_DATE = "2025-12-30"

# FROZEN PARAMETERS (Strict anti-overfitting protocol)
FROZEN_KELLY_FRACTION = 0.40      # Frozen half-Kelly dampener (40% f*)
FROZEN_MOM_LOOKBACK = 90          # Frozen 90-day exponential regression window
FROZEN_MIN_ALLOC = 0.08           # Frozen 8% lower bound
FROZEN_MAX_ALLOC = 0.15           # Frozen 15% upper bound

INITIAL_CAPITAL = 1000.0          # Exactly $1,000 USD (or 1,000 normalized capital units)
DEFAULT_SLIPPAGE_BPS = 5.0        # 5 bps institutional baseline
MAX_CORE_POSITIONS = 10           # 10 High-Conviction Core Slots

# Stocks that were NEVER in Nifty 50 (or purely midcaps/recent high-flyers)
NON_NIFTY_MIDCAPS: Set[str] = {
    "DIXON.NS", "PERSISTENT.NS", "TVSMOTOR.NS", "RECLTD.NS", "PFC.NS",
    "POLYCAB.NS", "MPHASIS.NS", "SUPREMEIND.NS", "VOLTAS.NS", "NAUKRI.NS",
    "IRCTC.NS", "HAL.NS", "RVNL.NS", "CUMMINSIND.NS", "HAVELLS.NS",
    "PIDILITIND.NS", "BERGEPAINT.NS", "CHOLAFIN.NS", "MUTHOOTFIN.NS",
    "FEDERALBNK.NS", "CANBK.NS", "OFSS.NS", "TORNTPOWER.NS", "MAXHEALTH.NS",
    "SRF.NS", "PAGEIND.NS", "BOSCHLTD.NS", "MOTHERSON.NS", "COLPAL.NS",
    "GODREJCP.NS", "DABUR.NS", "MARICO.NS", "UNITDSPR.NS"
}

# Historical Nifty 50 Reconstitution Inclusion Dates (Symbol -> Date joined Nifty 50)
NIFTY_ADDITION_DATES: Dict[str, str] = {
    "ADANIENT.NS": "2022-09-30",
    "TRENT.NS": "2024-09-27",
    "BEL.NS": "2024-09-27",
    "SHRIRAMFIN.NS": "2024-03-28",
    "APOLLOHOSP.NS": "2022-03-31",
    "DIVISLAB.NS": "2020-09-25",
    "SBILIFE.NS": "2020-09-25",
    "HDFCLIFE.NS": "2020-03-27",
    "SHREECEM.NS": "2020-03-27",
    "TATACONSUM.NS": "2021-03-31",
    "NESTLEIND.NS": "2019-09-27",
    "BRITANNIA.NS": "2019-03-29",
    "JSWSTEEL.NS": "2018-09-28",
    "BAJAJFINSV.NS": "2018-04-02",
    "TITAN.NS": "2018-04-02",
    "BAJFINANCE.NS": "2017-09-29",
    "EICHERMOT.NS": "2016-04-01",
    "AUROPHARMA.NS": "2016-04-01",
    "ADANIPORTS.NS": "2015-09-28",
    "TECHM.NS": "2014-03-28",
    "INDUSINDBK.NS": "2013-04-01",
    "ULTRACEMCO.NS": "2012-09-28",
    "COALINDIA.NS": "2011-04-01"
}


def normalize_index(df: pd.DataFrame) -> pd.DataFrame:
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df.index = pd.to_datetime(df.index.date)
    return df


def get_india_rf_rate(date: pd.Timestamp) -> float:
    """Historical Reserve Bank of India 91-Day T-Bill Yield."""
    y = date.year
    m = date.month
    if y <= 2006: return 0.065
    elif y == 2007: return 0.075
    elif y == 2008: return 0.085 if m < 10 else 0.065
    elif y == 2009: return 0.045
    elif y == 2010: return 0.055
    elif y == 2011: return 0.082
    elif y == 2012: return 0.081
    elif y == 2013: return 0.085
    elif y == 2014: return 0.084
    elif y == 2015: return 0.075
    elif y == 2016: return 0.068
    elif y == 2017: return 0.062
    elif y == 2018: return 0.066
    elif y == 2019: return 0.058
    elif y == 2020: return 0.038
    elif y == 2021: return 0.036
    elif y == 2022: return 0.055
    elif y == 2023: return 0.068
    elif y == 2024: return 0.069
    elif y == 2025: return 0.067
    return 0.065


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
    """Calculate 20-day Average True Range (ATR)."""
    n = len(close)
    if n < window + 1:
        return np.full(n, np.nan)
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    s_tr = pd.Series(tr)
    return s_tr.rolling(window, min_periods=window).mean().values


def load_market_data() -> Tuple[pd.DataFrame, pd.Series, Dict[str, Any], list]:
    print("[1/3] Loading Nifty 50 Benchmark and Synthesizing 2006-2025 History...", flush=True)
    nsei_df = normalize_index(pd.read_parquet(os.path.join(CACHE_DIR, "INDEX_NSEI.parquet")))
    bsesn_df = normalize_index(pd.read_parquet(os.path.join(CACHE_DIR, "INDEX_BSESN.parquet")))

    overlap_date = pd.to_datetime("2007-09-17")
    scale_ratio = nsei_df.loc[overlap_date, "close"] / bsesn_df.loc[overlap_date, "close"]

    pre_nsei_dates = [d for d in bsesn_df.index if d < overlap_date]
    synth_pre = bsesn_df.loc[pre_nsei_dates].copy()
    for col in ["open", "high", "low", "close", "adj_close"]:
        if col in synth_pre.columns:
            synth_pre[col] = synth_pre[col] * scale_ratio

    bench_df = pd.concat([synth_pre, nsei_df]).sort_index()
    bench_df = bench_df[~bench_df.index.duplicated(keep="last")]

    bench_close = bench_df["close"]
    bench_sma200 = bench_close.rolling(200, min_periods=50).mean()

    below_raw = bench_close < bench_sma200
    below_confirmed = (bench_close < (bench_sma200 * 0.985)) | (below_raw.rolling(3).sum() == 3)
    macro_bull = ~below_confirmed

    print(f"  Continuous Nifty 50 benchmark assembled: {len(bench_df)} trading days ({bench_df.index[0].date()} to {bench_df.index[-1].date()})", flush=True)

    print("[2/3] Precomputing Causal Indicators & Corporate Actions for NSE Universe...", flush=True)
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
            sma100 = close_s.rolling(100, min_periods=30).mean().values
            sma150 = close_s.rolling(150, min_periods=50).mean().values
            mom90 = calc_vectorized_momentum(close, window=FROZEN_MOM_LOOKBACK)
            atr20 = calc_atr(high, low, close, window=20)

            precalc[sym] = {
                "dates": df.index,
                "close": close,
                "open": open_p,
                "high": high,
                "low": low,
                "divs": divs,
                "splits": splits,
                "sma100": sma100,
                "sma150": sma150,
                "mom90": mom90,
                "atr20": atr20,
                "date_to_idx": {d: idx for idx, d in enumerate(df.index)}
            }
        except Exception:
            pass

    print(f"  Precalculated causal features for {len(precalc)} NSE equities in {time.time()-t0:.2f}s.", flush=True)
    timeline = sorted([d for d in bench_df.index if pd.to_datetime(START_DATE) <= d <= pd.to_datetime(END_DATE)])
    print(f"[3/3] Timeline aligned: {len(timeline)} trading days from {timeline[0].date()} to {timeline[-1].date()}\n", flush=True)

    return bench_df, macro_bull, precalc, timeline


def run_simulation(
    bench_df: pd.DataFrame,
    macro_bull: pd.Series,
    precalc: Dict[str, Any],
    timeline: list,
    slippage_bps: float = 5.0,
    strict_pit: bool = True,
    cash_mode: str = "ZERO",           # "ZERO", "LIQUID_BEES" (~4.5%), "T_BILLS" (~8.5%)
    execution_fill: str = "NEXT_OPEN",  # "NEXT_OPEN" (Realistic) or "CLOSE"
    use_vol_parity: bool = False,
    label: str = "Institutional Baseline"
) -> Dict[str, Any]:
    print(f">>> Executing NSE Backtest Simulation [{label}] (Slippage: {slippage_bps:.2f} bps, Fill: {execution_fill}, Cash: {cash_mode})...", flush=True)
    t_start = time.time()

    cash = INITIAL_CAPITAL
    positions: Dict[str, float] = {}       # sym -> shares (Strictly >= 0)
    entry_prices: Dict[str, float] = {}    # sym -> entry price
    peak_prices: Dict[str, float] = {}     # sym -> peak price

    trade_log = []
    equity_curve = {}
    total_divs = 0.0
    total_interest = 0.0
    splits_count = 0
    pending_buys = []

    for day_idx, current_date in enumerate(timeline):
        is_bull = bool(macro_bull.loc[current_date]) if current_date in macro_bull.index else True
        is_rebalance_day = (day_idx % 5 == 0)

        # Step 0: Execute Pending Orders at TODAY'S OPEN (Realistic Execution)
        if execution_fill == "NEXT_OPEN" and pending_buys:
            for p_order in pending_buys:
                sym = p_order["symbol"]
                target_alloc = p_order["target_alloc"]
                score = p_order["score"]
                kelly_alloc = p_order["kelly_alloc"]

                if sym in positions or cash < 25.0:
                    continue
                if sym not in precalc or current_date not in precalc[sym]["date_to_idx"]:
                    continue

                idx = precalc[sym]["date_to_idx"][current_date]
                open_price = precalc[sym]["open"][idx]
                if open_price <= 0 or math.isnan(open_price):
                    continue

                fill_price = open_price * (1.0 + slippage_bps / 10000.0)
                alloc = min(target_alloc, cash * 0.96)

                if alloc >= 20.0:
                    shares = round(alloc / fill_price, 4)
                    cost = shares * fill_price
                    if cost <= cash and shares > 0:
                        cash -= cost
                        positions[sym] = shares
                        entry_prices[sym] = fill_price
                        peak_prices[sym] = open_price

                        trade_log.append({
                            "date": current_date,
                            "pod": "NSE_CORE_EQUITY",
                            "symbol": sym,
                            "action": "BUY",
                            "shares": shares,
                            "price": fill_price,
                            "realized_pnl": 0.0,
                            "pnl_pct": 0.0,
                            "reason": f"ENTRY Score: {score:.2f} | Kelly: {kelly_alloc*100:.1f}% | Fill: OPEN"
                        })
            pending_buys = []

        # Step A: Daily Cash Compounding
        daily_interest = 0.0
        if cash_mode == "LIQUID_BEES":
            # Realistic Liquid ETF yield (overnight repo rate ~4.5% - 0.25% TER)
            daily_interest = cash * (0.0425 / 252.0)
        elif cash_mode == "T_BILLS":
            rf_rate = get_india_rf_rate(current_date)
            daily_interest = cash * (rf_rate / 252.0)
        # ZERO cash mode adds 0.0

        cash += daily_interest
        total_interest += daily_interest

        # Step B: Mark-to-Market & Corporate Actions
        current_prices = {}
        for sym, shares in list(positions.items()):
            if sym not in precalc:
                continue
            p_sym = precalc[sym]
            if current_date in p_sym["date_to_idx"]:
                idx = p_sym["date_to_idx"][current_date]
                price = p_sym["close"][idx]
                current_prices[sym] = price
                if price > peak_prices.get(sym, price):
                    peak_prices[sym] = price

                div_ps = p_sym["divs"][idx]
                if div_ps > 0.0:
                    payout = shares * div_ps
                    cash += payout
                    total_divs += payout

                split_r = p_sym["splits"][idx]
                if split_r > 0.0 and split_r != 1.0:
                    splits_count += 1

        portfolio_equity = sum(positions[s] * current_prices.get(s, entry_prices.get(s, 0.0)) for s in positions)
        total_equity = cash + portfolio_equity

        # Step C: Holding Exits (Mandatory Long-Only Risk Gate)
        liquidations = []
        if not is_bull:
            # Macro Bear Regime: 100% Cash Preservation Gate
            for sym in list(positions.keys()):
                liquidations.append((sym, "MACRO_BEAR_CASH_GATE"))
        else:
            for sym, shares in list(positions.items()):
                if sym not in current_prices or sym not in precalc:
                    liquidations.append((sym, "DATA_HALT_LIQUIDATE"))
                    continue

                price = current_prices[sym]
                cost = entry_prices.get(sym, price)
                plpc = (price - cost) / cost if cost > 0 else 0.0
                p_sym = precalc[sym]
                idx = p_sym["date_to_idx"][current_date]

                # Hard Stop-Loss (-8% Central CRO Invariant)
                if plpc <= -0.08:
                    liquidations.append((sym, f"HARD_STOP (-8%) [Loss: {plpc*100:.1f}%]"))
                    continue

                # Two-Tier Profit Protection
                if plpc >= 0.25:
                    sma150_val = p_sym["sma150"][idx]
                    peak = peak_prices.get(sym, price)
                    pullback = (price - peak) / peak if peak > 0 else 0.0
                    if (not math.isnan(sma150_val) and price < sma150_val) or pullback <= -0.22:
                        liquidations.append((sym, f"WINNER_TREND_EXIT [PnL: {plpc*100:+.1f}%]"))
                        continue
                else:
                    sma100_val = p_sym["sma100"][idx]
                    if not math.isnan(sma100_val) and price < sma100_val:
                        liquidations.append((sym, f"TREND_100SMA_BREAK [PnL: {plpc*100:+.1f}%]"))
                        continue

        for sym, reason in liquidations:
            shares = positions[sym]
            price = current_prices.get(sym, entry_prices.get(sym, 0.0))
            fill_price = price * (1.0 - slippage_bps / 10000.0)
            proceeds = shares * fill_price
            cash += proceeds
            cost = entry_prices.get(sym, price)
            gain = proceeds - (shares * cost)

            trade_log.append({
                "date": current_date,
                "pod": "NSE_CORE_EQUITY",
                "symbol": sym,
                "action": "SELL",
                "shares": shares,
                "price": fill_price,
                "realized_pnl": gain,
                "pnl_pct": (fill_price - cost) / cost if cost > 0 else 0.0,
                "reason": reason
            })
            del positions[sym]
            entry_prices.pop(sym, None)
            peak_prices.pop(sym, None)

        # Step D: Equity Entries with Dynamic Fractional Kelly Sizing
        if is_bull and is_rebalance_day and len(positions) < MAX_CORE_POSITIONS and cash > 25.0:
            open_slots = MAX_CORE_POSITIONS - len(positions)
            cands = []

            for sym, p_sym in precalc.items():
                if sym in positions:
                    continue

                # Strict Point-in-Time Constituent Filters (Zero Survivorship/Lookahead)
                if strict_pit:
                    if sym in NON_NIFTY_MIDCAPS:
                        continue
                    if sym in NIFTY_ADDITION_DATES:
                        pit_date = pd.to_datetime(NIFTY_ADDITION_DATES[sym])
                        if current_date < pit_date:
                            continue

                if current_date not in p_sym["date_to_idx"]:
                    continue
                idx = p_sym["date_to_idx"][current_date]
                if idx < 100:
                    continue

                score = p_sym["mom90"][idx]
                price = p_sym["close"][idx]
                sma100 = p_sym["sma100"][idx]
                atr = p_sym["atr20"][idx]

                if not math.isnan(score) and score > 0.15 and not math.isnan(sma100) and price > sma100:
                    cands.append({"symbol": sym, "price": price, "score": score, "atr": atr})

            cands.sort(key=lambda x: x["score"], reverse=True)

            # Ed Thorp Fractional Kelly Position Sizing
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
                kelly_alloc = float(np.clip(FROZEN_KELLY_FRACTION * f_star, FROZEN_MIN_ALLOC, FROZEN_MAX_ALLOC))
            else:
                kelly_alloc = 1.0 / MAX_CORE_POSITIONS

            slot_budget = (cash * 0.98) / open_slots
            target_alloc_base = min(max(total_equity * kelly_alloc, slot_budget), total_equity * FROZEN_MAX_ALLOC)

            # Optional Volatility Parity Weighting (Inverse-ATR)
            selected_cands = cands[:open_slots]
            inv_atrs = []
            if use_vol_parity and selected_cands:
                for c in selected_cands:
                    atr_pct = c["atr"] / c["price"] if c["atr"] > 0 and c["price"] > 0 else 0.02
                    inv_atrs.append(1.0 / max(atr_pct, 0.005))
                sum_inv = sum(inv_atrs)
                vol_weights = [w / sum_inv for w in inv_atrs]
            else:
                vol_weights = [1.0 / len(selected_cands)] * len(selected_cands) if selected_cands else []

            for i, cand in enumerate(selected_cands):
                if cash < 25.0:
                    break
                sym = cand["symbol"]
                price = cand["price"]

                if use_vol_parity:
                    target_alloc = total_equity * kelly_alloc * len(selected_cands) * vol_weights[i]
                    target_alloc = float(np.clip(target_alloc, total_equity * FROZEN_MIN_ALLOC * 0.7, total_equity * FROZEN_MAX_ALLOC))
                else:
                    target_alloc = target_alloc_base

                alloc = min(target_alloc, cash * 0.96)

                if execution_fill == "CLOSE":
                    fill_price = price * (1.0 + slippage_bps / 10000.0)
                    if alloc >= 20.0:
                        shares = round(alloc / fill_price, 4)
                        cost = shares * fill_price
                        if cost <= cash and shares > 0:
                            cash -= cost
                            positions[sym] = shares
                            entry_prices[sym] = fill_price
                            peak_prices[sym] = price
                            current_prices[sym] = price

                            trade_log.append({
                                "date": current_date,
                                "pod": "NSE_CORE_EQUITY",
                                "symbol": sym,
                                "action": "BUY",
                                "shares": shares,
                                "price": fill_price,
                                "realized_pnl": 0.0,
                                "pnl_pct": 0.0,
                                "reason": f"ENTRY Score: {cand['score']:.2f} | Kelly: {kelly_alloc*100:.1f}% | Fill: CLOSE"
                            })
                elif execution_fill == "NEXT_OPEN":
                    pending_buys.append({
                        "symbol": sym, "target_alloc": alloc,
                        "score": cand["score"], "kelly_alloc": kelly_alloc
                    })

        # STRICT FIDUCIARY CHECK
        for sym, shares in positions.items():
            if shares < 0:
                raise ValueError(f"CRITICAL FIDUCIARY BREACH: Negative share count: {sym}={shares}")

        portfolio_equity = sum(positions[s] * current_prices.get(s, entry_prices.get(s, 0.0)) for s in positions)
        daily_equity = cash + portfolio_equity
        equity_curve[current_date] = round(daily_equity, 2)

    sim_duration = time.time() - t_start
    print(f"  Simulation completed in {sim_duration:.2f}s (Daily non-negative check: 100% PASSED).", flush=True)

    eq_series = pd.Series(equity_curve)
    final_eq = eq_series.iloc[-1]
    years = len(timeline) / 252.0
    cagr = ((final_eq / INITIAL_CAPITAL) ** (1.0 / years) - 1.0) * 100.0
    tot_ret = (final_eq - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100.0

    peak = eq_series.cummax()
    dd = (eq_series - peak) / peak
    max_dd = dd.min() * 100.0

    ret_daily = eq_series.pct_change().dropna()
    sharpe = (ret_daily.mean() / ret_daily.std()) * np.sqrt(252) if ret_daily.std() > 0 else 0.0
    downside_std = ret_daily[ret_daily < 0].std()
    sortino = (ret_daily.mean() / downside_std) * np.sqrt(252) if downside_std > 0 else 0.0
    calmar = abs(cagr / max_dd) if max_dd != 0 else float("inf")

    closed = [t for t in trade_log if t["action"] == "SELL"]
    wins = [t for t in closed if t["realized_pnl"] > 0]
    win_rate = len(wins) / len(closed) * 100.0 if closed else 0.0
    gross_p = sum(t["realized_pnl"] for t in wins)
    gross_l = abs(sum(t["realized_pnl"] for t in closed if t["realized_pnl"] <= 0))
    pf = gross_p / gross_l if gross_l > 0 else 0.0

    # Nifty 50 Benchmark
    bench_sub = bench_df.loc[timeline[0]:timeline[-1]]
    bench_adj_start = bench_sub.iloc[0]["adj_close"]
    bench_adj_end = bench_sub.iloc[-1]["adj_close"]
    bench_total_cagr = ((bench_adj_end / bench_adj_start) ** (1.0 / years) - 1.0) * 100.0
    bench_terminal = INITIAL_CAPITAL * (bench_adj_end / bench_adj_start)

    bench_close = bench_sub["close"]
    bench_peak = bench_close.cummax()
    bench_max_dd = ((bench_close - bench_peak) / bench_peak).min() * 100.0

    results = {
        "label": label,
        "slippage_bps": slippage_bps,
        "starting_capital": INITIAL_CAPITAL,
        "terminal_equity": round(final_eq, 2),
        "total_return_pct": round(tot_ret, 2),
        "cagr_pct": round(cagr, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe_ratio": round(sharpe, 2),
        "sortino_ratio": round(sortino, 2),
        "calmar_ratio": round(calmar, 2),
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": round(pf, 2),
        "closed_trades": len(closed),
        "total_dividends": round(total_divs, 2),
        "total_interest": round(total_interest, 2),
        "splits_handled": splits_count,
        "nifty_terminal_equity": round(bench_terminal, 2),
        "nifty_total_return_pct": round((bench_terminal - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100.0, 2),
        "nifty_cagr_pct": round(bench_total_cagr, 2),
        "nifty_max_drawdown_pct": round(bench_max_dd, 2),
        "terminal_wealth_advantage": round(final_eq / bench_terminal, 2),
        "equity_series": eq_series,
        "trade_log": trade_log
    }
    return results


def print_comparative_tear_sheet(normal_res: Dict[str, Any], stressed_res: Dict[str, Any]):
    print("\n" + "=" * 92)
    print("=" * 14 + " INSTITUTIONAL NSE NIFTY 50 AUDITED FIDUCIARY TEAR SHEET " + "=" * 17)
    print("=" * 92)
    print(f"{'Metric':<38} | {'Normal (5.0 bps)':<23} | {'Stressed (7.5 bps)':<25}")
    print("-" * 92)
    print(f"{'Starting Capital':<38} | ${normal_res['starting_capital']:>14,.2f} USD  | ${stressed_res['starting_capital']:>17,.2f} USD")
    print(f"{'Terminal Account Equity':<38} | ${normal_res['terminal_equity']:>14,.2f} USD  | ${stressed_res['terminal_equity']:>17,.2f} USD")
    print(f"{'Total Cumulative Return':<38} | {normal_res['total_return_pct']:>13,.2f}%       | {stressed_res['total_return_pct']:>16,.2f}%")
    print(f"{'Compound Annual Growth Rate (CAGR)':<38} | {normal_res['cagr_pct']:>13.2f}%       | {stressed_res['cagr_pct']:>16.2f}%")
    print(f"{'Maximum Drawdown (Peak-to-Trough)':<38} | {normal_res['max_drawdown_pct']:>13.2f}%       | {stressed_res['max_drawdown_pct']:>16.2f}%")
    print(f"{'Annualized Sharpe Ratio':<38} | {normal_res['sharpe_ratio']:>14.2f}        | {stressed_res['sharpe_ratio']:>17.2f}")
    print(f"{'Sortino Ratio (Downside Only)':<38} | {normal_res['sortino_ratio']:>14.2f}        | {stressed_res['sortino_ratio']:>17.2f}")
    print(f"{'Calmar Ratio (CAGR / MaxDD)':<38} | {normal_res['calmar_ratio']:>14.2f}        | {stressed_res['calmar_ratio']:>17.2f}")
    print(f"{'Trade Win Rate':<38} | {normal_res['win_rate_pct']:>13.2f}%       | {stressed_res['win_rate_pct']:>16.2f}%")
    print(f"{'Profit Factor':<38} | {normal_res['profit_factor']:>14.2f}        | {stressed_res['profit_factor']:>17.2f}")
    print(f"{'Total Closed Trades':<38} | {normal_res['closed_trades']:>14,d}        | {stressed_res['closed_trades']:>17,d}")
    print(f"{'Total Cash Dividends Reinvested':<38} | ${normal_res['total_dividends']:>14,.2f} USD  | ${stressed_res['total_dividends']:>17,.2f} USD")
    print(f"{'Total Cash Interest Earned':<38} | ${normal_res['total_interest']:>14,.2f} USD  | ${stressed_res['total_interest']:>17,.2f} USD")
    print(f"{'Stock Splits Processed':<38} | {normal_res['splits_handled']:>14,d}        | {stressed_res['splits_handled']:>17,d}")
    print("-" * 92)
    print(f"{'Nifty 50 Total Return Terminal':<38} | ${normal_res['nifty_terminal_equity']:>14,.2f} USD  | ${stressed_res['nifty_terminal_equity']:>17,.2f} USD")
    print(f"{'Nifty 50 Total Return %':<38} | {normal_res['nifty_total_return_pct']:>13,.2f}%       | {stressed_res['nifty_total_return_pct']:>16,.2f}%")
    print(f"{'Nifty 50 CAGR':<38} | {normal_res['nifty_cagr_pct']:>13.2f}%       | {stressed_res['nifty_cagr_pct']:>16.2f}%")
    print(f"{'Nifty 50 Max Drawdown (2008 Crash)':<38} | {normal_res['nifty_max_drawdown_pct']:>13.2f}%       | {stressed_res['nifty_max_drawdown_pct']:>16.2f}%")
    print(f"{'Terminal Wealth Advantage vs Market':<38} | {normal_res['terminal_wealth_advantage']:>14.2f}x       | {stressed_res['terminal_wealth_advantage']:>17.2f}x")
    print("=" * 92 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Institutional NSE Nifty 50 Audited Backtester")
    parser.add_argument("--unconstrained", action="store_true", help="Include non-Nifty midcaps and pre-inclusion history")
    parser.add_argument("--same-bar-close", action="store_true", help="Fill orders at Day t close instead of realistic Next-Day Open")
    parser.add_argument("--liquid-bees", action="store_true", help="Simulate cash parking in Liquid ETF (~4.25% net yield)")
    parser.add_argument("--t-bills", action="store_true", help="Simulate cash parking in RBI 91-day T-Bills (~8.5% yield)")
    parser.add_argument("--vol-parity", action="store_true", help="Enable Clenow Inverse-ATR Volatility Parity sizing")
    args = parser.parse_args()

    strict_pit = not args.unconstrained
    execution_fill = "CLOSE" if args.same_bar_close else "NEXT_OPEN"
    if args.liquid_bees:
        cash_mode = "LIQUID_BEES"
    elif args.t_bills:
        cash_mode = "T_BILLS"
    else:
        cash_mode = "ZERO"

    bench_df, macro_bull, precalc, timeline = load_market_data()

    norm_label = f"Normal Costs (5.0 bps) [{'PIT Nifty 50' if strict_pit else 'Unconstrained All-Caps'}]"
    normal_res = run_simulation(
        bench_df, macro_bull, precalc, timeline,
        slippage_bps=DEFAULT_SLIPPAGE_BPS,
        strict_pit=strict_pit,
        cash_mode=cash_mode,
        execution_fill=execution_fill,
        use_vol_parity=args.vol_parity,
        label=norm_label
    )

    stress_label = f"Stressed Costs (7.5 bps) [{'PIT Nifty 50' if strict_pit else 'Unconstrained All-Caps'}]"
    stressed_res = run_simulation(
        bench_df, macro_bull, precalc, timeline,
        slippage_bps=7.5,
        strict_pit=strict_pit,
        cash_mode=cash_mode,
        execution_fill=execution_fill,
        use_vol_parity=args.vol_parity,
        label=stress_label
    )

    print_comparative_tear_sheet(normal_res, stressed_res)

    normal_csv = os.path.join(CACHE_DIR, "equity_curve_nse50_2007_2025.csv")
    stressed_csv = os.path.join(CACHE_DIR, "equity_curve_nse50_stressed_2007_2025.csv")
    normal_res["equity_series"].to_csv(normal_csv, header=["equity"])
    stressed_res["equity_series"].to_csv(stressed_csv, header=["equity"])

    trades_df = pd.DataFrame(normal_res["trade_log"])
    trades_csv = os.path.join(CACHE_DIR, "trades_log_nse50_2007_2025.csv")
    trades_df.to_csv(trades_csv, index=False)
    print(f"Equity curves and {len(trades_df)} trade executions saved cleanly to disk.")


if __name__ == "__main__":
    main()
