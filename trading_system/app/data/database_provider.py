import pandas as pd
from datetime import datetime
from trading_system.app.common.interfaces import PointInTimeDataProvider
from trading_system.app.models.data import MarketBar
from trading_system.app.common.logger import get_logger
from trading_system.app.data.corporate_actions import CorporateActionProcessor

logger = get_logger("DatabaseProvider")

class DatabaseDataProvider(PointInTimeDataProvider):
    """
    V2 Institutional Data Provider.
    Queries strictly from the local PostgreSQL database, ensuring that only data 
    available ON OR BEFORE the `current_time` is ever returned to a strategy.
    It automatically dynamically calculates point-in-time adjusted prices.
    """
    def __init__(self, db_session):
        self.db = db_session

    def get_data_as_of(self, symbol: str, current_time: datetime) -> pd.DataFrame:
        query = self.db.query(MarketBar).filter(
            MarketBar.symbol == symbol,
            MarketBar.timestamp <= current_time
        ).order_by(MarketBar.timestamp.asc())
        
        # Read directly into pandas
        # This approach ensures absolute point-in-time constraints.
        df = pd.read_sql(query.statement, self.db.bind)
        
        if df.empty:
            return df
            
        df.set_index('timestamp', inplace=True)
        
        # At this point, the DataFrame is purely RAW execution prices.
        # We must now apply the Corporate Actions backwards from `current_time`
        # so that technical analysis (RSI, Moving Averages) functions smoothly.
        # Because we queried with `timestamp <= current_time`, the CorporateActionProcessor
        # has absolutely no knowledge of future stock splits.
        df['stock splits'] = df['stock_splits'] # Align with processor expectations
        df = CorporateActionProcessor.calculate_adjustment_factors(df)
        
        return df

    def fetch_historical_data(self, symbol: str, start_date: datetime, end_date: datetime, **kwargs) -> pd.DataFrame:
        """
        Maintains backwards compatibility for the MultiAssetBacktester which handles its own PIT slicing.
        """
        query = self.db.query(MarketBar).filter(
            MarketBar.symbol == symbol,
            MarketBar.timestamp >= start_date,
            MarketBar.timestamp <= end_date
        ).order_by(MarketBar.timestamp.asc())
        
        df = pd.read_sql(query.statement, self.db.bind)
        if df.empty:
            return df
            
        df.set_index('timestamp', inplace=True)
        df['stock splits'] = df['stock_splits']
        df = CorporateActionProcessor.calculate_adjustment_factors(df)
        return df
