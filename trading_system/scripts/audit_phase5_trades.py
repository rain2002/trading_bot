"""
Forensic Trade-Level Audit for Phase 5 Candidate S2
===================================================
1. Analyzes Top 5 Trades and Top 10 Ticker Contributors.
2. Computes CAGR excluding the Top 5 Trades.
3. Audits prices of top contributors for unadjusted splits and Bhavcopy anomalies.
4. Performs a trade-by-trade comparison of Baseline (14.0% CAGR) vs Stressed 2x Costs (18.06% CAGR).
"""

import os
import sys
import math
import json
from typing import Tuple, List, Dict, Any
import pandas as pd
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from trading_system.scripts.run_phase5_nse_whole_market_gate_a import (
    load_all_data,
    calc_vectorized_momentum,
    build_verified_split_adjustment_matrix,
    IN_SAMPLE_START, IN_SAMPLE_END,
    INITIAL_CAPITAL, CORE_SLOTS, MAX_ALLOC_PER_STOCK,
    MIN_SHARE_PRICE, MIN_SEASONING_DAYS, MIN_MEDIAN_TURNOVER,
    CASH_YIELD_PA,
    BUY_FRICTION_BPS_BASE, SELL_FRICTION_BPS_BASE, FLAT_DP_FEE_BASE,
    BUY_FRICTION_BPS_STRESSED, SELL_FRICTION_BPS_STRESSED, FLAT_DP_FEE_STRESSED
)


def run_detailed_simulation(
    close_df: pd.DataFrame,
    open_df: pd.DataFrame,
    turnover_df: pd.DataFrame,
    bench_df: pd.DataFrame,
    sim_start: str,
    sim_end: str,
    buy_friction_bps: float,
    sell_friction_bps: float,
    dp_fee_rupees: float,
) -> Tuple[pd.Series, List[Dict[str, Any]], Dict[str, Any]]:
    dates = close_df.loc[sim_start:sim_end].index

    mult_df, adj_factors = build_verified_split_adjustment_matrix(close_df)
    adj_close = close_df * adj_factors

    med_turnover = turnover_df.rolling(60, min_periods=5).median()
    is_valid_bar = close_df.notna() & (close_df > 0.0)
    seasoning = is_valid_bar.cumsum()

    bench_close = bench_df["close"].loc[dates]
    bench_sma200 = bench_df["sma200"].loc[dates]
    exit_sma = adj_close.rolling(150, min_periods=112).mean()

    df_d = pd.DataFrame({"date": dates}, index=dates)
    df_d["month"] = df_d["date"].dt.to_period("M")
    rebalance_dates = set(df_d.groupby("month")["date"].max())

    cash = INITIAL_CAPITAL
    hwm_true = INITIAL_CAPITAL
    hwm_ladder = INITIAL_CAPITAL

    holdings = {}
    equity_curve = []
    trade_log = []

    in_tier4_defense = False
    cooling_off_counter = 0
    recovery_streak = 0
    recovery_stage = 0
    recovery_stage_days = 0

    daily_cash_yield = (1.0 + CASH_YIELD_PA) ** (1.0 / 252.0) - 1.0

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

        if not in_tier4_defense:
            if total_equity > hwm_ladder:
                hwm_ladder = total_equity
        operating_dd = (total_equity - hwm_ladder) / max(hwm_ladder, 1e-4)

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

        allowed_ladder = min(ladder_exposure, recovery_stage_exposure)
        radar_exposure = 1.00 if is_routine_bull else 0.00
        effective_exposure_cap = min(allowed_ladder, radar_exposure)

        if cash > 0.0:
            cash += cash * daily_cash_yield

        equity_curve.append(total_equity)

        if i == len(dates) - 1:
            break

        next_date = dates[i + 1]
        next_open = open_df.loc[next_date]

        exits_to_execute = []
        if in_tier4_defense:
            for sym in list(holdings.keys()):
                exits_to_execute.append((sym, "EMERGENCY_TIER4_LIQUIDATION"))
        else:
            for sym, pos in list(holdings.items()):
                p_close = current_close.get(sym, np.nan)
                if math.isnan(p_close) or p_close <= 0.0:
                    continue

                prev_p = close_df.loc[dates[i - 1], sym] if i > 0 else p_close
                pct_chg = (p_close - prev_p) / max(prev_p, 1e-4) if prev_p > 0 else 0.0
                is_circuit = abs(pct_chg) >= 0.1950

                gain_pct = (p_close - pos["fill_price"]) / max(pos["fill_price"], 1e-4)
                peak_p = pos["peak_price"]
                dd_from_peak = (p_close - peak_p) / max(peak_p, 1e-4)

                if gain_pct <= -0.12:
                    if not is_circuit:
                        exits_to_execute.append((sym, "HARD_STOP"))
                    continue

                trail_hit = False
                if gain_pct >= 1.00:
                    if dd_from_peak <= -0.25:
                        trail_hit = True
                elif gain_pct >= 0.50:
                    if dd_from_peak <= -0.20:
                        trail_hit = True
                elif gain_pct >= 0.25:
                    if dd_from_peak <= -0.15:
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

            cost_basis = holdings[sym]["shares"] * holdings[sym]["fill_price"]
            realized_pnl = net_proceeds - cost_basis
            ret_pct = (eff_sell_price - holdings[sym]["fill_price"]) / max(holdings[sym]["fill_price"], 1e-4)

            trade_log.append({
                "symbol": sym,
                "entry_date": holdings[sym]["entry_date"],
                "exit_date": str(next_date.date()),
                "shares": holdings[sym]["shares"],
                "fill_price": holdings[sym]["fill_price"],
                "exit_price": eff_sell_price,
                "cost_basis": cost_basis,
                "net_proceeds": net_proceeds,
                "realized_pnl": realized_pnl,
                "return_pct": ret_pct,
                "reason": reason
            })
            del holdings[sym]

        if (current_date in rebalance_dates) and (not in_tier4_defense) and (effective_exposure_cap > 0.05):
            available_slots = CORE_SLOTS - len(holdings)
            if available_slots > 0:
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
                    scores_dict = {}
                    window_slice = adj_close.loc[:current_date].iloc[-(180 + 20):]
                    for s in eligible_syms:
                        p_arr = window_slice[s].dropna().values
                        if len(p_arr) >= 180:
                            s90 = calc_vectorized_momentum(p_arr, 90)[-1]
                            s180 = calc_vectorized_momentum(p_arr, 180)[-1]
                            if not (math.isnan(s90) or math.isnan(s180)):
                                blended = 0.60 * s90 + 0.40 * s180
                                if blended > 0.15:
                                    scores_dict[s] = blended

                    sorted_candidates = sorted(scores_dict.items(), key=lambda x: x[1], reverse=True)
                    picks = [s for s, _ in sorted_candidates[:available_slots]]

                    target_equity_exposure = total_equity * effective_exposure_cap
                    current_invested = sum(pos["shares"] * pos.get("current_price", pos["fill_price"]) for pos in holdings.values())
                    allocatable_cash = max(0.0, min(cash, target_equity_exposure - current_invested))

                    if allocatable_cash > 1000.0 and picks:
                        target_per_slot = min(allocatable_cash / len(picks), total_equity * MAX_ALLOC_PER_STOCK)
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
                                    "current_price": eff_buy_price
                                }

    eq_series = pd.Series(equity_curve, index=dates)
    years = max((dates[-1] - dates[0]).days / 365.25, 0.1)
    cagr = (eq_series.iloc[-1] / eq_series.iloc[0]) ** (1.0 / years) - 1.0
    daily_ret = eq_series.pct_change().dropna()
    sharpe = (daily_ret.mean() / daily_ret.std() * math.sqrt(252.0)) if daily_ret.std() > 0 else 0.0
    cummax = eq_series.cummax()
    max_dd = float(((eq_series - cummax) / cummax).min())

    summary = {
        "cagr_pct": round(cagr * 100.0, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_pct": round(max_dd * 100.0, 2),
        "ending_equity": round(eq_series.iloc[-1], 2),
        "total_trades": len(trade_log)
    }

    return eq_series, trade_log, summary


def main():
    close_df, open_df, turnover_df, bench_df, coverage_audit = load_all_data()

    print("\n" + "=" * 80)
    print("RUNNING DETAILED BASELINE SIMULATION...")
    print("=" * 80)
    base_eq, base_trades, base_sum = run_detailed_simulation(
        close_df, open_df, turnover_df, bench_df,
        IN_SAMPLE_START, IN_SAMPLE_END,
        BUY_FRICTION_BPS_BASE, SELL_FRICTION_BPS_BASE, FLAT_DP_FEE_BASE
    )

    print("\n" + "=" * 80)
    print("RUNNING DETAILED STRESSED 2X SIMULATION...")
    print("=" * 80)
    stress_eq, stress_trades, stress_sum = run_detailed_simulation(
        close_df, open_df, turnover_df, bench_df,
        IN_SAMPLE_START, IN_SAMPLE_END,
        BUY_FRICTION_BPS_STRESSED, SELL_FRICTION_BPS_STRESSED, FLAT_DP_FEE_STRESSED
    )

    df_base = pd.DataFrame(base_trades)
    df_stress = pd.DataFrame(stress_trades)

    print(f"\nBaseline Total Trades: {len(df_base)}, Stressed Total Trades: {len(df_stress)}")

    # 1. Top 5 Trades by Return and PnL
    df_base["abs_pnl"] = df_base["realized_pnl"]
    top5_ret = df_base.sort_values(by="return_pct", ascending=False).head(5)
    top5_pnl = df_base.sort_values(by="realized_pnl", ascending=False).head(5)

    print("\n" + "=" * 80)
    print("TOP 5 TRADES BY RETURN % (BASELINE):")
    print("=" * 80)
    for _, r in top5_ret.iterrows():
        print(f"  {r['symbol']:15s} | {r['entry_date']} to {r['exit_date']} | Return: {r['return_pct']*100:+7.2f}% | PnL: Rs {r['realized_pnl']:+10.2f} | Reason: {r['reason']}")

    print("\n" + "=" * 80)
    print("TOP 5 TRADES BY REALIZED PNL (BASELINE):")
    print("=" * 80)
    for _, r in top5_pnl.iterrows():
        print(f"  {r['symbol']:15s} | {r['entry_date']} to {r['exit_date']} | Return: {r['return_pct']*100:+7.2f}% | PnL: Rs {r['realized_pnl']:+10.2f} | Reason: {r['reason']}")

    # 2. Top 10 Contributors by Ticker (Sum of Realized PnL)
    ticker_pnl = df_base.groupby("symbol")["realized_pnl"].sum().sort_values(ascending=False)
    top10_tickers = ticker_pnl.head(10)
    print("\n" + "=" * 80)
    print("TOP 10 CONTRIBUTORS BY TICKER (TOTAL REALIZED PNL):")
    print("=" * 80)
    for sym, pnl in top10_tickers.items():
        n_t = len(df_base[df_base["symbol"] == sym])
        print(f"  {sym:15s} | Realized PnL: Rs {pnl:+12.2f} | Trades: {n_t}")

    # Check for unadjusted splits or abnormal jumps in Top 10 tickers
    print("\n" + "=" * 80)
    print("AUDITING TOP 10 CONTRIBUTORS FOR ABNORMAL PRINTS / UNADJUSTED SPLITS:")
    print("=" * 80)
    mult_df, adj_factors = build_verified_split_adjustment_matrix(close_df)
    for sym in top10_tickers.index:
        p_series = close_df[sym].dropna()
        max_daily_chg = ((p_series - p_series.shift(1)) / p_series.shift(1)).abs().max()
        splits_found = mult_df[sym][mult_df[sym] != 1.0] if sym in mult_df.columns else []
        print(f"  {sym:15s} | First: {p_series.index[0].date()} | Last: {p_series.index[-1].date()} | Max 1-Day Jump: {max_daily_chg*100:6.1f}% | Verified Splits: {len(splits_found)}")

    # 3. Recompute CAGR without Top 5 Trades
    # If the top 5 PnL trades had instead produced 0% return (or repo yield):
    total_top5_pnl = top5_pnl["realized_pnl"].sum()
    end_eq_base = base_sum["ending_equity"]
    adj_end_eq = end_eq_base - total_top5_pnl
    years = (pd.to_datetime(IN_SAMPLE_END) - pd.to_datetime(IN_SAMPLE_START)).days / 365.25
    cagr_no_top5 = (max(adj_end_eq, 1000.0) / INITIAL_CAPITAL) ** (1.0 / years) - 1.0

    print("\n" + "=" * 80)
    print("CAGR SENSITIVITY: EXCLUDING TOP 5 TRADES:")
    print("=" * 80)
    print(f"  Baseline Ending Equity      : Rs {end_eq_base:,.2f} (CAGR: {base_sum['cagr_pct']}%)")
    print(f"  Top 5 Trades Total PnL      : Rs {total_top5_pnl:,.2f}")
    print(f"  Adjusted Ending Equity      : Rs {adj_end_eq:,.2f} (CAGR: {cagr_no_top5*100:.2f}%)")
    print(f"  CAGR Drop Without Top 5     : {base_sum['cagr_pct'] - cagr_no_top5*100:.2f}% percentage points")

    # 4. Trade-by-Trade Comparison: Baseline vs Stressed (Why did 2x cost give 18.06% vs 14.0%?)
    print("\n" + "=" * 80)
    print("TRADE-BY-TRADE DIVERGENCE: BASELINE VS STRESSED 2X COSTS:")
    print("=" * 80)
    base_trades_set = set((r["symbol"], r["entry_date"]) for _, r in df_base.iterrows())
    stress_trades_set = set((r["symbol"], r["entry_date"]) for _, r in df_stress.iterrows())

    in_base_not_stress = base_trades_set - stress_trades_set
    in_stress_not_base = stress_trades_set - base_trades_set
    common_trades = base_trades_set.intersection(stress_trades_set)

    print(f"  Common Trades               : {len(common_trades)}")
    print(f"  In Baseline but NOT Stressed: {len(in_base_not_stress)}")
    print(f"  In Stressed but NOT Baseline: {len(in_stress_not_base)}")

    # Analyze PnL of diverged trades
    df_base["key"] = list(zip(df_base["symbol"], df_base["entry_date"]))
    df_stress["key"] = list(zip(df_stress["symbol"], df_stress["entry_date"]))

    base_diverged_pnl = df_base[df_base["key"].isin(in_base_not_stress)]["realized_pnl"].sum()
    stress_diverged_pnl = df_stress[df_stress["key"].isin(in_stress_not_base)]["realized_pnl"].sum()

    print(f"  PnL of trades taken ONLY by Baseline : Rs {base_diverged_pnl:+10.2f}")
    print(f"  PnL of trades taken ONLY by Stressed : Rs {stress_diverged_pnl:+10.2f}")

    # Inspect top diverged trades in stressed run
    print("\n  Top 5 Unique Trades in Stressed Run (that Baseline did not take):")
    unique_stress = df_stress[df_stress["key"].isin(in_stress_not_base)].sort_values(by="realized_pnl", ascending=False).head(5)
    for _, r in unique_stress.iterrows():
        print(f"    {r['symbol']:15s} | {r['entry_date']} to {r['exit_date']} | Ret: {r['return_pct']*100:+7.2f}% | PnL: Rs {r['realized_pnl']:+10.2f}")

    print("\n  Worst 5 Unique Trades in Baseline Run (that Stressed avoided):")
    unique_base_worst = df_base[df_base["key"].isin(in_base_not_stress)].sort_values(by="realized_pnl", ascending=True).head(5)
    for _, r in unique_base_worst.iterrows():
        print(f"    {r['symbol']:15s} | {r['entry_date']} to {r['exit_date']} | Ret: {r['return_pct']*100:+7.2f}% | PnL: Rs {r['realized_pnl']:+10.2f}")


if __name__ == "__main__":
    main()
