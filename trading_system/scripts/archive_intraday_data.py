import sys
import os
import argparse
import logging
from datetime import datetime, date, timedelta, timezone
import pandas as pd
import yfinance as yf

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from trading_system.app.data.intraday_archiver import IntradayBarArchiver

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("IntradayArchiverScript")


def run_archival(days_back: int = 5, interval: str = "5m", max_symbols: int = 100):
    """
    Downloads intraday bars for the Nifty 100 universe and archives to Parquet files.
    """
    archiver = IntradayBarArchiver(interval=interval)
    symbols = archiver.load_universe()[:max_symbols]
    logger.info(f"Targeting {len(symbols)} tickers for intraday archival ({interval}).")

    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=days_back + 4) # Fetch extra days to cover weekends/holidays

    # Download data symbol by symbol or batch
    symbol_data_by_date = {}

    for sym in symbols:
        try:
            ticker = yf.Ticker(sym)
            df = ticker.history(start=start_dt.strftime("%Y-%m-%d"), end=end_dt.strftime("%Y-%m-%d"), interval=interval, auto_adjust=False)
            if df.empty:
                continue

            df.columns = [c.lower() for c in df.columns]
            if "timestamp" not in df.columns:
                df = df.reset_index()
                df.rename(columns={df.columns[0]: "timestamp"}, inplace=True)

            df["date_part"] = pd.to_datetime(df["timestamp"]).dt.date
            for d_part, group in df.groupby("date_part"):
                if d_part not in symbol_data_by_date:
                    symbol_data_by_date[d_part] = {}
                symbol_data_by_date[d_part][sym] = group.drop(columns=["date_part"])
        except Exception as e:
            logger.warning(f"Failed to fetch {sym}: {e}")

    # Process most recent trading days
    available_dates = sorted(list(symbol_data_by_date.keys()))[-days_back:]
    logger.info(f"Archiving {len(available_dates)} trading days: {available_dates}")

    report = archiver.archive_multi_day_dataset(available_dates, symbol_data_by_date)
    logger.info(f"Archival complete. Overall Status: {report['overall_status']}")
    logger.info(f"Days verified: {report['consecutive_days_verified']}/{len(available_dates)}")
    logger.info(f"Total bars archived: {report['total_bars_archived']}")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Archive Indian Equity Intraday Bars")
    parser.add_argument("--days", type=int, default=5, help="Number of trading days to archive")
    parser.add_argument("--interval", type=str, default="5m", help="Intraday bar interval")
    parser.add_argument("--max_symbols", type=int, default=100, help="Maximum symbols to archive")
    args = parser.parse_args()

    run_archival(days_back=args.days, interval=args.interval, max_symbols=args.max_symbols)
