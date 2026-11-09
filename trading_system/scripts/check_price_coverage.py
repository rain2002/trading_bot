import os
import pandas as pd
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data")

df_close = pd.read_parquet(os.path.join(DATA_DIR, "causal_panel_close.parquet"))

# Canonical Bhavcopy ticker alias map:
# Maps active Nifty 100 tickers to historical predecessor and successor symbols
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

for canon, alts in HISTORICAL_TICKER_ALIASES.items():
    if canon in df_close.columns:
        s = df_close[canon].copy()
        for a in alts:
            if a in df_close.columns:
                s = s.combine_first(df_close[a])
        df_close[canon] = s

# Forward fill up to 65 days for surveillance / BE series transfers
df_close = df_close.ffill(limit=65)

df_int = pd.read_csv(os.path.join(DATA_DIR, "nifty100_ticker_start_end.csv"))
df_int["ticker_clean"] = df_int["ticker"].str.replace(".NS", "", regex=False)
df_int["start_date"] = pd.to_datetime(df_int["start_date"])
df_int["end_date"] = pd.to_datetime(df_int["end_date"]).fillna(pd.Timestamp("2099-12-31"))

dates = df_close.index[(df_close.index >= "2007-09-24") & (df_close.index <= "2024-07-05")]
df_d = pd.DataFrame({"date": dates}, index=dates)
df_d["month"] = df_d["date"].dt.to_period("M")
month_ends = sorted(df_d.groupby("month")["date"].max().tolist())

coverage_records = []
all_nan_syms = set()

for me in month_ends:
    active = df_int[(df_int["start_date"] <= me) & (df_int["end_date"] > me)]["ticker_clean"].unique()
    n_active = len(active)
    
    usable = []
    missing = []
    nan_price = []
    
    for sym in active:
        if sym not in df_close.columns:
            missing.append(sym)
        else:
            p = df_close.loc[me, sym]
            if pd.isna(p) or p <= 0:
                nan_price.append(sym)
                all_nan_syms.add(sym)
            else:
                usable.append(sym)
                
    cov_pct = len(usable) / n_active if n_active > 0 else 0
    coverage_records.append({
        "date": me.strftime("%Y-%m-%d"),
        "n_active": n_active,
        "n_usable": len(usable),
        "cov_pct": cov_pct,
        "missing": missing,
        "nan_price": nan_price
    })

df_cov = pd.DataFrame(coverage_records)
print(f"Total months evaluated: {len(df_cov)}")
print(f"Average monthly coverage: {df_cov['cov_pct'].mean() * 100:.2f}%")
print(f"Min monthly coverage: {df_cov['cov_pct'].min() * 100:.2f}% on {df_cov.loc[df_cov['cov_pct'].idxmin(), 'date']}")
print(f"Max monthly coverage: {df_cov['cov_pct'].max() * 100:.2f}%")

print(f"\nMonths with coverage < 95%: {len(df_cov[df_cov['cov_pct'] < 0.95])}")
for idx, r in df_cov[df_cov["cov_pct"] < 0.95].iterrows():
    print(f"  {r['date']}: active={r['n_active']}, usable={r['n_usable']}, cov={r['cov_pct']*100:.1f}%, missing={r['missing']}, nan={r['nan_price']}")

print(f"\nTotal distinct symbols that ever had NaN/Missing price while active: {len(all_nan_syms)}")
for s in sorted(list(all_nan_syms)):
    # count how many months it was NaN
    bad_months = [r["date"] for idx, r in df_cov.iterrows() if s in r["nan_price"]]
    print(f"  {s}: NaN/missing in {len(bad_months)} active months (e.g. {bad_months[:3]})")

df_cov.to_csv(os.path.join(DATA_DIR, "nifty100_monthly_price_coverage_report.csv"), index=False)
print(f"\nSaved full report to nifty100_monthly_price_coverage_report.csv")
