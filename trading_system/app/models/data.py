from sqlalchemy import Column, Integer, String, Float, DateTime, Index, Boolean, Date
from datetime import datetime, timezone
from trading_system.app.common.database import Base

class Instrument(Base):
    """Tracks tradable universe, metadata, and status."""
    __tablename__ = "instruments"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True)
    asset_class = Column(String, default="equity")
    is_active = Column(Boolean, default=True)
    tick_size = Column(Float, nullable=True)
    added_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class MarketBar(Base):
    """Raw execution prices (unadjusted) strictly for Point-In-Time reconstruction."""
    __tablename__ = "market_bars"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True, nullable=False)
    timestamp = Column(DateTime, index=True, nullable=False)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    
    # We keep these for convenience if needed, but CorporateAction table is the source of truth
    dividends = Column(Float, default=0.0)
    stock_splits = Column(Float, default=0.0)
    
    # Composite index for ultra-fast point-in-time querying
    __table_args__ = (
        Index('idx_symbol_timestamp', 'symbol', 'timestamp', unique=True),
    )

class CorporateAction(Base):
    """Explicitly tracks splits, reverse splits, cash dividends, symbol changes, etc."""
    __tablename__ = "corporate_actions"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True, nullable=False)
    ex_date = Column(Date, index=True, nullable=False)
    action_type = Column(String, nullable=False) # e.g., 'dividend', 'split', 'reverse_split', 'delisting'
    value = Column(Float, nullable=False) # Cash amount or split ratio
    recorded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class DatasetVersion(Base):
    """Tracks versions of the ingested dataset to guarantee experiment reproducibility."""
    __tablename__ = "dataset_versions"
    
    id = Column(Integer, primary_key=True, index=True)
    version_name = Column(String, unique=True, index=True, nullable=False)
    description = Column(String, nullable=True)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
