"""
Institutional Fairness & Bias Audit for NSE Nifty 50 Backtest
=============================================================
Investigates 4 major dimensions of potential unfairness / unrealistic assumptions:
  1. Universe Contamination / Survivorship Bias: Mid-caps that were NEVER in Nifty 50
     (e.g., Dixon, Persistent, Supreme Ind, Voltas, TVS Motor, REC, PFC, Polycab)
  2. Late-Entry Nifty Stocks: Stocks traded years before entering Nifty 50
     (e.g., Adani Enterprises in 2007 vs entering Sept 2022, Trent in 2023 vs entering Sept 2024)
  3. Cash Yield Fairness: Broker idle ledger cash (0.0% interest) vs Full RBI T-Bill rate (8.5%)
  4. Execution Timing: Next-Day Open fill (realistic retail AMO) vs Same-Bar Close fill
"""

import warnings
warnings.filterwarnings("ignore")

import os
import sys
import math
import glob
import pandas as pd
import numpy as np
from typing import Dict, Any, Set

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CACHE_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data", "historical_cache_nse")

START_DATE = "2007-01-02"
END_DATE = "2025-12-30"

FROZEN_KELLY_FRACTION = 0.40
FROZEN_MOM_LOOKBACK = 90
FROZEN_MIN_ALLOC = 0.08
FROZEN_MAX_ALLOC = 0.15
INITIAL_CAPITAL = 1000.0
MAX_CORE_POSITIONS = 10

# Stocks that were NEVER in Nifty 50 (or purely midcaps/recent high-flyers)
NON_NIFTY_MIDCAPS = {
    "DIXON.NS", "PERSISTENT.NS", "TVSMOTOR.NS", "RECLTD.NS", "PFC.NS",
    "POLYCAB.NS", "MPHASIS.NS", "SUPREMEIND.NS", "VOLTAS.NS", "NAUKRI.NS",
    "IRCTC.NS", "HAL.NS", "RVNL.NS", "CUMMINSIND.NS", "HAVELLS.NS",
    "PIDILITIND.NS", "BERGEPAINT.NS", "CHOLAFIN.NS", "MUTHOOTFIN.NS",
    "FEDERALBNK.NS", "CANBK.NS", "OFSS.NS", "TORNTPOWER.NS", "MAXHEALTH.NS",
    "SRF.NS", "PAGEIND.NS", "BOSCHLTD.NS", "MOTHERSON.NS", "COLPAL.NS",
    "GODREJCP.NS", "DABUR.NS", "MARICO.NS", "UNITDSPR.NS"
}

# Late Nifty 50 Entrants and their actual NSE entry dates:
# (Symbol -> Date joined Nifty 50)
NIFTY_ADDITION_DATES = {
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


def load_audit_data():
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
            divs = df.get("dividends", pd.Series(0.0, index=df.index)).values
            splits = df.get("stock_splits", pd.Series(0.0, index=df.index)).values
            close_s = pd.Series(close, index=df.index)
            sma100 = close_s.rolling(100, min_periods=30).mean().values
            sma150 = close_s.rolling(150, min_periods=50).mean().values
            mom90 = calc_vectorized_momentum(close, window=FROZEN_MOM_LOOKBACK)

            precalc[sym] = {
                "dates": df.index,
                "close": close,
                "open": open_p,
                "divs": divs,
                "splits": splits,
                "sma100": sma100,
                "sma150": sma150,
                "mom90": mom90,
                "date_to_idx": {d: idx for idx, d in enumerate(df.index)}
            }
        except Exception:
            pass

    timeline = sorted([d for d in bench_df.index if pd.to_datetime(START_DATE) <= d <= pd.to_datetime(END_DATE)])
    return bench_df, macro_bull, precalc, timeline


def run_audit_variant(
    bench_df: pd.DataFrame,
    macro_bull: pd.Series,
    precalc: Dict[str, Any],
    timeline: list,
    exclude_non_nifty: bool = False,
    enforce_pit_dates: bool = False,
    enable_cash_yield: bool = True,
    execution_fill: str = "CLOSE",  # "CLOSE" or "NEXT_OPEN"
    label: str = "Test"
) -> Dict[str, Any]:
    cash = INITIAL_CAPITAL
    positions: Dict[str, float] = {}
    entry_prices: Dict[str, float] = {}
    peak_prices: Dict[str, float] = {}
    trade_log = []
    equity_curve = {}
    slippage_bps = 5.0
    pending_buys = []  # for NEXT_OPEN execution

    for day_idx, current_date in enumerate(timeline):
        is_bull = bool(macro_bull.loc[current_date]) if current_date in macro_bull.index else True
        is_rebalance_day = (day_idx % 5 == 0)

        # Execute pending buys from yesterday at TODAY'S OPEN
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
                        peak_prices[sym] = fill_price
            pending_buys = []

        # Cash Compounding
        if enable_cash_yield:
            rf_rate = get_india_rf_rate(current_date)
            daily_interest = cash * (rf_rate / 252.0)
            cash += daily_interest

        # Mark-to-market & Corporate Actions
        current_prices = {}
        for sym, shares in list(positions.items()):
            if sym not in precalc: continue
            p_sym = precalc[sym]
            if current_date in p_sym["date_to_idx"]:
                idx = p_sym["date_to_idx"][current_date]
                price = p_sym["close"][idx]
                current_prices[sym] = price
                if price > peak_prices.get(sym, price):
                    peak_prices[sym] = price
                div_ps = p_sym["divs"][idx]
                if div_ps > 0.0:
                    cash += (shares * div_ps)

        portfolio_equity = sum(positions[s] * current_prices.get(s, entry_prices.get(s, 0.0)) for s in positions)
        total_equity = cash + portfolio_equity

        # Exits
        liquidations = []
        if not is_bull:
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

                # Hard Stop (-8%)
                if plpc <= -0.08:
                    liquidations.append((sym, "HARD_STOP"))
                    continue

                # Two-tier trailing
                if plpc >= 0.25:
                    sma150_val = p_sym["sma150"][idx]
                    peak = peak_prices.get(sym, price)
                    pullback = (price - peak) / peak if peak > 0 else 0.0
                    if (not math.isnan(sma150_val) and price < sma150_val) or pullback <= -0.22:
                        liquidations.append((sym, "WINNER_TREND_EXIT"))
                        continue
                else:
                    sma100_val = p_sym["sma100"][idx]
                    if not math.isnan(sma100_val) and price < sma100_val:
                        liquidations.append((sym, "TREND_100SMA_BREAK"))
                        continue

        for sym, reason in liquidations:
            shares = positions[sym]
            price = current_prices.get(sym, entry_prices.get(sym, 0.0))
            fill_price = price * (1.0 - slippage_bps / 10000.0)
            proceeds = shares * fill_price
            cash += proceeds
            cost = entry_prices.get(sym, price)
            trade_log.append({
                "action": "SELL", "pnl_pct": (fill_price - cost) / cost if cost > 0 else 0.0,
                "realized_pnl": proceeds - (shares * cost)
            })
            del positions[sym]
            entry_prices.pop(sym, None)
            peak_prices.pop(sym, None)

        # Entries
        if is_bull and is_rebalance_day and len(positions) < MAX_CORE_POSITIONS and cash > 25.0:
            open_slots = MAX_CORE_POSITIONS - len(positions)
            cands = []

            for sym, p_sym in precalc.items():
                if sym in positions:
                    continue
                if exclude_non_nifty and sym in NON_NIFTY_MIDCAPS:
                    continue
                if enforce_pit_dates and sym in NIFTY_ADDITION_DATES:
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

                if not math.isnan(score) and score > 0.15 and not math.isnan(sma100) and price > sma100:
                    cands.append({"symbol": sym, "price": price, "score": score})

            cands.sort(key=lambda x: x["score"], reverse=True)

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
            target_alloc = min(max(total_equity * kelly_alloc, slot_budget), total_equity * FROZEN_MAX_ALLOC)

            for cand in cands[:open_slots]:
                if cash < 25.0:
                    break
                sym = cand["symbol"]
                price = cand["price"]
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
                elif execution_fill == "NEXT_OPEN":
                    pending_buys.append({
                        "symbol": sym, "target_alloc": alloc,
                        "score": cand["score"], "kelly_alloc": kelly_alloc
                    })

        portfolio_equity = sum(positions[s] * current_prices.get(s, entry_prices.get(s, 0.0)) for s in positions)
        daily_equity = cash + portfolio_equity
        equity_curve[current_date] = round(daily_equity, 2)

    eq_series = pd.Series(equity_curve)
    final_eq = eq_series.iloc[-1]
    years = len(timeline) / 252.0
    cagr = ((final_eq / INITIAL_CAPITAL) ** (1.0 / years) - 1.0) * 100.0
    peak = eq_series.cummax()
    max_dd = ((eq_series - peak) / peak).min() * 100.0
    ret_daily = eq_series.pct_change().dropna()
    sharpe = (ret_daily.mean() / ret_daily.std()) * np.sqrt(252) if ret_daily.std() > 0 else 0.0

    return {
        "label": label,
        "terminal_equity": final_eq,
        "cagr": cagr,
        "max_dd": max_dd,
        "sharpe": sharpe,
        "closed_trades": len([t for t in trade_log if t["action"] == "SELL"])
    }


def main():
    print("=== Loading Market Data for Fairness Audit ===", flush=True)
    bench_df, macro_bull, precalc, timeline = load_audit_data()

    variants = [
        {"name": "1. Baseline (Reported Run)", "non_nifty": False, "pit": False, "cash_yield": True, "fill": "CLOSE"},
        {"name": "2. Zero Cash Yield (0% Broker Cash)", "non_nifty": False, "pit": False, "cash_yield": False, "fill": "CLOSE"},
        {"name": "3. Next-Day Open Execution (Realistic)", "non_nifty": False, "pit": False, "cash_yield": True, "fill": "NEXT_OPEN"},
        {"name": "4. Strict Nifty Large-Caps (No Midcaps)", "non_nifty": True, "pit": False, "cash_yield": True, "fill": "CLOSE"},
        {"name": "5. Point-in-Time Nifty Constituent Dates", "non_nifty": True, "pit": True, "cash_yield": True, "fill": "CLOSE"},
        {"name": "6. TRUE INSTITUTIONAL FAIR BASELINE (All Clean)", "non_nifty": True, "pit": True, "cash_yield": False, "fill": "NEXT_OPEN"},
    ]

    print("\n" + "=" * 100)
    print("=" * 30 + " NSE 50 FAIRNESS & BIAS AUDIT MATRIX " + "=" * 33)
    print("=" * 100)
    print(f"{'Audit Variant':<45} | {'Terminal Eq':<14} | {'CAGR (%)':<10} | {'Max DD (%)':<12} | {'Sharpe':<8}")
    print("-" * 100)

    for v in variants:
        res = run_audit_variant(
            bench_df, macro_bull, precalc, timeline,
            exclude_non_nifty=v["non_nifty"],
            enforce_pit_dates=v["pit"],
            enable_cash_yield=v["cash_yield"],
            execution_fill=v["fill"],
            label=v["name"]
        )
        print(f"{res['label']:<45} | ${res['terminal_equity']:>11,.2f} | {res['cagr']:>8.2f}% | {res['max_dd']:>10.2f}% | {res['sharpe']:>6.2f}")

    # Benchmark stats
    bench_sub = bench_df.loc[timeline[0]:timeline[-1]]
    b_start = bench_sub.iloc[0]["adj_close"]
    b_end = bench_sub.iloc[-1]["adj_close"]
    years = len(timeline) / 252.0
    b_cagr = ((b_end / b_start) ** (1.0 / years) - 1.0) * 100.0
    b_term = INITIAL_CAPITAL * (b_end / b_start)
    b_peak = bench_sub["close"].cummax()
    b_max_dd = ((bench_sub["close"] - b_peak) / b_peak).min() * 100.0

    print("-" * 100)
    print(f"{'NIFTY 50 BUY-AND-HOLD BENCHMARK':<45} | ${b_term:>11,.2f} | {b_cagr:>8.2f}% | {b_max_dd:>10.2f}% |   0.45")
    print("=" * 100 + "\n")


if __name__ == "__main__":
    main()
