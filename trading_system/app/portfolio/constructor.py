from typing import Dict
from trading_system.app.common.logger import get_logger

logger = get_logger("PortfolioConstructor")

class EqualWeightPortfolioConstructor:
    """
    Takes raw signals from the strategy and converts them into target portfolio weights.
    This architecture explicitly separates "What to trade" from "How much to allocate".
    """
    def generate_target_weights(self, signals: Dict[str, dict]) -> Dict[str, float]:
        target_weights = {}
        
        # Filter for assets that actually generated an active signal (1 or -1)
        active_symbols = [sym for sym, sig in signals.items() if sig.get('signal', 0) != 0]
        
        if not active_symbols:
            return target_weights
            
        # Allocate equal capital to all active signals
        weight_per_asset = 1.0 / len(active_symbols)
        
        for symbol in active_symbols:
            direction = signals[symbol]['signal']
            # If direction is 1 (buy), weight is positive. If -1 (sell), weight is negative.
            target_weights[symbol] = weight_per_asset * direction
            
        return target_weights
