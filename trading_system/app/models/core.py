from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from trading_system.app.common.database import Base

class Strategy(Base):
    """Strategy Registry: metadata and status for strategies."""
    __tablename__ = "strategies"
    
    id = Column(Integer, primary_key=True, index=True)
    strategy_id = Column(String, unique=True, index=True)
    name = Column(String)
    author = Column(String, nullable=True)
    description = Column(String, nullable=True)
    status = Column(String, default="RESEARCH") # RESEARCH, CANDIDATE, VALIDATED, PAPER, CANARY, PRODUCTION, RETIRED
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class StrategyVersion(Base):
    """Versions of a specific strategy."""
    __tablename__ = "strategy_versions"
    
    id = Column(Integer, primary_key=True, index=True)
    strategy_id = Column(String, ForeignKey("strategies.strategy_id"), index=True)
    version = Column(String, index=True)
    git_commit = Column(String, nullable=True)
    parameters = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    strategy = relationship("Strategy", backref="versions")

class Experiment(Base):
    """Tracks research runs to guarantee reproducibility and prevent survivorship/look-ahead bias claims without evidence."""
    __tablename__ = "experiments"
    
    id = Column(Integer, primary_key=True, index=True)
    experiment_id = Column(String, unique=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    strategy_id = Column(String, index=True)
    strategy_version = Column(String)
    dataset_version = Column(String)
    git_commit = Column(String, nullable=True)
    universe = Column(String, nullable=True)
    training_period = Column(String, nullable=True)
    execution_assumptions = Column(JSON, nullable=True)
    parameters = Column(JSON)
    metrics = Column(JSON)

class PortfolioDecision(Base):
    """Audit trail of portfolio decisions BEFORE they become orders."""
    __tablename__ = "portfolio_decisions"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    strategy_id = Column(String, index=True)
    experiment_id = Column(String, index=True, nullable=True)
    symbol = Column(String, index=True)
    target_weight = Column(Float)
    confidence = Column(Float, nullable=True)
    decision_metadata = Column(JSON, nullable=True) # Used to store reasons, risk limits applied, etc.

class Order(Base):
    """The central source of truth for the Order Management System state machine."""
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    client_order_id = Column(String, unique=True, index=True)
    symbol = Column(String, index=True)
    quantity = Column(Float)
    price = Column(Float)
    side = Column(String, nullable=True) # buy or sell
    status = Column(String) # CREATED, SUBMITTED, PARTIALLY_FILLED, FILLED, CANCELED, REJECTED
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class Fill(Base):
    """Tracks individual executions of an order (partial or full)."""
    __tablename__ = "fills"
    
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), index=True)
    fill_id = Column(String, unique=True, index=True) # Broker's fill ID
    quantity = Column(Float)
    price = Column(Float)
    commission = Column(Float, default=0.0)
    slippage = Column(Float, default=0.0)
    filled_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    order = relationship("Order", backref="fills")

class Position(Base):
    """Internal ledger of open positions. Used for reconciliation against broker."""
    __tablename__ = "positions"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, unique=True, index=True)
    quantity = Column(Float)
    average_price = Column(Float)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class Account(Base):
    """Internal accounting of cash and equity."""
    __tablename__ = "accounts"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    cash = Column(Float, default=0.0)
    equity = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class PerformanceSnapshot(Base):
    """Daily or intraday performance snapshots for accounting and charting."""
    __tablename__ = "performance_snapshots"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), index=True)
    cash = Column(Float)
    equity = Column(Float)
    realized_pnl = Column(Float, default=0.0)
    unrealized_pnl = Column(Float, default=0.0)
    drawdown = Column(Float, default=0.0)

class RiskEvent(Base):
    """Audit log for the Risk Engine overrides and actions."""
    __tablename__ = "risk_events"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    event_type = Column(String, index=True) # e.g. 'LIMIT_BREACH', 'POSITION_REDUCED', 'KILL_SWITCH'
    description = Column(String)
    symbol = Column(String, nullable=True, index=True)
    strategy_id = Column(String, nullable=True)
    action_taken = Column(String)

class SystemEvent(Base):
    """Tracks system health, broker disconnects, and data anomalies."""
    __tablename__ = "system_events"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    component = Column(String, index=True) # e.g., 'DATA_INGESTION', 'BROKER_API'
    level = Column(String) # INFO, WARNING, ERROR, CRITICAL
    message = Column(String)
    event_metadata = Column(JSON, nullable=True)
