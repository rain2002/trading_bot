import pytest
from datetime import datetime
from trading_system.app.data.synthetic import SyntheticDataProvider
from trading_system.app.strategies.dummy import DummyMovingAverageStrategy
from trading_system.app.portfolio.basic import BasicPortfolio
from trading_system.app.risk.basic import BasicRiskEngine
from trading_system.app.execution.paper import PaperExecutionAdapter
from trading_system.app.backtesting.engine import MinimalBacktestEngine

def test_minimal_synthetic_pipeline():
    """
    Test the architectural end-to-end pipeline using purely synthetic components 
    to verify interfaces communicate correctly without leakage or bypassing risk.
    """
    start = datetime(2026, 1, 1)
    end = datetime(2026, 3, 1)
    
    data_provider = SyntheticDataProvider()
    strategy = DummyMovingAverageStrategy(fast_window=2, slow_window=5)
    portfolio = BasicPortfolio(initial_cash=10000.0)
    risk = BasicRiskEngine(max_position_size=20) # Strict risk limit
    execution = PaperExecutionAdapter()
    
    engine = MinimalBacktestEngine(
        data_provider=data_provider,
        strategy=strategy,
        portfolio=portfolio,
        risk_engine=risk,
        execution_adapter=execution
    )
    
    final_portfolio = engine.run("FAKE_TICKER", start, end)
    
    positions = final_portfolio.get_positions()
    
    # 1. Assert a position was taken (strategy generated valid signals)
    assert "FAKE_TICKER" in positions
    
    # 2. Assert risk engine correctly blocked trades that exceeded the limit of 20
    assert abs(positions["FAKE_TICKER"]) <= 20
    
    # 3. Assert cash was mutated correctly based on executions (portfolio update logic)
    assert final_portfolio.cash != 10000.0
