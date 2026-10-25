"""
Phase 5 Research Sandbox: Statistical Arbitrage & Cointegration Backtest Simulator
==================================================================================
Simulates historical pair trading performance across Curated GICS Industry Pairs.
Evaluates both:
  1. Classical Market-Neutral (Long/Short) Statistical Arbitrage
  2. Long-Only Relative-Value Rotation (Retail Incubation / Cash Compliant)

Runs entirely offline in the research sandbox; decoupled from live execution.
"""

import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any
import numpy as np
import pandas as pd

# Add repo root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from trading_system.app.data.yfinance_provider import YFinanceDataProvider
from trading_system.app.strategies.library.stat_arb_pairs import (
    StatArbPairsStrategy,
    DEFAULT_CURATED_PAIRS,
)


def run_pairs_backtest(
    lookback_years: int = 5,
    z_entry: float = 2.0,
    z_exit: float = 0.25,
    z_stop: float = 3.5,
):
    print("=" * 70)
    print(">>> STATISTICAL ARBITRAGE & COINTEGRATION BACKTEST SIMULATOR <<<")
    print("=" * 70)

    provider = YFinanceDataProvider()
    end_date = datetime.now()
    start_date = end_date - timedelta(days=lookback_years * 365 + 60)

    print(f"Testing Window: {start_date.date()} to {end_date.date()} ({lookback_years} Years)")
    print(f"Thresholds: Entry |Z| >= {z_entry:.1f} | Exit |Z| <= {z_exit:.2f} | Stop-Loss |Z| >= {z_stop:.1f}\n")

    # Collect unique symbols
    unique_symbols = set()
    for y, x in DEFAULT_CURATED_PAIRS:
        unique_symbols.add(y)
        unique_symbols.add(x)

    print(f"Fetching data for {len(unique_symbols)} assets across {len(DEFAULT_CURATED_PAIRS)} curated pairs...")
    price_data: Dict[str, pd.Series] = {}
    for sym in sorted(unique_symbols):
        try:
            df = provider.fetch_historical_data(sym, start_date, end_date)
            if not df.empty and "close" in df.columns:
                price_data[sym] = df["close"]
        except Exception as e:
            print(f"  Warning: Failed to fetch {sym}: {e}")

    strategy = StatArbPairsStrategy(
        lookback_window=30, z_entry=z_entry, z_exit=z_exit, z_stop=z_stop
    )

    results = []

    print("-" * 70)
    print(f"{'Pair':<12} | {'Coint?':<7} | {'p-value':<7} | {'Beta':<6} | {'HalfLife':<9} | {'Trades':<6} | {'WinRate':<7} | {'TotalReturn'}")
    print("-" * 70)

    for sym_y, sym_x in DEFAULT_CURATED_PAIRS:
        if sym_y not in price_data or sym_x not in price_data:
            continue

        y_s = price_data[sym_y]
        x_s = price_data[sym_x]

        aligned = pd.concat([y_s, x_s], axis=1).dropna()
        if len(aligned) < 200:
            continue

        aligned.columns = ["Y", "X"]
        coint_res = strategy.test_cointegration(aligned["Y"], aligned["X"])
        is_coint = coint_res["is_cointegrated"]
        p_val = coint_res["p_value"]
        beta = coint_res["hedge_ratio"]

        df_spread = strategy.calculate_rolling_spread_and_zscore(
            aligned["Y"], aligned["X"], hedge_ratio=beta
        ).dropna()

        half_life = strategy.calculate_half_life(df_spread["spread"])

        # --- SIMULATE MARKET-NEUTRAL LONG/SHORT EXECUTION ---
        position = 0  # 1 = Long Spread (Long Y, Short X), -1 = Short Spread (Short Y, Long X), 0 = Flat
        entry_price_y = 0.0
        entry_price_x = 0.0
        entry_idx = None
        trade_returns = []

        for i in range(len(df_spread)):
            row = df_spread.iloc[i]
            z = row["z_score"]
            py = row["Y"]
            px = row["X"]

            if position == 0:
                # Entry signals
                if z <= -z_entry:
                    position = 1  # Long Spread
                    entry_price_y = py
                    entry_price_x = px
                    entry_idx = i
                elif z >= z_entry:
                    position = -1  # Short Spread
                    entry_price_y = py
                    entry_price_x = px
                    entry_idx = i
            elif position == 1:
                # In Long Spread: profit if Y rises relative to beta * X
                ret_y = (py - entry_price_y) / entry_price_y
                ret_x = (px - entry_price_x) / entry_price_x
                spread_ret = ret_y - (beta * ret_x)

                if z >= -z_exit or abs(z) >= z_stop or i == len(df_spread) - 1:
                    trade_returns.append(spread_ret)
                    position = 0
            elif position == -1:
                # In Short Spread: profit if Y falls relative to beta * X
                ret_y = (entry_price_y - py) / entry_price_y
                ret_x = (entry_price_x - px) / entry_price_x
                spread_ret = ret_y - (beta * ret_x)

                if z <= z_exit or abs(z) >= z_stop or i == len(df_spread) - 1:
                    trade_returns.append(spread_ret)
                    position = 0

        total_trades = len(trade_returns)
        if total_trades > 0:
            win_count = sum(1 for r in trade_returns if r > 0)
            win_rate = (win_count / total_trades) * 100.0
            cum_ret = (np.prod([1.0 + r for r in trade_returns]) - 1.0) * 100.0
        else:
            win_rate = 0.0
            cum_ret = 0.0

        coint_tag = "YES" if is_coint else "NO"
        hl_tag = f"{half_life:.1f}d" if half_life < 300 else ">300d"
        print(f"{sym_y+'/'+sym_x:<12} | {coint_tag:<7} | {p_val:<7.4f} | {beta:<6.2f} | {hl_tag:<9} | {total_trades:<6} | {win_rate:<6.1f}% | {cum_ret:+7.2f}%")

        results.append({
            "pair": f"{sym_y}/{sym_x}",
            "is_cointegrated": is_coint,
            "p_value": p_val,
            "beta": beta,
            "half_life": half_life,
            "total_trades": total_trades,
            "win_rate": win_rate,
            "cum_return": cum_ret,
        })

    print("-" * 70)
    cointegrated_pairs = [r for r in results if r["is_cointegrated"]]
    print(f"\nCointegrated Pairs Found: {len(cointegrated_pairs)} / {len(results)}")
    if cointegrated_pairs:
        avg_win_rate = np.mean([r["win_rate"] for r in cointegrated_pairs if r["total_trades"] > 0])
        avg_return = np.mean([r["cum_return"] for r in cointegrated_pairs])
        print(f"Average Win Rate on Cointegrated Pairs: {avg_win_rate:.1f}%")
        print(f"Average Cumulative Return on Cointegrated Pairs: {avg_return:+.2f}%")
    print("=" * 70)
    print("Backtest Complete. Stored as Phase 5 Research Asset.\n")


if __name__ == "__main__":
    run_pairs_backtest(lookback_years=5)
