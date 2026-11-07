"""
Institutional Baseline Diagnostic for NSE Nifty 50 (2007-09-17 to 2024-12-31)
=============================================================================
Evaluates:
  1. Baseline 1: Buy-and-Hold Nifty 50 TRI (Price + 1.35% Div Reinvestment)
  2. Baseline 2: Equal-Weight Nifty 50 Rebalanced Annually (Strict PIT Dated Membership)
  3. Baseline 3: Trend-Switch Nifty 50 > 200-SMA, Else Cash (Liquid ETF Net Yield)

Both Pre-Tax and Post-Tax metrics are computed under identical institutional costs:
  - Stressed Costs: 25.35 bps buy, 31.23 bps sell + flat Rs 14.75 DP fee per sale.
  - Statutory Indian Tax:
      * STCG (< 365 days): 15% pre-23 July 2024, 20% post-23 July 2024
      * LTCG (>= 365 days): 0% pre-1 April 2018, 10% 2018-2024, 12.5% post-23 July 2024
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

# Sourced Dhan schedule & statutory rates
FLAT_DP_FEE_RUPEES = 14.75
INITIAL_CAPITAL_INR = 80000.0  # ~$1,000 USD at ~80 INR/USD

BUY_COST_BPS = 25.35
SELL_COST_BPS = 31.23

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


def get_liquid_etf_yield(dt: pd.Timestamp) -> float:
    dates, _, liquid = _get_cash_yield_arrays()
    if len(dates) == 0:
        return 0.0425
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
    calmar = abs(cagr / max_dd) if abs(max_dd) > 1e-6 else 0.0

    daily_ret = equity_series.pct_change().dropna()
    sharpe = (daily_ret.mean() / (daily_ret.std() + 1e-9)) * math.sqrt(252)

    return {
        "label": label,
        "start_val": round(start_val, 2),
        "end_val": round(end_val, 2),
        "cagr_pct": round(cagr, 2),
        "total_return_pct": round(tot_return, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "calmar_ratio": round(calmar, 2),
        "sharpe_ratio": round(sharpe, 2),
        "years": round(years, 2),
    }


def compute_capital_gains_tax(entry_date, exit_date, gain):
    if gain <= 0:
        return 0.0
    holding_days = (pd.to_datetime(exit_date) - pd.to_datetime(entry_date)).days
    exit_dt = pd.to_datetime(exit_date)
    budget_2024_dt = pd.to_datetime("2024-07-23")
    ltcg_start_dt = pd.to_datetime("2018-04-01")

    if holding_days < 365:
        # STCG
        rate = 0.20 if exit_dt >= budget_2024_dt else 0.15
        return gain * rate
    else:
        # LTCG
        if exit_dt < ltcg_start_dt:
            return 0.0  # Exempt under Section 10(38)
        rate = 0.125 if exit_dt >= budget_2024_dt else 0.10
        return gain * rate


def main():
    print("=" * 85)
    print(">>> NSE NIFTY 50 AUDITED BASELINES (2007-09-17 TO 2024-12-31) <<<")
    print(f"Starting Capital: INR {INITIAL_CAPITAL_INR:,.0f} | Stressed Costs: {BUY_COST_BPS} buy / {SELL_COST_BPS} sell bps + Rs {FLAT_DP_FEE_RUPEES} DP fee")
    print("=" * 85)

    nsei_path = os.path.join(CACHE_DIR, "INDEX_NSEI.parquet")
    if not os.path.exists(nsei_path):
        print(f"Error: {nsei_path} missing.")
        return

    nsei_df = normalize_index(pd.read_parquet(nsei_path))
    nsei_sub = nsei_df.loc[START_DATE:END_DATE].copy()
    dates = list(nsei_sub.index)
    print(f"Sessions: {len(nsei_sub)} trading days from {dates[0].date()} to {dates[-1].date()}")

    nsei_close = nsei_sub["close"]

    # -------------------------------------------------------------------------
    # Baseline 1: Buy-and-Hold Nifty 50 TRI (Price + 1.35% Dividend Reinvestment)
    # -------------------------------------------------------------------------
    # Buy on Day 1 with buy costs
    b1_start_cash = INITIAL_CAPITAL_INR * (1.0 - BUY_COST_BPS / 10000.0)
    b1_shares = b1_start_cash / nsei_close.iloc[0]
    b1_pretax_list = []
    
    for dt, p in zip(dates, nsei_close):
        b1_shares *= (1.0 + 0.0135 / 252.0)
        b1_pretax_list.append(b1_shares * p)

    b1_pretax_series = pd.Series(b1_pretax_list, index=dates)
    m_b1_pre = compute_metrics(b1_pretax_series, "Baseline 1: Buy-and-Hold Nifty 50 TRI (Pre-Tax)")

    # Post-tax at termination (2024-12-31): sell with exit friction + LTCG tax
    final_p = nsei_close.iloc[-1]
    final_proceeds = b1_shares * final_p * (1.0 - SELL_COST_BPS / 10000.0) - FLAT_DP_FEE_RUPEES
    total_gain = final_proceeds - INITIAL_CAPITAL_INR
    tax_b1 = compute_capital_gains_tax(dates[0], dates[-1], total_gain)
    final_post_tax = final_proceeds - tax_b1
    
    b1_post_tax_list = b1_pretax_series.copy()
    b1_post_tax_list.iloc[-1] = final_post_tax
    m_b1_post = compute_metrics(b1_post_tax_list, "Baseline 1: Buy-and-Hold Nifty 50 TRI (Post-Tax)")

    # -------------------------------------------------------------------------
    # Baseline 3: Trend-Switch Nifty 50 > 200-SMA, Else Cash (Liquid ETF Net Yield)
    # -------------------------------------------------------------------------
    sma200 = nsei_close.rolling(200, min_periods=50).mean()
    above_200 = nsei_close > sma200

    for is_stressed, cost_label in [(True, "Post-Tax Stressed Costs")]:
        b3_cash = INITIAL_CAPITAL_INR
        b3_shares = 0.0
        b3_entry_date = None
        b3_entry_cost = 0.0
        b3_equity_list = []
        annual_stcg = 0.0
        annual_ltcg = 0.0

        for dt, close_p, is_above in zip(dates, nsei_close, above_200):
            daily_yield = get_liquid_etf_yield(dt) / 252.0
            
            if is_above:
                if b3_shares == 0.0 and b3_cash > 0:
                    # Buy ETF
                    buy_proceeds = b3_cash * (1.0 - BUY_COST_BPS / 10000.0)
                    b3_shares = buy_proceeds / close_p
                    b3_entry_cost = b3_cash
                    b3_entry_date = dt
                    b3_cash = 0.0
                b3_shares *= (1.0 + 0.0135 / 252.0)
                daily_val = b3_shares * close_p
            else:
                if b3_shares > 0:
                    # Sell ETF to cash
                    gross_sale = b3_shares * close_p
                    net_sale = gross_sale * (1.0 - SELL_COST_BPS / 10000.0) - FLAT_DP_FEE_RUPEES
                    gain = net_sale - b3_entry_cost
                    tax = compute_capital_gains_tax(b3_entry_date, dt, gain)
                    b3_cash = net_sale - tax
                    b3_shares = 0.0
                    b3_entry_date = None
                b3_cash *= (1.0 + daily_yield)
                daily_val = b3_cash

            b3_equity_list.append(daily_val)

        b3_post_tax_series = pd.Series(b3_equity_list, index=dates)
        m_b3_post = compute_metrics(b3_post_tax_series, f"Baseline 3: Trend-Switch > 200-SMA ({cost_label})")

    # -------------------------------------------------------------------------
    # Baseline 2: Equal-Weight Nifty 50 (Strict PIT Membership, Annual Rebalance)
    # -------------------------------------------------------------------------
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

    from trading_system.app.data.constituent_manager import PointInTimeConstituentManager
    nifty_changes_csv = os.path.join(PROJECT_ROOT, "trading_system", "data", "nifty50_historical_components_changes.csv")
    nifty_start_end_csv = os.path.join(PROJECT_ROOT, "trading_system", "data", "nifty50_ticker_start_end.csv")
    pit_mgr = PointInTimeConstituentManager(changes_csv_path=nifty_changes_csv, start_end_csv_path=nifty_start_end_csv)

    years_list = sorted(list(set(d.year for d in dates)))
    ew_cash = INITIAL_CAPITAL_INR
    ew_positions = {}  # sym -> {shares, entry_price, entry_date}
    ew_equity_list = []

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

        # Liquidate old portfolio at year start
        if ew_positions:
            for s, pos in list(ew_positions.items()):
                p = stock_dfs[s].loc[first_day] if first_day in stock_dfs[s].index else pos["entry_price"]
                gross = pos["shares"] * p
                net = gross * (1.0 - SELL_COST_BPS / 10000.0) - FLAT_DP_FEE_RUPEES
                gain = net - (pos["shares"] * pos["entry_price"])
                tax = compute_capital_gains_tax(pos["entry_date"], first_day, gain)
                ew_cash += (net - tax)
            ew_positions = {}

        # Rebalance equal dollar into eligible
        if eligible and ew_cash > 0:
            alloc_per_stock = ew_cash / len(eligible)
            for s in eligible:
                p = stock_dfs[s].loc[first_day]
                net_alloc = alloc_per_stock * (1.0 - BUY_COST_BPS / 10000.0)
                shares = net_alloc / p
                ew_positions[s] = {"shares": shares, "entry_price": p, "entry_date": first_day}
            ew_cash = 0.0

        for d in yr_dates:
            active_today = pit_mgr.get_active_constituents(d)
            # Liquidate removed mid-year
            for s in list(ew_positions.keys()):
                if PointInTimeConstituentManager.normalize_symbol(s) not in active_today:
                    pos = ew_positions.pop(s)
                    p = stock_dfs[s].loc[d] if d in stock_dfs[s].index else pos["entry_price"]
                    gross = pos["shares"] * p
                    net = gross * (1.0 - SELL_COST_BPS / 10000.0) - FLAT_DP_FEE_RUPEES
                    gain = net - (pos["shares"] * pos["entry_price"])
                    tax = compute_capital_gains_tax(pos["entry_date"], d, gain)
                    ew_cash += (net - tax)

            daily_val = ew_cash + sum(
                pos["shares"] * stock_dfs[s].loc[d]
                for s, pos in ew_positions.items()
                if d in stock_dfs[s].index and not math.isnan(stock_dfs[s].loc[d])
            )
            ew_equity_list.append(daily_val)

    ew_post_tax_series = pd.Series(ew_equity_list, index=dates[:len(ew_equity_list)])
    m_b2_post = compute_metrics(ew_post_tax_series, "Baseline 2: Equal-Weight Nifty 50 (PIT Rebalanced Yearly, Post-Tax)")

    print("\n" + "=" * 85)
    print(f"{'STRATEGY / BASELINE':<45} | {'CAGR (%)':<9} | {'MaxDD (%)':<10} | {'Calmar':<7} | {'Sharpe':<7}")
    print("-" * 85)
    for m in [m_b1_pre, m_b1_post, m_b2_post, m_b3_post]:
        print(f"{m['label']:<45} | {m['cagr_pct']:>8.2f}% | {m['max_drawdown_pct']:>9.2f}% | {m['calmar_ratio']:>7.2f} | {m['sharpe_ratio']:>7.2f}")
    print("=" * 85)


if __name__ == "__main__":
    main()
