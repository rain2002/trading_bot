from typing import Any
import uuid
from trading_system.app.common.interfaces import ExecutionAdapter

class PaperExecutionAdapter(ExecutionAdapter):
    def __init__(self, slippage_bps: float = 5.0, fixed_fee: float = 1.0):
        """
        slippage_bps: slippage in basis points (e.g. 5.0 = 0.05%)
        fixed_fee: flat broker fee per trade
        """
        self.slippage_bps = slippage_bps
        self.fixed_fee = fixed_fee
        
    def submit_order(self, order: Any) -> Any:
        """
        Simulate an order execution instantly, injecting realistic slippage and fees 
        so backtests are not overly optimistic.
        """
        intended_price = order.get('price_hint')
        quantity = order.get('quantity')
        
        # Calculate slippage direction (worse price for the trader)
        # If buying (qty > 0), price goes UP. If selling (qty < 0), price goes DOWN.
        slippage_factor = (self.slippage_bps / 10000.0)
        
        if quantity > 0:
            fill_price = intended_price * (1.0 + slippage_factor)
        else:
            fill_price = intended_price * (1.0 - slippage_factor)
            
        return {
            "order_id": order.get('client_order_id', str(uuid.uuid4())),
            "status": "FILLED",
            "symbol": order.get("symbol"),
            "filled_quantity": quantity,
            "fill_price": round(fill_price, 4),
            "fees": self.fixed_fee
        }
