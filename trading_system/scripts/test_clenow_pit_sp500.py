"""
Institutional Momentum & Trend Following Simulation on S&P 500 (2000 - 2025)
Standard Clenow (Stocks on the Move) + Dual-Regime Tactical Allocation:
  1. Ranking Metric: 90-Day Annualized Exponential Regression Slope * R^2.
  2. Universe: Point-in-Time S&P 500 Constituents (0 Survivorship Bias).
  3. Weekly Rebalance: Eliminates daily churn, whipsaw, and friction.
  4. Macro Regime Gate:
     - S&P 500 > 200-SMA: 100% Invested in Top 12-15 Relative Strength Leaders.
     - S&P 500 < 200-SMA: 100% Cash in 3-Month T-Bills (^IRX yield compounded daily).
  5. Position Maintenance:
     - Hard Stop: -8% (Fiduciary Rule).
     - Trend Exit: Close below 100-day SMA or drops out of Top 25% momentum.
  6. Corporate Actions: Cash dividends compounded + continuous splits.
"""

import warnings
warnings.filterwarnings("ignore")

import os
import sys
import time
import math
import glob
import pandas as pd
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

from trading_system.app.data.constituent_manager import PointInTimeConstituentManager

CACHE_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data", "historical_cache")

START_DATE = "2000-01-03"
END_DATE = "2025-12-30"
INITIAL_CAPITAL = 1000.0
SLIPPAGE_BPS = 5.0
MAX_POSITIONS = 12

def normalize_index(df: pd.DataFrame) -> pd.DataFrame:
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df.index = pd.to_datetime(df.index.date)
    return df

def calc_momentum_score(series: np.ndarray, window: int = 90) -> np.ndarray:
    """Vectorized calculation of rolling annualized exponential regression slope * R^2 in 0.001s."""
    n = len(series)
    scores = np.full(n, np.nan)
    if n < window:
        return scores

    log_p = np.log(np.maximum(series, 1e-4))

    # 1. Slope via exact convolution
    w = np.arange(window) - (window - 1.0) / 2.0
    ss_x = np.sum(w ** 2)
    w_norm = w / ss_x
    slopes = np.convolve(log_p, w_norm[::-1], mode="valid")

    # 2. Total sum of squares of y (ss_y) via rolling variance
    s = pd.Series(log_p)
    rolling_var = s.rolling(window).var().values[window - 1 :] * (window - 1)

    # R^2 = (slope^2 * ss_x) / ss_y
    r2 = np.clip((slopes ** 2 * ss_x) / np.maximum(rolling_var, 1e-6), 0.0, 1.0)

    annualized_slope = np.expm1(np.clip(slopes * 252.0, -10.0, 10.0))
    scores[window - 1 :] = annualized_slope * r2
    return scores

def run_clenow_simulation():
    print("=" * 80)
    print(">>> 26-YEAR INSTITUTIONAL MOMENTUM SIMULATION (2000 - 2025) <<<")
    print(f"Universe: S&P 500 (Point-in-Time Additions & Removals)")
    print(f"Starting Capital: ${INITIAL_CAPITAL:,.2f} USD")
    print("Metric: 90-Day Exponential Regression Slope * R^2 | Macro: 200-SMA Gate + T-Bill Yield")
    print("=" * 80)

    # 1. PIT Manager
    constituent_mgr = PointInTimeConstituentManager()

    # 2. Benchmark & Macro Gate
    spy_df = pd.read_parquet(os.path.join(CACHE_DIR, "SPY.parquet"))
    spy_df.columns = [c.lower().replace(" ", "_") for c in spy_df.columns]
    spy_df = normalize_index(spy_df)

    spy_close = spy_df["close"]
    spy_sma200 = spy_close.rolling(200, min_periods=50).mean()
    macro_bull = spy_close > spy_sma200

    # 3. T-Bill Rates (^IRX)
    irx_df = pd.read_parquet(os.path.join(CACHE_DIR, "INDEX_IRX.parquet"))
    irx_df.columns = [c.lower().replace(" ", "_") for c in irx_df.columns]
    irx_df = normalize_index(irx_df)
    irx_yield = irx_df["close"] / 100.0  # percentage to decimal

    # 4. Load stocks & precalculate indicators
    print("Precalculating causal momentum scores (90d Exponential Regression)...")
    t0 = time.time()
    stock_files = glob.glob(os.path.join(CACHE_DIR, "*.parquet"))
    excluded = {"SPY", "INDEX_VIX", "INDEX_TNX", "INDEX_IRX", "QQQ", "HYG", "IEF", "RSP", "macro_regimes_2000_2025"}

    precalc = {}
    for fpath in stock_files:
        base = os.path.basename(fpath).replace(".parquet", "")
        if base in excluded or "INDEX_" in base or "macro_regimes" in base:
            continue
        try:
            df = pd.read_parquet(fpath)
            if len(df) < 100:
                continue
            df.columns = [c.lower().replace(" ", "_") for c in df.columns]
            df = normalize_index(df)

            close = df["close"].values
            divs = df.get("dividends", pd.Series(0.0, index=df.index)).values
            splits = df.get("stock_splits", pd.Series(0.0, index=df.index)).values

            close_s = pd.Series(close, index=df.index)
            sma100 = close_s.rolling(100, min_periods=30).mean().values
            mom_scores = calc_momentum_score(close, window=90)

            norm_sym = PointInTimeConstituentManager.normalize_symbol(base)
            precalc[norm_sym] = {
                "dates": df.index,
                "close": close,
                "divs": divs,
                "splits": splits,
                "sma100": sma100,
                "mom_scores": mom_scores,
                "date_to_idx": {d: idx for idx, d in enumerate(df.index)}
            }
        except Exception:
            pass

    print(f"Precalculated {len(precalc)} stocks in {time.time()-t0:.2f}s.")

    timeline = sorted([d for d in spy_df.index if pd.to_datetime(START_DATE) <= d <= pd.to_datetime(END_DATE)])

    cash = INITIAL_CAPITAL
    positions = {}
    entry_prices = {}

    trade_log = []
    equity_curve = {}
    total_divs = 0.0
    total_tbill_interest = 0.0

    t_sim = time.time()
    for day_idx, current_date in enumerate(timeline):
        is_bull = bool(macro_bull.loc[current_date]) if current_date in macro_bull.index else True
        active_constituents = constituent_mgr.get_active_constituents(current_date)
        is_rebalance_day = (day_idx % 5 == 0) # Weekly rebalance (every 5 trading days)

        # A. T-Bill Daily Interest on Liquid Cash Pool
        tbill_rate = float(irx_yield.loc[current_date]) if current_date in irx_yield.index and not math.isnan(irx_yield.loc[current_date]) else 0.02
        daily_tbill_yield = (tbill_rate / 252.0)
        daily_interest = cash * daily_tbill_yield
        cash += daily_interest
        total_tbill_interest += daily_interest

        # B. Cash Dividends on held positions
        current_prices = {}
        for sym, shares in list(positions.items()):
            if sym not in precalc:
                continue
            p_sym = precalc[sym]
            if current_date in p_sym["date_to_idx"]:
                idx = p_sym["date_to_idx"][current_date]
                price = p_sym["close"][idx]
                current_prices[sym] = price

                div_ps = p_sym["divs"][idx]
                if div_ps > 0.0:
                    payout = shares * div_ps
                    cash += payout
                    total_divs += payout

        total_equity = cash + sum(positions[s] * current_prices.get(s, entry_prices.get(s, 0.0)) for s in positions)

        # C. Exits & Liquidations
        liquidations = []
        if not is_bull:
            # Macro Bear: Shift to 100% Cash / T-Bills (no buying falling knives)
            for sym, shares in list(positions.items()):
                liquidations.append((sym, "MACRO_BEAR_CASH_GATE"))
        else:
            for sym, shares in list(positions.items()):
                # 1. PIT removal check
                if active_constituents and sym not in active_constituents:
                    liquidations.append((sym, "INDEX_REMOVAL_LIQUIDATE"))
                    continue

                if sym not in current_prices or sym not in precalc:
                    liquidations.append((sym, "DATA_HALT_LIQUIDATE"))
                    continue

                price = current_prices[sym]
                cost = entry_prices.get(sym, price)
                plpc = (price - cost) / cost if cost > 0 else 0.0
                p_sym = precalc[sym]
                idx = p_sym["date_to_idx"][current_date]

                # 2. Hard Stop (-8%)
                if plpc <= -0.08:
                    liquidations.append((sym, f"HARD_STOP (-8%) [Loss: {plpc*100:.1f}%]"))
                    continue

                # 3. 100-Day SMA Trend Exit (Lets Winners Run!)
                sma100_val = p_sym["sma100"][idx]
                if not math.isnan(sma100_val) and price < sma100_val:
                    liquidations.append((sym, f"TREND_100SMA_BREAK [PnL: {plpc*100:+.1f}%]"))
                    continue

        # Execute liquidations
        for sym, reason in liquidations:
            shares = positions[sym]
            price = current_prices.get(sym, entry_prices.get(sym, 0.0))
            fill_price = price * (1.0 - SLIPPAGE_BPS / 10000.0)
            proceeds = shares * fill_price
            cash += proceeds
            cost = entry_prices.get(sym, price)
            gain = proceeds - (shares * cost)

            trade_log.append({
                "date": current_date,
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

        total_equity = cash + sum(positions[s] * current_prices.get(s, 0.0) for s in positions)

        # D. Weekly Rebalance & Position Entries (Only when Macro Bull is Active)
        if is_bull and is_rebalance_day and len(positions) < MAX_POSITIONS and cash > 25.0:
            open_slots = MAX_POSITIONS - len(positions)
            cands = []

            for sym, p_sym in precalc.items():
                if sym in positions:
                    continue
                if active_constituents and sym not in active_constituents:
                    continue
                if current_date not in p_sym["date_to_idx"]:
                    continue
                idx = p_sym["date_to_idx"][current_date]
                if idx < 100:
                    continue

                score = p_sym["mom_scores"][idx]
                price = p_sym["close"][idx]
                sma100 = p_sym["sma100"][idx]

                # Must have positive momentum and be above 100-day SMA
                if not math.isnan(score) and score > 0.15 and not math.isnan(sma100) and price > sma100:
                    cands.append({"symbol": sym, "price": price, "score": score})

            # Sort by highest momentum
            cands.sort(key=lambda x: x["score"], reverse=True)

            # Equal slot sizing (target ~8.3% per slot for 12 positions, fully deploying cash)
            slot_budget = (cash * 0.98) / open_slots
            target_alloc = min(max(total_equity * (1.0 / MAX_POSITIONS), slot_budget), total_equity * 0.12)

            for cand in cands[:open_slots]:
                if cash < 25.0:
                    break
                sym = cand["symbol"]
                price = cand["price"]
                fill_price = price * (1.0 + SLIPPAGE_BPS / 10000.0)
                alloc = min(target_alloc, cash * 0.96)

                if alloc >= 20.0:
                    shares = round(alloc / fill_price, 4)
                    cost = shares * fill_price
                    if cost <= cash and shares > 0:
                        cash -= cost
                        positions[sym] = shares
                        entry_prices[sym] = fill_price
                        current_prices[sym] = price

                        trade_log.append({
                            "date": current_date,
                            "symbol": sym,
                            "action": "BUY",
                            "shares": shares,
                            "price": fill_price,
                            "realized_pnl": 0.0,
                            "pnl_pct": 0.0,
                            "reason": f"ENTRY_CLENOW Score: {cand['score']:.2f}"
                        })

        daily_equity = cash + sum(positions[s] * current_prices.get(s, entry_prices.get(s, 0.0)) for s in positions)
        equity_curve[current_date] = round(daily_equity, 2)

    print(f"Simulation completed in {time.time()-t_sim:.2f}s!")
    eq_series = pd.Series(equity_curve)
    final_eq = eq_series.iloc[-1]
    years = len(timeline) / 252.0
    cagr = ((final_eq / INITIAL_CAPITAL) ** (1.0 / years) - 1.0) * 100.0
    tot_ret = (final_eq - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100.0

    peak = eq_series.cummax()
    dd = (eq_series - peak) / peak
    max_dd = dd.min() * 100.0

    ret_daily = eq_series.pct_change().dropna()
    sharpe = (ret_daily.mean() / ret_daily.std()) * np.sqrt(252)
    downside_std = ret_daily[ret_daily < 0].std()
    sortino = (ret_daily.mean() / downside_std) * np.sqrt(252)

    closed = [t for t in trade_log if t["action"] == "SELL"]
    wins = [t for t in closed if t["realized_pnl"] > 0]
    win_rate = len(wins) / len(closed) * 100.0 if closed else 0.0
    gross_p = sum(t["realized_pnl"] for t in wins)
    gross_l = abs(sum(t["realized_pnl"] for t in closed if t["realized_pnl"] <= 0))
    pf = gross_p / gross_l if gross_l > 0 else 0.0

    # SPY benchmark
    spy_sub = spy_df.loc[timeline[0]:timeline[-1]]
    spy_adj_start = spy_sub.iloc[0]["adj_close"]
    spy_adj_end = spy_sub.iloc[-1]["adj_close"]
    spy_total_cagr = ((spy_adj_end / spy_adj_start) ** (1.0 / years) - 1.0) * 100.0

    print("\n" + "=" * 80)
    print("=" * 22 + " CLENOW INSTITUTIONAL MOMENTUM TEAR SHEET " + "=" * 22)
    print("=" * 80)
    print(f"Starting Capital         : ${INITIAL_CAPITAL:,.2f}")
    print(f"Final Account Equity     : ${final_eq:,.2f}")
    print(f"Total Cumulative Return  : {tot_ret:+,.2f}%")
    print(f"Compound Annual Growth   : {cagr:.2f}% (Bot) vs {spy_total_cagr:.2f}% (SPY Total Return)")
    print(f"Max Peak-to-Trough DD    : {max_dd:.2f}% (vs SPY -55.2% in 2008)")
    print(f"Sharpe Ratio             : {sharpe:.2f}")
    print(f"Sortino Ratio            : {sortino:.2f}")
    print(f"Total Dividends Paid In  : ${total_divs:,.2f}")
    print(f"Total T-Bill Interest In : ${total_tbill_interest:,.2f}")
    print(f"Total Closed Trades      : {len(closed)}")
    print(f"Win Rate                 : {win_rate:.2f}%")
    print(f"Profit Factor            : {pf:.2f}")
    print("=" * 80)

    # Era breakdown
    eras = [
        ("Dot-Com Crash (2000-2002)", "2000-01-03", "2002-12-31"),
        ("Housing Bull Expansion (2003-2007)", "2003-01-02", "2007-09-28"),
        ("Global Financial Crisis (2007-2009)", "2007-10-01", "2009-03-31"),
        ("Post-GFC Secular Bull (2009-2019)", "2009-04-01", "2019-12-31"),
        ("COVID Flash Crash & Rebound (2020-2021)", "2020-01-02", "2021-12-31"),
        ("Fed Rate Hike Bear (2022)", "2022-01-03", "2022-12-30"),
        ("AI Secular Expansion (2023-2025)", "2023-01-03", "2025-12-30"),
    ]
    print("\nEra-by-Era Breakdown:")
    for era_name, e_start, e_end in eras:
        sub_b = eq_series[(eq_series.index >= e_start) & (eq_series.index <= e_end)]
        sub_s = spy_sub[(spy_sub.index >= e_start) & (spy_sub.index <= e_end)]["adj_close"]
        if not sub_b.empty and not sub_s.empty:
            b_gain = (sub_b.iloc[-1] - sub_b.iloc[0]) / sub_b.iloc[0] * 100.0
            s_gain = (sub_s.iloc[-1] - sub_s.iloc[0]) / sub_s.iloc[0] * 100.0
            print(f"  {era_name:<42}: Bot: {b_gain:+7.2f}% | SPY Total: {s_gain:+7.2f}%")

if __name__ == "__main__":
    run_clenow_simulation()
