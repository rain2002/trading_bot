import pandas as pd
from typing import Dict, Any

class M001_Momentum6Month:
    """
    M001: 6-Month Cross-Sectional Momentum.
    Ranks the universe by 126-day (6 month) absolute return.
    Goes long the top N performers, provided their momentum is actually positive.
    """
    def __init__(self, lookback_days=126, top_n=2):
        self.lookback = lookback_days
        self.top_n = top_n
        
    def generate_signals(self, point_in_time_universe: Dict[str, pd.DataFrame]) -> Dict[str, Dict[str, Any]]:
        returns = {}
        for sym, df in point_in_time_universe.items():
            if len(df) > self.lookback:
                current_price = df['close'].iloc[-1]
                past_price = df['close'].iloc[-self.lookback]
                ret = (current_price - past_price) / past_price
                returns[sym] = ret
                
        if not returns:
            return {}
            
        # Sort descending (highest returns first)
        sorted_assets = sorted(returns.items(), key=lambda x: x[1], reverse=True)
        
        signals = {}
        # Buy Top N
        for i in range(min(self.top_n, len(sorted_assets))):
            sym, ret = sorted_assets[i]
            if ret > 0: # Only buy if absolute momentum is positive
                signals[sym] = {"signal": 1, "confidence": 0.9}
                
        return signals
