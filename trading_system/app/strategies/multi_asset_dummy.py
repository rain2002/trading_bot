from typing import Dict, Any
import pandas as pd

class MultiAssetMomentumStrategy:
    """
    A cross-sectional momentum strategy.
    Evaluates the entire universe simultaneously: buys the strongest asset, sells the weakest.
    """
    def __init__(self, lookback: int = 20):
        self.lookback = lookback
        
    def generate_signals(self, point_in_time_universe: Dict[str, pd.DataFrame]) -> Dict[str, Dict[str, Any]]:
        returns = {}
        for sym, df in point_in_time_universe.items():
            if len(df) >= self.lookback:
                # Calculate simple percentage return over the lookback window
                ret = (df['close'].iloc[-1] - df['close'].iloc[-self.lookback]) / df['close'].iloc[-self.lookback]
                returns[sym] = ret
                
        if not returns:
            return {}
            
        # Rank assets by momentum
        sorted_assets = sorted(returns.items(), key=lambda x: x[1])
        
        weakest_asset = sorted_assets[0][0]
        strongest_asset = sorted_assets[-1][0]
        
        signals = {}
        if returns[strongest_asset] > 0:
            signals[strongest_asset] = {"signal": 1, "confidence": 1.0} # BUY
            
        if returns[weakest_asset] < 0:
            signals[weakest_asset] = {"signal": -1, "confidence": 1.0} # SELL (Short)
            
        return signals
