import pandas as pd
from typing import Dict
from trading_system.app.common.logger import get_logger
from trading_system.app.features.regime import RegimeDetector

logger = get_logger("AdaptiveAllocator")

class AdaptivePortfolioAllocator:
    """
    A meta-controller that observes the Market Weather (Regime) and adjusts 
    target portfolio weights accordingly. It wraps a base constructor (e.g. EqualWeight).
    """
    def __init__(self, base_constructor, regime_index="SPY"):
        self.base_constructor = base_constructor
        self.regime_detector = RegimeDetector(index_symbol=regime_index)
        
    def generate_target_weights(self, signals: Dict[str, dict], point_in_time_universe: Dict[str, pd.DataFrame]) -> Dict[str, float]:
        # 1. Ask the base constructor for what the strategy *wants* to do
        base_weights = self.base_constructor.generate_target_weights(signals, point_in_time_universe)
        
        if not base_weights:
            return {}
            
        # 2. Check the Weather (Regime) using our proxy index (e.g., SPY)
        index_data = point_in_time_universe.get(self.regime_detector.index_symbol)
        
        if index_data is None or len(index_data) < 200:
            # If we don't have enough data to determine weather, act normally
            return base_weights
            
        current_regime = self.regime_detector.detect_regime(index_data)
        
        # 3. Override weights based on the Regime Rules
        if current_regime == "CRASH_WARNING":
            logger.warning("CRASH_WARNING Detected! Activating V3 Short-Selling Defense Protocol.")
            # V3: Rather than just going to cash, we take a 100% short position on the market index 
            # to hedge our portfolio and aggressively profit from the crash.
            # The execution adapter will issue a SELL order, which automatically opens a Short on Margin accounts.
            return {self.regime_detector.index_symbol: -1.0}
            
        elif current_regime in ["BEAR_NORMAL", "BEAR_VOLATILE"]:
            # logger.info(f"Regime {current_regime}: Reducing all long exposure by 50%.")
            adjusted_weights = {}
            for sym, weight in base_weights.items():
                if isinstance(weight, str) and weight == "HOLD":
                    adjusted_weights[sym] = weight
                elif weight > 0:
                    adjusted_weights[sym] = weight * 0.5 # De-leverage long positions
                else:
                    adjusted_weights[sym] = weight # Keep short positions normal
            return adjusted_weights
            
        else:
            # BULL_NORMAL or BULL_VOLATILE -> Proceed as normal
            return base_weights
