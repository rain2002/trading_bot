"""
Stage 3: Weekly Shadow Replay & Fidelity Audit (NSE S2)
=======================================================
Replays the shadowed forward days using the committed S2 rules on the same
Yahoo Finance universe data, compares signals/fills/NAV against the live
zero-capital shadow logs, and appends a weekly fidelity row to:
  trading_system/data/nse_s2_shadow_fidelity.csv
"""

import os
import sys
import math
import json
import argparse
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from trading_system.scripts.run_nse_s2_shadow import (
    DATA_DIR,
    INITIAL_CAPITAL,
    CORE_SLOTS,
    MAX_ALLOC_PCT,
    MIN_SHARE_PRICE,
    MIN_MEDIAN_TURNOVER,
    MIN_HISTORY_DAYS,
    HARD_STOP_PCT,
    EXIT_SMA_WINDOW,
    TRAIL_TIERS,
    BUY_FRICTION_BPS,
    SELL_FRICTION_BPS,
    FLAT_DP_FEE,
    CASH_YIELD_PA,
    calc_clenow_score,
    fetch_nse_market_data,
    load_nse_s2_equity_universe,
)
from trading_system.app.data.corporate_actions import is_etf_ticker
from trading_system.app.research.momentum_crash import evaluate_dual_pod_regime_and_volatility

TRADES_CSV = os.path.join(DATA_DIR, "nse_s2_shadow_trades.csv")
EQUITY_LOG_CSV = os.path.join(DATA_DIR, "nse_s2_shadow_equity_log.csv")
FIDELITY_CSV = os.path.join(DATA_DIR, "nse_s2_shadow_fidelity.csv")

FIDELITY_COLUMNS = [
    "week_end_date",
    "shadow_days",
    "shadow_trades",
    "replay_trades",
    "signal_match_rate_pct",
    "shadow_nav",
    "replay_nav",
    "equity_gap_pct",
    "price_source",
    "data_faults",
    "fidelity_passed",
]


def _extract_row_date(row: pd.Series) -> str:
    """Extract YYYY-MM-DD session date cleanly from either production (`session_date`) or test (`date`) logs."""
    val = row.get("session_date")
    if val is None or (isinstance(val, float) and math.isnan(val)) or str(val).strip() == "":
        val = row.get("date")
    if val is None or (isinstance(val, float) and math.isnan(val)) or str(val).strip() == "":
        val = row.get("timestamp", "")
    return str(val).strip()[:10]


def compute_signal_match_rate(
    shadow_trades: pd.DataFrame,
    replay_trades: pd.DataFrame,
) -> float:
    """
    Computes % of (session_date, symbol, action) signals that match between shadow and replay.
    Returns 100.0 when both have 0 trades.
    """
    def to_key_set(df: pd.DataFrame) -> set:
        if df is None or df.empty:
            return set()
        return {
            (_extract_row_date(r), str(r["symbol"]).strip().upper(), str(r["action"]).strip().upper())
            for _, r in df.iterrows()
        }

    s_keys = to_key_set(shadow_trades)
    r_keys = to_key_set(replay_trades)
    union = s_keys | r_keys
    if not union:
        return 100.0
    return round(len(s_keys & r_keys) / len(union) * 100.0, 2)


def replay_shadow_window(
    shadow_dates: List[str],
    universe_data: Dict[str, pd.DataFrame],
    bench_df: pd.DataFrame,
    initial_capital: float = INITIAL_CAPITAL,
) -> Tuple[pd.DataFrame, List[Dict[str, Any]], List[str]]:
    """
    Pure causal replay of S2 shadow rules over `shadow_dates` using `universe_data`
    and `bench_df` (which include >= 252d warmup prior to shadow_dates[0]).
    Returns (replay_trades_df, daily_nav_rows, data_faults).
    """
    cash = float(initial_capital)
    positions: Dict[str, Dict[str, Any]] = {}
    pending_buys: List[Dict[str, Any]] = []
    pending_sells: List[Dict[str, Any]] = []
    replay_trades: List[Dict[str, Any]] = []
    nav_rows: List[Dict[str, Any]] = []
    data_faults: List[str] = []

    daily_cash_yield = (1.0 + CASH_YIELD_PA) ** (1.0 / 252.0) - 1.0

    for dt_str in shadow_dates:
        dt_ts = pd.to_datetime(dt_str)

        # 1. Execute pending sells at today's open (parity with NSES2ShadowRunner)
        for s_item in pending_sells:
            sym = s_item["sym"]
            if sym not in positions or sym not in universe_data:
                continue
            df_s = universe_data[sym]
            sub = df_s.loc[df_s.index <= dt_ts]
            if sub.empty:
                data_faults.append(f"{dt_str}:{sym}:missing_sell_bar")
                continue
            open_p = float(sub["open"].dropna().iloc[-1]) if "open" in sub.columns and not sub["open"].dropna().empty else float(sub["close"].iloc[-1])
            if math.isnan(open_p) or open_p <= 0:
                continue
            eff_sell = open_p * (1.0 - SELL_FRICTION_BPS / 10000.0)
            shares = positions[sym]["shares"]
            cash += max(0.0, shares * eff_sell - FLAT_DP_FEE)
            replay_trades.append({
                "date": dt_str,
                "symbol": sym,
                "action": "SELL",
                "shares": shares,
                "fill_price": round(eff_sell, 4),
            })
            del positions[sym]

        # 2. Execute pending buys at today's open (matching cash * 0.96 & MIN_SHARE_PRICE guard)
        for b_item in pending_buys:
            sym = b_item["sym"]
            if sym in positions or sym not in universe_data or is_etf_ticker(sym):
                continue
            df_s = universe_data[sym]
            sub = df_s.loc[df_s.index <= dt_ts]
            if sub.empty:
                data_faults.append(f"{dt_str}:{sym}:missing_buy_bar")
                continue
            open_p = float(sub["open"].dropna().iloc[-1]) if "open" in sub.columns and not sub["open"].dropna().empty else float(sub["close"].iloc[-1])
            if math.isnan(open_p) or open_p <= MIN_SHARE_PRICE:
                continue
            eff_buy = open_p * (1.0 + BUY_FRICTION_BPS / 10000.0)
            alloc = min(float(b_item["target_alloc"]), cash * 0.96)
            shares = math.floor(alloc / eff_buy)
            cost = shares * eff_buy
            if shares > 0 and cash >= cost:
                cash -= cost
                positions[sym] = {
                    "shares": shares,
                    "entry_price": round(eff_buy, 4),
                    "peak_price": round(eff_buy, 4),
                    "last_close": round(eff_buy, 4),
                }
                replay_trades.append({
                    "date": dt_str,
                    "symbol": sym,
                    "action": "BUY",
                    "shares": shares,
                    "fill_price": round(eff_buy, 4),
                })

        # Credit daily overnight yield AFTER open fills (parity with NSES2ShadowRunner)
        cash *= (1.0 + daily_cash_yield)

        # 3. Mark to market at today's close
        port_val = 0.0
        for sym, pos in positions.items():
            if sym in universe_data:
                sub = universe_data[sym].loc[universe_data[sym].index <= dt_ts]
                if not sub.empty:
                    c_p = float(sub.iloc[-1]["close"])
                    pos["last_close"] = c_p
                    if c_p > pos["peak_price"]:
                        pos["peak_price"] = c_p
            port_val += pos["shares"] * pos["last_close"]

        equity = cash + port_val
        nav_rows.append({"date": dt_str, "replay_nav": round(equity, 2)})

        # 4. Macro & Vol Radar as of dt_ts
        b_sub = bench_df.loc[bench_df.index <= dt_ts]
        radar = evaluate_dual_pod_regime_and_volatility(
            benchmark_df=b_sub, target_vol=0.15, vol_lookback=20,
            crash_vol_threshold=0.24, bear_sma_lookback=200, caution_scale_threshold=0.75,
        )
        macro_regime = radar["regime"]
        max_exposure = float(radar["max_exposure"])

        # 5. Evaluate next-day exits
        next_sells: List[Dict[str, Any]] = []
        if macro_regime == "BEAR_DEFENSE":
            for sym in list(positions.keys()):
                next_sells.append({"sym": sym, "reason": "BEAR_DEFENSE_EXIT"})
        else:
            for sym, pos in list(positions.items()):
                px = float(pos["last_close"])
                entry = float(pos["entry_price"])
                peak = float(pos["peak_price"])
                plpc = (px - entry) / entry if entry > 0 else 0.0
                pullback = (px - peak) / peak if peak > 0 else 0.0
                if plpc <= HARD_STOP_PCT:
                    next_sells.append({"sym": sym, "reason": "HARD_STOP"})
                    continue
                trailed = False
                for min_g, tr_stop in TRAIL_TIERS:
                    if plpc >= min_g and pullback <= tr_stop:
                        next_sells.append({"sym": sym, "reason": "TRAIL_TIER"})
                        trailed = True
                        break
                if trailed:
                    continue
                if sym in universe_data:
                    sub = universe_data[sym].loc[universe_data[sym].index <= dt_ts]
                    if len(sub) >= EXIT_SMA_WINDOW:
                        sma150 = float(sub["close"].rolling(EXIT_SMA_WINDOW, min_periods=112).mean().iloc[-1])
                        if px < sma150:
                            next_sells.append({"sym": sym, "reason": "TREND_SMA150_BREAK"})
        pending_sells = next_sells

        # 6. Evaluate next-day buys
        held_after = len(positions) - len(next_sells)
        open_slots = max(0, CORE_SLOTS - held_after)
        next_buys: List[Dict[str, Any]] = []
        if macro_regime != "BEAR_DEFENSE" and open_slots > 0 and cash > 500.0:
            cands = []
            for sym, df_s in universe_data.items():
                if is_etf_ticker(sym) or sym in positions or any(s["sym"] == sym for s in next_sells):
                    continue
                sub = df_s.loc[df_s.index <= dt_ts]
                if len(sub) < MIN_HISTORY_DAYS:
                    continue
                c_arr = sub["close"].values
                cur_p = float(c_arr[-1])
                if math.isnan(cur_p) or cur_p < MIN_SHARE_PRICE:
                    continue
                if "volume" in sub.columns:
                    med_val = float((sub["close"] * sub["volume"]).rolling(60, min_periods=20).median().iloc[-1])
                    if math.isnan(med_val) or med_val < MIN_MEDIAN_TURNOVER:
                        continue
                sma150 = float(pd.Series(c_arr).rolling(EXIT_SMA_WINDOW, min_periods=112).mean().iloc[-1])
                if cur_p <= sma150:
                    continue
                score = 0.60 * calc_clenow_score(c_arr, 90) + 0.40 * calc_clenow_score(c_arr, 180)
                if score > 0.10:
                    cands.append({"sym": sym, "score": score})

            cands.sort(key=lambda x: x["score"], reverse=True)
            avail = cash * 0.96
            target_per_slot = min(equity * MAX_ALLOC_PCT, equity / CORE_SLOTS) * max_exposure
            for c in cands[:open_slots]:
                if avail < 500.0 or target_per_slot < 500.0:
                    break
                alloc = min(target_per_slot, avail)
                next_buys.append({"sym": c["sym"], "target_alloc": round(alloc, 2)})
                avail -= alloc
        pending_buys = next_buys

    trades_df = pd.DataFrame(replay_trades)
    return trades_df, nav_rows, data_faults


def evaluate_weekly_fidelity(
    equity_log_path: str = EQUITY_LOG_CSV,
    trades_csv_path: str = TRADES_CSV,
    fidelity_csv_path: str = FIDELITY_CSV,
    universe_data: Optional[Dict[str, pd.DataFrame]] = None,
    bench_df: Optional[pd.DataFrame] = None,
    price_source: str = "Yahoo Finance (.NS)",
) -> Dict[str, Any]:
    """
    Evaluates shadow fidelity over logged shadow dates and appends a weekly row
    to `fidelity_csv_path`.
    """
    if not os.path.exists(equity_log_path):
        return {"status": "NO_SHADOW_LOG", "message": f"Shadow equity log not found: {equity_log_path}"}

    eq_df = pd.read_csv(equity_log_path)
    if eq_df.empty:
        return {"status": "EMPTY_SHADOW_LOG", "message": "Shadow equity log has 0 rows."}

    # Use canonical `session_date` (market bar date written by NSES2ShadowRunner), falling back to `date`
    eq_date_col = "session_date" if "session_date" in eq_df.columns else "date"
    shadow_dates = sorted(eq_df[eq_date_col].astype(str).str[:10].unique().tolist())
    shadow_nav = float(eq_df.iloc[-1]["nav"])
    week_end_date = shadow_dates[-1]

    sh_trades_df = pd.read_csv(trades_csv_path) if os.path.exists(trades_csv_path) else pd.DataFrame()
    if not sh_trades_df.empty:
        tr_date_col = "session_date" if "session_date" in sh_trades_df.columns else ("date" if "date" in sh_trades_df.columns else "timestamp")
        sh_trades_df = sh_trades_df[sh_trades_df[tr_date_col].astype(str).str[:10].isin(shadow_dates)]

    if universe_data is None or bench_df is None:
        tickers = load_nse_s2_equity_universe()
        if not sh_trades_df.empty and "symbol" in sh_trades_df.columns:
            tickers = sorted(list(set(tickers) | set(sh_trades_df["symbol"].astype(str).tolist())))
        universe_data, bench_df = fetch_nse_market_data(tickers)
        for df_s in universe_data.values():
            df_s.index = pd.to_datetime(df_s.index).tz_localize(None).normalize()
        if not bench_df.empty:
            bench_df.index = pd.to_datetime(bench_df.index).tz_localize(None).normalize()

    replay_trades_df, nav_rows, data_faults = replay_shadow_window(shadow_dates, universe_data, bench_df)
    replay_nav = float(nav_rows[-1]["replay_nav"]) if nav_rows else INITIAL_CAPITAL

    match_rate = compute_signal_match_rate(sh_trades_df, replay_trades_df)
    eq_gap_pct = round(abs(shadow_nav - replay_nav) / max(replay_nav, 1e-4) * 100.0, 4)
    fidelity_passed = bool(match_rate >= 95.0 and eq_gap_pct < 1.5)

    row = {
        "week_end_date": week_end_date,
        "shadow_days": len(shadow_dates),
        "shadow_trades": len(sh_trades_df),
        "replay_trades": len(replay_trades_df),
        "signal_match_rate_pct": match_rate,
        "shadow_nav": round(shadow_nav, 2),
        "replay_nav": round(replay_nav, 2),
        "equity_gap_pct": eq_gap_pct,
        "price_source": price_source,
        "data_faults": ";".join(data_faults) if data_faults else "NONE",
        "fidelity_passed": fidelity_passed,
    }

    os.makedirs(os.path.dirname(fidelity_csv_path), exist_ok=True)
    write_header = not os.path.exists(fidelity_csv_path) or os.path.getsize(fidelity_csv_path) == 0
    pd.DataFrame([row], columns=FIDELITY_COLUMNS).to_csv(fidelity_csv_path, mode="a", header=write_header, index=False)
    return {"status": "REPLAYED", **row}


def main():
    parser = argparse.ArgumentParser(description="NSE S2 Weekly Shadow Fidelity Replay")
    parser.add_argument("--equity-log", default=EQUITY_LOG_CSV)
    parser.add_argument("--trades-csv", default=TRADES_CSV)
    parser.add_argument("--fidelity-csv", default=FIDELITY_CSV)
    args = parser.parse_args()
    res = evaluate_weekly_fidelity(args.equity_log, args.trades_csv, args.fidelity_csv)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
