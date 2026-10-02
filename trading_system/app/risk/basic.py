from typing import Any
from trading_system.app.common.interfaces import RiskEngine

class BasicRiskEngine(RiskEngine):
    def __init__(self, max_position_size: int = 100):
        self.max_position_size = max_position_size
        
    def evaluate_trade(self, trade_request: Any, portfolio_state: Any) -> bool:
        """
        Independent risk check: Prevent any trade that would result in a position 
        exceeding our configured maximum exposure.
        """
        symbol = trade_request.get('symbol')
        proposed_quantity = trade_request.get('quantity', 0)
        
        current_position = portfolio_state.get(symbol, 0)
        new_position = current_position + proposed_quantity
        
        if abs(new_position) > self.max_position_size:
            return False
            
        return True
