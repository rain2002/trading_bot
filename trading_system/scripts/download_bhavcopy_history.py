"""
Multi-Threaded Historical NSE Bhavcopy Downloader (2007 - 2024)
==============================================================
Downloads daily official Bhavcopy archives from archives.nseindia.com
into trading_system/data/bhavcopy_cache/ as compressed Parquets.
"""

import os
import sys
import time
import pandas as pd
import concurrent.futures
from datetime import datetime

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

BHAVCOPY_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data", "bhavcopy_cache")
os.makedirs(BHAVCOPY_DIR, exist_ok=True)

from trading_system.scripts.build_causal_bhavcopy_universe import download_single_bhavcopy

START_DATE = "2007-09-01"
END_DATE = "2024-12-31"


def download_all_bhavcopies(max_workers: int = 16):
    dates = pd.date_range(START_DATE, END_DATE, freq="B")
    total_dates = len(dates)
    print(f"=== Starting Download of {total_dates} Business Days ({START_DATE} to {END_DATE}) ===", flush=True)

    # Filter out already downloaded
    existing_files = set(os.listdir(BHAVCOPY_DIR))
    needed_dates = []
    for d in dates:
        fname = f"cm{d.strftime('%d%b%Y').upper()}bhav.csv.parquet"
        if fname not in existing_files:
            needed_dates.append(d)

    print(f"Already cached: {total_dates - len(needed_dates)} | Remaining to download: {len(needed_dates)}", flush=True)

    if not needed_dates:
        print("All historical bhavcopies are already cached!", flush=True)
        return

    t0 = time.time()
    downloaded = 0
    failed_or_holiday = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_date = {executor.submit(download_single_bhavcopy, d, BHAVCOPY_DIR): d for d in needed_dates}
        
        for i, future in enumerate(concurrent.futures.as_completed(future_to_date)):
            res = future.result()
            if res is not None:
                downloaded += 1
            else:
                failed_or_holiday += 1

            if (i + 1) % 250 == 0 or (i + 1) == len(needed_dates):
                elapsed = time.time() - t0
                rate = (i + 1) / max(elapsed, 0.001)
                print(f"  Progress: {i+1}/{len(needed_dates)} days processed ({downloaded} valid days, {failed_or_holiday} holidays/closed) [{rate:.1f} days/sec]", flush=True)

    total_files = len([f for f in os.listdir(BHAVCOPY_DIR) if f.endswith(".parquet")])
    print(f"\n[DONE] Finished download! Total cached trading days in {BHAVCOPY_DIR}: {total_files}", flush=True)


if __name__ == "__main__":
    download_all_bhavcopies()
