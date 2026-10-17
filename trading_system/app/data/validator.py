import pandas as pd
from trading_system.app.common.logger import get_logger

logger = get_logger("DataValidator")

class DataValidator:
    @staticmethod
    def validate_ohlcv(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """
        Validates the dataset according to rigorous quantitative standards.
        Drops or quarantines invalid rows and logs warnings to prevent garbage-in-garbage-out.
        """
        original_len = len(df)
        if original_len == 0:
            logger.warning(f"Empty dataset provided for {symbol}")
            return df
            
        # 1. Remove duplicate timestamps
        df = df[~df.index.duplicated(keep='first')]
        
        # 2. Check for missing required fields
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            logger.error(f"Dataset for {symbol} missing columns: {missing}")
            raise ValueError(f"Missing required columns: {missing}")
            
        # 3. Check for NaNs and non-positive prices
        nan_mask = df[required_cols].isna().any(axis=1)
        non_positive_mask = (df['open'] <= 0) | (df['high'] <= 0) | (df['low'] <= 0) | (df['close'] <= 0)
        invalid_prices_mask = nan_mask | non_positive_mask
        if invalid_prices_mask.any():
            logger.warning(f"Found {invalid_prices_mask.sum()} rows with NaN or <=0 prices for {symbol}. Dropping.")
            df = df[~invalid_prices_mask]
            
        # 4. Check impossible OHLC relationships (e.g., low > high)
        impossible_ohlc_mask = (
            (df['low'] > df['high']) | 
            (df['open'] > df['high']) | 
            (df['open'] < df['low']) | 
            (df['close'] > df['high']) | 
            (df['close'] < df['low'])
        )
        if impossible_ohlc_mask.any():
            logger.warning(f"Found {impossible_ohlc_mask.sum()} rows with impossible OHLC relationships for {symbol}. Dropping.")
            df = df[~impossible_ohlc_mask]
            
        final_len = len(df)
        if final_len < original_len:
            logger.info(f"Data validation for {symbol}: Dropped {original_len - final_len} invalid rows.")
            
        return df
