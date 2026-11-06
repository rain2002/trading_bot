"""
Download and Cache Historical Daily Data for NSE Nifty 50 Universe (2006 - 2025)
==============================================================================
Saves Parquet files to trading_system/data/historical_cache_nse/
Columns: open, high, low, close, adj_close, volume, dividends, stock_splits
"""

import os
import sys
import time
import pandas as pd
import yfinance as yf

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CACHE_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data", "historical_cache_nse")
os.makedirs(CACHE_DIR, exist_ok=True)

START_DATE = "2006-01-01"
END_DATE = "2025-12-31"

BENCHMARKS = ["^NSEI", "^BSESN"]


def sanitize_filename(sym: str) -> str:
    return sym.replace("^", "INDEX_").replace(".", "-")


def download_benchmarks():
    print("=== Downloading NSE Benchmarks (^NSEI, ^BSESN) ===", flush=True)
    for sym in BENCHMARKS:
        fname = f"{sanitize_filename(sym)}.parquet"
        fpath = os.path.join(CACHE_DIR, fname)
        if os.path.exists(fpath):
            print(f"  [CACHED] {sym}", flush=True)
            continue
        print(f"  Downloading {sym}...", flush=True)
        try:
            ticker = yf.Ticker(sym)
            df = ticker.history(start=START_DATE, end=END_DATE, auto_adjust=False)
            if not df.empty:
                df.columns = [c.lower().replace(" ", "_") for c in df.columns]
                df.to_parquet(fpath)
                print(f"  -> Saved {sym} ({len(df)} rows)", flush=True)
            else:
                print(f"  -> Warning: Empty data for {sym}", flush=True)
        except Exception as e:
            print(f"  -> Error fetching {sym}: {e}", flush=True)


def download_universe():
    tickers_file = os.path.join(PROJECT_ROOT, "trading_system", "data", "nse_tickers.txt")
    with open(tickers_file) as f:
        existing = [line.strip() for line in f if line.strip()]

    extras = [
        "ACC.NS", "BHEL.NS", "SAIL.NS", "HINDPETRO.NS", "BANKBARODA.NS", "CANBK.NS",
        "HINDALCO.NS", "ZEEL.NS", "YESBANK.NS", "UPL.NS", "ZYDUSLIFE.NS", "BERGEPAINT.NS",
        "ICICIPRULI.NS", "HDFCLIFE.NS", "BAJAJHLDNG.NS", "SBILIFE.NS", "SIEMENS.NS",
        "ABB.NS", "SHREECEM.NS", "GAIL.NS", "IOC.NS", "BPCL.NS"
    ]
    all_tickers = sorted(list(set(existing + extras)))
    print(f"\n=== Downloading NSE 50 Universe ({len(all_tickers)} Tickers) ===", flush=True)

    missing = []
    for sym in all_tickers:
        fname = f"{sanitize_filename(sym)}.parquet"
        fpath = os.path.join(CACHE_DIR, fname)
        if not os.path.exists(fpath):
            missing.append(sym)
        else:
            print(f"  [CACHED] {sym}", flush=True)

    if not missing:
        print("All tickers already cached in historical_cache_nse!", flush=True)
        return

    print(f"Fetching {len(missing)} missing tickers...", flush=True)
    # Batch download in chunks of 20
    chunk_size = 20
    for i in range(0, len(missing), chunk_size):
        chunk = missing[i:i + chunk_size]
        print(f"  Downloading batch {i//chunk_size + 1}/{(len(missing)+chunk_size-1)//chunk_size}: {chunk[:3]} ...", flush=True)
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
                    if not df.empty and len(df) > 50:
                        df.columns = [c.lower().replace(" ", "_") for c in df.columns]
                        fname = f"{sanitize_filename(sym)}.parquet"
                        df.to_parquet(os.path.join(CACHE_DIR, fname))
                        print(f"    -> Saved {sym} ({len(df)} rows)", flush=True)
                    else:
                        print(f"    -> Warning: Incomplete/empty data for {sym}", flush=True)
                except Exception as inner_e:
                    print(f"    -> Error processing {sym}: {inner_e}", flush=True)
        except Exception as batch_e:
            print(f"  -> Batch failed: {batch_e}. Falling back to single downloads...", flush=True)
            for sym in chunk:
                try:
                    ticker = yf.Ticker(sym)
                    df = ticker.history(start=START_DATE, end=END_DATE, auto_adjust=False)
                    if not df.empty and len(df) > 50:
                        df.columns = [c.lower().replace(" ", "_") for c in df.columns]
                        fname = f"{sanitize_filename(sym)}.parquet"
                        df.to_parquet(os.path.join(CACHE_DIR, fname))
                        print(f"    -> Fallback saved {sym} ({len(df)} rows)", flush=True)
                except Exception as single_e:
                    print(f"    -> Fallback error {sym}: {single_e}", flush=True)
        time.sleep(0.5)


if __name__ == "__main__":
    download_benchmarks()
    download_universe()
    print("\nNSE caching complete!", flush=True)
