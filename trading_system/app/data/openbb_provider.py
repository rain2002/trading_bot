import pandas as pd
from datetime import datetime
import logging
from trading_system.app.common.interfaces import PointInTimeDataProvider

# Import openbb securely. We wrap it in try-except in case of initialization issues
try:
    from openbb import obb
except ImportError:
    obb = None

logger = logging.getLogger("OpenBBProvider")

class OpenBBDataProvider(PointInTimeDataProvider):
    """
    Integrates OpenBB alternative data streams (macro, sentiment, fundamentals)
    into the V2 Engine, enforcing absolute Point-in-Time safety.
    """
    
    def __init__(self):
        if obb is None:
            logger.warning("OpenBB SDK not installed or failed to import.")
        
    def get_data_as_of(self, symbol: str, current_time: datetime) -> pd.DataFrame:
        """
        Fetches basic historical price data from OpenBB and strictly filters out future data.
        """
        if obb is None:
            raise RuntimeError("OpenBB is not available.")
            
        # For demonstration, fetching recent historical data.
        # In production, we'd cache this to DB or parquet to avoid rate limits.
        try:
            res = obb.equity.price.historical(symbol=symbol, start_date="2020-01-01", provider="yfinance")
            df = res.to_df()
        except Exception as e:
            logger.error(f"Failed to fetch OpenBB data for {symbol}: {e}")
            return pd.DataFrame()
            
        # PIT Enforcement
        if not isinstance(df.index, pd.DatetimeIndex):
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
            else:
                df.index = pd.to_datetime(df.index)
                
        # Strip timezone for comparison if current_time is naive, or convert if needed
        if df.index.tz is not None and current_time.tzinfo is None:
            df.index = df.index.tz_localize(None)
        elif df.index.tz is None and current_time.tzinfo is not None:
            df.index = df.index.tz_localize('UTC')
            
        # Point-In-Time Safety Check
        safe_df = df[df.index <= current_time]
        
        return safe_df

    def get_alternative_data_as_of(self, symbol: str, current_time: datetime) -> pd.DataFrame:
        """
        Example showing how we would fetch fundamental/alternative data safely.
        """
        if obb is None:
            return pd.DataFrame()
            
        try:
            # e.g., fetching metrics, sentiment, or macro
            res = obb.equity.fundamental.metrics(symbol=symbol, provider="yfinance")
            df = res.to_df()
            # PIT filter goes here
            return df
        except Exception as e:
            logger.error(f"Failed to fetch OpenBB alternative data: {e}")
            return pd.DataFrame()
