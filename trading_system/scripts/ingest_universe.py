import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
import pandas as pd
from trading_system.app.common.database import engine
from trading_system.app.models.data import MarketBar
from sqlalchemy.orm import sessionmaker
from trading_system.app.data.yfinance_provider import YFinanceDataProvider

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def ingest_universe():
    print("="*50)
    print(">>> INGESTING CONTROLLED UNIVERSE (RAW BARS) <<<")
    print("="*50)
    
    # Phase 1: Small Controlled Universe
    universe = ["SPY", "AAPL", "MSFT"]
    
    start = datetime(2010, 1, 1)
    end = datetime(2023, 12, 31)
    
    provider = YFinanceDataProvider()
    db = SessionLocal()
    
    for sym in universe:
        print(f"Ingesting strictly unadjusted raw data for {sym}...")
        df = provider.fetch_historical_data(sym, start, end)
        
        if df.empty:
            continue
            
        # We need to drop the dynamically calculated adj_* columns, because we only want to store RAW data.
        # The engine will recalculate adj_* dynamically at runtime to prevent lookahead bias.
        cols_to_keep = ['open', 'high', 'low', 'close', 'volume', 'dividends', 'stock splits']
        # Rename 'stock splits' to 'stock_splits' to match the DB column
        df = df.rename(columns={'stock splits': 'stock_splits'})
        
        # Insert into Database (upsert)
        records = []
        for index, row in df.iterrows():
            bar = MarketBar(
                symbol=sym,
                timestamp=index.to_pydatetime(),
                open=float(row['open']),
                high=float(row['high']),
                low=float(row['low']),
                close=float(row['close']),
                volume=float(row['volume']),
                dividends=float(row.get('dividends', 0.0)),
                stock_splits=float(row.get('stock_splits', 0.0))
            )
            records.append(bar)
            
        # Bulk save
        try:
            # Simple insert (if it fails due to unique constraint, it means data is already there)
            db.bulk_save_objects(records)
            db.commit()
            print(f"SUCCESS: Ingested {len(records)} bars for {sym}")
        except Exception as e:
            db.rollback()
            print(f"WARNING: Data for {sym} already exists or error occurred (skipping).")
            
    db.close()
    print("\nIngestion Complete. Data is now secured locally in PostgreSQL.")

if __name__ == "__main__":
    # Ensure tables exist
    import trading_system.app.models.data
    from trading_system.app.common.database import Base
    Base.metadata.create_all(bind=engine)
    
    ingest_universe()
