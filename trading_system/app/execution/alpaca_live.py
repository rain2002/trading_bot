import requests
import uuid
from typing import Any
from trading_system.app.common.interfaces import ExecutionAdapter
from trading_system.app.common.logger import get_logger

logger = get_logger("AlpacaExecutionAdapter")

class AlpacaExecutionAdapter(ExecutionAdapter):
    """
    Routes production orders to the Alpaca live or paper API.
    """
    def __init__(self, api_key: str, api_secret: str, base_url: str = "https://paper-api.alpaca.markets"):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.headers = {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.api_secret
        }
        
    def submit_order(self, order: Any) -> Any:
        symbol = order.get("symbol")
        quantity = order.get("quantity")
        
        # Determine side
        side = "buy" if quantity > 0 else "sell"
        abs_qty = abs(quantity)
        
        # Alpaca V2 Order Payload
        payload = {
            "symbol": symbol,
            "qty": str(abs_qty),
            "side": side,
            "type": "market",
            "time_in_force": "gtc"
        }
        if order.get("client_order_id"):
            payload["client_order_id"] = order.get("client_order_id")
        
        # Dry Run Mode (If keys aren't provided, log the intent)
        if not self.api_key or self.api_key == "mock":
            logger.info(f"[LIVE ROUTING DRY RUN] -> POST {self.base_url}/v2/orders | {side.upper()} {abs_qty} shares of {symbol}")
            return {
                "status": "FILLED",
                "order_id": str(uuid.uuid4()),
                "filled_quantity": quantity,
                "fill_price": order.get("price_hint", 0.0)
            }
            
        logger.info(f"Routing real live order to Alpaca: {side.upper()} {abs_qty} {symbol}")
        
        response = requests.post(
            f"{self.base_url}/v2/orders",
            headers=self.headers,
            json=payload
        )
        
        if response.status_code not in (200, 201):
            logger.error(f"Alpaca Order Failed: {response.text}")
            print(f" -> Alpaca Order Error ({response.status_code}): {response.text}")
            return {"status": "REJECTED"}
            
        data = response.json()
        
        return {
            "status": "SUBMITTED",
            "order_id": data.get("id"),
            "filled_quantity": 0,
            "fill_price": 0.0
        }
