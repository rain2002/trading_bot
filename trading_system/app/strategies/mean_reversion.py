from typing import Any, Dict
from trading_system.app.common.interfaces import Strategy
import pandas as pd
import pandas_ta as ta

class MeanReversionStrategy(Strategy):
    """
    Baseline Mean Reversion Strategy.
    Buys when the asset is oversold (RSI < 30) and below its lower Bollinger Band.
    Sells when the asset is overbought (RSI > 70) and above its upper Bollinger Band.
    """
    def __init__(self, rsi_length: int = 14, bb_length: int = 20, bb_std: float = 2.0):
        self.rsi_length = rsi_length
        self.bb_length = bb_length
        self.bb_std = bb_std
        # Minimum data required to calculate the longest indicator
        self.min_data_required = max(rsi_length, bb_length)
        
    def generate_signal(self, point_in_time_data: pd.DataFrame) -> Dict[str, Any]:
        if len(point_in_time_data) < self.min_data_required:
            return {"signal": 0, "confidence": 0.0}
            
        # To avoid the computational cost of recalculating TA on a massive dataframe 
        # every single time step, we apply it to a rolling window of recent data.
        tail_data = point_in_time_data.tail(self.min_data_required * 4).copy()
        
        # Calculate RSI
        rsi = ta.rsi(tail_data['close'], length=self.rsi_length)
        
        # Calculate Bollinger Bands
        bbands = ta.bbands(tail_data['close'], length=self.bb_length, std=self.bb_std)
        
        if rsi is None or bbands is None or rsi.empty or bbands.empty:
            return {"signal": 0, "confidence": 0.0}
            
        current_rsi = rsi.iloc[-1]
        current_close = tail_data['close'].iloc[-1]
        
        # bbands returns a DataFrame with columns like BBL_20_2.0 (Lower), BBU_20_2.0 (Upper)
        bb_lower_col = f"BBL_{self.bb_length}_{self.bb_std}"
        bb_upper_col = f"BBU_{self.bb_length}_{self.bb_std}"
        
        if bb_lower_col not in bbands.columns or bb_upper_col not in bbands.columns:
            return {"signal": 0, "confidence": 0.0}
            
        current_bb_lower = bbands[bb_lower_col].iloc[-1]
        current_bb_upper = bbands[bb_upper_col].iloc[-1]
        
        # Mean Reversion Logic
        if current_rsi < 30 and current_close < current_bb_lower:
            return {"signal": 1, "confidence": 0.8}
        elif current_rsi > 70 and current_close > current_bb_upper:
            return {"signal": -1, "confidence": 0.8}
            
        return {"signal": 0, "confidence": 0.0}
