import os
import logging
from datetime import datetime, date, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple
import pandas as pd
import numpy as np

from trading_system.app.common.logger import get_logger

logger = get_logger("IntradayArchiver")


class IntradayBarArchiver:
    """
    Read-only intraday bar archiver for the Indian equity universe.
    Archives raw intraday bars into partitioned Parquet files:
    storage_dir/YYYY-MM-DD.parquet
    """

    def __init__(
        self,
        storage_dir: Optional[str] = None,
        interval: str = "5m"
    ):
        base_dir = storage_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data", "historical", "intraday"
        )
        self.storage_dir = os.path.abspath(base_dir)
        self.interval = interval
        os.makedirs(self.storage_dir, exist_ok=True)

    def load_universe(self, universe_path: Optional[str] = None) -> List[str]:
        """Loads ticker symbols from nse_tickers.txt or configured path."""
        if universe_path is None:
            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            universe_path = os.path.join(root_dir, "data", "nse_tickers.txt")

        if not os.path.exists(universe_path):
            logger.warning(f"Universe file {universe_path} not found. Returning default list.")
            return ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS"]

        symbols = []
        with open(universe_path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s and not s.startswith("#"):
                    if not s.endswith(".NS"):
                        s = f"{s}.NS"
                    symbols.append(s)
        return symbols

    def validate_bars(self, df: pd.DataFrame, symbol: str) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Validates OHLCV bars:
        - Drops duplicates
        - Checks for NaNs in required columns
        - Rejects non-positive prices
        - Rejects low > high, open/close out of range
        - Counts zero-volume bars
        """
        stats: Dict[str, Any] = {
            "symbol": symbol,
            "raw_bars": len(df),
            "valid_bars": 0,
            "dropped_nan_or_negative": 0,
            "dropped_impossible_ohlc": 0,
            "zero_volume_bars": 0,
            "status": "GREEN"
        }

        if df is None or df.empty:
            stats["status"] = "EMPTY"
            return pd.DataFrame(), stats

        clean_df = df.copy()

        # Normalize column names
        clean_df.columns = [c.lower() for c in clean_df.columns]

        required = ["open", "high", "low", "close", "volume"]
        missing = [c for c in required if c not in clean_df.columns]
        if missing:
            stats["status"] = "CORRUPT_MISSING_COLUMNS"
            logger.error(f"{symbol}: Missing columns {missing}")
            return pd.DataFrame(), stats

        # Ensure timestamp is a column or index
        if "timestamp" not in clean_df.columns:
            if isinstance(clean_df.index, pd.DatetimeIndex):
                clean_df = clean_df.reset_index()
                clean_df.rename(columns={clean_df.columns[0]: "timestamp"}, inplace=True)
            else:
                stats["status"] = "MISSING_TIMESTAMP"
                return pd.DataFrame(), stats

        # 1. Deduplicate by timestamp
        clean_df = clean_df.drop_duplicates(subset=["timestamp"], keep="first")

        # 2. Check NaNs and non-positive prices
        nan_or_neg = (
            clean_df[required].isna().any(axis=1) |
            (clean_df["open"] <= 0) |
            (clean_df["high"] <= 0) |
            (clean_df["low"] <= 0) |
            (clean_df["close"] <= 0)
        )
        stats["dropped_nan_or_negative"] = int(nan_or_neg.sum())
        clean_df = clean_df[~nan_or_neg]

        # 3. Check impossible OHLC (low > high, open/close out of high/low bounds)
        impossible = (
            (clean_df["low"] > clean_df["high"]) |
            (clean_df["open"] > clean_df["high"]) |
            (clean_df["open"] < clean_df["low"]) |
            (clean_df["close"] > clean_df["high"]) |
            (clean_df["close"] < clean_df["low"])
        )
        stats["dropped_impossible_ohlc"] = int(impossible.sum())
        clean_df = clean_df[~impossible]

        # 4. Check zero-volume bars (retained for research, but logged)
        zero_vol = (clean_df["volume"] == 0)
        stats["zero_volume_bars"] = int(zero_vol.sum())

        stats["valid_bars"] = len(clean_df)

        # Quality status determination
        total_dropped = stats["dropped_nan_or_negative"] + stats["dropped_impossible_ohlc"]
        if stats["raw_bars"] == 0 or stats["valid_bars"] == 0:
            stats["status"] = "RED"
        elif total_dropped / max(1, stats["raw_bars"]) > 0.05:
            stats["status"] = "YELLOW"
        else:
            stats["status"] = "GREEN"

        clean_df["symbol"] = symbol
        return clean_df, stats

    def archive_day(
        self,
        day_date: date,
        symbol_data_map: Dict[str, pd.DataFrame]
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        """
        Consolidates validated symbol data for a single trading day and writes to:
        storage_dir/YYYY-MM-DD.parquet
        """
        all_dfs = []
        day_stats = {
            "date": day_date.isoformat(),
            "symbols_processed": len(symbol_data_map),
            "symbols_successful": 0,
            "total_bars": 0,
            "zero_volume_bars": 0,
            "status": "GREEN"
        }

        for sym, raw_df in symbol_data_map.items():
            valid_df, stat = self.validate_bars(raw_df, sym)
            if not valid_df.empty:
                # Filter specifically for this date
                valid_df["date_part"] = pd.to_datetime(valid_df["timestamp"]).dt.date
                day_df = valid_df[valid_df["date_part"] == day_date].drop(columns=["date_part"])
                if not day_df.empty:
                    all_dfs.append(day_df)
                    day_stats["symbols_successful"] += 1
                    day_stats["total_bars"] += len(day_df)
                    day_stats["zero_volume_bars"] += stat["zero_volume_bars"]

        if not all_dfs:
            day_stats["status"] = "EMPTY"
            return None, day_stats

        combined_df = pd.concat(all_dfs, ignore_index=True)
        # Ensure timestamp is standardized
        combined_df["timestamp"] = pd.to_datetime(combined_df["timestamp"])
        combined_df = combined_df.sort_values(by=["symbol", "timestamp"]).reset_index(drop=True)

        # Write to partitioned Parquet file
        file_name = f"{day_date.isoformat()}.parquet"
        file_path = os.path.join(self.storage_dir, file_name)
        combined_df.to_parquet(file_path, index=False, engine="pyarrow")
        logger.info(f"Archived {len(combined_df)} bars across {day_stats['symbols_successful']} symbols into {file_path}")

        return file_path, day_stats

    def archive_multi_day_dataset(
        self,
        dates: List[date],
        symbol_data_map_by_date: Dict[date, Dict[str, pd.DataFrame]]
    ) -> Dict[str, Any]:
        """
        Archives multiple trading days and produces a comprehensive Data Quality Report.
        """
        overall_report: Dict[str, Any] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "interval": self.interval,
            "storage_dir": self.storage_dir,
            "days_processed": len(dates),
            "consecutive_days_verified": 0,
            "total_bars_archived": 0,
            "total_zero_volume_bars": 0,
            "daily_reports": [],
            "overall_status": "GREEN"
        }

        for day in sorted(dates):
            day_map = symbol_data_map_by_date.get(day, {})
            fp, d_stat = self.archive_day(day, day_map)
            d_stat["file_path"] = fp
            overall_report["daily_reports"].append(d_stat)

            if fp and os.path.exists(fp) and d_stat["total_bars"] > 0:
                overall_report["consecutive_days_verified"] += 1
                overall_report["total_bars_archived"] += d_stat["total_bars"]
                overall_report["total_zero_volume_bars"] += d_stat["zero_volume_bars"]
            else:
                overall_report["overall_status"] = "RED"

        if overall_report["consecutive_days_verified"] < len(dates):
            overall_report["overall_status"] = "RED"

        return overall_report
