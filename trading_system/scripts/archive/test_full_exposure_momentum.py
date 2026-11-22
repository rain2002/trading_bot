"""
Test 100% Bull-Market Exposure US Momentum Strategy (2007-2024)
Hypothesis:
1. During Bull Regime (SPY > 200-SMA): 100% fully invested in Top 10 Momentum Compounders.
2. During Bear Regime (SPY < 200-SMA): 100% protected in Liquid Cash / T-Bills.
3. Exits: Trailing Stop (3.5x ATR from peak) + Relative Momentum Replacement.
"""

import os
import sys
import math
import pandas as pd
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from trading_system.scripts.backtest_us_growth_stock_momentum import (
    load_market_data,
    compute_us_capital_gains_tax,
    calc_atr,
    START_DATE,
    DEFAULT_END_DATE,
    INITIAL_CAPITAL
)

def run_test(mom_window=126, skip_days=21, max_slots=10, atr_trail=3.5, rebal_days=10):
    bench_df, macro_bull, irx_close, precalc, timeline = load_market_data(START_DATE, DEFAULT_END_DATE)

    # Compute skip-month momentum
    for sym, p_sym in precalc.items():
        c = p_sym["close"]
        n = len(c)
        m = np.full(n, np.nan)
        for i in range(mom_window + skip_days, n):
            p0 = c[i - mom_window - skip_days]
            p1 = c[i - skip_days]
            if p0 > 0:
                m[i] = (p1 - p0) / p0
        p_sym["mom_score"] = m

    cash = INITIAL_CAPITAL
    positions = {}     # sym -> shares
    entry_prices = {}  # sym -> fill_p
    entry_dates = {}
    peak_prices = {}
    initial_atr = {}

    hwm = INITIAL_CAPITAL
    max_dd = 0.0
    pending_sells = []
    pending_buys = []
    equity_records = []
    trade_log = []

    t_idx = 0
    for dt in timeline:
        t_idx += 1
        is_bull = bool(macro_bull.loc[dt]) if dt in macro_bull.index else True
        is_rebal = (t_idx % rebal_days == 0)

        # 1. Execute Open Orders (09:30 EST)
        if pending_sells:
            for sym, reason in pending_sells:
                if sym not in positions:
                    continue
                p_sym = precalc[sym]
                idx = p_sym["date_to_idx"][dt]
                fill_p = p_sym["open"][idx] * (1.0 - 0.00075) # 7.5 bps slippage
                shares = positions[sym]
                proceeds = shares * fill_p
                # Fees & taxes
                net_proc = proceeds * 0.9997 # SEC/FINRA approx
                gain = net_proc - (shares * entry_prices[sym])
                tax = compute_us_capital_gains_tax(entry_dates[sym], dt, gain)
                cash += (net_proc - tax)
                trade_log.append({
                    "symbol": sym, "gain": gain, "tax": tax, "reason": reason,
                    "ret": (fill_p - entry_prices[sym]) / entry_prices[sym]
                })
                del positions[sym]
                del entry_prices[sym]
                del entry_dates[sym]
                del peak_prices[sym]
                if sym in initial_atr:
                    del initial_atr[sym]
            pending_sells = []

        if pending_buys:
            for b in pending_buys:
                sym = b["symbol"]
                target_alloc = b["target_alloc"]
                if sym not in precalc or dt not in precalc[sym]["date_to_idx"]:
                    continue
                p_sym = precalc[sym]
                idx = p_sym["date_to_idx"][dt]
                fill_p = p_sym["open"][idx] * (1.0 + 0.00075)
                shares = math.floor(target_alloc / fill_p)
                cost = shares * fill_p
                if cost <= cash and shares > 0:
                    cash -= cost
                    positions[sym] = shares
                    entry_prices[sym] = fill_p
                    entry_dates[sym] = dt
                    peak_prices[sym] = fill_p
                    cur_atr = p_sym["atr20"][idx]
                    initial_atr[sym] = cur_atr if not math.isnan(cur_atr) and cur_atr > 0 else (fill_p * 0.03)
            pending_buys = []

        # 2. Dividends & Cash Yield
        for sym, shares in positions.items():
            p_sym = precalc[sym]
            if dt in p_sym["date_to_idx"]:
                idx = p_sym["date_to_idx"][dt]
                d = p_sym["divs"][idx]
                if d > 0:
                    cash += shares * d

        if cash > 0.0 and dt in irx_close.index:
            t_rate = irx_close.loc[dt] / 100.0
            cash += cash * (t_rate / 252.0)

        # 3. Mark to Market
        current_prices = {}
        for sym in positions:
            p_sym = precalc[sym]
            if dt in p_sym["date_to_idx"]:
                idx = p_sym["date_to_idx"][dt]
                cp = p_sym["close"][idx]
                current_prices[sym] = cp
                if cp > peak_prices.get(sym, cp):
                    peak_prices[sym] = cp

        port_val = sum(positions[s] * current_prices.get(s, entry_prices.get(s, 0.0)) for s in positions)
        total_eq = cash + port_val
        if total_eq > hwm:
            hwm = total_eq
        dd = (total_eq - hwm) / hwm
        if dd < max_dd:
            max_dd = dd

        equity_records.append({"date": dt, "equity": total_eq, "cash": cash, "port": port_val})

        # 4. Exit Evaluation
        sells = []
        if not is_bull:
            # Full Macro Bear Protection: If SPY is below 200-SMA, liquidate into cash
            for sym in list(positions.keys()):
                sells.append((sym, "MACRO_BEAR_200SMA_EXIT"))
        else:
            for sym, shares in list(positions.items()):
                if sym not in current_prices:
                    continue
                price = current_prices[sym]
                cost = entry_prices[sym]
                peak = peak_prices.get(sym, price)
                p_sym = precalc[sym]
                idx = p_sym["date_to_idx"][dt]
                atr = p_sym["atr20"][idx]
                if math.isnan(atr) or atr <= 0:
                    atr = initial_atr.get(sym, price * 0.03)

                # Trailing ATR stop from peak
                trail_stop = peak - (atr_trail * atr)
                if price <= trail_stop:
                    sells.append((sym, f"ATR_TRAIL_STOP (-{atr_trail}x ATR)"))
                    continue

                # Hard stop at -12% from entry
                if (price - cost) / cost <= -0.12:
                    sells.append((sym, "HARD_STOP (-12%)"))
                    continue

        pending_sells.extend(sells)

        # 5. Entry Evaluation (Only in Bull Market)
        active_count = len(positions) - len(pending_sells) + len(pending_buys)
        if is_bull and is_rebal and active_count < max_slots and cash > 50.0:
            open_slots = max_slots - active_count
            cands = []
            for sym, p_sym in precalc.items():
                if sym in positions or any(s[0] == sym for s in sells):
                    continue
                if dt not in p_sym["date_to_idx"]:
                    continue
                idx = p_sym["date_to_idx"][dt]
                if idx < 150:
                    continue
                price = p_sym["close"][idx]
                if price < 10.0:
                    continue
                sma150 = p_sym["sma150"][idx]
                if math.isnan(sma150) or price <= sma150:
                    continue
                score = p_sym["mom_score"][idx]
                if not math.isnan(score) and score > 0.05:
                    cands.append((sym, score, price))

            cands.sort(key=lambda x: x[1], reverse=True)
            chosen = cands[:open_slots]

            alloc_per_slot = total_eq / max_slots
            avail = cash * 0.98
            for sym, sc, cur_p in chosen:
                if avail < 50.0:
                    break
                alloc = min(alloc_per_slot, avail)
                pending_buys.append({"symbol": sym, "target_alloc": alloc, "score": sc})
                avail -= alloc

    df_eq = pd.DataFrame(equity_records).set_index("date")
    end_val = df_eq["equity"].iloc[-1]
    years = len(timeline) / 252.0
    cagr = (end_val / INITIAL_CAPITAL) ** (1.0 / years) - 1.0

    daily_rets = df_eq["equity"].pct_change().dropna()
    mean_ret = daily_rets.mean() * 252.0
    vol = daily_rets.std() * math.sqrt(252.0)
    sharpe = (mean_ret - 0.02) / vol if vol > 0 else 0.0

    downside_vol = daily_rets[daily_rets < 0.0].std() * math.sqrt(252.0)
    sortino = (mean_ret - 0.02) / downside_vol if downside_vol > 0 else 0.0

    df_t = pd.DataFrame(trade_log) if trade_log else pd.DataFrame()
    win_rate = (df_t["gain"] > 0).mean() if not df_t.empty else 0.0
    avg_exp = (df_eq["port"] / df_eq["equity"]).mean()

    print(f"Params: mom={mom_window}d_skip{skip_days}d, slots={max_slots}, trail={atr_trail}x, rebal={rebal_days}d")
    print(f"  CAGR: {cagr:.2%} | Sharpe: {sharpe:.2f} | Sortino: {sortino:.2f} | MaxDD: {max_dd:.2%} | WinRate: {win_rate:.1%} | Exp: {avg_exp:.1%} | Multiple: {end_val/INITIAL_CAPITAL:.2f}x")
    return {"cagr": cagr, "sharpe": sharpe, "max_dd": max_dd, "multiple": end_val / INITIAL_CAPITAL}

if __name__ == "__main__":
    for slots in [8, 10, 12]:
        for trail in [3.0, 3.5, 4.0]:
            for rebal in [5, 10, 20]:
                run_test(mom_window=126, skip_days=21, max_slots=slots, atr_trail=trail, rebal_days=rebal)
