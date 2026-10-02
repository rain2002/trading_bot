from typing import Dict
from trading_system.app.common.interfaces import Portfolio

class BasicPortfolio(Portfolio):
    def __init__(self, initial_cash: float = 10000.0):
        self.positions: Dict[str, float] = {}
        self.cash: float = initial_cash
        
    def update_position(self, symbol: str, quantity: float, price: float) -> None:
        """Called only AFTER a successful execution response."""
        current_qty = self.positions.get(symbol, 0.0)
        self.positions[symbol] = current_qty + quantity
        self.cash -= (quantity * price)
        
    def get_target_weights(self) -> Dict[str, float]:
        return {}
        
    def get_positions(self) -> Dict[str, float]:
        return self.positions
