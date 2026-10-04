import pytest
import pandas as pd
from datetime import datetime
from trading_system.app.strategies.library.debug001_random_walk import DEBUG001_RandomWalk
from trading_system.app.portfolio.basic import BasicPortfolio
from trading_system.app.risk.basic import BasicRiskEngine
from trading_system.app.portfolio.constructor import EqualWeightPortfolioConstructor
from trading_system.app.execution.paper import PaperExecutionAdapter
from trading_system.app.backtesting.multi_asset_engine import MultiAssetBacktester
from trading_system.app.reporting.performance import QuantitativePerformanceAnalyzer
from trading_system.app.common.database import engine, Base
from sqlalchemy.orm import sessionmaker

# We use the YFinanceDataProvider for testing because the DB might not be populated in CI
from trading_system.app.data.yfinance_provider import YFinanceDataProvider

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def test_random_walk_has_no_alpha():
    """
    V2 Leakage Prevention Test.
    Ensures that randomly entering and exiting trades does not accidentally
    generate consistent Alpha due to future-data leakage in the event engine.
    """
    start = datetime(2020, 1, 1)
    end = datetime(2023, 12, 31)
    
    data_provider = YFinanceDataProvider()
    strategy = DEBUG001_RandomWalk(seed=42) # Fixed seed
    portfolio = BasicPortfolio(initial_cash=100000.0)
    risk_engine = BasicRiskEngine(max_position_size=100000)
    constructor = EqualWeightPortfolioConstructor()
    execution = PaperExecutionAdapter()
    
    db = SessionLocal()
    
    backtester = MultiAssetBacktester(
        data_provider, strategy, portfolio, risk_engine, constructor, execution, db_session=db
    )
    
    import time
    backtester.run(symbols=["SPY"], start_date=start, end_date=end, experiment_id=f"PYTEST-LEAK-001-{int(time.time())}")
    
    analyzer = QuantitativePerformanceAnalyzer()
    equity_series = pd.Series(backtester.equity_curve)
    metrics = analyzer.calculate_metrics([], equity_series)
    
    sharpe = metrics.get("Sharpe_Ratio", 0.0)
    
    # A randomly guessing strategy, combined with transaction friction (or even without it)
    # should NOT generate a Sharpe Ratio > 1.0. If it does, the engine is leaking future execution prices.
    assert sharpe < 1.0, f"Leakage detected! Random Walk achieved anomalous Sharpe Ratio: {sharpe}"
    
    db.close()
