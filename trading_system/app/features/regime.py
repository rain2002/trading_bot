import pandas as pd
import pandas_ta as ta
from typing import Dict

class RegimeDetector:
    """
    Analyzes broad market data (e.g. SPY) to determine the current 'Market Weather'.
    This prevents the bot from trading aggressive long strategies during market crashes.
    """
    def __init__(self, index_symbol="SPY"):
        self.index_symbol = index_symbol

    def detect_regime(self, market_data: pd.DataFrame) -> str:
        """
        Returns the current market regime based on Trend and Volatility.
        Possible states: 'BULL_NORMAL', 'BULL_VOLATILE', 'BEAR_NORMAL', 'BEAR_VOLATILE', 'CRASH_WARNING'
        """
        if len(market_data) < 200:
            return "UNKNOWN" # Not enough data to confidently assess macro trend
            
        close = market_data['close']
        
        # 1. Trend Detection (200-day Simple Moving Average)
        sma200 = ta.sma(close, length=200).iloc[-1]
        current_price = close.iloc[-1]
        is_bull_trend = current_price > sma200
        
        # 2. Volatility Detection (Average True Range relative to price)
        atr = ta.atr(market_data['high'], market_data['low'], close, length=14).iloc[-1]
        atr_pct = (atr / current_price) * 100
        
        # If daily average movement is > 1.5% for an index like SPY, volatility is highly elevated
        is_high_vol = atr_pct > 1.5 
        
        # 3. Crash Warning (Severe short-term breakdown coupled with broken macro trend)
        sma20 = ta.sma(close, length=20).iloc[-1]
        is_severe_breakdown = current_price < (sma20 * 0.95) # 5% below the 20-day MA
        
        if not is_bull_trend and is_high_vol and is_severe_breakdown:
            return "CRASH_WARNING"
            
        if is_bull_trend:
            return "BULL_VOLATILE" if is_high_vol else "BULL_NORMAL"
        else:
            return "BEAR_VOLATILE" if is_high_vol else "BEAR_NORMAL"
