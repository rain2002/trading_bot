"""
Phase 1 Causal Universe Generator: NSE Bhavcopy Trailing Liquidity Engine
========================================================================
Implements a 100% survivorship-bias-free, causal universe selection model:
1. Ingests official daily NSE Bhavcopy files (including delisted / defunct equities).
2. For each monthly rebalance date, analyzes the trailing 6-month window (126 trading days).
3. Computes the median daily turnover (Price x Volume / TOTTRDVAL) for all listed 'EQ' securities.
4. Filters out penny stocks (Price < INR 20.0).
5. Ranks all active securities and selects the Top N (e.g. 300 or 500) most liquid names.
6. Outputs a Point-In-Time monthly universe mapping without requiring index committee membership lists.
"""

import os
import sys
import io
import time
import zipfile
import urllib.request
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BHAVCOPY_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data", "bhavcopy_cache")
OUTPUT_UNIVERSE_JSON = os.path.join(PROJECT_ROOT, "trading_system", "data", "nse_causal_universe_monthly.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*"
}


def download_single_bhavcopy(date: pd.Timestamp, cache_dir: str = BHAVCOPY_DIR) -> Optional[pd.DataFrame]:
    """
    Downloads and caches a single day's NSE Bhavcopy.
    URL Format: https://archives.nseindia.com/content/historical/EQUITIES/<YEAR>/<MON>/cm<DD><MON><YEAR>bhav.csv.zip
    """
    os.makedirs(cache_dir, exist_ok=True)
    date_str = date.strftime("%d%b%Y").upper()
    year_str = date.strftime("%Y")
    month_str = date.strftime("%b").upper()
    csv_fname = f"cm{date_str}bhav.csv"
    cached_path = os.path.join(cache_dir, f"{csv_fname}.parquet")

    if os.path.exists(cached_path):
        return pd.read_parquet(cached_path)

    url = f"https://archives.nseindia.com/content/historical/EQUITIES/{year_str}/{month_str}/cm{date_str}bhav.csv.zip"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            zip_bytes = resp.read()
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            target_name = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
            with z.open(target_name) as f:
                df = pd.read_csv(f)
        
        # Standardize columns
        df.columns = [c.strip().upper() for c in df.columns]
        if "SERIES" in df.columns:
            df = df[df["SERIES"] == "EQ"].copy()
        
        # Keep essential columns
        cols = ["SYMBOL", "OPEN", "HIGH", "LOW", "CLOSE", "TOTTRDQTY", "TOTTRDVAL", "TIMESTAMP"]
        cols = [c for c in cols if c in df.columns]
        df = df[cols].copy()
        df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"], format="%d-%b-%Y", errors="coerce")
        df.to_parquet(cached_path)
        return df
    except Exception:
        # Market closed, weekend, or holiday
        return None


def compute_monthly_causal_universe(
    daily_records: List[pd.DataFrame],
    top_n: int = 500,
    min_price: float = 20.0,
    lookback_days: int = 126
) -> Dict[str, List[str]]:
    """
    Given a sequence of daily bhavcopy DataFrames, generates a Point-in-Time universe
    for each month-end based on trailing 6-month (126 trading days) median daily turnover.
    """
    if not daily_records:
        return {}

    full_df = pd.concat(daily_records, ignore_index=True)
    full_df = full_df.dropna(subset=["TIMESTAMP", "SYMBOL", "CLOSE", "TOTTRDVAL"])
    full_df["DATE"] = pd.to_datetime(full_df["TIMESTAMP"]).dt.normalize()

    unique_dates = sorted(full_df["DATE"].unique())
    if not unique_dates:
        return {}

    # Identify month-end rebalance dates
    df_dates = pd.DataFrame({"date": unique_dates})
    df_dates["month"] = df_dates["date"].dt.to_period("M")
    rebalance_dates = df_dates.groupby("month")["date"].max().tolist()

    monthly_universe: Dict[str, List[str]] = {}

    for reb_date in rebalance_dates:
        # Trailing 6 months (up to 126 trading days) ending on reb_date
        window_dates = [d for d in unique_dates if d <= reb_date][-lookback_days:]
        if len(window_dates) < 20:
            # Need at least 20 trading days of history
            continue

        window_df = full_df[full_df["DATE"].isin(window_dates)]

        # Latest close price on or before reb_date for penny stock filter
        latest_prices = window_df.sort_values("DATE").groupby("SYMBOL")["CLOSE"].last()
        valid_symbols = latest_prices[latest_prices >= min_price].index

        # Median daily turnover (TOTTRDVAL)
        median_turnover = (
            window_df[window_df["SYMBOL"].isin(valid_symbols)]
            .groupby("SYMBOL")["TOTTRDVAL"]
            .median()
            .sort_values(ascending=False)
        )

        selected_symbols = median_turnover.head(top_n).index.tolist()
        # Add .NS suffix for standard symbol mapping
        formatted_symbols = [f"{s}.NS" for s in selected_symbols]
        monthly_universe[reb_date.strftime("%Y-%m-%d")] = formatted_symbols

    return monthly_universe
