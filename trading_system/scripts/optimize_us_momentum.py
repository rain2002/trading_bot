"""
Institutional US Momentum Strategy Optimizer & Backtester
Tests:
- Momentum Metrics: 12M-1M Skip-Month, 6M-1M, Multi-Window Exponential
- Risk Management: ATR Trailing Stops (2.5x, 3.0x, 3.5x) vs Fixed -10% Stops
- Macro Regime Defense: SPY 200-SMA filter with T-Bill Yield Compounding
- Portfolio Sizing: 10 vs 15 positions, eliminating panicky bottom-selling
"""

import os
import sys
import time
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

def run_enhanced_us_simulation(
    bench_df: pd.DataFrame,
    macro_bull: pd.Series,
    irx_close: pd.Series,
    precalc: dict,
    timeline: pd.DatetimeIndex,
    max_positions: int = 12,
    mom_metric: str = "12m_skip1m", # "12m_skip1m", "6m_skip1m", "blend"
    atr_stop_mult: float = 3.5,     # Initial ATR stop multiplier
    atr_trail_mult: float = 3.0,    # Trailing ATR stop multiplier
    trend_exit_sma: str = "sma150", # "sma100", "sma150", "none"
    rebalance_freq: int = 5,        # Weekly rebalance
    slippage_bps: float = 5.0,
    stress_slippage_bps: float = 7.5,
    use_dd_ladder: bool = True
):
    # Pre-calculate 12m-1m and 6m-1m momentum if not present
    for sym, p_sym in precalc.items():
        close = p_sym["close"]
        n = len(close)
        if "mom_12m_skip" not in p_sym:
            m12 = np.full(n, np.nan)
            m6 = np.full(n, np.nan)
            for i in range(252, n):
                # 12M minus 1M: return from t-252 to t-21
                p_base = close[i - 252]
                p_skip = close[i - 21]
                if p_base > 0:
                    m12[i] = (p_skip - p_base) / p_base
            for i in range(126, n):
                p_base = close[i - 126]
                p_skip = close[i - 21]
                if p_base > 0:
                    m6[i] = (p_skip - p_base) / p_base
            p_sym["mom_12m_skip"] = m12
            p_sym["mom_6m_skip"] = m6

    # Run backtest
    cash = INITIAL_CAPITAL
    positions = {}      # sym -> shares
    entry_prices = {}   # sym -> fill_price
    entry_dates = {}    # sym -> date
    peak_prices = {}    # sym -> peak
    initial_atr = {}    # sym -> atr at entry

    hwm_true = INITIAL_CAPITAL
    max_true_drawdown = 0.0
    pending_sells = []
    pending_buys = []
    equity_records = []
    trade_log = []
    total_tax_paid = 0.0
    total_interest = 0.0
    total_dividends = 0.0

    t_idx = 0
    for current_date in timeline:
        t_idx += 1
        is_routine_bull = bool(macro_bull.loc[current_date]) if current_date in macro_bull.index else True
        is_rebalance_day = (t_idx % rebalance_freq == 0)

        # -------------------------------------------------------------
        # STEP 0: EXECUTE OPEN ORDERS (09:30 EST)
        # -------------------------------------------------------------
        # 0A. Execute Sells
        if pending_sells:
            for sym, reason in pending_sells:
                if sym not in positions:
                    continue
                p_sym = precalc[sym]
                idx = p_sym["date_to_idx"][current_date]
                open_p = p_sym["open"][idx]
                slippage = (stress_slippage_bps / 10000.0)
                fill_p = open_p * (1.0 - slippage)

                shares = positions[sym]
                proceeds = shares * fill_p

                # SEC Section 31 + FINRA TAF
                sec_fee = proceeds * 0.0000278
                taf_fee = min(7.27, shares * 0.000166)
                net_proceeds = proceeds - sec_fee - taf_fee

                gain = net_proceeds - (shares * entry_prices[sym])
                tax = compute_us_capital_gains_tax(entry_dates[sym], current_date, gain)
                net_after_tax = net_proceeds - tax
                total_tax_paid += tax

                cash += net_after_tax
                trade_log.append({
                    "symbol": sym,
                    "entry_date": entry_dates[sym],
                    "exit_date": current_date,
                    "holding_days": (current_date - pd.to_datetime(entry_dates[sym])).days,
                    "entry_price": entry_prices[sym],
                    "exit_price": fill_p,
                    "shares": shares,
                    "gain": gain,
                    "tax": tax,
                    "return_pct": (fill_p - entry_prices[sym]) / entry_prices[sym],
                    "reason": reason
                })
                del positions[sym]
                del entry_prices[sym]
                del entry_dates[sym]
                del peak_prices[sym]
                if sym in initial_atr:
                    del initial_atr[sym]
            pending_sells = []

        # 0B. Execute Buys
        if pending_buys:
            for b in pending_buys:
                sym = b["symbol"]
                target_alloc = b["target_alloc"]
                if sym not in precalc or current_date not in precalc[sym]["date_to_idx"]:
                    continue
                p_sym = precalc[sym]
                idx = p_sym["date_to_idx"][current_date]
                open_p = p_sym["open"][idx]
                slippage = (stress_slippage_bps / 10000.0)
                fill_p = open_p * (1.0 + slippage)

                shares = math.floor(target_alloc / fill_p)
                cost = shares * fill_p
                if cost <= cash and shares > 0:
                    cash -= cost
                    positions[sym] = shares
                    entry_prices[sym] = fill_p
                    entry_dates[sym] = current_date
                    peak_prices[sym] = fill_p
                    cur_atr = p_sym["atr20"][idx]
                    initial_atr[sym] = cur_atr if not math.isnan(cur_atr) and cur_atr > 0 else (fill_p * 0.03)
            pending_buys = []

        # -------------------------------------------------------------
        # STEP 1: DIVIDENDS & DAILY T-BILL CASH YIELD
        # -------------------------------------------------------------
        for sym, shares in positions.items():
            p_sym = precalc[sym]
            if current_date in p_sym["date_to_idx"]:
                idx = p_sym["date_to_idx"][current_date]
                div = p_sym["divs"][idx]
                if div > 0:
                    div_amt = shares * div
                    cash += div_amt
                    total_dividends += div_amt

        if cash > 0.0 and current_date in irx_close.index:
            t_rate = irx_close.loc[current_date] / 100.0
            daily_interest = cash * (t_rate / 252.0)
            cash += daily_interest
            total_interest += daily_interest

        # -------------------------------------------------------------
        # STEP 2: MARK TO MARKET & DRAWDOWN TRACKING
        # -------------------------------------------------------------
        current_prices = {}
        for sym in positions:
            p_sym = precalc[sym]
            if current_date in p_sym["date_to_idx"]:
                idx = p_sym["date_to_idx"][current_date]
                c_p = p_sym["close"][idx]
                current_prices[sym] = c_p
                if c_p > peak_prices.get(sym, c_p):
                    peak_prices[sym] = c_p

        port_val = sum(positions[s] * current_prices.get(s, entry_prices.get(s, 0.0)) for s in positions)
        total_equity = cash + port_val
        if total_equity > hwm_true:
            hwm_true = total_equity
        true_dd = (total_equity - hwm_true) / hwm_true
        if true_dd < max_true_drawdown:
            max_true_drawdown = true_dd

        equity_records.append({
            "date": current_date,
            "total_equity": total_equity,
            "cash": cash,
            "portfolio_value": port_val,
            "hwm": hwm_true,
            "drawdown": true_dd,
            "positions_count": len(positions)
        })

        # -------------------------------------------------------------
        # STEP 3: EXIT SIGNALS AT CLOSE FOR NEXT OPEN
        # -------------------------------------------------------------
        signals_to_exit = []
        for sym, shares in list(positions.items()):
            if sym not in current_prices or sym not in precalc:
                signals_to_exit.append((sym, "DATA_HALT_LIQUIDATE"))
                continue

            price = current_prices[sym]
            cost = entry_prices[sym]
            peak = peak_prices.get(sym, price)
            p_sym = precalc[sym]
            idx = p_sym["date_to_idx"][current_date]

            atr_val = p_sym["atr20"][idx]
            if math.isnan(atr_val) or atr_val <= 0:
                atr_val = initial_atr.get(sym, price * 0.03)

            # 1. Dynamic ATR Hard Stop from Entry
            atr_stop_price = cost - (atr_stop_mult * initial_atr.get(sym, atr_val))
            if price <= atr_stop_price:
                signals_to_exit.append((sym, f"ATR_HARD_STOP (-{atr_stop_mult:.1f}x ATR)"))
                continue

            # 2. Dynamic Trailing ATR Exit from Peak
            # Activates once in profit > 1.0x ATR
            if peak > cost + (1.0 * initial_atr.get(sym, atr_val)):
                trail_stop_price = peak - (atr_trail_mult * atr_val)
                if price <= trail_stop_price:
                    signals_to_exit.append((sym, f"ATR_TRAIL_EXIT (-{atr_trail_mult:.1f}x ATR from Peak)"))
                    continue

            # 3. Macro Bear Tighten: If SPY is in Bear regime, tighten trail to 2.0x ATR
            if not is_routine_bull and price > cost:
                tight_trail = peak - (2.0 * atr_val)
                if price <= tight_trail:
                    signals_to_exit.append((sym, "MACRO_BEAR_TIGHT_TRAIL"))
                    continue

            # 4. Trend Filter Exit
            if trend_exit_sma != "none" and trend_exit_sma in p_sym:
                sma_val = p_sym[trend_exit_sma][idx]
                if not math.isnan(sma_val) and price < sma_val:
                    signals_to_exit.append((sym, f"TREND_{trend_exit_sma.upper()}_BREAK"))
                    continue

        pending_sells.extend(signals_to_exit)

        # -------------------------------------------------------------
        # STEP 4: ENTRY SIGNALS AT CLOSE FOR NEXT OPEN
        # -------------------------------------------------------------
        # Only enter new positions when Macro Regime is Bullish (SPY > 200-SMA)
        active_and_pending = len(positions) - len(pending_sells) + len(pending_buys)
        if is_routine_bull and is_rebalance_day and active_and_pending < max_positions and cash > 50.0:
            open_slots = max_positions - active_and_pending
            cands = []

            for sym, p_sym in precalc.items():
                if sym in positions or any(p[0] == sym for p in signals_to_exit):
                    continue
                if current_date not in p_sym["date_to_idx"]:
                    continue
                idx = p_sym["date_to_idx"][current_date]
                if idx < 150:
                    continue
                price = p_sym["close"][idx]
                if price < 10.0:
                    continue

                # Ensure stock is above its 150-SMA
                sma150 = p_sym["sma150"][idx]
                if math.isnan(sma150) or price <= sma150:
                    continue

                # Select momentum score
                if mom_metric == "12m_skip1m":
                    score = p_sym["mom_12m_skip"][idx]
                elif mom_metric == "6m_skip1m":
                    score = p_sym["mom_6m_skip"][idx]
                elif mom_metric == "blend":
                    m90 = p_sym["mom90"][idx]
                    m180 = p_sym["mom180"][idx]
                    score = 0.60 * m90 + 0.40 * m180 if not (math.isnan(m90) or math.isnan(m180)) else np.nan
                else:
                    score = p_sym["mom90"][idx]

                if not math.isnan(score) and score > 0.10:
                    cands.append((sym, score, price))

            cands.sort(key=lambda x: x[1], reverse=True)
            selected = cands[:open_slots]

            alloc_per_candidate = total_equity / max_positions
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

    # Compute Final Performance Metrics
    df_eq = pd.DataFrame(equity_records).set_index("date")
    end_val = df_eq["total_equity"].iloc[-1]
    years = len(timeline) / 252.0
    cagr = (end_val / INITIAL_CAPITAL) ** (1.0 / years) - 1.0

    daily_rets = df_eq["total_equity"].pct_change().dropna()
    mean_ret = daily_rets.mean() * 252.0
    vol = daily_rets.std() * math.sqrt(252.0)
    sharpe = (mean_ret - 0.02) / vol if vol > 0 else 0.0

    downside_rets = daily_rets[daily_rets < 0.0]
    downside_vol = downside_rets.std() * math.sqrt(252.0)
    sortino = (mean_ret - 0.02) / downside_vol if downside_vol > 0 else 0.0
    calmar = cagr / abs(max_true_drawdown) if max_true_drawdown < 0 else 0.0

    df_trades = pd.DataFrame(trade_log) if trade_log else pd.DataFrame()
    win_rate = (df_trades["gain"] > 0).mean() if not df_trades.empty else 0.0
    total_gains = df_trades[df_trades["gain"] > 0]["gain"].sum() if not df_trades.empty else 0.0
    total_losses = abs(df_trades[df_trades["gain"] < 0]["gain"].sum()) if not df_trades.empty else 1.0
    profit_factor = total_gains / total_losses if total_losses > 0 else 0.0

    avg_exposure = (df_eq["portfolio_value"] / df_eq["total_equity"]).mean()

    return {
        "terminal_equity": end_val,
        "wealth_multiple": end_val / INITIAL_CAPITAL,
        "cagr": cagr,
        "max_drawdown": max_true_drawdown,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "total_trades": len(df_trades),
        "avg_exposure": avg_exposure,
        "total_tax_paid": total_tax_paid,
        "total_interest": total_interest,
        "total_dividends": total_dividends
    }

if __name__ == "__main__":
    print("=" * 95)
    print("AUDITING & OPTIMIZING US GROWTH MOMENTUM STRATEGY (2007-2024)")
    print("=" * 95)
    bench_df, macro_bull, irx_close, precalc, timeline = load_market_data(START_DATE, DEFAULT_END_DATE)

    # Benchmark stats
    spy_cagr = (bench_df["tri_close"].iloc[-1] / bench_df["tri_close"].iloc[0]) ** (1.0 / (len(timeline) / 252.0)) - 1.0
    spy_rets = bench_df["tri_close"].pct_change().dropna()
    spy_vol = spy_rets.std() * math.sqrt(252.0)
    spy_sharpe = (spy_rets.mean() * 252.0 - 0.02) / spy_vol
    spy_hwm = bench_df["tri_close"].cummax()
    spy_max_dd = ((bench_df["tri_close"] - spy_hwm) / spy_hwm).min()

    print(f"\nBenchmark SPY TRI: CAGR = {spy_cagr:.2%}, Sharpe = {spy_sharpe:.2f}, MaxDD = {spy_max_dd:.2%}\n")

    experiments = [
        {"name": "Exp 1: Baseline Variant 2 (Fixed -10% Stop, 10 Slots)", "slots": 10, "mom": "blend", "atr_stop": 2.0, "atr_trail": 2.5, "trend": "sma150"},
        {"name": "Exp 2: 12M-1M Skip Momentum + 3.5x ATR Stop (10 Slots)", "slots": 10, "mom": "12m_skip1m", "atr_stop": 3.5, "atr_trail": 3.0, "trend": "sma150"},
        {"name": "Exp 3: 12M-1M Skip Momentum + 3.5x ATR Stop (12 Slots)", "slots": 12, "mom": "12m_skip1m", "atr_stop": 3.5, "atr_trail": 3.0, "trend": "sma150"},
        {"name": "Exp 4: 12M-1M Skip Momentum + 3.5x ATR Stop (15 Slots)", "slots": 15, "mom": "12m_skip1m", "atr_stop": 3.5, "atr_trail": 3.0, "trend": "sma150"},
        {"name": "Exp 5: 6M-1M Skip Momentum + 3.0x ATR Stop (12 Slots)", "slots": 12, "mom": "6m_skip1m", "atr_stop": 3.0, "atr_trail": 2.5, "trend": "sma150"},
        {"name": "Exp 6: 12M-1M Skip + Wider 4.0x ATR Trail (12 Slots)", "slots": 12, "mom": "12m_skip1m", "atr_stop": 4.0, "atr_trail": 3.5, "trend": "sma150"},
    ]

    results = []
    for exp in experiments:
        t0 = time.time()
        res = run_enhanced_us_simulation(
            bench_df, macro_bull, irx_close, precalc, timeline,
            max_positions=exp["slots"],
            mom_metric=exp["mom"],
            atr_stop_mult=exp["atr_stop"],
            atr_trail_mult=exp["atr_trail"],
            trend_exit_sma=exp["trend"]
        )
        dt = time.time() - t0
        res["name"] = exp["name"]
        results.append(res)
        print(f"[{exp['name']}] -> CAGR: {res['cagr']:.2%}, Sharpe: {res['sharpe']:.2f}, MaxDD: {res['max_drawdown']:.2%}, WinRate: {res['win_rate']:.1%}, Multiple: {res['wealth_multiple']:.2f}x ({dt:.1f}s)")

    print("\n" + "=" * 115)
    print(f"{'Strategy Experiment':<55} | {'CAGR':<8} | {'Sharpe':<7} | {'MaxDD':<8} | {'WinRate':<8} | {'Multiple':<9}")
    print("-" * 115)
    print(f"{'S&P 500 TRI Benchmark (Buy & Hold)':<55} | {spy_cagr:.2%}  | {spy_sharpe:.2f}   | {spy_max_dd:.2%} | {'N/A':<8} | {(bench_df['tri_close'].iloc[-1]/bench_df['tri_close'].iloc[0]):.2f}x")
    for r in results:
        print(f"{r['name']:<55} | {r['cagr']:.2%}  | {r['sharpe']:.2f}   | {r['max_drawdown']:.2%} | {r['win_rate']:.1%}   | {r['wealth_multiple']:.2f}x")
    print("=" * 115)
