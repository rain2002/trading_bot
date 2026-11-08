"""
Quality Breakout + Asymmetric Tight Risk Model (17-Year Causal NSE Bhavcopy)
=============================================================================
Implements the 3 structural edges:
1. Breakout on Strength: Stocks within 5% of 52-week High, above 50 & 200 SMA with volume expansion.
2. Asymmetric Risk Management (Institutional StopLossManager):
   - Initial Hard Stop: -7.0% from entry.
   - Breakeven Ratchet: Gain >= +6.0% moves stop to entry price.
   - Trailing Stop: Gain >= +15.0% trails peak price by 8.0%.
3. Macro Volatility Radar: Gates entries during bear/panic regimes; compounds idle cash at 6%.
4. Full statutory Indian costs: STT, turnover, DP fees (Rs 14.75), and 15% STCG tax.
"""

import os
import sys
import math
import json
import time
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Set, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from trading_system.app.validation.trial_logger import log_trial

PANEL_CLOSE_FILE = os.path.join(PROJECT_ROOT, "trading_system", "data", "causal_panel_close.parquet")
PANEL_OPEN_FILE = os.path.join(PROJECT_ROOT, "trading_system", "data", "causal_panel_open.parquet")
PANEL_TURNOVER_FILE = os.path.join(PROJECT_ROOT, "trading_system", "data", "causal_panel_turnover.parquet")
NSEI_BENCHMARK = os.path.join(PROJECT_ROOT, "trading_system", "data", "historical_cache_nse", "INDEX_NSEI.parquet")

INITIAL_CAPITAL = 80000.0
MAX_SLOTS = 10
FLAT_DP_FEE_RUPEES = 14.75
BUY_COST_BPS = 22.85
SELL_COST_BPS = 21.35
TAX_RATE_STCG = 0.15
MIN_PRICE = 20.0

HARD_STOP_PCT = -0.07          # -7% initial risk cut
BREAKEVEN_TRIGGER_PCT = 0.06   # +6% profit ratchets stop to entry
TRAILING_TRIGGER_PCT = 0.15    # +15% profit triggers trailing stop
TRAILING_DISTANCE_PCT = 0.08   # 8% trailing buffer from peak


def run_tight_risk_simulation():
    print("=" * 80)
    print("TESTING QUALITY BREAKOUT + ASYMMETRIC TIGHT RISK ON CAUSAL BHAVCOPY (17 YEARS)")
    print("=" * 80, flush=True)

    t0 = time.time()
    close_df = pd.read_parquet(PANEL_CLOSE_FILE)
    open_df = pd.read_parquet(PANEL_OPEN_FILE)
    turnover_df = pd.read_parquet(PANEL_TURNOVER_FILE)
    bench_df = pd.read_parquet(NSEI_BENCHMARK)

    if hasattr(bench_df.index, "tz") and bench_df.index.tz is not None:
        bench_df.index = bench_df.index.tz_localize(None)
    bench_df.index = pd.to_datetime(bench_df.index.date)

    dates = close_df.index.intersection(bench_df.index)
    close_df = close_df.loc[dates]
    open_df = open_df.loc[dates]
    turnover_df = turnover_df.loc[dates]
    bench_df = bench_df.loc[dates]

    print(f"Loaded {len(dates)} trading days ({dates[0].date()} to {dates[-1].date()}) in {time.time()-t0:.1f}s.", flush=True)

    # Benchmark indicators
    bench_close = bench_df["close"]
    bench_sma200 = bench_close.rolling(200, min_periods=50).mean()
    bench_ret = bench_close.pct_change()
    bench_vol20 = bench_ret.rolling(20, min_periods=10).std() * math.sqrt(252)
    bench_ret6m = bench_close.pct_change(126)

    # Monthly rebalance dates
    df_d = pd.DataFrame({"date": dates}, index=dates)
    df_d["month"] = df_d["date"].dt.to_period("M")
    month_ends = set(df_d.groupby("month")["date"].max())

    print("Precomputing indicators (52-week High, SMA 50, SMA 200, Turnover)...", flush=True)
    t1 = time.time()
    high252 = close_df.rolling(252, min_periods=100).max()
    sma50 = close_df.rolling(50, min_periods=20).mean()
    sma200 = close_df.rolling(200, min_periods=50).mean()
    turnover_sma20 = turnover_df.rolling(20, min_periods=10).mean()
    print(f"Indicators precomputed in {time.time()-t1:.1f}s.", flush=True)

    # Simulation State
    cash = INITIAL_CAPITAL
    positions: Dict[str, float] = {}       # symbol -> shares
    entry_prices: Dict[str, float] = {}    # symbol -> entry fill price
    entry_dates: Dict[str, pd.Timestamp] = {}
    peak_prices: Dict[str, float] = {}     # symbol -> peak close price
    stop_prices: Dict[str, float] = {}     # symbol -> dynamic stop price

    active_universe: Set[str] = set()
    trade_log = []
    equity_curve = []
    hwm = INITIAL_CAPITAL
    max_dd = 0.0

    total_dp_fees = 0.0
    total_tax_paid = 0.0
    total_interest = 0.0

    pending_sells: List[Tuple[str, str]] = []
    pending_buys: List[Tuple[str, float, float]] = []  # (symbol, target_alloc, score)

    start_idx = 252  # Need 1 year of warmup for 52-week high & SMA200
    sim_dates = dates[start_idx:]

    print(f"Simulating {len(sim_dates)} trading days strictly at NEXT-DAY OPEN ({sim_dates[0].date()} to {sim_dates[-1].date()})...", flush=True)

    for i, current_date in enumerate(sim_dates):
        hist_idx = start_idx + i

        # =========================================================================
        # PHASE 1: EXECUTE PENDING ORDERS AT TODAY'S OPEN (NEXT_OPEN EXECUTION)
        # =========================================================================
        # 1A. Execute Pending Sells at Open
        for sym, reason in pending_sells:
            if sym not in positions:
                continue
            shares = positions.pop(sym)
            e_price = entry_prices.pop(sym)
            entry_dates.pop(sym, None)
            peak_prices.pop(sym, None)
            stop_prices.pop(sym, None)

            fill_price = open_df.loc[current_date, sym] if sym in open_df.columns and not math.isnan(open_df.loc[current_date, sym]) else e_price * 0.5
            if fill_price <= 0:
                fill_price = e_price * 0.5

            gross_sale = shares * fill_price
            sell_costs = gross_sale * (SELL_COST_BPS / 10000.0) + FLAT_DP_FEE_RUPEES
            total_dp_fees += FLAT_DP_FEE_RUPEES
            net_proceeds = gross_sale - sell_costs

            gain = net_proceeds - (shares * e_price)
            if gain > 0:
                tax = gain * TAX_RATE_STCG
                net_proceeds -= tax
                total_tax_paid += tax

            cash += net_proceeds
            trade_log.append({
                "date": current_date,
                "symbol": sym,
                "action": "SELL",
                "shares": shares,
                "fill_price": fill_price,
                "proceeds": net_proceeds,
                "gain": gain,
                "gain_pct": round((fill_price / e_price - 1.0) * 100, 2),
                "reason": reason
            })
        pending_sells = []

        # 1B. Execute Pending Buys at Open
        for sym, target_alloc, score in pending_buys:
            if sym in positions:
                continue
            o_price = open_df.loc[current_date, sym] if sym in open_df.columns else np.nan
            if math.isnan(o_price) or o_price <= 0:
                continue

            buy_fill = o_price * (1.0 + (BUY_COST_BPS / 10000.0))
            alloc = min(target_alloc, cash * 0.95)
            if alloc >= 500.0:
                shares = round(alloc / buy_fill, 4)
                cost = shares * buy_fill
                if cost <= cash and shares > 0:
                    cash -= cost
                    positions[sym] = shares
                    entry_prices[sym] = buy_fill
                    entry_dates[sym] = current_date
                    peak_prices[sym] = o_price
                    stop_prices[sym] = buy_fill * (1.0 + HARD_STOP_PCT)
                    trade_log.append({
                        "date": current_date,
                        "symbol": sym,
                        "action": "BUY",
                        "shares": shares,
                        "fill_price": buy_fill,
                        "cost": cost,
                        "reason": f"BREAKOUT_52W_SURGE (Score: {score:.2f})"
                    })
        pending_buys = []

        # 1C. Daily Cash Yield Compounding
        daily_interest = cash * (0.060 / 252.0)
        cash += daily_interest
        total_interest += daily_interest

        # 1D. Mark-to-Market Total Equity at Close
        tot_eq = cash
        for sym, shares in positions.items():
            c_p = close_df.loc[current_date, sym] if sym in close_df.columns else np.nan
            if math.isnan(c_p) or c_p <= 0:
                c_p = entry_prices.get(sym, 0.0)
            tot_eq += shares * c_p

        if tot_eq > hwm:
            hwm = tot_eq
        dd = (tot_eq - hwm) / hwm
        if dd < max_dd:
            max_dd = dd

        equity_curve.append({
            "date": current_date.strftime("%Y-%m-%d"),
            "equity": round(tot_eq, 2),
            "cash": round(cash, 2),
            "drawdown": round(dd * 100, 2)
        })

        # =========================================================================
        # PHASE 2: EVALUATE SIGNALS AT TODAY'S CLOSE FOR TOMORROW'S OPEN EXECUTION
        # =========================================================================
        # Step 2A: Update Monthly Causal Universe on Month-End
        if current_date in month_ends or not active_universe:
            window_turnover = turnover_df.iloc[max(0, hist_idx - 126):hist_idx]
            latest_prices = close_df.iloc[hist_idx]
            valid_mask = latest_prices >= MIN_PRICE
            med_turnover = window_turnover.loc[:, valid_mask].median().dropna()
            top_300 = set(med_turnover.sort_values(ascending=False).head(300).index)
            active_universe = top_300

        # Step 2B: Macro Volatility Radar
        b_vol = bench_vol20.iloc[hist_idx] if not math.isnan(bench_vol20.iloc[hist_idx]) else 0.15
        b_ret6m = bench_ret6m.iloc[hist_idx] if not math.isnan(bench_ret6m.iloc[hist_idx]) else 0.05
        b_close = bench_close.iloc[hist_idx]
        b_sma200 = bench_sma200.iloc[hist_idx]

        is_panic = (b_ret6m < 0.0) and (b_vol >= 0.24)
        is_trend_broken = (b_close < b_sma200)

        port_dd = (tot_eq - hwm) / hwm if hwm > 0 else 0.0
        if port_dd >= -0.10:
            ladder_exposure = 1.00
        elif port_dd >= -0.14:
            ladder_exposure = 0.70
        elif port_dd >= -0.18:
            ladder_exposure = 0.40
        else:
            ladder_exposure = 0.00

        raw_vol_scale = min(1.0, 0.15 / max(b_vol, 0.08)) if b_vol > 0 else 1.0
        if is_panic or is_trend_broken:
            radar_exposure = 0.0
        elif raw_vol_scale < 0.75:
            radar_exposure = round(raw_vol_scale, 2)
        else:
            radar_exposure = 1.0

        allowed_exposure = min(radar_exposure, ladder_exposure)
        allow_entries = (allowed_exposure > 0.0) and not is_panic and not is_trend_broken

        # Step 2C: Check Exit Signals on Current Positions
        for sym, shares in list(positions.items()):
            c_p = close_df.loc[current_date, sym] if sym in close_df.columns and not math.isnan(close_df.loc[current_date, sym]) else None
            if c_p is None or math.isnan(c_p):
                pending_sells.append((sym, "DELISTED_OR_HALTED_LIQUIDATION"))
                continue

            entry_p = entry_prices[sym]
            gain_pct = (c_p - entry_p) / entry_p

            if c_p > peak_prices.get(sym, entry_p):
                peak_prices[sym] = c_p

            peak_p = peak_prices[sym]

            # Dynamic Stop Loss Ratchet
            curr_stop = stop_prices.get(sym, entry_p * (1.0 + HARD_STOP_PCT))

            # 1. Breakeven Ratchet: if gain >= +6%, stop moves to entry + 0.5%
            if gain_pct >= BREAKEVEN_TRIGGER_PCT:
                breakeven_p = entry_p * 1.005
                if breakeven_p > curr_stop:
                    curr_stop = breakeven_p

            # 2. Trailing Stop: if gain >= +15%, stop trails peak by 8%
            if (peak_p - entry_p) / entry_p >= TRAILING_TRIGGER_PCT:
                trail_p = peak_p * (1.0 - TRAILING_DISTANCE_PCT)
                if trail_p > curr_stop:
                    curr_stop = trail_p

            stop_prices[sym] = curr_stop

            # Check if Stop Loss Breached
            if c_p <= curr_stop:
                reason = "HARD_STOP (-7%)" if curr_stop <= entry_p else ("BREAKEVEN_STOP (+0.5%)" if curr_stop < peak_p * 0.93 else "PROFIT_TRAILING_STOP (-8% from peak)")
                pending_sells.append((sym, reason))
                continue

            if sym not in active_universe:
                pending_sells.append((sym, "DROPPED_FROM_CAUSAL_TOP300"))
                continue

            s50 = sma50.loc[current_date, sym] if sym in sma50.columns else np.nan
            if not math.isnan(s50) and c_p < s50 * 0.98:
                pending_sells.append((sym, "SMA50_BREAKDOWN"))
                continue

        # Step 2D: Check Entry Signals for Tomorrow
        projected_positions_count = len(positions) - len(pending_sells)
        avail_slots = MAX_SLOTS - projected_positions_count

        if allow_entries and avail_slots > 0 and allowed_exposure > 0:
            c_today = close_df.loc[current_date]
            h_today = high252.loc[current_date]
            s50_today = sma50.loc[current_date]
            s200_today = sma200.loc[current_date]
            v_today = turnover_df.loc[current_date]
            v_avg = turnover_sma20.loc[current_date]

            candidates = []
            for sym in active_universe:
                if sym in positions or any(sym == ps[0] for ps in pending_sells):
                    continue
                if sym not in c_today.index or sym not in h_today.index:
                    continue

                cp = c_today[sym]
                hp = h_today[sym]
                s50p = s50_today.get(sym, np.nan)
                s200p = s200_today.get(sym, np.nan)
                vt = v_today.get(sym, np.nan)
                va = v_avg.get(sym, np.nan)

                if math.isnan(cp) or math.isnan(hp) or cp < MIN_PRICE or hp <= 0:
                    continue

                near_high = (cp / hp) >= 0.95
                in_uptrend = (not math.isnan(s50p) and not math.isnan(s200p) and cp > s50p and s50p > s200p)
                vol_surge = (not math.isnan(vt) and not math.isnan(va) and va > 0 and vt >= 1.25 * va)

                if near_high and in_uptrend and vol_surge:
                    score = (cp / hp) * (cp / s200p)
                    candidates.append((sym, score))

            candidates.sort(key=lambda x: x[1], reverse=True)
            to_buy = candidates[:avail_slots]

            slot_budget = (tot_eq * allowed_exposure) / MAX_SLOTS
            for sym, score in to_buy:
                pending_buys.append((sym, slot_budget, score))

        # Step 5: Daily Cash Yield Compounding
        daily_interest = cash * (0.060 / 252.0)
        cash += daily_interest
        total_interest += daily_interest

        # Step 6: Mark-to-Market Total Equity
        tot_eq = cash
        for sym, shares in positions.items():
            c_p = close_df.loc[current_date, sym] if sym in close_df.columns else np.nan
            if math.isnan(c_p) or c_p <= 0:
                c_p = entry_prices.get(sym, 0.0)
            tot_eq += shares * c_p

        if tot_eq > hwm:
            hwm = tot_eq
        dd = (tot_eq - hwm) / hwm
        if dd < max_dd:
            max_dd = dd

        equity_curve.append({
            "date": current_date.strftime("%Y-%m-%d"),
            "equity": round(tot_eq, 2),
            "cash": round(cash, 2),
            "drawdown": round(dd * 100, 2)
        })

    # Final Statistics
    start_dt = sim_dates[0]
    end_dt = sim_dates[-1]
    years = (end_dt - start_dt).days / 365.25
    terminal_equity = equity_curve[-1]["equity"]
    total_return_pct = ((terminal_equity / INITIAL_CAPITAL) - 1.0) * 100.0
    cagr_pct = ((terminal_equity / INITIAL_CAPITAL) ** (1.0 / years) - 1.0) * 100.0
    calmar = cagr_pct / abs(max_dd * 100.0) if max_dd < 0 else 0.0

    eq_series = pd.Series([e["equity"] for e in equity_curve])
    daily_rets = eq_series.pct_change().dropna()
    sharpe = (daily_rets.mean() / daily_rets.std() * math.sqrt(252)) if daily_rets.std() > 0 else 0.0

    sells = [t for t in trade_log if t["action"] == "SELL"]
    winners = [t for t in sells if t["gain"] > 0]
    win_rate = (len(winners) / len(sells) * 100.0) if sells else 0.0
    avg_win = np.mean([t["gain_pct"] for t in winners]) if winners else 0.0
    losers = [t for t in sells if t["gain"] <= 0]
    avg_loss = np.mean([t["gain_pct"] for t in losers]) if losers else 0.0

    gross_profit = sum(t["gain"] for t in winners)
    gross_loss = abs(sum(t["gain"] for t in losers)) if losers else 1.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

    # Benchmark TRI
    bench_sub = bench_close.loc[sim_dates]
    bench_tri_ret = bench_sub.pct_change().fillna(0.0) + (0.0135 / 252.0)
    bench_tri = (1.0 + bench_tri_ret).cumprod() * INITIAL_CAPITAL
    bench_cagr = ((bench_tri.iloc[-1] / INITIAL_CAPITAL) ** (1.0 / years) - 1.0) * 100.0
    bench_dd = ((bench_tri - bench_tri.cummax()) / bench_tri.cummax()).min() * 100.0

    print("\n" + "=" * 80)
    print("RESULTS: QUALITY BREAKOUT + TIGHT ASYMMETRIC RISK (CAUSAL BHAVCOPY)")
    print("=" * 80)
    print(f"{'Performance Metric':<40} | {'Tight Risk Breakout Model':<22} | {'Nifty 50 TRI (Passive)':<22}")
    print("-" * 80)
    print(f"{'Starting Capital':<40} | INR {INITIAL_CAPITAL:>18,.0f} | INR {INITIAL_CAPITAL:>18,.0f}")
    print(f"{'Terminal Equity (Post-Tax)':<40} | INR {terminal_equity:>18,.0f} | INR {bench_tri.iloc[-1]:>18,.0f}")
    print(f"{'Compound Annual Growth Rate (CAGR)':<40} | {cagr_pct:>21.2f}% | {bench_cagr:>21.2f}%")
    print(f"{'Maximum Drawdown Depth':<40} | {max_dd*100:>21.2f}% | {bench_dd:>21.2f}%")
    print(f"{'Calmar Ratio (CAGR / MaxDD)':<40} | {calmar:>22.2f} | {bench_cagr/abs(bench_dd):>22.2f}")
    print(f"{'Annualized Sharpe Ratio':<40} | {sharpe:>22.2f} | N/A")
    print(f"{'Trade Win Rate':<40} | {win_rate:>21.2f}% | N/A")
    print(f"{'Average Winner Gain':<40} | {avg_win:>21.2f}% | N/A")
    print(f"{'Average Loser Loss':<40} | {avg_loss:>21.2f}% | N/A")
    print(f"{'Win/Loss Ratio (Asymmetry)':<40} | {abs(avg_win/avg_loss) if avg_loss!=0 else 0:>22.2f} | N/A")
    print(f"{'Profit Factor':<40} | {profit_factor:>22.2f} | N/A")
    print(f"{'Total Closed Trades':<40} | {len(sells):>22} | N/A")
    print("=" * 80)

    # Log to trial_log.csv
    log_trial(
        cagr_pct=round(cagr_pct, 2),
        max_drawdown_pct=round(max_dd * 100, 2),
        sharpe_ratio=round(sharpe, 2),
        kelly_fraction=0.40,
        lookback_days=252,
        is_holdout_opened=False,
        script="test_quality_breakout_tight_risk.py",
        universe="NSE_BHAVCOPY_CAUSAL_TOP300",
        notes="Quality Breakout (52w High + SMA50/200 + Volume Surge) + Tight Risk (-7% Stop, BE +6%, Trail +15%/8%)"
    )


if __name__ == "__main__":
    run_tight_risk_simulation()
