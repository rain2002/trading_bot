"""
Diagnostic and Baseline Evaluation for NSE Nifty 50 (2007 - 2024 In-Sample)
=============================================================================
Evaluates:
  1. Baseline 1: Buy-and-Hold Nifty 50 TRI
  2. Baseline 2: Equal-Weight Nifty 50 Rebalanced Yearly
  3. Baseline 3: Nifty 50 > 200-SMA, Else Cash (with RBI Repo Cash Yield)
  4. Diagnostic on Strategy: Days in cash %, average exposure %, trades/year, costs paid,
     and impact of cash yield (0% vs RBI Repo).
"""

import os
import sys
import math
import glob
import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

CACHE_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data", "historical_cache_nse")
INDIA_CASH_YIELD_CSV = os.path.join(PROJECT_ROOT, "trading_system", "data", "india_cash_yield_history.csv")

START_DATE = "2007-09-17"
END_DATE = "2024-12-31"  # Sealed holdout 2025 preserved

_CASH_YIELD_CACHE = None


def _get_cash_yield_arrays():
    global _CASH_YIELD_CACHE
    if _CASH_YIELD_CACHE is None:
        if os.path.exists(INDIA_CASH_YIELD_CSV):
            df = pd.read_csv(INDIA_CASH_YIELD_CSV)
            dates = pd.to_datetime(df["effective_date"]).values
            repo = df["rbi_repo_rate"].astype(float).values
            liquid = df["liquid_etf_net_yield"].astype(float).values
            _CASH_YIELD_CACHE = (dates, repo, liquid)
        else:
            _CASH_YIELD_CACHE = (np.array([]), np.array([]), np.array([]))
    return _CASH_YIELD_CACHE


def get_repo_rate(dt: pd.Timestamp) -> float:
    """Historical Reserve Bank of India Repo Rate sourced from india_cash_yield_history.csv."""
    dates, repo, _ = _get_cash_yield_arrays()
    if len(dates) == 0:
        return 0.065
    dt_val = np.datetime64(pd.to_datetime(dt).strftime("%Y-%m-%d"))
    idx = np.searchsorted(dates, dt_val, side="right") - 1
    if idx < 0:
        return float(repo[0])
    return float(repo[idx])


def get_liquid_etf_yield(dt: pd.Timestamp) -> float:
    """Realistic retail Liquid ETF yield net of ~65 bps total expense ratio, sourced from india_cash_yield_history.csv."""
    dates, _, liquid = _get_cash_yield_arrays()
    if len(dates) == 0:
        return max(0.0, get_repo_rate(dt) - 0.0065)
    dt_val = np.datetime64(pd.to_datetime(dt).strftime("%Y-%m-%d"))
    idx = np.searchsorted(dates, dt_val, side="right") - 1
    if idx < 0:
        return float(liquid[0])
    return float(liquid[idx])


def normalize_index(df: pd.DataFrame) -> pd.DataFrame:
    df.index = [d.tz_localize(None) if hasattr(d, "tz") and d.tz is not None else d for d in df.index]
    return df.sort_index()


def compute_metrics(equity_series: pd.Series, label: str) -> dict:
    start_val = equity_series.iloc[0]
    end_val = equity_series.iloc[-1]
    years = (equity_series.index[-1] - equity_series.index[0]).days / 365.25
    cagr = ((end_val / start_val) ** (1.0 / years) - 1.0) * 100.0
    tot_return = ((end_val / start_val) - 1.0) * 100.0

    cummax = equity_series.cummax()
    drawdowns = (equity_series - cummax) / cummax
    max_dd = drawdowns.min() * 100.0

    daily_ret = equity_series.pct_change().dropna()
    sharpe = (daily_ret.mean() / (daily_ret.std() + 1e-9)) * math.sqrt(252)

    return {
        "label": label,
        "start_val": round(start_val, 2),
        "end_val": round(end_val, 2),
        "cagr_pct": round(cagr, 2),
        "total_return_pct": round(tot_return, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe_ratio": round(sharpe, 2),
        "years": round(years, 2),
    }


def main():
    print("=" * 80)
    print(">>> NSE NIFTY 50 BASELINES & CAUSE DIAGNOSTIC (2007 - 2024 IN-SAMPLE) <<<")
    print("=" * 80)

    # 1. Load official ^NSEI benchmark
    nsei_path = os.path.join(CACHE_DIR, "INDEX_NSEI.parquet")
    if not os.path.exists(nsei_path):
        print(f"Error: {nsei_path} missing. Run cache_historical_nse.py first.")
        return

    nsei_df = normalize_index(pd.read_parquet(nsei_path))
    nsei_sub = nsei_df.loc[START_DATE:END_DATE].copy()
    dates = list(nsei_sub.index)
    print(f"Loaded official ^NSEI series: {len(nsei_sub)} sessions from {dates[0].date()} to {dates[-1].date()}")

    # -------------------------------------------------------------------------
    # Baseline 1: Buy-and-Hold Nifty 50 TRI (Dividends Reinvested @ 1.35% avg)
    # -------------------------------------------------------------------------
    nsei_close = nsei_sub["close"]
    nsei_daily_ret = nsei_close.pct_change().fillna(0.0)

    # Nifty 50 TRI adds daily dividend yield (~1.35% / 252)
    tri_daily_ret = nsei_daily_ret + (0.0135 / 252.0)
    b1_equity = 1000.0 * (1.0 + tri_daily_ret).cumprod()
    m_b1 = compute_metrics(b1_equity, "Baseline 1: Approx Nifty 50 TRI (Price + 1.35% Dividend Reinvestment)")

    # Pure Price Return (^NSEI)
    pr_equity = 1000.0 * (1.0 + nsei_daily_ret).cumprod()
    m_pr = compute_metrics(pr_equity, "Benchmark Ref: Nifty 50 Price Index (^NSEI)")

    # -------------------------------------------------------------------------
    # Baseline 3: Nifty 50 > 200-SMA, Else Cash (earning RBI repo yield)
    # -------------------------------------------------------------------------
    sma200 = nsei_close.rolling(200, min_periods=50).mean()
    above_200 = nsei_close > sma200

    b3_cash = 1000.0
    b3_shares = 0.0
    b3_equity_list = []
    b3_days_in_cash = 0

    for dt, close_p, is_above in zip(dates, nsei_close, above_200):
        daily_yield = get_liquid_etf_yield(dt) / 252.0
        if is_above:
            # Invested in Nifty TRI
            if b3_shares == 0.0 and b3_cash > 0:
                b3_shares = b3_cash / close_p
                b3_cash = 0.0
            # Accrue dividend yield into shares
            b3_shares *= (1.0 + 0.0135 / 252.0)
            daily_eq = b3_shares * close_p
        else:
            # Sells to cash earning Liquid ETF net yield
            b3_days_in_cash += 1
            if b3_shares > 0:
                b3_cash = b3_shares * close_p
                b3_shares = 0.0
            b3_cash *= (1.0 + daily_yield)
            daily_eq = b3_cash

        b3_equity_list.append(daily_eq)

    b3_equity = pd.Series(b3_equity_list, index=dates)
    m_b3 = compute_metrics(b3_equity, "Baseline 3: Nifty 50 > 200-SMA, Else Cash (Liquid ETF Net Yield)")

    # Also calculate Baseline 3 with 0% cash yield to show cash yield impact!
    b3_zero_cash = 1000.0
    b3_zero_shares = 0.0
    b3_zero_eq_list = []
    for dt, close_p, is_above in zip(dates, nsei_close, above_200):
        if is_above:
            if b3_zero_shares == 0.0 and b3_zero_cash > 0:
                b3_zero_shares = b3_zero_cash / close_p
                b3_zero_cash = 0.0
            b3_zero_shares *= (1.0 + 0.0135 / 252.0)
            daily_eq = b3_zero_shares * close_p
        else:
            if b3_zero_shares > 0:
                b3_zero_cash = b3_zero_shares * close_p
                b3_zero_shares = 0.0
            # 0% cash yield
            daily_eq = b3_zero_cash
        b3_zero_eq_list.append(daily_eq)
    b3_zero_equity = pd.Series(b3_zero_eq_list, index=dates)
    m_b3_zero = compute_metrics(b3_zero_equity, "Baseline 3b: Nifty 50 > 200-SMA, Else Cash (0% Yield)")

    # -------------------------------------------------------------------------
    # Baseline 2: Equal-Weight Nifty 50 (Rebalanced Annually)
    # -------------------------------------------------------------------------
    # Load available stock parquets
    stock_files = glob.glob(os.path.join(CACHE_DIR, "*-NS.parquet"))
    stock_dfs = {}
    for f in stock_files:
        sym = os.path.basename(f).replace("-NS.parquet", ".NS")
        try:
            df = normalize_index(pd.read_parquet(f))
            if len(df) > 200:
                stock_dfs[sym] = df["adj_close"]
        except Exception:
            pass

    print(f"Loaded {len(stock_dfs)} stock series for Equal-Weight baseline evaluation.")

    from trading_system.app.data.constituent_manager import PointInTimeConstituentManager
    nifty_changes_csv = os.path.join(PROJECT_ROOT, "trading_system", "data", "nifty50_historical_components_changes.csv")
    nifty_start_end_csv = os.path.join(PROJECT_ROOT, "trading_system", "data", "nifty50_ticker_start_end.csv")
    pit_mgr = PointInTimeConstituentManager(changes_csv_path=nifty_changes_csv, start_end_csv_path=nifty_start_end_csv)

    # Equal-weight yearly rebalancing simulation with strict PIT dated constituents
    years_list = sorted(list(set(d.year for d in dates)))
    ew_equity_list = []
    current_portfolio = {}
    ew_cash = 1000.0

    for yr in years_list:
        yr_dates = [d for d in dates if d.year == yr]
        if not yr_dates:
            continue
        first_day = yr_dates[0]

        # Select stocks that were actual Nifty 50 members on first_day
        eligible = [
            s for s, s_series in stock_dfs.items()
            if pit_mgr.is_constituent(s, first_day) and first_day in s_series.index and not math.isnan(s_series.loc[first_day]) and s_series.loc[first_day] > 0
        ]

        # Rebalance: buy equal dollar of each eligible
        alloc_per_stock = ew_cash / len(eligible) if eligible else 0.0
        current_portfolio = {s: alloc_per_stock / stock_dfs[s].loc[first_day] for s in eligible}
        ew_cash = 0.0

        for d in yr_dates:
            # Liquidate stocks removed from index mid-year
            active_today = pit_mgr.get_active_constituents(d)
            for s in list(current_portfolio.keys()):
                if PointInTimeConstituentManager.normalize_symbol(s) not in active_today:
                    shares = current_portfolio.pop(s)
                    if d in stock_dfs[s].index:
                        ew_cash += shares * stock_dfs[s].loc[d]

            daily_val = sum(shares * stock_dfs[s].loc[d] for s, shares in current_portfolio.items() if d in stock_dfs[s].index and not math.isnan(stock_dfs[s].loc[d]))
            ew_equity_list.append(daily_val + ew_cash)

        # End of year value becomes cash for next year
        ew_cash = ew_equity_list[-1]
        current_portfolio = {}

    ew_equity = pd.Series(ew_equity_list, index=dates[:len(ew_equity_list)])
    m_b2 = compute_metrics(ew_equity, "Baseline 2: Equal-Weight Nifty 50 (PIT Dated Membership)")

    # -------------------------------------------------------------------------
    # Diagnostic on Momentum Strategy: Days in cash %, Exposure, Friction
    # -------------------------------------------------------------------------
    # Run the current strategy logic and collect telemetry
    from trading_system.scripts.backtest_nse50 import load_market_data, run_simulation

    bench_df, macro_bull, precalc, timeline = load_market_data()
    # Filter timeline to in-sample (2007-09-17 to 2024-12-31)
    sub_timeline = [d for d in timeline if pd.to_datetime(START_DATE) <= d <= pd.to_datetime(END_DATE)]

    # Run 1: Zero Cash Yield
    strat_zero = run_simulation(
        bench_df=bench_df,
        macro_bull=macro_bull,
        precalc=precalc,
        timeline=sub_timeline,
        slippage_bps=5.0,
        cash_mode="ZERO",
        label="Momentum Strategy (0.0% Cash Yield)"
    )

    # Run 2: T-Bills / RBI Repo Cash Yield
    strat_rf = run_simulation(
        bench_df=bench_df,
        macro_bull=macro_bull,
        precalc=precalc,
        timeline=sub_timeline,
        slippage_bps=5.0,
        cash_mode="LIQUID_BEES",
        label="Momentum Strategy (Liquid ETF Net Yield)"
    )

    # Parse equity curve telemetry for strat_zero
    zero_eq_series = strat_zero["equity_series"]
    zero_cash_series = strat_zero["cash_series"]
    zero_stock_series = strat_zero["stock_series"]

    days_100pct_cash = sum(zero_stock_series == 0.0)
    pct_days_in_cash = (days_100pct_cash / len(zero_eq_series)) * 100.0
    avg_exposure_pct = ((zero_stock_series / zero_eq_series).mean()) * 100.0
    trades_count = len(strat_zero["trade_log"])
    trades_per_year = trades_count / m_b1["years"]

    m_strat_zero = compute_metrics(zero_eq_series, "Current Momentum Strategy (0% Cash Yield)")

    rf_eq_series = strat_rf["equity_series"]
    m_strat_rf = compute_metrics(rf_eq_series, "Current Momentum Strategy (Liquid ETF Net Yield)")

    # -------------------------------------------------------------------------
    # PRINT AUDIT RESULTS & DIAGNOSTIC TABLE
    # -------------------------------------------------------------------------
    results = [m_pr, m_b1, m_b2, m_b3, m_b3_zero, m_strat_zero, m_strat_rf]

    print("\n" + "=" * 115)
    print("                  NSE NIFTY 50 BASELINES & STRATEGY COMPARISON (2007 - 2024 IN-SAMPLE)")
    print("=" * 115)
    print(f"{'Performance Metric':<45} | {'CAGR (%)':<10} | {'Total Ret':<12} | {'Max DD (%)':<12} | {'Sharpe':<8} | {'Terminal ($)':<12}")
    print("-" * 115)
    for r in results:
        print(f"{r['label']:<45} | {r['cagr_pct']:>8.2f}% | {r['total_return_pct']:>10.2f}% | {r['max_drawdown_pct']:>10.2f}% | {r['sharpe_ratio']:>6.2f} | ${r['end_val']:>10.2f}")
    print("=" * 115)

    print("\n" + "=" * 80)
    print(">>> ROOT CAUSE DIAGNOSTIC: WHY DID THE INITIAL STRATEGY PRODUCE 0.5% - 3.7% CAGR? <<<")
    print("=" * 80)
    print(f"1. Total In-Sample Sessions Evaluated : {len(sub_timeline)} trading days ({m_b1['years']} years)")
    print(f"2. Days Spent 100% in Idle Cash       : {days_100pct_cash} days ({pct_days_in_cash:.1f}% of entire history)")
    print(f"3. Average Portfolio Equity Exposure   : {avg_exposure_pct:.1f}% (over half the time capital was NOT in stocks)")
    print(f"4. Total Trades Executed               : {trades_count} trades ({trades_per_year:.1f} trades/year)")
    print(f"5. Total Dividends Collected           : ${strat_zero['total_dividends']:.2f}")
    print(f"6. Total Interest (0% mode)            : ${strat_zero['total_interest']:.2f} (Idle cash earned ZERO)")
    print(f"7. Total Interest (Liquid ETF mode)     : ${strat_rf['total_interest']:.2f}")
    print(f"8. CAGR Impact of Cash Yield           : +{m_strat_rf['cagr_pct'] - m_strat_zero['cagr_pct']:.2f}% CAGR purely from fixing 0% cash yield")
    print("=" * 80 + "\n")

    # Save summary json
    summary_path = os.path.join(PROJECT_ROOT, "trading_system", "data", "nse_baselines_diagnostic.json")
    with open(summary_path, "w", encoding="utf-8") as jf:
        import json
        json.dump({
            "baselines": results,
            "diagnostic": {
                "total_days": len(sub_timeline),
                "days_in_cash_pct": pct_days_in_cash,
                "avg_exposure_pct": avg_exposure_pct,
                "total_trades": trades_count,
                "trades_per_year": trades_per_year,
                "total_divs": strat_zero["total_dividends"],
                "interest_zero": strat_zero["total_interest"],
                "interest_rf": strat_rf["total_interest"]
            }
        }, jf, indent=2)
    print(f"[OK] Full diagnostic report exported to: {summary_path}")


if __name__ == "__main__":
    main()
