import os
from datetime import date, timedelta
import pandas as pd
import numpy as np
import pytest

from trading_system.app.data.intraday_archiver import IntradayBarArchiver


def generate_synthetic_day_bars(day: date, symbol: str, num_bars: int = 75, inject_bad_data: bool = False):
    """Generates 5-minute intraday bars for NSE trading session (9:15 AM to 3:30 PM)."""
    start_dt = pd.Timestamp(day).replace(hour=9, minute=15)
    timestamps = [start_dt + timedelta(minutes=5 * i) for i in range(num_bars)]

    np.random.seed(int(day.strftime("%d%m%Y")) % 10000 + len(symbol))
    base_price = 2500.0 if "RELIANCE" in symbol else 1500.0
    returns = np.random.normal(0.0001, 0.002, size=num_bars)
    prices = base_price * np.exp(np.cumsum(returns))

    df = pd.DataFrame({
        "timestamp": timestamps,
        "open": prices,
        "high": prices * 1.002,
        "low": prices * 0.998,
        "close": prices * (1 + np.random.normal(0, 0.001, num_bars)),
        "volume": np.random.randint(100, 10000, size=num_bars)
    })

    if inject_bad_data:
        # Inject 1 NaN row
        df.loc[2, "close"] = np.nan
        # Inject 1 impossible OHLC row (low > high)
        df.loc[5, "low"] = 9999.0
        # Inject 1 zero-volume bar
        df.loc[10, "volume"] = 0

    return df


def test_intraday_archiver_five_consecutive_days_and_green_quality_report(tmp_path):
    """
    Asserts that:
    1. Archiver processes 5 consecutive trading days.
    2. Writes partitioned Parquet files: YYYY-MM-DD.parquet.
    3. Validates and purges NaNs and impossible OHLC.
    4. Tracks zero volume bars.
    5. Produces a GREEN data quality report verifying all 5 consecutive days.
    """
    archiver = IntradayBarArchiver(storage_dir=str(tmp_path), interval="5m")

    symbols = ["RELIANCE.NS", "TCS.NS", "INFY.NS"]
    start_date = date(2026, 10, 26) # Monday
    consecutive_days = [start_date + timedelta(days=i) for i in range(5)] # Mon to Fri

    test_data_by_date = {}
    for day in consecutive_days:
        test_data_by_date[day] = {}
        for sym in symbols:
            # Inject slight bad data on INFY to test filter and quality tracking
            inject = (sym == "INFY.NS")
            test_data_by_date[day][sym] = generate_synthetic_day_bars(day, sym, num_bars=75, inject_bad_data=inject)

    # Execute multi-day archival
    report = archiver.archive_multi_day_dataset(consecutive_days, test_data_by_date)

    # 1. Assert quality report summary
    assert report["overall_status"] == "GREEN"
    assert report["consecutive_days_verified"] == 5
    assert report["days_processed"] == 5
    assert report["total_bars_archived"] > 1000
    assert report["total_zero_volume_bars"] == 5  # 1 per day on INFY

    # 2. Assert each consecutive daily Parquet file exists and verifies schema
    for day in consecutive_days:
        parquet_path = os.path.join(str(tmp_path), f"{day.isoformat()}.parquet")
        assert os.path.exists(parquet_path), f"Missing parquet file for {day}"

        loaded_df = pd.read_parquet(parquet_path)
        assert len(loaded_df) > 0
        assert set(["timestamp", "symbol", "open", "high", "low", "close", "volume"]).issubset(loaded_df.columns)

        # Confirm no NaNs or impossible OHLC survived validation
        assert not loaded_df[["open", "high", "low", "close"]].isna().any().any()
        assert (loaded_df["low"] <= loaded_df["high"]).all()
        assert (loaded_df["open"] <= loaded_df["high"]).all()
        assert (loaded_df["open"] >= loaded_df["low"]).all()
        assert (loaded_df["close"] <= loaded_df["high"]).all()
        assert (loaded_df["close"] >= loaded_df["low"]).all()

        # Confirm all 3 symbols exist in the partitioned file
        assert set(loaded_df["symbol"].unique()) == set(symbols)


def test_intraday_archiver_empty_dataset_handling(tmp_path):
    """Asserts that empty or corrupt data fails safely without creating corrupted Parquet files."""
    archiver = IntradayBarArchiver(storage_dir=str(tmp_path), interval="5m")
    target_day = date(2026, 11, 2)

    empty_map = {"RELIANCE.NS": pd.DataFrame()}
    fp, stats = archiver.archive_day(target_day, empty_map)

    assert fp is None
    assert stats["status"] == "EMPTY"
    assert not os.path.exists(os.path.join(str(tmp_path), f"{target_day.isoformat()}.parquet"))
