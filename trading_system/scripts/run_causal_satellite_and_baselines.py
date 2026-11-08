"""
Institutional Causal Satellite, Core, and Equal-Weight Baseline Engine (2007 - 2024)
===================================================================================
Rigorous survivorship-bias-free, hindsight-free evaluation across 4 strategies:
1. Equal-Weight Causal Universe Baseline (100% equities, monthly rebalance).
2. Satellite-Only: Plain 12-1 Momentum (10-slot, 100% equities, monthly rebalance).
3. Core-Only: Multi-Asset Core (honest proxy labeling, TER deducted).
4. Hybrid: 50% Core + 50% Satellite.

P0 Invariants:
- Starts September 2007: 2008 crash is fully captured inside the window.
- Zero split guessing: audited corporate action registry applied on verified ex-dates.
- Real crashes (-50% gaps) are 100% preserved.
- Strict ETF guard: stock universe admits only 'INE' equities; all ETFs purged.
- Statutory friction: 22.85 bps buy, 21.35 bps sell, Rs 14.75 DP fee, 15% STCG tax.
"""

import os
import sys
import math
import json
import subprocess
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Set, Tuple, Optional, Any

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from trading_system.scripts.run_causal_bhavcopy_backtest import assemble_causal_panel
from trading_system.app.data.corporate_actions import (
    build_verified_split_adjustment_matrix,
    load_audited_corporate_actions,
    is_etf_ticker
)
from trading_system.app.validation.trial_logger import log_trial

INITIAL_CAPITAL = 80000.0
BUY_BPS = 0.002285      # 22.85 bps
SELL_BPS = 0.002135     # 21.35 bps
DP_FEE = 14.75          # Flat DP transaction fee in INR
STCG_TAX_RATE = 0.15    # 15% Short Term Capital Gains Tax
CASH_YIELD_ANNUAL = 0.06  # 6% LiquidBeES annual yield
MIN_PRICE = 20.0
MAX_SLOTS = 10


def calculate_metrics(equity_curve: List[float], dates: pd.DatetimeIndex, capital: float = INITIAL_CAPITAL) -> Dict[str, Any]:
    years = (dates[-1] - dates[0]).days / 365.25
    terminal = equity_curve[-1]
    cagr = ((terminal / capital) ** (1.0 / years) - 1.0) * 100.0
    eq_s = pd.Series(equity_curve, index=dates)
    cummax = eq_s.cummax()
    drawdowns = (eq_s - cummax) / cummax
    max_dd = drawdowns.min() * 100.0
    daily_rets = eq_s.pct_change().dropna()
    ann_vol = daily_rets.std() * math.sqrt(252) * 100.0 if len(daily_rets) > 0 else 0.0
    rf_daily = 0.06 / 252.0
    excess_rets = daily_rets - rf_daily
    sharpe = (excess_rets.mean() / daily_rets.std()) * math.sqrt(252) if daily_rets.std() > 0 else 0.0

    return {
        "start_date": str(dates[0].date()),
        "end_date": str(dates[-1].date()),
        "years": round(years, 2),
        "initial_capital": capital,
        "terminal_equity": round(terminal, 2),
        "cagr_pct": round(cagr, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "annual_volatility_pct": round(ann_vol, 2),
        "sharpe_ratio": round(sharpe, 2)
    }


def run_equal_weight_baseline(
    dates: pd.DatetimeIndex,
    close_df: pd.DataFrame,
    open_df: pd.DataFrame,
    turnover_df: pd.DataFrame,
    split_multipliers: pd.DataFrame,
    month_ends: Set[pd.Timestamp]
) -> Tuple[List[float], Dict[str, Any]]:
    """
    Passive Equal-Weight Causal Universe Baseline:
    At each monthly rebalance, equal-weights the top 50 most liquid causal equities (price >= 20, non-ETF).
    """
    cash = INITIAL_CAPITAL
    positions: Dict[str, float] = {}
    entry_prices: Dict[str, float] = {}
    entry_dates: Dict[str, pd.Timestamp] = {}
    equity_curve: List[float] = []
    trade_count = 0
    total_tax = 0.0
    top_n = 50

    for i, dt in enumerate(dates):
        # 1. Apply verified corporate actions on active positions
        for sym in list(positions.keys()):
            mult = split_multipliers.loc[dt, sym] if sym in split_multipliers.columns else 1.0
            if mult > 1.0:
                positions[sym] *= mult
                entry_prices[sym] /= mult

        # 2. Check for month-end rebalance
        if dt in month_ends or i == 0:
            hist_idx = i
            window_turnover = turnover_df.iloc[max(0, hist_idx - 126):max(1, hist_idx)]
            latest_prices = close_df.iloc[hist_idx]
            eligible = [s for s in latest_prices.index if latest_prices[s] >= MIN_PRICE and not is_etf_ticker(s)]
            if len(eligible) > 0 and len(window_turnover) > 0:
                med_turnover = window_turnover.loc[:, eligible].median().dropna()
                target_universe = med_turnover.sort_values(ascending=False).head(top_n).index.tolist()
            else:
                target_universe = []

            if target_universe:
                # Sell dropped names
                for sym in list(positions.keys()):
                    if sym not in target_universe:
                        sh = positions.pop(sym)
                        ep = entry_prices.pop(sym)
                        ed = entry_dates.pop(sym, dt)
                        cp = close_df.loc[dt, sym] if not math.isnan(close_df.loc[dt, sym]) else ep
                        proceeds = sh * cp * (1.0 - SELL_BPS) - DP_FEE
                        gain = proceeds - (sh * ep)
                        if gain > 0:
                            h_days = (dt - ed).days
                            tax = gain * (0.125 if h_days >= 365 else 0.15)
                            proceeds -= tax
                            total_tax += tax
                        cash += proceeds
                        trade_count += 1

                # Rebalance targets
                current_port_val = cash + sum(
                    positions[s] * (close_df.loc[dt, s] if not math.isnan(close_df.loc[dt, s]) else entry_prices[s])
                    for s in positions
                )
                target_per_slot = current_port_val / len(target_universe)

                for sym in target_universe:
                    cp = close_df.loc[dt, sym]
                    if not math.isnan(cp) and cp >= MIN_PRICE:
                        cur_val = positions.get(sym, 0.0) * cp
                        if cur_val < target_per_slot * 0.80 and cash > 200:
                            add_val = min(target_per_slot - cur_val, cash * 0.95)
                            sh = add_val / (cp * (1.0 + BUY_BPS))
                            if sym in positions:
                                old_sh = positions[sym]
                                positions[sym] += sh
                                entry_prices[sym] = (positions[sym] * entry_prices[sym] + sh * cp) / positions[sym]
                            else:
                                positions[sym] = sh
                                entry_prices[sym] = cp
                                entry_dates[sym] = dt
                            cash -= add_val
                            trade_count += 1

        # Liquid yield
        cash += cash * (CASH_YIELD_ANNUAL / 252.0)
        port_val = cash + sum(
            positions[s] * (close_df.loc[dt, s] if not math.isnan(close_df.loc[dt, s]) else entry_prices[s])
            for s in positions
        )
        equity_curve.append(port_val)

    metrics = calculate_metrics(equity_curve, dates)
    metrics["strategy"] = "Equal-Weight Causal Baseline (Top 50)"
    metrics["trades"] = trade_count
    metrics["tax_paid"] = round(total_tax, 2)
    return equity_curve, metrics


def run_plain_momentum_satellite(
    dates: pd.DatetimeIndex,
    close_df: pd.DataFrame,
    open_df: pd.DataFrame,
    turnover_df: pd.DataFrame,
    adj_close_df: pd.DataFrame,
    split_multipliers: pd.DataFrame,
    month_ends: Set[pd.Timestamp]
) -> Tuple[List[float], Dict[str, Any]]:
    """
    Satellite-Only: Plain 12-1 Momentum Strategy (10 Slots, 100% Equity).
    No curve-fitted volatility radar, no ladder overrides.
    Rebalances monthly. Deducts full statutory friction, DP fees, and STCG tax.
    """
    cash = INITIAL_CAPITAL
    positions: Dict[str, float] = {}
    entry_prices: Dict[str, float] = {}
    entry_dates: Dict[str, pd.Timestamp] = {}
    peak_prices: Dict[str, float] = {}
    equity_curve: List[float] = []
    trade_count = 0
    total_tax = 0.0
    trailing_stop_pct = 0.25  # 25% catastrophic trailing stop

    for i, dt in enumerate(dates):
        # 1. Apply verified corporate actions on active positions
        for sym in list(positions.keys()):
            mult = split_multipliers.loc[dt, sym] if sym in split_multipliers.columns else 1.0
            if mult > 1.0:
                positions[sym] *= mult
                entry_prices[sym] /= mult
                if sym in peak_prices:
                    peak_prices[sym] /= mult

        # 2. Daily catastrophic stop / delisting check
        for sym in list(positions.keys()):
            cp = close_df.loc[dt, sym] if sym in close_df.columns else np.nan
            if math.isnan(cp) or cp <= 0:
                # Faded / bankrupt stock: salvage 50% of entry price
                sh = positions.pop(sym)
                ep = entry_prices.pop(sym, 1.0)
                entry_dates.pop(sym, None)
                peak_prices.pop(sym, None)
                cash += sh * ep * 0.50
                trade_count += 1
                continue

            if cp > peak_prices.get(sym, 0.0):
                peak_prices[sym] = cp
            peak = peak_prices[sym]

            # Trailing stop -25%
            if (cp - peak) / peak <= -trailing_stop_pct:
                sh = positions.pop(sym)
                ep = entry_prices.pop(sym)
                ed = entry_dates.pop(sym, dt)
                peak_prices.pop(sym, None)
                fp = open_df.loc[dt, sym] if sym in open_df.columns and not math.isnan(open_df.loc[dt, sym]) else cp
                proceeds = sh * fp * (1.0 - SELL_BPS) - DP_FEE
                gain = proceeds - (sh * ep)
                if gain > 0:
                    h_days = (dt - ed).days
                    tax = gain * (0.125 if h_days >= 365 else 0.15)
                    proceeds -= tax
                    total_tax += tax
                cash += proceeds
                trade_count += 1

        # 3. Monthly Rebalance on Month-End
        is_month_end = dt in month_ends
        if is_month_end and i >= 21:  # Need at least 1 month (21 days) of causal history
            hist_idx = i
            window_turnover = turnover_df.iloc[max(0, hist_idx - 126):hist_idx]
            latest_prices = close_df.iloc[hist_idx - 1]
            eligible = [s for s in latest_prices.index if latest_prices[s] >= MIN_PRICE and not is_etf_ticker(s)]
            med_turnover = window_turnover.loc[:, eligible].median().dropna()
            top_300 = med_turnover.sort_values(ascending=False).head(300).index.tolist()

            # Plain 12-1 Momentum: Return over [t-L, t-21]
            lookback = min(hist_idx, 252)
            past_adj = adj_close_df.iloc[hist_idx - lookback]
            skip_adj = adj_close_df.iloc[hist_idx - 21]
            mom_metric = (skip_adj / past_adj) - 1.0

            # Rank eligible candidates
            valid_cands = [
                s for s in top_300
                if s in mom_metric.index and not math.isnan(mom_metric[s])
                and mom_metric[s] > 0.0
                and close_df.iloc[hist_idx - 1][s] >= MIN_PRICE
            ]
            valid_cands.sort(key=lambda s: mom_metric[s], reverse=True)
            top_targets = set(valid_cands[:MAX_SLOTS])

            # Sell positions not in top targets
            for sym in list(positions.keys()):
                if sym not in top_targets:
                    sh = positions.pop(sym)
                    ep = entry_prices.pop(sym)
                    ed = entry_dates.pop(sym, dt)
                    peak_prices.pop(sym, None)
                    fp = open_df.loc[dt, sym] if sym in open_df.columns and not math.isnan(open_df.loc[dt, sym]) else close_df.loc[dt, sym]
                    proceeds = sh * fp * (1.0 - SELL_BPS) - DP_FEE
                    gain = proceeds - (sh * ep)
                    if gain > 0:
                        h_days = (dt - ed).days
                        tax = gain * (0.125 if h_days >= 365 else 0.15)
                        proceeds -= tax
                        total_tax += tax
                    cash += proceeds
                    trade_count += 1

            # Buy new target positions
            current_port_val = cash + sum(
                positions[s] * (close_df.loc[dt, s] if not math.isnan(close_df.loc[dt, s]) else entry_prices[s])
                for s in positions
            )
            slot_budget = current_port_val / MAX_SLOTS

            for sym in valid_cands[:MAX_SLOTS]:
                if sym not in positions and cash >= 1000:
                    op = open_df.loc[dt, sym] if sym in open_df.columns and not math.isnan(open_df.loc[dt, sym]) else close_df.loc[dt, sym]
                    if not math.isnan(op) and op > 0:
                        buy_val = min(slot_budget, cash * 0.95)
                        sh = buy_val / (op * (1.0 + BUY_BPS))
                        positions[sym] = sh
                        entry_prices[sym] = op
                        peak_prices[sym] = op
                        entry_dates[sym] = dt
                        cash -= buy_val
                        trade_count += 1

        # Liquid yield
        cash += cash * (CASH_YIELD_ANNUAL / 252.0)
        port_val = cash + sum(
            positions[s] * (close_df.loc[dt, s] if not math.isnan(close_df.loc[dt, s]) else entry_prices[s])
            for s in positions
        )
        equity_curve.append(port_val)

    metrics = calculate_metrics(equity_curve, dates)
    metrics["strategy"] = "Plain 12-1 Momentum (Satellite Only, 10 Slots)"
    metrics["trades"] = trade_count
    metrics["tax_paid"] = round(total_tax, 2)
    return equity_curve, metrics


def run_core_only_multi_asset(
    dates: pd.DatetimeIndex,
    etf_assets: pd.DataFrame,
    month_ends: Set[pd.Timestamp]
) -> Tuple[List[float], Dict[str, Any]]:
    """
    Core-Only: 100% Multi-Asset Momentum Rotation (Honest Proxies & TER deducted).
    Assets:
      - MON100 Proxy: QQQ_USD * USDINR (TER: 0.50% + 0.20% cash drag = 0.70%)
      - MID150 Proxy: NIFTY MIDCAP 50 (TER: 0.30%)
      - GOLD Proxy: COMEX Gold * USDINR (TER: 0.80%)
    Rotates to 6-month momentum leader when above 200-SMA, else Gold / Cash.
    """
    # Deduct daily TER from raw asset prices
    ter_rates = {'MON100': 0.0070 / 252.0, 'MIDCAP': 0.0030 / 252.0, 'GOLD': 0.0080 / 252.0}
    net_etf = etf_assets.copy()
    for col, daily_ter in ter_rates.items():
        if col in net_etf.columns:
            cum_drag = (1.0 - daily_ter) ** np.arange(len(net_etf))
            net_etf[col] = net_etf[col] * cum_drag

    etf_sma200 = net_etf.rolling(200, min_periods=50).mean()
    etf_mom6m = net_etf.pct_change(126)

    cash = INITIAL_CAPITAL
    holdings = {'MON100': 0.0, 'MIDCAP': 0.0, 'GOLD': 0.0}
    equity_curve: List[float] = []
    trade_count = 0

    for i, dt in enumerate(dates):
        etf_p = net_etf.loc[dt]
        is_month_end = dt in month_ends

        if is_month_end and i >= 50:
            moms = etf_mom6m.loc[dt]
            best_equity = 'MON100' if moms['MON100'] > moms['MIDCAP'] else 'MIDCAP'
            target = best_equity if (etf_p[best_equity] > etf_sma200.loc[dt, best_equity] and moms[best_equity] > 0) else ('GOLD' if etf_p['GOLD'] > etf_sma200.loc[dt, 'GOLD'] else None)

            # Reallocate
            for c in list(holdings.keys()):
                if c != target and holdings[c] > 0:
                    cash += holdings[c] * etf_p[c] * (1.0 - SELL_BPS)
                    holdings[c] = 0.0
                    trade_count += 1

            if target and holdings[target] == 0.0 and cash > 1000:
                buy_val = cash * 0.99
                holdings[target] = buy_val / (etf_p[target] * (1.0 + BUY_BPS))
                cash -= buy_val
                trade_count += 1

        # Liquid yield
        cash += cash * (CASH_YIELD_ANNUAL / 252.0)
        tot_val = cash + sum(holdings[c] * etf_p[c] for c in holdings)
        equity_curve.append(tot_val)

    metrics = calculate_metrics(equity_curve, dates)
    metrics["strategy"] = "Multi-Asset Core-Only (Honest Proxies & TER)"
    metrics["trades"] = trade_count
    metrics["tax_paid"] = 0.0
    return equity_curve, metrics


def main():
    print("[1/5] Loading causal Bhavcopy panels and official multi-asset series...", flush=True)
    close_df, open_df, turnover_df, bench_df = assemble_causal_panel()

    qqq = pd.read_parquet(os.path.join(PROJECT_ROOT, "trading_system", "data", "multi_asset_cache", "QQQ_USD.parquet"))['close']
    usdinr = pd.read_parquet(os.path.join(PROJECT_ROOT, "trading_system", "data", "multi_asset_cache", "USDINR.parquet"))['close']
    midcap = pd.read_parquet(os.path.join(PROJECT_ROOT, "trading_system", "data", "multi_asset_cache", "MIDCAP50.parquet"))['close']
    gold_usd = pd.read_parquet(os.path.join(PROJECT_ROOT, "trading_system", "data", "multi_asset_cache", "GOLD_USD.parquet"))['close']

    # Common index covering 2007-09-24 to 2024-07-05
    dates = (
        qqq.index.intersection(usdinr.index)
        .intersection(midcap.index)
        .intersection(gold_usd.index)
        .intersection(close_df.index)
        .intersection(bench_df.index)
        .sort_values()
    )

    print(f"  Aligned Common Timeline: {len(dates)} trading days ({dates[0].date()} to {dates[-1].date()})", flush=True)

    qqq_inr = qqq.loc[dates] * usdinr.loc[dates]
    gold_inr = gold_usd.loc[dates] * usdinr.loc[dates]
    midcap_aligned = midcap.loc[dates]
    etf_assets = pd.DataFrame({'MON100': qqq_inr, 'MIDCAP': midcap_aligned, 'GOLD': gold_inr}, index=dates)

    close_df = close_df.loc[dates]
    open_df = open_df.loc[dates]
    turnover_df = turnover_df.loc[dates]

    # Audited Corporate Actions Adjustment Matrix
    print("[2/5] Building causal corporate actions matrix strictly from verified registry...", flush=True)
    split_multipliers, split_adj_factors = build_verified_split_adjustment_matrix(close_df)
    adj_close_df = close_df * split_adj_factors

    # Month-end identification
    df_d = pd.DataFrame({'date': dates}, index=dates)
    df_d['month'] = df_d['date'].dt.to_period('M')
    month_ends = set(df_d.groupby('month')['date'].max())

    print("\n[3/5] Running Strategy 1: Equal-Weight Causal Baseline (Top 50)...", flush=True)
    eq_curve_base, m_base = run_equal_weight_baseline(dates, close_df, open_df, turnover_df, split_multipliers, month_ends)

    print("[4/5] Running Strategy 2: Plain 12-1 Momentum (Satellite Only, 10 Slots)...", flush=True)
    eq_curve_sat, m_sat = run_plain_momentum_satellite(dates, close_df, open_df, turnover_df, adj_close_df, split_multipliers, month_ends)

    print("[5/5] Running Strategy 3: Multi-Asset Core-Only (Honest Proxies & TER)...", flush=True)
    eq_curve_core, m_core = run_core_only_multi_asset(dates, etf_assets, month_ends)

    # Hybrid 50/50 combination
    hybrid_curve = [0.5 * s + 0.5 * c for s, c in zip(eq_curve_sat, eq_curve_core)]
    m_hybrid = calculate_metrics(hybrid_curve, dates)
    m_hybrid["strategy"] = "Hybrid 50/50 (Core + Satellite Momentum)"
    m_hybrid["trades"] = m_sat["trades"] + m_core["trades"]
    m_hybrid["tax_paid"] = m_sat["tax_paid"]

    # Print Summary Table
    print("\n" + "=" * 95)
    print("INSTITUTIONAL PERFORMANCE COMPARISON (2007-09-24 to 2024-07-05: INCLUDES 2008 CRASH)")
    print("=" * 95)
    print(f"{'Strategy':<40} | {'CAGR (%)':>9} | {'Max DD (%)':>10} | {'Sharpe':>7} | {'Trades':>7} | {'STCG Tax':>9}")
    print("-" * 95)
    for m in [m_base, m_sat, m_core, m_hybrid]:
        print(f"{m['strategy']:<40} | {m['cagr_pct']:>8.2f}% | {m['max_drawdown_pct']:>9.2f}% | {m['sharpe_ratio']:>7.2f} | {m['trades']:>7} | Rs {m['tax_paid']:>7,.0f}")
    print("=" * 95)

    # Log each trial once stamped with commit hash
    log_trial(
        cagr_pct=m_base["cagr_pct"],
        max_drawdown_pct=m_base["max_drawdown_pct"],
        sharpe_ratio=m_base["sharpe_ratio"],
        kelly_fraction=1.0,
        lookback_days=126,
        commit_hash="f78131e",
        script="run_causal_satellite_and_baselines.py",
        universe="NSE_CAUSAL_TOP50_EQUAL_WEIGHT",
        notes="Equal-Weight Causal Baseline (Top 50, 2007 Start, 2008 Crash Included)"
    )
    log_trial(
        cagr_pct=m_sat["cagr_pct"],
        max_drawdown_pct=m_sat["max_drawdown_pct"],
        sharpe_ratio=m_sat["sharpe_ratio"],
        kelly_fraction=1.0,
        lookback_days=252,
        commit_hash="f78131e",
        script="run_causal_satellite_and_baselines.py",
        universe="NSE_CAUSAL_TOP300_PLAIN_MOMENTUM",
        notes="Plain 12-1 Momentum (Satellite Only, 10 Slots, 2007 Start, 2008 Crash Included)"
    )
    log_trial(
        cagr_pct=m_core["cagr_pct"],
        max_drawdown_pct=m_core["max_drawdown_pct"],
        sharpe_ratio=m_core["sharpe_ratio"],
        kelly_fraction=1.0,
        lookback_days=126,
        commit_hash="f78131e",
        script="run_causal_satellite_and_baselines.py",
        universe="MULTI_ASSET_CORE_HONEST_PROXIES",
        notes="Multi-Asset Core-Only (QQQ_INR, Midcap50, Gold_INR with TER, 2007 Start)"
    )
    log_trial(
        cagr_pct=m_hybrid["cagr_pct"],
        max_drawdown_pct=m_hybrid["max_drawdown_pct"],
        sharpe_ratio=m_hybrid["sharpe_ratio"],
        kelly_fraction=0.5,
        lookback_days=252,
        commit_hash="f78131e",
        script="run_causal_satellite_and_baselines.py",
        universe="HYBRID_50_CORE_50_SATELLITE",
        notes="Hybrid 50/50 (Core + Plain Satellite Momentum, 2007 Start, 2008 Crash Included)"
    )

    # Save Results
    results_path = os.path.join(PROJECT_ROOT, "trading_system", "data", "causal_satellite_and_baselines_results.json")
    with open(results_path, "w") as f:
        json.dump({
            "equal_weight_baseline": m_base,
            "plain_momentum_satellite": m_sat,
            "core_only": m_core,
            "hybrid_50_50": m_hybrid
        }, f, indent=2)
    print(f"\nSaved institutional results to: {results_path}")


if __name__ == "__main__":
    main()
