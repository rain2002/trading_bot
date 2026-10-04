import pandas as pd
from typing import Dict, List
from trading_system.app.common.interfaces import Strategy
from trading_system.app.common.logger import get_logger
import pandas_ta as ta

logger = get_logger("EnsembleRegimeSwitch")

class EnsembleRegimeSwitch(Strategy):
    """
    Advanced Multi-Strategy Ensemble.
    Automatically switches between different strategies based on current market volatility and regime.
    - Low Volatility Bull Market -> Uses Trend Following Strategy
    - High Volatility / Sideways Market -> Uses Mean Reversion Strategy
    """
    def __init__(self, strategies: Dict[str, Strategy], benchmark_symbol: str = "SPY"):
        self.strategies = strategies
        self.benchmark_symbol = benchmark_symbol
        self.volatility_lookback = 20
        
    def generate_signals(self, point_in_time_universe: Dict[str, pd.DataFrame]) -> Dict[str, Dict]:
        if self.benchmark_symbol not in point_in_time_universe:
            # Fallback if benchmark missing
            logger.warning(f"Benchmark {self.benchmark_symbol} missing. Defaulting to first strategy.")
            first_strat = list(self.strategies.values())[0]
            return first_strat.generate_signals(point_in_time_universe)
            
        bench_df = point_in_time_universe[self.benchmark_symbol]
        
        if len(bench_df) < self.volatility_lookback + 1:
            first_strat = list(self.strategies.values())[0]
            return first_strat.generate_signals(point_in_time_universe)
            
        # Calculate Market Volatility (ATR % or VIX equivalent)
        atr = ta.atr(bench_df['high'], bench_df['low'], bench_df['close'], length=self.volatility_lookback)
        if atr is None or atr.empty:
            first_strat = list(self.strategies.values())[0]
            return first_strat.generate_signals(point_in_time_universe)
            
        current_atr = atr.iloc[-1]
        current_price = bench_df['close'].iloc[-1]
        volatility_pct = (current_atr / current_price) * 100
        
        # Calculate Market Regime (200 SMA)
        sma200 = ta.sma(bench_df['close'], length=200)
        is_bull_market = False if sma200 is None or sma200.empty else current_price > sma200.iloc[-1]
        
        # Strategy Selection Logic
        # 1. High Volatility (> 1.5% daily avg swing) OR Bear Market -> Sideways/Choppy -> Use Mean Reversion
        # 2. Low Volatility (< 1.5%) AND Bull Market -> Smooth uptrend -> Use Trend Following
        
        if volatility_pct > 1.5 or not is_bull_market:
            selected_strat_name = "MeanReversion"
        else:
            selected_strat_name = "TrendFollowing"
            
        # Ensure the selected strategy was actually provided to the ensemble
        if selected_strat_name not in self.strategies:
            selected_strat_name = list(self.strategies.keys())[0]
            
        logger.info(f"Ensemble detected Volatility={volatility_pct:.2f}%, Bull_Market={is_bull_market} -> Selected Strategy: {selected_strat_name}")
        
        active_strategy = self.strategies[selected_strat_name]
        return active_strategy.generate_signals(point_in_time_universe)
