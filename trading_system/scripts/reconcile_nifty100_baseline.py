import os
import sys
import pandas as pd
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)
DATA_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data")

from trading_system.scripts.run_causal_satellite_and_baselines import (
    PointInTimeConstituentManager,
    build_verified_split_adjustment_matrix,
    calculate_metrics
)

# 1. Load data
df_close = pd.read_parquet(os.path.join(DATA_DIR, "causal_panel_close.parquet"))

aliases = {
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

for canon, alts in aliases.items():
    if canon in df_close.columns:
        s = df_close[canon].copy()
        for a in alts:
            if a in df_close.columns:
                s = s.combine_first(df_close[a])
        df_close[canon] = s

df_close = df_close.ffill(limit=65)

dates = df_close.index[(df_close.index >= '2007-09-24') & (df_close.index <= '2024-07-05')]
df_close = df_close.loc[dates]
split_mults, split_factors = build_verified_split_adjustment_matrix(df_close)

df_d = pd.DataFrame({'date': dates}, index=dates)
df_d['month'] = df_d['date'].dt.to_period('M')
month_ends = sorted(df_d.groupby('month')['date'].max().tolist())

pit_n100 = PointInTimeConstituentManager(
    changes_csv_path=os.path.join(DATA_DIR, "nifty100_historical_components_changes.csv"),
    start_end_csv_path=os.path.join(DATA_DIR, "nifty100_ticker_start_end.csv")
)

# 2. Compute monthly equal-weight return of Nifty 100
monthly_returns = []
monthly_counts = []

for i in range(len(month_ends) - 1):
    m0 = month_ends[i]
    m1 = month_ends[i + 1]
    active_set = pit_n100.get_active_constituents(m0)
    
    rets = []
    for s_raw in active_set:
        s = s_raw.replace("-NS", "").replace(".NS", "")
        if s in df_close.columns:
            p0 = df_close.loc[m0, s]
            p1 = df_close.loc[m1, s]
            
            # Cumulative split multiplier between m0 and m1
            # If split occurred strictly after m0 up to m1
            sub_mult = split_mults.loc[m0:m1, s] if s in split_mults.columns else None
            mult = sub_mult.iloc[1:].prod() if sub_mult is not None and len(sub_mult) > 1 else 1.0
            
            if p0 > 0 and p1 > 0 and not pd.isna(p0) and not pd.isna(p1):
                r = (p1 * mult / p0) - 1.0
                rets.append(r)
                
    if rets:
        monthly_returns.append(np.mean(rets))
        monthly_counts.append(len(rets))

m_arr = np.array(monthly_returns)
print(f"Total evaluated months: {len(m_arr)}")
print(f"Mean constituents per month: {np.mean(monthly_counts):.1f}")
print(f"Min constituents in any month: {np.min(monthly_counts)}")

cum_ew = np.prod(1.0 + m_arr)
years = (dates[-1] - dates[0]).days / 365.25
cagr_ew = cum_ew ** (1.0 / years) - 1.0
ann_vol = np.std(m_arr) * np.sqrt(12)
sharpe = cagr_ew / ann_vol if ann_vol > 0 else 0.0

# Max Drawdown of equal-weight series
cum_series = np.cumprod(1.0 + m_arr)
peaks = np.maximum.accumulate(cum_series)
drawdowns = (cum_series - peaks) / peaks
max_dd = np.min(drawdowns)

print("\n" + "=" * 80)
print(">>> RECONCILED POINT-IN-TIME NIFTY 100 EQUAL-WEIGHT BENCHMARK <<<")
print("=" * 80)
print(f"Evaluation Window:  {dates[0].date()} to {dates[-1].date()} ({years:.2f} years)")
print(f"CAGR (Pre-Tax):     {cagr_ew * 100:.2f}%")
print(f"Annualized Vol:     {ann_vol * 100:.2f}%")
print(f"Sharpe Ratio:       {sharpe:.2f}")
print(f"Max Drawdown:       {max_dd * 100:.2f}%\n")
