import pandas as pd
import yfinance as yf
from datetime import datetime
import hashlib
from typing import Optional
from trading_system.app.common.interfaces import DataProvider
from trading_system.app.data.validator import DataValidator
from trading_system.app.common.logger import get_logger

logger = get_logger("YFinanceProvider")

class YFinanceDataProvider(DataProvider):
    def fetch_historical_data(self, symbol: str, start_date: datetime, end_date: datetime, interval: str = '1d', **kwargs) -> pd.DataFrame:
        """
        Fetch data using yfinance, run it through the validator, and attach a lineage hash 
        to guarantee research reproducibility.
        """
        logger.info(f"Fetching yfinance data for {symbol} from {start_date.date()} to {end_date.date()}")
        
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start_date, end=end_date, interval=interval)
        
        if df.empty:
            logger.warning(f"No data returned for {symbol}")
            return df
            
        # Normalize index and columns
        if 'Datetime' in df.columns or df.index.name == 'Datetime':
            df.index.name = 'timestamp'
        elif 'Date' in df.columns or df.index.name == 'Date':
            df.index.name = 'timestamp'
            
        df.columns = [col.lower() for col in df.columns]
        
        # 1. Run rigorous validation
        df = DataValidator.validate_ohlcv(df, symbol)
        
        # 2. Attach lineage / versioning metadata directly to the DataFrame attrs
        # This ensures any experiment using this frame can record exactly what data it saw.
        dataset_hash = hashlib.sha256(pd.util.hash_pandas_object(df, index=True).values).hexdigest()[:12]
        
        df.attrs['lineage'] = {
            'provider': 'yfinance',
            'symbol': symbol,
            'retrieval_timestamp': datetime.utcnow().isoformat() + "Z",
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'interval': interval,
            'version_hash': dataset_hash
        }
        
        logger.info(f"Dataset securely versioned with hash: {dataset_hash}")
        
        return df
