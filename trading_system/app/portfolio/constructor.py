from typing import Dict
from trading_system.app.common.logger import get_logger

logger = get_logger("PortfolioConstructor")

class EqualWeightPortfolioConstructor:
    """
    Takes raw signals from the strategy and converts them into target portfolio weights.
    This architecture explicitly separates "What to trade" from "How much to allocate".
    """
    def generate_target_weights(self, signals: Dict[str, dict], point_in_time_universe: Dict[str, 'pd.DataFrame'] = None) -> Dict[str, float]:
        target_weights = {}
        
        # Process active signals (1, -1) and explicit HOLD signals
        active_symbols = [sym for sym, sig in signals.items() if sig.get('signal') in (1, -1)]
        hold_symbols = [sym for sym, sig in signals.items() if sig.get('signal') == 'HOLD']
        
        # Calculate weight only for actively targeted assets
        # Note: If HOLD assets exist, we technically should subtract their current weight from available capital,
        # but for V1 Equal Weight, we just equal weight the active assets and let the engine pass HOLD signals.
        weight_per_asset = 1.0 / len(active_symbols) if active_symbols else 0.0
        
        for symbol in active_symbols:
            direction = signals[symbol]['signal']
            target_weights[symbol] = weight_per_asset * direction
            
        for symbol in hold_symbols:
            target_weights[symbol] = 'HOLD'
            
        return target_weights
