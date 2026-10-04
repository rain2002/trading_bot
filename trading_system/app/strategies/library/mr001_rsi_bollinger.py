import pandas as pd
import pandas_ta as ta
from typing import Dict, Any

class MR001_RSIBollinger:
    """
    MR001: Mean Reversion based on RSI and standard deviation extremes.
    Buys when RSI < 30 AND Price is below Lower Bollinger Band (2.5 std dev).
    Sells when RSI > 70 AND Price is above Upper Bollinger Band.
    """
    def __init__(self, rsi_len=14, bb_len=20, bb_std=2.5):
        self.rsi_len = rsi_len
        self.bb_len = bb_len
        self.bb_std = bb_std
        
    def generate_signals(self, point_in_time_universe: Dict[str, pd.DataFrame]) -> Dict[str, Dict[str, Any]]:
        signals = {}
        for sym, df in point_in_time_universe.items():
            min_data = max(self.rsi_len, self.bb_len)
            if len(df) < min_data:
                continue
                
            rsi = ta.rsi(df['close'], length=self.rsi_len)
            bbands = ta.bbands(df['close'], length=self.bb_len, std=self.bb_std)
            
            if rsi is None or bbands is None:
                continue
                
            current_rsi = rsi.iloc[-1]
            current_close = df['close'].iloc[-1]
            
            lower_band_col = f"BBL_{self.bb_len}_{self.bb_std}"
            upper_band_col = f"BBU_{self.bb_len}_{self.bb_std}"
            
            if lower_band_col not in bbands.columns:
                continue
                
            current_lower = bbands[lower_band_col].iloc[-1]
            current_upper = bbands[upper_band_col].iloc[-1]
            
            if current_rsi < 30 and current_close < current_lower:
                signals[sym] = {"signal": 1, "confidence": 0.8}
            elif current_rsi > 70 and current_close > current_upper:
                # In V1 this signals a SELL of an existing long position.
                signals[sym] = {"signal": -1, "confidence": 0.8}
                
        return signals
