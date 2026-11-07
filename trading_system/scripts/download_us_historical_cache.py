"""
Institutional Downloader & Parquet Cacher for US Growth Equities
================================================================
Fetches split-adjusted historical OHLCV + corporate actions from 2000-01-01 to 2025-12-31.
Saves to trading_system/data/historical_cache_us/{ticker}.parquet
"""

import os
import sys
import time
import pandas as pd
import yfinance as yf

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CACHE_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data", "historical_cache_us")
TICKERS_FILE = os.path.join(PROJECT_ROOT, "trading_system", "data", "us_growth_tickers.txt")
os.makedirs(CACHE_DIR, exist_ok=True)


def download_symbol(sym: str) -> bool:
    target_path = os.path.join(CACHE_DIR, f"{sym}.parquet")
    if os.path.exists(target_path) and os.path.getsize(target_path) > 1000:
        return True
    try:
        t = yf.Ticker(sym)
        df = t.history(start="2000-01-01", end="2025-12-31", auto_adjust=False)
        if df.empty or len(df) < 50:
            print(f"  [WARN] {sym}: Insufficient data ({len(df)} rows)")
            return False
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        df.index = pd.to_datetime(df.index.date)
        df.columns = [c.lower().replace(" ", "_") for c in df.columns]
        df.to_parquet(target_path)
        return True
    except Exception as e:
        print(f"  [ERROR] {sym}: {e}")
        return False


def main():
    with open(TICKERS_FILE, "r") as f:
        tickers = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    print(f"Starting historical download for {len(tickers)} US growth tickers...")
    t0 = time.time()
    success = 0
    for i, s in enumerate(tickers):
        ok = download_symbol(s)
        if ok:
            success += 1
        if (i + 1) % 15 == 0 or (i + 1) == len(tickers):
            print(f"  Progress: {i+1}/{len(tickers)} symbols downloaded ({time.time()-t0:.1f}s)...")
    print(f"Finished: {success}/{len(tickers)} symbols cached in {time.time()-t0:.2f}s.")


if __name__ == "__main__":
    main()
