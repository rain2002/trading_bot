from typing import Dict, Optional
from trading_system.app.common.logger import get_logger

logger = get_logger("PortfolioConstructor")

class EqualWeightPortfolioConstructor:
    """
    Takes raw signals from the strategy and converts them into target portfolio weights.
    This architecture explicitly separates "What to trade" from "How much to allocate".
    Supports dynamic holdings based on conviction and opportunity quality without fixed caps.
    """
    def __init__(self, rebalance_freq: str = "monthly", max_holdings: Optional[int] = None, min_position_pct: float = 0.015):
        self.rebalance_freq = rebalance_freq
        self.max_holdings = max_holdings
        self.min_position_pct = min_position_pct
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
        raw_active = [sym for sym, sig in signals.items() if sig.get('signal') in (1, -1)]
        hold_symbols = [sym for sym, sig in signals.items() if sig.get('signal') == 'HOLD']
        
        # Rank by conviction score / confidence
        active_symbols = sorted(
            raw_active,
            key=lambda s: signals[s].get('conviction_score', signals[s].get('confidence', 1.0)),
            reverse=True
        )
        if self.max_holdings is not None:
            active_symbols = active_symbols[:self.max_holdings]
        
        # Calculate weight only for actively targeted assets, matching Dynamic Sizing (max 95%, max 15% per stock)
        total_signals = len(active_symbols)
        weight_per_asset = min(0.95 / total_signals, 0.15) if total_signals > 0 else 0.0

        # Filter out dust allocations below min_position_pct
        if weight_per_asset < self.min_position_pct and total_signals > 0:
            max_allowed = int(0.95 / self.min_position_pct)
            active_symbols = active_symbols[:max_allowed]
            total_signals = len(active_symbols)
            weight_per_asset = min(0.95 / total_signals, 0.15) if total_signals > 0 else 0.0
        
        for symbol in active_symbols:
            direction = signals[symbol]['signal']
            target_weights[symbol] = weight_per_asset * direction
            
        for symbol in hold_symbols:
            target_weights[symbol] = 'HOLD'
            
        return target_weights
