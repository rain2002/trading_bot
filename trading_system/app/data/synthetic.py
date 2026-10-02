import pandas as pd
import numpy as np
from datetime import datetime
from trading_system.app.common.interfaces import DataProvider

class SyntheticDataProvider(DataProvider):
    def fetch_historical_data(self, symbol: str, start_date: datetime, end_date: datetime, **kwargs) -> pd.DataFrame:
        """Generate a random walk OHLCV dataset for synthetic testing."""
        dates = pd.date_range(start=start_date, end=end_date, freq='B')
        np.random.seed(42) # Deterministic for reproducible tests
        
        returns = np.random.normal(loc=0.0001, scale=0.01, size=len(dates))
        price_series = 100.0 * np.exp(np.cumsum(returns))
        
        df = pd.DataFrame({
            'timestamp': dates,
            'open': price_series * np.random.uniform(0.99, 1.01, len(dates)),
            'high': price_series * np.random.uniform(1.0, 1.02, len(dates)),
            'low': price_series * np.random.uniform(0.98, 1.0, len(dates)),
            'close': price_series,
            'volume': np.random.randint(1000, 100000, len(dates))
        })
        
        # Ensure high is highest, low is lowest
        df['high'] = df[['open', 'close', 'high']].max(axis=1)
        df['low'] = df[['open', 'close', 'low']].min(axis=1)
        
        return df.set_index('timestamp')
