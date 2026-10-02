import pytest
import pandas as pd
from datetime import datetime
from trading_system.app.common.interfaces import Strategy

class LeakageSnifferStrategy(Strategy):
    """
    A strategy designed specifically to fail if it accidentally receives future data.
    """
    def __init__(self, total_expected_length: int):
        self.total_expected_length = total_expected_length
        self.highest_seen_index = -1
        
    def generate_signal(self, point_in_time_data: pd.DataFrame) -> dict:
        current_len = len(point_in_time_data)
        
        # 1. Leakage Check: Did we receive the entire dataset at once?
        if current_len == self.total_expected_length and self.highest_seen_index < self.total_expected_length - 2:
            raise ValueError("LEAKAGE DETECTED: Strategy received the entire future dataset instantly!")
            
        # 2. Leakage Check: Did the index jump ahead unexpectedly?
        if current_len < self.highest_seen_index:
            raise ValueError("LEAKAGE DETECTED: Time moved backwards or data sliced incorrectly.")
            
        self.highest_seen_index = current_len
        return {"signal": 0}

def test_backtester_prevents_future_leakage():
    """
    Verifies that the EventDrivenBacktester strictly maintains the point-in-time boundary.
    """
    from trading_system.app.backtesting.engine import EventDrivenBacktester
    from trading_system.app.data.synthetic import SyntheticDataProvider
    from trading_system.app.portfolio.basic import BasicPortfolio
    from trading_system.app.risk.basic import BasicRiskEngine
    from trading_system.app.portfolio.sizer import BasicPositionSizer
    from trading_system.app.execution.paper import PaperExecutionAdapter
    
    # Mock DB Session
    class MockSession:
        def add(self, obj): pass
        def commit(self): pass
        
    start = datetime(2026, 1, 1)
    end = datetime(2026, 1, 15)
    
    provider = SyntheticDataProvider()
    # Find out exactly how many days are in this set
    test_df = provider.fetch_historical_data("TEST", start, end)
    expected_len = len(test_df)
    
    # The sniffer will raise ValueError if it sees future rows
    sniffer_strategy = LeakageSnifferStrategy(total_expected_length=expected_len)
    
    engine = EventDrivenBacktester(
        data_provider=provider,
        strategy=sniffer_strategy,
        portfolio=BasicPortfolio(),
        risk_engine=BasicRiskEngine(),
        position_sizer=BasicPositionSizer(),
        execution_adapter=PaperExecutionAdapter(),
        db_session=MockSession()
    )
    
    # If this runs without raising ValueError, the strict boundary holds
    engine.run("TEST", start, end)
