import pandas as pd
import numpy as np
from typing import Dict
from trading_system.app.common.interfaces import Strategy
from trading_system.app.common.logger import get_logger
import pandas_ta as ta

logger = get_logger("MR001_MeanReversion")

class MR001_MeanReversion(Strategy):
    """
    Mean Reversion Strategy based on Bollinger Bands and RSI.
    Performs best in sideways, range-bound, or highly volatile markets.
    """
    def __init__(self, bb_length=20, bb_std=2.0, rsi_length=14, rsi_oversold=30, rsi_overbought=70):
        self.bb_length = bb_length
        self.bb_std = bb_std
        self.rsi_length = rsi_length
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        
    def generate_signals(self, point_in_time_universe: Dict[str, pd.DataFrame]) -> Dict[str, Dict]:
        signals = {}
        
        for sym, df in point_in_time_universe.items():
            if len(df) < max(self.bb_length, self.rsi_length) + 1:
                signals[sym] = {'signal': 0, 'confidence': 0.0}
                continue
                
            close = df['close']
            
            # Use adjusted close for indicators if available, else raw close
            calc_close = df['adj_close'] if 'adj_close' in df.columns else close
            
            bbands = ta.bbands(calc_close, length=self.bb_length, std=self.bb_std)
            rsi = ta.rsi(calc_close, length=self.rsi_length)
            
            if bbands is None or rsi is None or bbands.empty or rsi.empty:
                signals[sym] = {'signal': 0, 'confidence': 0.0}
                continue
                
            current_price = calc_close.iloc[-1]
            lower_band = bbands.iloc[:, 0].iloc[-1]
            upper_band = bbands.iloc[:, 2].iloc[-1]
            current_rsi = rsi.iloc[-1]
            
            # Mean Reversion Logic: Buy when price drops below lower Bollinger Band AND RSI is oversold
            if current_price < lower_band and current_rsi < self.rsi_oversold:
                signals[sym] = {'signal': 1, 'confidence': 0.8}
            # Sell when price jumps above upper Bollinger Band AND RSI is overbought
            elif current_price > upper_band and current_rsi > self.rsi_overbought:
                signals[sym] = {'signal': -1, 'confidence': 0.8}
            else:
                signals[sym] = {'signal': 0, 'confidence': 0.0}
                
        return signals
