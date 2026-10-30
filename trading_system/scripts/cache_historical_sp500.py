import os
import sys
import time
from datetime import datetime
import pandas as pd
import yfinance as yf

CACHE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "historical_cache"))
os.makedirs(CACHE_DIR, exist_ok=True)

START_DATE = "1999-01-01"
END_DATE = "2025-12-31"

MACRO_TICKERS = ["SPY", "^VIX", "^TNX", "^IRX", "QQQ", "HYG", "IEF", "RSP"]

def sanitize_filename(sym: str) -> str:
    return sym.replace("^", "INDEX_").replace(".", "-")

def download_and_cache_macro():
    print("=== Downloading Macro Instruments (1999 - 2025) ===")
    for sym in MACRO_TICKERS:
        fname = f"{sanitize_filename(sym)}.parquet"
        fpath = os.path.join(CACHE_DIR, fname)
        if os.path.exists(fpath):
            print(f"  [CACHED] {sym}")
            continue
        print(f"  Downloading {sym}...")
        try:
            ticker = yf.Ticker(sym)
            df = ticker.history(start=START_DATE, end=END_DATE, auto_adjust=False)
            if not df.empty:
                df.columns = [c.lower() for c in df.columns]
                df.to_parquet(fpath)
                print(f"  -> Saved {sym} ({len(df)} rows)")
            else:
                print(f"  -> Empty data for {sym}")
        except Exception as e:
            print(f"  -> Error fetching {sym}: {e}")

def download_and_cache_universe():
    tickers_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "sp500_tickers.txt"))
    with open(tickers_file, "r") as f:
        all_tickers = [line.strip().replace(".", "-") for line in f if line.strip()]

    print(f"\n=== Downloading S&P 500 Universe ({len(all_tickers)} Tickers) ===")
    
    # Filter out already cached tickers
    missing_tickers = []
    for sym in all_tickers:
        fpath = os.path.join(CACHE_DIR, f"{sanitize_filename(sym)}.parquet")
        if not os.path.exists(fpath):
            missing_tickers.append(sym)
            
    print(f"Already cached: {len(all_tickers) - len(missing_tickers)} | Need to download: {len(missing_tickers)}")
    
    if not missing_tickers:
        print("All tickers already cached!")
        return

    # Download in batches of 50
    batch_size = 50
    for i in range(0, len(missing_tickers), batch_size):
        batch = missing_tickers[i:i + batch_size]
        print(f"\n[Batch {i // batch_size + 1}/{(len(missing_tickers) + batch_size - 1) // batch_size}] Fetching {len(batch)} tickers: {batch[:5]}...")
        t0 = time.time()
        try:
            data = yf.download(
                batch,
                start=START_DATE,
                end=END_DATE,
                auto_adjust=False,
                actions=True,
                group_by="ticker",
                threads=True,
                progress=False
            )
            
            saved_count = 0
            for sym in batch:
                try:
                    if len(batch) == 1:
                        df = data.copy()
                    else:
                        if sym not in data.columns.levels[0]:
                            continue
                        df = data[sym].dropna(how="all").copy()
                        
                    if not df.empty:
                        df.columns = [str(c).lower().replace(" ", "_") for c in df.columns]
                        fpath = os.path.join(CACHE_DIR, f"{sanitize_filename(sym)}.parquet")
                        df.to_parquet(fpath)
                        saved_count += 1
                except Exception as ex:
                    pass
            print(f"  -> Batch saved {saved_count} tickers in {time.time() - t0:.2f}s")
        except Exception as e:
            print(f"  -> Batch failed: {e}")
            time.sleep(2)

if __name__ == "__main__":
    t_start = time.time()
    download_and_cache_macro()
    download_and_cache_universe()
    print(f"\n=== Cache Complete in {time.time() - t_start:.2f}s ===")
