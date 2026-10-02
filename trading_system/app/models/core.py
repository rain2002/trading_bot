from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from trading_system.app.common.database import Base

class Experiment(Base):
    """Tracks research runs to guarantee reproducibility and prevent survivorship/look-ahead bias claims without evidence."""
    __tablename__ = "experiments"
    
    id = Column(Integer, primary_key=True, index=True)
    experiment_id = Column(String, unique=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    strategy_id = Column(String, index=True)
    strategy_version = Column(String)
    dataset_version = Column(String)
    parameters = Column(JSON)
    metrics = Column(JSON)

class Order(Base):
    """The central source of truth for the Order Management System state machine."""
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    client_order_id = Column(String, unique=True, index=True)
    symbol = Column(String, index=True)
    quantity = Column(Float)
    price = Column(Float)
    status = Column(String) # CREATED, SUBMITTED, FILLED, CANCELED, REJECTED
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    filled_at = Column(DateTime, nullable=True)

class Position(Base):
    """Internal ledger of open positions. Used for reconciliation against broker."""
    __tablename__ = "positions"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, unique=True, index=True)
    quantity = Column(Float)
    average_price = Column(Float)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
