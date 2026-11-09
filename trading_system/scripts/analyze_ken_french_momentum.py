"""
Kenneth French Official CRSP Survivor-Bias-Free US Momentum Factor & Deciles (2007 - 2024)
==========================================================================================
Evaluates the gold-standard Kenneth French / CRSP survivor-bias-free US Equity Momentum Factor
(UMD - Up Minus Down) and 10 Prior-Return Decile Portfolios across 2007-09 to 2024-07.

Dataset Source:
  Kenneth R. French Data Library (Dartmouth College / CRSP)
  - F-F_Momentum_Factor_CSV.zip (Official Carhart Momentum Factor)
  - 10_Portfolios_Prior_12_2_CSV.zip (10 Prior 12-2 Return Portfolios, VW and EW)
  Includes all NYSE, AMEX, and NASDAQ common stocks, fully accounting for all bankruptcies,
  delistings, mergers, and spinoffs with accurate CRSP delisting returns from 1927 to 2026.

Decision Gate Protocol (Gate A Stand-In):
  - Evaluates whether UMD factor and D10 - D1 decile spread achieved persistent positive alpha
    across rolling 3-year (36-month) windows (>= 75% positive windows).
  - If UMD is also weak/negative across 2007-2024, stock momentum long-short is officially
    eliminated, and Strategy S3 (Beta-Hedged Multi-Asset ETF Spread) becomes the sole market-neutral candidate.
"""

import os
import sys
import io
import json
import zipfile
import urllib.request
import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from trading_system.app.validation.trial_logger import log_trial

DATA_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data")
OUTPUT_JSON = os.path.join(DATA_DIR, "ken_french_momentum_analysis.json")
OUTPUT_CSV = os.path.join(DATA_DIR, "ken_french_momentum_monthly.csv")

URL_UMD = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Momentum_Factor_CSV.zip"
URL_DECILES = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/10_Portfolios_Prior_12_2_CSV.zip"

EVAL_START = "2007-09"
EVAL_END = "2024-07"


def download_and_parse_ken_french_data() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Download and parse official Kenneth French Momentum factor and 10 deciles."""
    print("[1/4] Fetching official CRSP Kenneth French Momentum datasets from Dartmouth...", flush=True)
    req_headers = {"User-Agent": "Mozilla/5.0"}

    # 1. Fetch UMD Factor
    req_umd = urllib.request.Request(URL_UMD, headers=req_headers)
    with urllib.request.urlopen(req_umd) as resp:
        z_umd = zipfile.ZipFile(io.BytesIO(resp.read()))
        with z_umd.open("F-F_Momentum_Factor.csv") as f:
            text_umd = f.read().decode("utf-8")

    block_umd = text_umd.split("\r\n\r\n")[2]
    df_umd = pd.read_csv(io.StringIO(block_umd))
    df_umd.columns = ["date", "UMD"]
    df_umd["date"] = pd.to_datetime(df_umd["date"].astype(str), format="%Y%m")
    df_umd.set_index("date", inplace=True)
    df_umd["UMD"] = pd.to_numeric(df_umd["UMD"], errors="coerce") / 100.0  # Convert pct to decimal

    # 2. Fetch 10 Prior 12-2 Portfolios
    req_dec = urllib.request.Request(URL_DECILES, headers=req_headers)
    with urllib.request.urlopen(req_dec) as resp:
        z_dec = zipfile.ZipFile(io.BytesIO(resp.read()))
        with z_dec.open("10_Portfolios_Prior_12_2.csv") as f:
            text_dec = f.read().decode("utf-8")

    blocks_dec = text_dec.split("\r\n\r\n")
    # Block 3 is Value Weight Returns -- Monthly
    lines_vw = [l for l in blocks_dec[3].splitlines() if l.strip()]
    df_vw = pd.read_csv(io.StringIO("\n".join(lines_vw[1:])))
    df_vw.columns = [c.strip() for c in df_vw.columns]
    df_vw.rename(columns={df_vw.columns[0]: "date"}, inplace=True)
    df_vw["date"] = pd.to_datetime(df_vw["date"].astype(str), format="%Y%m", errors="coerce")
    df_vw.dropna(subset=["date"], inplace=True)
    df_vw.set_index("date", inplace=True)
    for c in df_vw.columns:
        df_vw[c] = pd.to_numeric(df_vw[c], errors="coerce") / 100.0

    # Block 4 is Average Equal Weighted Returns -- Monthly
    lines_ew = [l for l in blocks_dec[4].splitlines() if l.strip()]
    df_ew = pd.read_csv(io.StringIO("\n".join(lines_ew[1:])))
    df_ew.columns = [c.strip() for c in df_ew.columns]
    df_ew.rename(columns={df_ew.columns[0]: "date"}, inplace=True)
    df_ew["date"] = pd.to_datetime(df_ew["date"].astype(str), format="%Y%m", errors="coerce")
    df_ew.dropna(subset=["date"], inplace=True)
    df_ew.set_index("date", inplace=True)
    for c in df_ew.columns:
        df_ew[c] = pd.to_numeric(df_ew[c], errors="coerce") / 100.0

    print("  Successfully loaded UMD factor and 10 Prior-Return portfolios (VW & EW).", flush=True)
    return df_umd, df_vw, df_ew


def compute_series_metrics(ret_series: pd.Series, label: str) -> Dict[str, Any]:
    """Compute institutional performance metrics for a monthly return series."""
    m_mean = ret_series.mean()
    m_std = ret_series.std()
    n_months = len(ret_series)
    years = n_months / 12.0

    cum_series = (1.0 + ret_series).cumprod()
    final_cum = cum_series.iloc[-1]
    cagr = (final_cum ** (1.0 / years) - 1.0) * 100.0 if final_cum > 0 else -100.0
    ann_vol = m_std * np.sqrt(12) * 100.0
    sharpe = (cagr - 2.0) / ann_vol if ann_vol > 0 else 0.0

    peaks = np.maximum.accumulate(cum_series)
    drawdowns = (cum_series - peaks) / peaks
    max_dd = drawdowns.min() * 100.0
    win_rate = (ret_series > 0).mean() * 100.0

    # Rolling 3-year (36-month) windows
    rolling_3y = []
    for i in range(len(ret_series) - 35):
        w = ret_series.iloc[i : i + 36]
        cum_w = np.prod(1.0 + w) - 1.0
        ann_w = ((1.0 + cum_w) ** (1.0 / 3.0) - 1.0) * 100.0
        rolling_3y.append(ann_w)

    roll_arr = np.array(rolling_3y)
    pos_roll = (roll_arr > 0).mean() * 100.0 if len(roll_arr) > 0 else 0.0
    mean_roll = np.mean(roll_arr) if len(roll_arr) > 0 else 0.0
    median_roll = np.median(roll_arr) if len(roll_arr) > 0 else 0.0
    min_roll = np.min(roll_arr) if len(roll_arr) > 0 else 0.0
    max_roll = np.max(roll_arr) if len(roll_arr) > 0 else 0.0

    return {
        "label": label,
        "n_months": n_months,
        "monthly_mean_pct": round(m_mean * 100.0, 2),
        "cagr_pct": round(cagr, 2),
        "ann_vol_pct": round(ann_vol, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "win_rate_pct": round(win_rate, 1),
        "rolling_3y_windows": len(roll_arr),
        "positive_3y_pct": round(pos_roll, 1),
        "mean_3y_spread_pct": round(mean_roll, 2),
        "median_3y_spread_pct": round(median_roll, 2),
        "worst_3y_window_pct": round(min_roll, 2),
        "best_3y_window_pct": round(max_roll, 2)
    }


def run_ken_french_momentum_analysis():
    print("=" * 85)
    print(">>> OFFICIAL KENNETH FRENCH CRSP US MOMENTUM FACTOR & DECILE AUDIT <<<")
    print(f">>> Evaluation Window: {EVAL_START} to {EVAL_END} (2008 Crash Included) <<<")
    print("=" * 85)

    df_umd, df_vw, df_ew = download_and_parse_ken_french_data()

    # Filter to evaluation window: 2007-09 to 2024-07
    sub_umd = df_umd.loc[EVAL_START:EVAL_END, "UMD"]
    sub_vw = df_vw.loc[EVAL_START:EVAL_END]
    sub_ew = df_ew.loc[EVAL_START:EVAL_END]

    print(f"\n[2/4] Aligned Timeline: {len(sub_umd)} months from {sub_umd.index[0].strftime('%Y-%m')} to {sub_umd.index[-1].strftime('%Y-%m')}.", flush=True)

    # Decile spread: Hi PRIOR (D10) minus Lo PRIOR (D1)
    vw_spread = sub_vw["Hi PRIOR"] - sub_vw["Lo PRIOR"]
    ew_spread = sub_ew["Hi PRIOR"] - sub_ew["Lo PRIOR"]

    # Compute metrics for UMD, VW Decile Spread, and EW Decile Spread
    m_umd = compute_series_metrics(sub_umd, "Ken French Official UMD Carhart Factor")
    m_vw_spread = compute_series_metrics(vw_spread, "CRSP Decile Spread (D10 - D1, Value-Weighted)")
    m_ew_spread = compute_series_metrics(ew_spread, "CRSP Decile Spread (D10 - D1, Equal-Weighted)")

    # Compute Decile 1 to 10 Breakdown for Value-Weighted
    vw_deciles = {}
    for c in sub_vw.columns:
        vw_deciles[c] = compute_series_metrics(sub_vw[c], f"VW {c}")

    ew_deciles = {}
    for c in sub_ew.columns:
        ew_deciles[c] = compute_series_metrics(sub_ew[c], f"EW {c}")

    # Print Summary Tables
    print("\n" + "=" * 90)
    print(">>> CRSP SURVIVOR-FREE 10 PRIOR-RETURN DECILES (2007 - 2024: VALUE-WEIGHTED) <<<")
    print("=" * 90)
    print(f"{'Decile':<15} | {'Monthly Mean':>12} | {'CAGR (%)':>9} | {'Ann Vol (%)':>11} | {'Sharpe':>7} | {'Max DD (%)':>10}")
    print("-" * 90)
    for c in sub_vw.columns:
        d = vw_deciles[c]
        print(f"{c:<15} | {d['monthly_mean_pct']:>11.2f}% | {d['cagr_pct']:>8.2f}% | {d['ann_vol_pct']:>10.2f}% | {d['sharpe_ratio']:>7.2f} | {d['max_drawdown_pct']:>9.2f}%")
    print("-" * 90)
    print(f"{'D10 - D1 Spread':<15} | {m_vw_spread['monthly_mean_pct']:>11.2f}% | {m_vw_spread['cagr_pct']:>8.2f}% | {m_vw_spread['ann_vol_pct']:>10.2f}% | {m_vw_spread['sharpe_ratio']:>7.2f} | {m_vw_spread['max_drawdown_pct']:>9.2f}%")
    print("=" * 90)

    print("\n" + "=" * 90)
    print(">>> CRSP SURVIVOR-FREE 10 PRIOR-RETURN DECILES (2007 - 2024: EQUAL-WEIGHTED) <<<")
    print("=" * 90)
    print(f"{'Decile':<15} | {'Monthly Mean':>12} | {'CAGR (%)':>9} | {'Ann Vol (%)':>11} | {'Sharpe':>7} | {'Max DD (%)':>10}")
    print("-" * 90)
    for c in sub_ew.columns:
        d = ew_deciles[c]
        print(f"{c:<15} | {d['monthly_mean_pct']:>11.2f}% | {d['cagr_pct']:>8.2f}% | {d['ann_vol_pct']:>10.2f}% | {d['sharpe_ratio']:>7.2f} | {d['max_drawdown_pct']:>9.2f}%")
    print("-" * 90)
    print(f"{'D10 - D1 Spread':<15} | {m_ew_spread['monthly_mean_pct']:>11.2f}% | {m_ew_spread['cagr_pct']:>8.2f}% | {m_ew_spread['ann_vol_pct']:>10.2f}% | {m_ew_spread['sharpe_ratio']:>7.2f} | {m_ew_spread['max_drawdown_pct']:>9.2f}%")
    print("=" * 90)

    print("\n" + "=" * 90)
    print(">>> US MOMENTUM FACTOR COMPARISON (2007 - 2024) <<<")
    print("=" * 90)
    print(f"{'Factor / Strategy':<42} | {'CAGR (%)':>9} | {'Max DD (%)':>10} | {'Sharpe':>7} | {'Win Rate':>8} | {'3Y Pos (%)':>10}")
    print("-" * 90)
    for m in [m_umd, m_vw_spread, m_ew_spread]:
        print(f"{m['label']:<42} | {m['cagr_pct']:>8.2f}% | {m['max_drawdown_pct']:>9.2f}% | {m['sharpe_ratio']:>7.2f} | {m['win_rate_pct']:>7.1f}% | {m['positive_3y_pct']:>9.1f}%")
    print("=" * 90)

    # Long-term comparison: 1927-2006 vs 2007-2024
    umd_pre = df_umd.loc["1927-01":"2006-12", "UMD"]
    m_umd_pre = compute_series_metrics(umd_pre, "Ken French UMD Pre-2007 (1927 - 2006)")

    print("\n" + "=" * 90)
    print(">>> LONG-TERM STRUCTURAL DECAY: PRE-2007 vs 2007-2024 <<<")
    print("=" * 90)
    print(f"  Historical UMD (1927 - 2006, 80 years):  CAGR: {m_umd_pre['cagr_pct']:+.2f}% | Sharpe: {m_umd_pre['sharpe_ratio']:.2f} | 3Y Pos: {m_umd_pre['positive_3y_pct']:.1f}%")
    print(f"  Modern UMD     (2007 - 2024, 17 years):  CAGR: {m_umd['cagr_pct']:+.2f}% | Sharpe: {m_umd['sharpe_ratio']:.2f} | 3Y Pos: {m_umd['positive_3y_pct']:.1f}%")
    print("=" * 90)

    # Gate Evaluation
    # Fails if 3Y positive windows < 75% or CAGR <= 0
    gate_passed = m_umd["positive_3y_pct"] >= 75.0 and m_umd["cagr_pct"] > 0.0
    print("\n" + "=" * 80)
    if gate_passed:
        print(">>> DECISION GATE A: PASSED <<<")
        print("  Ken French CRSP survivor-free UMD factor achieved persistent positive alpha.")
    else:
        print(">>> DECISION GATE A: FAILED <<<")
        print(f"  Ken French CRSP survivor-free UMD factor failed persistence threshold.")
        print(f"  - Modern UMD CAGR:             {m_umd['cagr_pct']:+.2f}% (vs {m_umd_pre['cagr_pct']:+.2f}% historical)")
        print(f"  - Positive 3-Year Windows:     {m_umd['positive_3y_pct']:.1f}% (Required: >= 75%)")
        print(f"  - Max Factor Drawdown:         {m_umd['max_drawdown_pct']:.2f}% (2009 Momentum Crash)")
        print("  VERDICT: STOCK-LEVEL MOMENTUM LONG-SHORT IS SYSTEMICALLY BROKEN IN MODERN MARKETS.")
        print("  MANDATE: MOVE IMMEDIATELY TO STRATEGY S3 (BETA-HEDGED MULTI-ASSET ETF SPREAD).")
    print("=" * 80 + "\n")

    # Save outputs
    df_combined = pd.DataFrame({
        "UMD": sub_umd,
        "VW_Spread_D10_minus_D1": vw_spread,
        "EW_Spread_D10_minus_D1": ew_spread
    })
    df_combined.to_csv(OUTPUT_CSV)

    with open(OUTPUT_JSON, "w") as f:
        json.dump({
            "umd_modern": m_umd,
            "umd_pre_2007": m_umd_pre,
            "vw_spread": m_vw_spread,
            "ew_spread": m_ew_spread,
            "vw_deciles": vw_deciles,
            "ew_deciles": ew_deciles,
            "gate_passed": bool(gate_passed)
        }, f, indent=2)

    # Log trial stamped with commit hash
    log_trial(
        cagr_pct=m_umd["cagr_pct"],
        max_drawdown_pct=m_umd["max_drawdown_pct"],
        sharpe_ratio=m_umd["sharpe_ratio"],
        kelly_fraction=1.0,
        lookback_days=252,
        script="analyze_ken_french_momentum.py",
        universe="US_CRSP_KEN_FRENCH_UMD_FACTOR",
        notes=f"Ken French CRSP Survivor-Free UMD Factor (2007-2024). Rolling 3Y positive in {m_umd['positive_3y_pct']:.1f}% of windows (Mean {m_umd['mean_3y_spread_pct']:+.2f}%). Max DD {m_umd['max_drawdown_pct']:.2f}%. Gate A {'PASSED' if gate_passed else 'FAILED'}."
    )

    return m_umd, m_vw_spread, m_ew_spread


if __name__ == "__main__":
    run_ken_french_momentum_analysis()
