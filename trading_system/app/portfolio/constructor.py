from typing import Dict
from trading_system.app.common.logger import get_logger

logger = get_logger("PortfolioConstructor")

class EqualWeightPortfolioConstructor:
    """
    Takes raw signals from the strategy and converts them into target portfolio weights.
    This architecture explicitly separates "What to trade" from "How much to allocate".
    """
    def __init__(self, rebalance_freq="monthly"):
        self.rebalance_freq = rebalance_freq
        self.last_rebalance_period = None

    def generate_target_weights(self, signals: Dict[str, dict], point_in_time_universe: Dict[str, 'pd.DataFrame'] = None) -> Dict[str, float]:
        target_weights = {}
        
        # Implement Rebalance Frequency (e.g. Monthly)
        should_rebalance = True
        if self.rebalance_freq == "monthly" and point_in_time_universe:
            current_date = None
            for df in point_in_time_universe.values():
                if not df.empty:
                    current_date = df.index[-1]
                    break
            
            if current_date:
                current_period = (current_date.year, current_date.month)
                if self.last_rebalance_period is None or self.last_rebalance_period != current_period:
                    self.last_rebalance_period = current_period
                    should_rebalance = True
                else:
                    should_rebalance = False
                    
        if not should_rebalance:
            # Emit HOLD for all active symbols so they drift naturally without forcing buys/sells
            for symbol in signals.keys():
                target_weights[symbol] = 'HOLD'
            return target_weights
        
        # Process active signals (1, -1) and explicit HOLD signals
        active_symbols = [sym for sym, sig in signals.items() if sig.get('signal') in (1, -1)]
        hold_symbols = [sym for sym, sig in signals.items() if sig.get('signal') == 'HOLD']
        
        # Calculate weight only for actively targeted assets
        weight_per_asset = 1.0 / len(active_symbols) if active_symbols else 0.0
        
        for symbol in active_symbols:
            direction = signals[symbol]['signal']
            target_weights[symbol] = weight_per_asset * direction
            
        for symbol in hold_symbols:
            target_weights[symbol] = 'HOLD'
            
        return target_weights
