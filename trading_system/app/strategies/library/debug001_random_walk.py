import pandas as pd
import numpy as np
from typing import Dict
from trading_system.app.common.interfaces import Strategy
from trading_system.app.common.logger import get_logger

logger = get_logger("RandomWalkStrategy")

class DEBUG001_RandomWalk(Strategy):
    """
    V2 Anti-Leakage Test Strategy.
    This strategy completely ignores price data and generates random buys and sells.
    If the engine shows this strategy making a consistent profit over time, the backtester
    is leaking future data or cheating on slippage.
    """
    def __init__(self, seed=42):
        self.rng = np.random.default_rng(seed)
        logger.info(f"Initialized Random-Walk Strategy with deterministic seed: {seed}")
        
    def generate_signals(self, point_in_time_universe: Dict[str, pd.DataFrame]) -> Dict[str, dict]:
        signals = {}
        
        for sym, df in point_in_time_universe.items():
            if df.empty:
                continue
                
            # Randomly decide to Buy (1), Sell/Short (-1), or Hold (0)
            choice = self.rng.choice([1, 0, -1])
            signals[sym] = {"signal": choice, "confidence": 0.5}
            
        return signals
