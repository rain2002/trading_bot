"""
Momentum Decile Spread (D10 - D1) Analysis on Point-in-Time Nifty 100
====================================================================
Evaluates whether 12-1 price momentum delivers persistent, positive long-short alpha
on the survivorship-bias-free Point-in-Time Nifty 100 universe across 2007-2024.

Decision Rule mandated by research protocol:
  - If rolling 3-year (36-month) decile spread (D10 - D1) is NOT positive,
    stock selection must be dropped empirically.
  - If rolling 3-year spread is consistently positive, Variant S1 gets pre-registered.
"""

import os
import sys
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data")


def load_data():
    # 1. Load adjusted close prices panel
    p_close = os.path.join(DATA_DIR, "causal_panel_close.parquet")
    df_close = pd.read_parquet(p_close)
    df_close.index = pd.to_datetime(df_close.index)

    # 2. Load PIT Nifty 100 membership intervals
    p_intervals = os.path.join(DATA_DIR, "nifty100_ticker_start_end.csv")
    df_int = pd.read_csv(p_intervals)
    df_int["ticker_clean"] = df_int["ticker"].str.replace(".NS", "", regex=False)
    df_int["start_date"] = pd.to_datetime(df_int["start_date"])
    df_int["end_date"] = pd.to_datetime(df_int["end_date"]).fillna(pd.Timestamp("2099-12-31"))

    return df_close, df_int


def get_active_constituents(df_int: pd.DataFrame, dt: pd.Timestamp) -> List[str]:
    active = df_int[(df_int["start_date"] <= dt) & (df_int["end_date"] > dt)]["ticker_clean"].unique()
    return sorted(list(active))


def run_decile_analysis():
    print("=" * 80)
    print(">>> 12-1 MOMENTUM DECILE SPREAD (D10 - D1) ANALYSIS: NIFTY 100 PIT <<<")
    print("=" * 80)

    df_close, df_int = load_data()

    # Evaluation window: 2007-09-24 to 2024-07-05
    all_dates = df_close.index.sort_values()
    eval_dates = all_dates[(all_dates >= "2007-09-24") & (all_dates <= "2024-07-05")]

    # Find monthly rebalancing dates (last trading day of each month)
    df_monthly_dates = pd.Series(eval_dates, index=eval_dates).resample("ME").last().dropna()
    rebal_dates = sorted(list(df_monthly_dates.values))
    print(f"Total monthly rebalance periods: {len(rebal_dates)} months ({pd.to_datetime(rebal_dates[0]).strftime('%Y-%m-%d')} to {pd.to_datetime(rebal_dates[-1]).strftime('%Y-%m-%d')})\n")

    records = []

    # Iterate through monthly rebalancing periods
    for i in range(len(rebal_dates) - 1):
        t_now = pd.to_datetime(rebal_dates[i])
        t_next = pd.to_datetime(rebal_dates[i + 1])

        # Active Nifty 100 members at t_now
        active_syms = get_active_constituents(df_int, t_now)
        # Filter for symbols present in price panel
        valid_syms = [s for s in active_syms if s in df_close.columns]

        # Calculate 12-1 momentum for each symbol
        # Lookback: 252 trading days ago to 21 trading days ago
        hist_dates = all_dates[all_dates <= t_now]
        if len(hist_dates) < 252:
            continue

        dt_252 = hist_dates[-252]
        dt_21 = hist_dates[-21]

        mom_scores = {}
        fwd_returns = {}

        for sym in valid_syms:
            s_series = df_close[sym].dropna()
            if dt_252 in s_series.index and dt_21 in s_series.index:
                p_start = s_series.loc[dt_252]
                p_lag = s_series.loc[dt_21]
                if p_start > 0 and p_lag > 0:
                    mom_12_1 = (p_lag / p_start) - 1.0
                    mom_scores[sym] = mom_12_1

            # Forward return from t_now to t_next
            if t_now in s_series.index and t_next in s_series.index:
                p_now = s_series.loc[t_now]
                p_fwd = s_series.loc[t_next]
                if p_now > 0 and p_fwd > 0:
                    fwd_returns[sym] = (p_fwd / p_now) - 1.0

        # Intersect stocks with both mom score and valid forward return
        eligible = [s for s in mom_scores if s in fwd_returns]
        if len(eligible) < 30:
            continue

        # Sort eligible stocks by 12-1 momentum score
        eligible_sorted = sorted(eligible, key=lambda s: mom_scores[s])
        n = len(eligible_sorted)

        # Partition into 10 deciles: D1 (lowest momentum) to D10 (highest momentum)
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
            "n_stocks": n,
            "market_ret": mkt_ret,
            "spread_D10_minus_D1": spread
        }
        row.update(decile_returns)
        records.append(row)

    df_res = pd.DataFrame(records)
    print(f"Computed monthly decile returns for {len(df_res)} consecutive months.")

    # 1. Monotonicity and Decile Return Summary
    print("\n" + "=" * 50)
    print(">>> AVERAGE MONTHLY & ANNUALIZED RETURNS BY DECILE <<<")
    print("=" * 50)
    summary_data = []
    for d in range(1, 11):
        col = f"D{d}"
        m_mean = df_res[col].mean()
        m_vol = df_res[col].std()
        ann_ret = (1.0 + m_mean) ** 12 - 1.0
        ann_vol = m_vol * np.sqrt(12)
        sharpe = ann_ret / ann_vol if ann_vol > 0 else 0.0
        summary_data.append({
            "Decile": col,
            "Monthly Mean": f"{m_mean * 100:.2f}%",
            "Ann Return": f"{ann_ret * 100:.2f}%",
            "Ann Vol": f"{ann_vol * 100:.2f}%",
            "Sharpe": f"{sharpe:.2f}"
        })
    print(pd.DataFrame(summary_data).to_string(index=False))

    # 2. Long-Short Spread (D10 - D1) Overall Metrics
    spr = df_res["spread_D10_minus_D1"]
    spr_mean = spr.mean()
    spr_vol = spr.std()
    spr_ann = (1.0 + spr_mean) ** 12 - 1.0
    spr_ann_vol = spr_vol * np.sqrt(12)
    spr_sharpe = spr_ann / spr_ann_vol if spr_ann_vol > 0 else 0.0
    win_rate = (spr > 0).mean() * 100

    print("\n" + "=" * 50)
    print(">>> LONG-SHORT SPREAD (D10 - D1) LIFETIME METRICS <<<")
    print("=" * 50)
    print(f"Monthly Mean Spread:       {spr_mean * 100:+.2f}%")
    print(f"Annualized Spread Return:  {spr_ann * 100:+.2f}%")
    print(f"Annualized Spread Vol:     {spr_ann_vol * 100:.2f}%")
    print(f"Long-Short Sharpe Ratio:   {spr_sharpe:.2f}")
    print(f"Positive Month Hit Rate:   {win_rate:.1f}% ({int((spr > 0).sum())}/{len(spr)} months)")

    # 3. Rolling 3-Year (36-Month) Windows Analysis
    print("\n" + "=" * 50)
    print(">>> ROLLING 3-YEAR (36-MONTH) SPREAD WINDOWS <<<")
    print("=" * 50)
    rolling_3y = []
    for i in range(len(df_res) - 35):
        w = df_res.iloc[i : i + 36]
        w_start = w["rebal_date"].iloc[0]
        w_end = w["fwd_date"].iloc[-1]
        # Cumulative spread return over 36 months: product of (1 + spread) - 1
        cum_spr = np.prod(1.0 + w["spread_D10_minus_D1"]) - 1.0
        # Annualized spread in this 3-year window
        ann_spr = (1.0 + cum_spr) ** (1.0 / 3.0) - 1.0
        rolling_3y.append({
            "start": w_start,
            "end": w_end,
            "3y_cum_spread": cum_spr,
            "3y_ann_spread": ann_spr
        })

    df_roll = pd.DataFrame(rolling_3y)
    pos_roll = (df_roll["3y_ann_spread"] > 0).mean() * 100
    min_roll = df_roll["3y_ann_spread"].min() * 100
    max_roll = df_roll["3y_ann_spread"].max() * 100
    mean_roll = df_roll["3y_ann_spread"].mean() * 100
    median_roll = df_roll["3y_ann_spread"].median() * 100

    print(f"Total 3-Year Rolling Windows: {len(df_roll)}")
    print(f"Positive 3-Year Windows:     {pos_roll:.1f}% ({int((df_roll['3y_ann_spread'] > 0).sum())}/{len(df_roll)})")
    print(f"Mean 3-Year Ann Spread:       {mean_roll:+.2f}%")
    print(f"Median 3-Year Ann Spread:     {median_roll:+.2f}%")
    print(f"Worst 3-Year Ann Spread:      {min_roll:+.2f}%")
    print(f"Best 3-Year Ann Spread:       {max_roll:+.2f}%")

    print("\nSample 3-Year Rolling Windows:")
    step = max(1, len(df_roll) // 10)
    for idx in range(0, len(df_roll), step):
        r = df_roll.iloc[idx]
        print(f"  Window {r['start']} to {r['end']}: 3Y Ann Spread = {r['3y_ann_spread'] * 100:+.2f}%")
    # Print the last window
    last_r = df_roll.iloc[-1]
    print(f"  Window {last_r['start']} to {last_r['end']}: 3Y Ann Spread = {last_r['3y_ann_spread'] * 100:+.2f}%")

    # Save outputs
    out_deciles = os.path.join(DATA_DIR, "nifty100_momentum_decile_returns.csv")
    df_res.to_csv(out_deciles, index=False)
    out_roll = os.path.join(DATA_DIR, "nifty100_momentum_rolling_3y_spread.csv")
    df_roll.to_csv(out_roll, index=False)
    print(f"\n[OK] Saved results to {out_deciles} and {out_roll}")

    # 4. DECISION GATE VERDICT
    print("\n" + "=" * 80)
    print(">>> DECISION GATE VERDICT <<<")
    print("=" * 80)
    if pos_roll >= 75.0 and mean_roll > 0:
        print(f"RESULT: PASS (Positive Rolling 3Y Spread in {pos_roll:.1f}% of windows, Mean = {mean_roll:+.2f}%)")
        print("Verdict: Stock 12-1 momentum exhibits positive alpha in large caps. Proceed to S1 pre-registration.")
    else:
        print(f"RESULT: FAIL (Positive Rolling 3Y Spread in only {pos_roll:.1f}% of windows, Mean = {mean_roll:+.2f}%)")
        print("Verdict: Stock 12-1 momentum does NOT deliver consistent positive alpha across 3-year windows.")
        print("EMPIRICAL ACTION: Drop stock selection permanently and allocate all trading logic to Core.")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    run_decile_analysis()
