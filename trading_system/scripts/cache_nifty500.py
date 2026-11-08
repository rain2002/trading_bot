"""
Download and Cache Historical Daily Data for the entire Nifty 500 (Broad Market)
=============================================================================
Saves Parquet files to trading_system/data/historical_cache_nifty500/
"""

import os
import sys
import time
import pandas as pd
import yfinance as yf

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CACHE_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data", "historical_cache_nifty500")
os.makedirs(CACHE_DIR, exist_ok=True)

START_DATE = "2006-01-01"
END_DATE = "2025-12-31"


def sanitize_filename(sym: str) -> str:
    return sym.replace("^", "INDEX_").replace(".", "-")


def download_nifty500():
    list_csv = os.path.join(PROJECT_ROOT, "trading_system", "data", "ind_nifty500list.csv")
    df_list = pd.read_csv(list_csv)
    symbols = [f"{sym}.NS" for sym in df_list["Symbol"].dropna()]
    print(f"Total Nifty 500 Universe: {len(symbols)} stocks.", flush=True)

    missing = []
    for sym in symbols:
        fname = f"{sanitize_filename(sym)}.parquet"
        fpath = os.path.join(CACHE_DIR, fname)
        if not os.path.exists(fpath):
            missing.append(sym)

    print(f"Already cached: {len(symbols) - len(missing)} | To download: {len(missing)}", flush=True)
    if not missing:
        print("All Nifty 500 tickers already cached!", flush=True)
        return

    chunk_size = 25
    for i in range(0, len(missing), chunk_size):
        chunk = missing[i:i + chunk_size]
        print(f"Downloading batch {i//chunk_size + 1}/{(len(missing)+chunk_size-1)//chunk_size} ({len(chunk)} tickers)...", flush=True)
        try:
            data = yf.download(
                chunk,
                start=START_DATE,
                end=END_DATE,
                group_by="ticker",
                actions=True,
                auto_adjust=False,
                progress=False
            )
            for sym in chunk:
                try:
                    if len(chunk) == 1:
                        df = data
                    else:
                        df = data[sym] if sym in data.columns.levels[0] else pd.DataFrame()
                    df = df.dropna(how="all")
                    if not df.empty and len(df) > 30:
                        df.columns = [c.lower().replace(" ", "_") for c in df.columns]
                        fname = f"{sanitize_filename(sym)}.parquet"
                        fpath = os.path.join(CACHE_DIR, fname)
                        df.to_parquet(fpath)
                    else:
                        print(f"  [Empty/Insufficient] {sym} (rows: {len(df)})", flush=True)
                except Exception as inner_e:
                    print(f"  [Error processing] {sym}: {inner_e}", flush=True)
        except Exception as e:
            print(f"  [Batch error] {e}", flush=True)
        time.sleep(0.5)

    cached_now = [f for f in os.listdir(CACHE_DIR) if f.endswith("-NS.parquet")]
    print(f"Finished downloading! Total tickers now in cache: {len(cached_now)}", flush=True)


if __name__ == "__main__":
    download_nifty500()
