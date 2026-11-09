"""
Nifty 100 Point-in-Time Price Usability & Stale-Fill Audit (2007 - 2024)
========================================================================
Audits every monthly rebalancing date to distinguish between:
1. Clean Direct Trades: Traded on that exact date under primary canonical ticker.
2. Alias-Merged Trades: Traded on that exact date under a historical predecessor symbol.
3. Stale-Filled Prices: Did NOT trade on that date, forward-filled from a prior date (<= 65 days).
4. Truly Missing Prices: No price available even within the 65-day forward-fill window.
"""

import os
import sys
import pandas as pd
import numpy as np
from typing import Dict, List, Set, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

DATA_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data")
OUTPUT_CSV = os.path.join(DATA_DIR, "nifty100_price_usability_breakdown.csv")


HISTORICAL_TICKER_ALIASES = {
    'INFY': ['INFOSYSTCH'],
    'HEROMOTOCO': ['HEROHONDA'],
    'VEDL': ['SSLT', 'SESAGOA'],
    'CROMPTON': ['CROMPGREAV', 'CGPOWER'],
    'INDUSTOWER': ['INFRATEL', 'BHARTIINFR'],
    'UPL': ['UNIPHOS'],
    'ADANIPORTS': ['MUNDRAPORT'],
    'TATACONSUM': ['TATAGLOBAL', 'TATATEA'],
    'BAJAJ-AUTO': ['BAJAJAUTO'],
    'RELINFRA': ['REL'],
    'TATACOMM': ['VSNL'],
    'SANOFI': ['AVENTIS'],
    'PIRHEALTH': ['NICOLASPIR', 'PEL'],
    'ADANITRANS': ['ADANIENSOL'],
    'LTI': ['LTIM'],
    'CADILAHC': ['ZYDUSLIFE'],
    'OFSS': ['I-FLEX'],
    'MCDOWELL-N': ['UNITDSPR']
}


def audit_price_usability():
    print("=" * 80)
    print(">>> NIFTY 100 POINT-IN-TIME PRICE USABILITY & STALE-FILL AUDIT (2007 - 2024) <<<")
    print("=" * 80)

    # 1. Load raw Bhavcopy close prices panel (strictly un-forward-filled)
    raw_close = pd.read_parquet(os.path.join(DATA_DIR, "causal_panel_close.parquet"))
    raw_close.index = pd.to_datetime(raw_close.index)

    # 2. Load PIT Nifty 100 membership intervals
    df_int = pd.read_csv(os.path.join(DATA_DIR, "nifty100_ticker_start_end.csv"))
    df_int["ticker_clean"] = df_int["ticker"].str.replace(".NS", "", regex=False)
    df_int["start_date"] = pd.to_datetime(df_int["start_date"])
    df_int["end_date"] = pd.to_datetime(df_int["end_date"]).fillna(pd.Timestamp("2099-12-31"))

    # Evaluation dates: 2007-09-24 to 2024-07-05
    dates = raw_close.index[(raw_close.index >= "2007-09-24") & (raw_close.index <= "2024-07-05")]
    raw_close = raw_close.loc[dates]

    # Build merged alias panel
    merged_close = raw_close.copy()
    for canon, alts in HISTORICAL_TICKER_ALIASES.items():
        if canon in merged_close.columns:
            s = merged_close[canon].copy()
            for a in alts:
                if a in merged_close.columns:
                    s = s.combine_first(merged_close[a])
            merged_close[canon] = s

    # Build forward-filled panel (limit=65)
    ffill_close = merged_close.ffill(limit=65)

    # Rebalancing dates (month ends)
    df_d = pd.DataFrame({"date": dates}, index=dates)
    df_d["month"] = df_d["date"].dt.to_period("M")
    month_ends = sorted(df_d.groupby("month")["date"].max().tolist())

    monthly_records = []
    stale_duration_counts = {"1-5_days": 0, "6-20_days": 0, "21-65_days": 0}

    for me in month_ends:
        active = df_int[(df_int["start_date"] <= me) & (df_int["end_date"] > me)]["ticker_clean"].unique()
        n_act = len(active)

        clean_direct = []
        alias_merged = []
        stale_filled = []
        truly_missing = []

        for s in active:
            # Check 1: Clean Direct
            if s in raw_close.columns and not pd.isna(raw_close.loc[me, s]) and raw_close.loc[me, s] > 0:
                clean_direct.append(s)
            else:
                # Check 2: Alias Merged on that exact day
                is_alias = False
                if s in HISTORICAL_TICKER_ALIASES:
                    for a in HISTORICAL_TICKER_ALIASES[s]:
                        if a in raw_close.columns and not pd.isna(raw_close.loc[me, a]) and raw_close.loc[me, a] > 0:
                            alias_merged.append(f"{s}<-{a}")
                            is_alias = True
                            break
                
                if not is_alias:
                    # Check 3: Stale-filled from previous trading days
                    if s in ffill_close.columns and not pd.isna(ffill_close.loc[me, s]) and ffill_close.loc[me, s] > 0:
                        # Find how many days stale
                        hist_s = merged_close[s].loc[:me].dropna()
                        if len(hist_s) > 0:
                            last_trade_date = hist_s.index[-1]
                            # Count trading days lag
                            lag_days = len(raw_close.loc[last_trade_date:me]) - 1
                            stale_filled.append((s, lag_days))
                            if lag_days <= 5:
                                stale_duration_counts["1-5_days"] += 1
                            elif lag_days <= 20:
                                stale_duration_counts["6-20_days"] += 1
                            else:
                                stale_duration_counts["21-65_days"] += 1
                        else:
                            stale_filled.append((s, 999))
                    else:
                        truly_missing.append(s)

        stale_share = (len(stale_filled) / n_act) * 100.0 if n_act > 0 else 0.0
        clean_share = (len(clean_direct) / n_act) * 100.0 if n_act > 0 else 0.0
        alias_share = (len(alias_merged) / n_act) * 100.0 if n_act > 0 else 0.0

        monthly_records.append({
            "rebal_date": me.strftime("%Y-%m-%d"),
            "n_active": n_act,
            "n_clean_direct": len(clean_direct),
            "n_alias_merged": len(alias_merged),
            "n_stale_filled": len(stale_filled),
            "n_truly_missing": len(truly_missing),
            "clean_direct_pct": round(clean_share, 2),
            "alias_merged_pct": round(alias_share, 2),
            "stale_filled_pct": round(stale_share, 2),
            "truly_missing_pct": round((len(truly_missing) / n_act) * 100.0, 2),
            "stale_details": "; ".join([f"{s}({d}d)" for s, d in stale_filled]),
            "alias_details": "; ".join(alias_merged),
            "missing_details": "; ".join(truly_missing)
        })

    df_out = pd.DataFrame(monthly_records)
    df_out.to_csv(OUTPUT_CSV, index=False)

    avg_act = df_out["n_active"].mean()
    avg_clean = df_out["n_clean_direct"].mean()
    avg_alias = df_out["n_alias_merged"].mean()
    avg_stale = df_out["n_stale_filled"].mean()
    avg_miss = df_out["n_truly_missing"].mean()

    print(f"\nTotal Monthly Rebalances Evaluated: {len(df_out)} months (2007-09 to 2024-07)")
    print(f"Average Active Constituents:        {avg_act:.1f} stocks\n")

    print("-" * 70)
    print(">>> 17-YEAR AVERAGE PRICE USABILITY BREAKDOWN <<<")
    print("-" * 70)
    print(f"  1. Clean Direct Trades:   {avg_clean:.2f} / {avg_act:.1f} ({avg_clean / avg_act * 100:.2f}%)")
    print(f"  2. Alias-Merged Trades:   {avg_alias:.2f} / {avg_act:.1f} ({avg_alias / avg_act * 100:.2f}%)")
    print(f"  3. Truly Priced on Day:   {avg_clean + avg_alias:.2f} / {avg_act:.1f} ({(avg_clean + avg_alias) / avg_act * 100:.2f}%)")
    print(f"  4. Stale-Filled Prices:   {avg_stale:.2f} / {avg_act:.1f} ({avg_stale / avg_act * 100:.2f}%)")
    print(f"  5. Truly Missing Prices:  {avg_miss:.2f} / {avg_act:.1f} ({avg_miss / avg_act * 100:.2f}%)")
    print("-" * 70)

    print(f"\nMonths with ZERO Stale Prices:     {len(df_out[df_out['n_stale_filled'] == 0])} / {len(df_out)} ({len(df_out[df_out['n_stale_filled'] == 0]) / len(df_out) * 100:.1f}%)")
    print(f"Max Stale-Filled in Any Month:      {df_out['n_stale_filled'].max()} stocks ({df_out.loc[df_out['n_stale_filled'].idxmax(), 'rebal_date']})")
    print(f"Stale-Fill Durations Across 17Y:")
    print(f"  1 - 5 Trading Days:               {stale_duration_counts['1-5_days']} occurrences")
    print(f"  6 - 20 Trading Days:              {stale_duration_counts['6-20_days']} occurrences")
    print(f"  21 - 65 Trading Days:             {stale_duration_counts['21-65_days']} occurrences")

    print(f"\nSaved detailed monthly breakdown to: {OUTPUT_CSV}")
    return df_out


if __name__ == "__main__":
    audit_price_usability()
