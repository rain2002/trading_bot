"""
US S&P 500 Point-in-Time 12-1 Momentum Decile Spread (D10 - D1) Analysis (2007 - 2024)
======================================================================================
Evaluates whether stock-level 12-1 price momentum delivers persistent, positive long-short alpha
on the US S&P 500 Point-in-Time universe across 2007-2024 (including the 2008 GFC crash).

Decision Gate Protocol (Gate A):
  - Decile 10 (highest momentum) vs Decile 1 (lowest momentum) long-short spread.
  - If the rolling 3-year (36-month) spread is NOT consistently positive (>= 75% positive windows),
    stock-level momentum long-short is officially rejected across all geographies.
    Strategy S3 (ETF spread) becomes the sole remaining market-neutral candidate.
  - If positive across rolling 3-year windows, Strategy S1 (US Equity Momentum L/S) is pre-registered.

Methodology:
  1. Universe: Active S&P 500 Point-in-Time constituents at each monthly rebalance from sp500_ticker_start_end.csv.
  2. Pricing: Corporate-action adjusted close prices (splits + dividends reinvested).
  3. Metric: 12-1 Momentum = (Close[t-21] / Close[t-252]) - 1.0.
  4. Deciles: Sorted into 10 equal buckets (D1 to D10).
  5. Forward Return: 1-month forward holding period from month-end t to month-end t+1.
  6. Rolling Windows: 36 consecutive monthly forward periods per window.
"""

import os
import sys
import time
import math
import numpy as np
import pandas as pd
import yfinance as yf
from typing import Dict, List, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from trading_system.app.validation.trial_logger import log_trial

DATA_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data")
CACHE_FILE = os.path.join(DATA_DIR, "us_sp500_close_panel.parquet")
OUTPUT_DECILES_CSV = os.path.join(DATA_DIR, "us_sp500_momentum_decile_returns.csv")
OUTPUT_ROLLING_CSV = os.path.join(DATA_DIR, "us_sp500_momentum_rolling_3y_spread.csv")

START_DATE = "2006-01-01"  # Needs 252 trading days before 2007-09-24
EVAL_START = "2007-09-24"
EVAL_END = "2024-07-05"


def load_pit_universe() -> pd.DataFrame:
    """Load S&P 500 point-in-time constituent start/end dates."""
    p_intervals = os.path.join(DATA_DIR, "sp500_ticker_start_end.csv")
    df_int = pd.read_csv(p_intervals)
    df_int["ticker_clean"] = df_int["ticker"].str.replace(".", "-", regex=False)
    df_int["start_date"] = pd.to_datetime(df_int["start_date"])
    df_int["end_date"] = pd.to_datetime(df_int["end_date"]).fillna(pd.Timestamp("2099-12-31"))
    return df_int


def get_active_constituents(df_int: pd.DataFrame, dt: pd.Timestamp) -> List[str]:
    """Return all active S&P 500 constituent tickers on a given date."""
    active = df_int[(df_int["start_date"] <= dt) & (df_int["end_date"] > dt)]["ticker_clean"].unique()
    return sorted(list(active))


def get_or_download_us_price_panel(df_int: pd.DataFrame) -> pd.DataFrame:
    """Load cached US price panel or download all active tickers via yfinance."""
    if os.path.exists(CACHE_FILE):
        print(f"[1/4] Loading cached US S&P 500 price panel from {CACHE_FILE}...", flush=True)
        df_close = pd.read_parquet(CACHE_FILE)
        df_close.index = pd.to_datetime(df_close.index)
        return df_close

    print(f"[1/4] Downloading historical prices for S&P 500 Point-in-Time constituents...", flush=True)
    # Identify all tickers active between EVAL_START and EVAL_END
    sub = df_int[(df_int["start_date"] <= EVAL_END) & (df_int["end_date"] >= EVAL_START)]
    tickers = sorted(list(sub["ticker_clean"].unique()))
    print(f"  Total historical constituents active in 2007-2024: {len(tickers)} tickers", flush=True)

    t0 = time.time()
    data = yf.download(
        tickers,
        start=START_DATE,
        end="2024-07-10",
        auto_adjust=True,
        progress=False,
        threads=True
    )
    df_close = data["Close"].dropna(how="all", axis=1)
    df_close.index = pd.to_datetime(df_close.index)
    if df_close.index.tz is not None:
        df_close.index = df_close.index.tz_localize(None)

    print(f"  Successfully fetched prices for {df_close.shape[1]}/{len(tickers)} tickers in {time.time()-t0:.2f}s", flush=True)
    df_close.to_parquet(CACHE_FILE)
    print(f"  Saved price panel to {CACHE_FILE}", flush=True)
    return df_close


def run_us_decile_spread_analysis():
    print("=" * 85)
    print(">>> US S&P 500 POINT-IN-TIME 12-1 MOMENTUM DECILE SPREAD (D10 - D1) ANALYSIS <<<")
    print(f">>> Evaluation Window: {EVAL_START} to {EVAL_END} (2008 Crash Included) <<<")
    print("=" * 85)

    df_int = load_pit_universe()
    df_close = get_or_download_us_price_panel(df_int)

    all_dates = df_close.index.sort_values()
    eval_dates = all_dates[(all_dates >= EVAL_START) & (all_dates <= EVAL_END)]

    # Month-end rebalance dates
    df_monthly = pd.Series(eval_dates, index=eval_dates).resample("ME").last().dropna()
    rebal_dates = sorted(list(df_monthly.values))
    print(f"\n[2/4] Aligned Timeline: {len(eval_dates)} trading days, {len(rebal_dates)} monthly rebalance dates.", flush=True)

    records = []
    coverage_stats = []

    for i in range(len(rebal_dates) - 1):
        t_now = pd.to_datetime(rebal_dates[i])
        t_next = pd.to_datetime(rebal_dates[i + 1])

        active_syms = get_active_constituents(df_int, t_now)
        n_active = len(active_syms)

        hist_dates = all_dates[all_dates <= t_now]
        if len(hist_dates) < 252:
            continue

        dt_252 = hist_dates[-252]
        dt_21 = hist_dates[-21]

        mom_scores = {}
        fwd_returns = {}

        for sym in active_syms:
            if sym not in df_close.columns:
                continue
            s_series = df_close[sym].dropna()
            if dt_252 in s_series.index and dt_21 in s_series.index:
                p_start = s_series.loc[dt_252]
                p_lag = s_series.loc[dt_21]
                if p_start > 0 and p_lag > 0:
                    mom_scores[sym] = (p_lag / p_start) - 1.0

            if t_now in s_series.index and t_next in s_series.index:
                p_now = s_series.loc[t_now]
                p_fwd = s_series.loc[t_next]
                if p_now > 0 and p_fwd > 0:
                    fwd_returns[sym] = (p_fwd / p_now) - 1.0

        eligible = [s for s in mom_scores if s in fwd_returns]
        cov_pct = len(eligible) / n_active if n_active > 0 else 0.0
        coverage_stats.append(cov_pct)

        if len(eligible) < 50:
            continue

        # Sort by 12-1 momentum score
        eligible_sorted = sorted(eligible, key=lambda s: mom_scores[s])
        n = len(eligible_sorted)

        decile_returns = {}
        decile_size = n / 10.0

        for d in range(10):
            start_idx = int(round(d * decile_size))
            end_idx = int(round((d + 1) * decile_size))
            decile_syms = eligible_sorted[start_idx:end_idx]
            d_ret = np.mean([fwd_returns[s] for s in decile_syms]) if decile_syms else 0.0
            decile_returns[f"D{d + 1}"] = d_ret

        spread = decile_returns["D10"] - decile_returns["D1"]
        mkt_ret = np.mean([fwd_returns[s] for s in eligible_sorted])

        row = {
            "rebal_date": t_now.strftime("%Y-%m-%d"),
            "fwd_date": t_next.strftime("%Y-%m-%d"),
            "n_active": n_active,
            "n_eligible": n,
            "coverage_pct": round(cov_pct * 100.0, 1),
            "market_ret": mkt_ret,
            "spread_D10_minus_D1": spread
        }
        row.update(decile_returns)
        records.append(row)

    df_res = pd.DataFrame(records)
    print(f"\n[3/4] Evaluated {len(df_res)} consecutive monthly rebalances.")
    print(f"  Average active constituent coverage: {np.mean(coverage_stats) * 100:.1f}%")
    print(f"  Average eligible stocks per month:   {df_res['n_eligible'].mean():.1f} (min: {df_res['n_eligible'].min()})")

    # Decile Summary Table
    print("\n" + "=" * 65)
    print(">>> S&P 500 12-1 MOMENTUM DECILE RETURNS (2007 - 2024) <<<")
    print("=" * 65)
    summary_data = []
    for d in range(1, 11):
        col = f"D{d}"
        m_mean = df_res[col].mean()
        m_vol = df_res[col].std()
        cum_ret = np.prod(1.0 + df_res[col])
        years = len(df_res) / 12.0
        cagr = cum_ret ** (1.0 / years) - 1.0
        ann_vol = m_vol * np.sqrt(12)
        sharpe = (cagr - 0.02) / ann_vol if ann_vol > 0 else 0.0
        summary_data.append({
            "Decile": f"D{d}{' (Losers)' if d==1 else (' (Winners)' if d==10 else '')}",
            "Monthly Mean": f"{m_mean * 100:+.2f}%",
            "CAGR": f"{cagr * 100:+.2f}%",
            "Ann Vol": f"{ann_vol * 100:.2f}%",
            "Sharpe (rf=2%)": f"{sharpe:.2f}"
        })
    print(pd.DataFrame(summary_data).to_string(index=False))

    # Long-Short Spread (D10 - D1) Metrics
    spr = df_res["spread_D10_minus_D1"]
    spr_mean = spr.mean()
    spr_vol = spr.std()
    cum_spr = np.prod(1.0 + spr)
    years = len(df_res) / 12.0
    spr_cagr = cum_spr ** (1.0 / years) - 1.0
    spr_ann_vol = spr_vol * np.sqrt(12)
    spr_sharpe = spr_cagr / spr_ann_vol if spr_ann_vol > 0 else 0.0
    win_rate = (spr > 0).mean() * 100.0

    print("\n" + "=" * 65)
    print(">>> S&P 500 LONG-SHORT SPREAD (D10 - D1) LIFETIME METRICS <<<")
    print("=" * 65)
    print(f"Monthly Mean Spread:       {spr_mean * 100:+.2f}%")
    print(f"CAGR Spread Return:        {spr_cagr * 100:+.2f}%")
    print(f"Annualized Spread Vol:     {spr_ann_vol * 100:.2f}%")
    print(f"Spread Sharpe Ratio:       {spr_sharpe:.2f}")
    print(f"Positive Month Hit Rate:   {win_rate:.1f}% ({int((spr > 0).sum())}/{len(spr)} months)")

    # Rolling 3-Year (36-Month) Windows
    print("\n" + "=" * 65)
    print(">>> ROLLING 3-YEAR (36-MONTH) SPREAD WINDOWS (GATE A) <<<")
    print("=" * 65)
    rolling_3y = []
    for i in range(len(df_res) - 35):
        w = df_res.iloc[i : i + 36]
        w_start = w["rebal_date"].iloc[0]
        w_end = w["fwd_date"].iloc[-1]
        cum_w = np.prod(1.0 + w["spread_D10_minus_D1"]) - 1.0
        ann_w = (1.0 + cum_w) ** (1.0 / 3.0) - 1.0
        rolling_3y.append({
            "start": w_start,
            "end": w_end,
            "3y_cum_spread": cum_w,
            "3y_ann_spread": ann_w
        })

    df_roll = pd.DataFrame(rolling_3y)
    pos_roll = (df_roll["3y_ann_spread"] > 0).mean() * 100.0
    min_roll = df_roll["3y_ann_spread"].min() * 100.0
    max_roll = df_roll["3y_ann_spread"].max() * 100.0
    mean_roll = df_roll["3y_ann_spread"].mean() * 100.0
    median_roll = df_roll["3y_ann_spread"].median() * 100.0

    print(f"Total 36-Month Rolling Windows:  {len(df_roll)}")
    print(f"Positive 3Y Windows:             {pos_roll:.1f}% ({int((df_roll['3y_ann_spread'] > 0).sum())}/{len(df_roll)})")
    print(f"Mean 3Y Annualized Spread:       {mean_roll:+.2f}%")
    print(f"Median 3Y Annualized Spread:     {median_roll:+.2f}%")
    print(f"Worst 3Y Window Spread:          {min_roll:+.2f}%")
    print(f"Best 3Y Window Spread:           {max_roll:+.2f}%")

    # Gate Decision Evaluation
    gate_passed = pos_roll >= 75.0 and spr_cagr > 0.0
    print("\n" + "=" * 65)
    if gate_passed:
        print(">>> DECISION GATE A: PASSED <<<")
        print("  US S&P 500 12-1 Momentum Decile Spread demonstrates persistent positive alpha.")
        print("  Strategy S1 (US Equity Momentum Long-Short) is ELIGIBLE for pre-registration.")
    else:
        print(">>> DECISION GATE A: FAILED <<<")
        print(f"  US S&P 500 Decile Spread failed persistence threshold (Positive Windows: {pos_roll:.1f}% < 75%).")
        print("  STOCK-LEVEL MOMENTUM LONG-SHORT IS PERMANENTLY DROPPED.")
        print("  Mandate shifts exclusively to Strategy S3 (Multi-Asset ETF Spread) & Core Rotation.")
    print("=" * 65 + "\n")

    # Save output CSVs
    df_res.to_csv(OUTPUT_DECILES_CSV, index=False)
    df_roll.to_csv(OUTPUT_ROLLING_CSV, index=False)
    print(f"Saved decile returns to: {OUTPUT_DECILES_CSV}")
    print(f"Saved rolling 3Y windows to: {OUTPUT_ROLLING_CSV}")

    # Compute spread max drawdown
    cum_spr_series = np.cumprod(1.0 + spr)
    peaks = np.maximum.accumulate(cum_spr_series)
    dds = (cum_spr_series - peaks) / peaks
    spr_max_dd = np.min(dds) * 100.0

    # Log trial stamped with commit hash
    log_trial(
        cagr_pct=round(spr_cagr * 100.0, 2),
        max_drawdown_pct=round(spr_max_dd, 2),
        sharpe_ratio=round(spr_sharpe, 2),
        kelly_fraction=1.0,
        lookback_days=252,
        script="analyze_us_sp500_momentum_decile_spread.py",
        universe="US_SP500_PIT_DECILE_SPREAD",
        notes=f"12-1 Momentum Decile Spread (D10 - D1 Long-Short on US S&P 500 PIT). Rolling 3Y positive in {pos_roll:.1f}% of windows (Mean {mean_roll:+.2f}%). Gate A {'PASSED' if gate_passed else 'FAILED'}."
    )

    return {
        "d10_cagr": cagr,
        "spread_cagr": spr_cagr,
        "spread_vol": spr_ann_vol,
        "spread_sharpe": spr_sharpe,
        "win_rate": win_rate,
        "pos_3y_pct": pos_roll,
        "gate_passed": gate_passed
    }


if __name__ == "__main__":
    run_us_decile_spread_analysis()
