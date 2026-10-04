import pandas as pd
from typing import Dict, Any
import pandas_ta as ta

class T001_MovingAverageTrend:
    """
    T001: Golden Cross / Trend Following
    Buys when the 50-day SMA crosses above the 200-day SMA.
    Sells/Exits when it crosses below.
    """
    def __init__(self, fast_length=50, slow_length=200):
        self.fast = fast_length
        self.slow = slow_length
        
    def generate_signals(self, point_in_time_universe: Dict[str, pd.DataFrame]) -> Dict[str, Dict[str, Any]]:
        signals = {}
        for sym, df in point_in_time_universe.items():
            if len(df) < self.slow + 1:
                continue
                
            fast_sma = ta.sma(df['close'], length=self.fast)
            slow_sma = ta.sma(df['close'], length=self.slow)
            
            if fast_sma is None or slow_sma is None:
                continue
                
            current_fast = fast_sma.iloc[-1]
            current_slow = slow_sma.iloc[-1]
            
            # Trend State (Continuous)
            if current_fast > current_slow:
                # We want to be Long
                signals[sym] = {"signal": 1, "confidence": 0.8}
            else:
                # We want to be Flat/Cash
                signals[sym] = {"signal": 0, "confidence": 0.8}
                
        return signals
