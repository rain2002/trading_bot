from typing import Any, Dict
from trading_system.app.common.interfaces import Strategy
import pandas as pd

class DummyMovingAverageStrategy(Strategy):
    def __init__(self, fast_window: int = 5, slow_window: int = 15):
        self.fast_window = fast_window
        self.slow_window = slow_window
        
    def generate_signal(self, point_in_time_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Expects a DataFrame containing data strictly up to the current point in time.
        NEVER looks ahead.
        """
        if len(point_in_time_data) < self.slow_window:
            return {"signal": 0, "confidence": 0.0}
            
        fast_sma = point_in_time_data['close'].tail(self.fast_window).mean()
        slow_sma = point_in_time_data['close'].tail(self.slow_window).mean()
        
        if fast_sma > slow_sma:
            return {"signal": 1, "confidence": 1.0} # BUY signal
        elif fast_sma < slow_sma:
            return {"signal": -1, "confidence": 1.0} # SELL signal
        
        return {"signal": 0, "confidence": 0.0}
