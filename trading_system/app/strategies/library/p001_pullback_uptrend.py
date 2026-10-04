import pandas as pd
import numpy as np
import pandas_ta as ta
from typing import Dict
from trading_system.app.common.interfaces import Strategy

class P001_PullbackUptrend(Strategy):
    """
    High-Probability Strategy: Pullback in a Secular Uptrend.
    Rule 1: Stock must be in a major uptrend (Close > 200 SMA).
    Rule 2: Stock must be in a minor uptrend (Close > 50 SMA).
    Rule 3: Stock experiences a sudden short-term dip (RSI < 40).
    Exit: Sell when the dip recovers (RSI > 70).
    """
    def __init__(self, sma_long=200, sma_short=50, rsi_buy=40, rsi_sell=70):
        self.sma_long = sma_long
        self.sma_short = sma_short
        self.rsi_buy = rsi_buy
        self.rsi_sell = rsi_sell
        # Keep track of active positions so we can hold until RSI > 70
        self.active_longs = set()

    def generate_signals(self, point_in_time_universe: Dict[str, pd.DataFrame]) -> Dict[str, Dict]:
        signals = {}
        
        for sym, df in point_in_time_universe.items():
            if len(df) < self.sma_long:
                signals[sym] = {'signal': 0, 'confidence': 0.0}
                continue
                
            calc_close = df['adj_close'] if 'adj_close' in df.columns else df['close']
            
            # Calculate indicators
            sma200 = ta.sma(calc_close, length=self.sma_long).iloc[-1]
            sma50 = ta.sma(calc_close, length=self.sma_short).iloc[-1]
            rsi = ta.rsi(calc_close, length=14).iloc[-1]
            current_price = calc_close.iloc[-1]
            
            # EXIT RULE
            if sym in self.active_longs:
                if rsi > self.rsi_sell:
                    # Target achieved, take profit
                    signals[sym] = {'signal': -1, 'confidence': 1.0}
                    self.active_longs.remove(sym)
                else:
                    # Hold position
                    signals[sym] = {'signal': 1, 'confidence': 1.0}
                continue
                
            # ENTRY RULE
            uptrend = (current_price > sma200) and (current_price > sma50)
            pullback = (rsi < self.rsi_buy)
            
            if uptrend and pullback:
                signals[sym] = {'signal': 1, 'confidence': 1.0}
                self.active_longs.add(sym)
            else:
                signals[sym] = {'signal': 0, 'confidence': 0.0}
                
        return signals
