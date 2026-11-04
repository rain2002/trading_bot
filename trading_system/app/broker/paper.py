"""
Standardized Paper Broker Adapter.
Implements BrokerAdapter interface with in-memory portfolio state, cash tracking,
and strict fail-closed governance for offline development and simulation.
"""

from typing import Dict, Any, List, Optional
import time
import math
import uuid
from datetime import datetime

from trading_system.app.common.interfaces import (
    BrokerAdapter,
    BrokerAPIError,
    BrokerConnectionError,
    OrderExecutionError,
)


class PaperBrokerAdapter(BrokerAdapter):
    """
    In-memory paper trading broker adapter.
    Simulates portfolio state, cash, positions, and order management without external network calls.
    """
    def __init__(
        self,
        initial_capital: float = 100000.0,
        currency: str = "USD",
        currency_symbol: str = "$",
    ):
        self.initial_capital = float(initial_capital)
        self.currency = currency
        self.currency_symbol = currency_symbol
        self.cash = float(initial_capital)
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.orders: List[Dict[str, Any]] = []
        self._connected = True

    def is_connected(self) -> bool:
        """Return connectivity status."""
        return self._connected

    def set_connected(self, status: bool) -> None:
        """Simulate connection drop or recovery."""
        self._connected = bool(status)

    def get_positions(self) -> Dict[str, float]:
        """Fetch active positions dictionary (symbol -> qty)."""
        if not self._connected:
            raise BrokerConnectionError("Fail-Closed: PaperBrokerAdapter is disconnected.")
        return {sym: float(data["qty"]) for sym, data in self.positions.items() if data.get("qty", 0.0) > 0}

    def get_positions_detailed(self) -> List[Dict[str, Any]]:
        """Fetch detailed positions with unrealized PnL."""
        if not self._connected:
            raise BrokerConnectionError("Fail-Closed: PaperBrokerAdapter is disconnected.")
        detailed = []
        for sym, data in self.positions.items():
            qty = float(data.get("qty", 0.0))
            if qty <= 0:
                continue
            avg_p = float(data.get("avg_entry_price", 0.0))
            curr_p = float(data.get("current_price", avg_p))
            mkt_val = qty * curr_p
            cost_val = qty * avg_p
            unrealized_pl = mkt_val - cost_val
            unrealized_plpc = (unrealized_pl / cost_val) if cost_val > 0 else 0.0
            detailed.append({
                "symbol": sym,
                "raw_symbol": sym,
                "qty": qty,
                "market_value": mkt_val,
                "avg_entry_price": avg_p,
                "current_price": curr_p,
                "unrealized_pl": unrealized_pl,
                "unrealized_plpc": unrealized_plpc,
            })
        return detailed

    def get_account_equity(self) -> float:
        """Fetch total portfolio equity (cash + invested market value)."""
        if not self._connected:
            raise BrokerConnectionError("Fail-Closed: PaperBrokerAdapter is disconnected.")
        inv = sum(p["market_value"] for p in self.get_positions_detailed())
        return self.cash + inv

    def get_account_details(self) -> Dict[str, Any]:
        """Fetch comprehensive account metrics."""
        if not self._connected:
            raise BrokerConnectionError("Fail-Closed: PaperBrokerAdapter is disconnected.")
        equity = self.get_account_equity()
        overall_pnl = equity - self.initial_capital
        overall_pnl_pct = (overall_pnl / self.initial_capital * 100) if self.initial_capital > 0 else 0.0
        return {
            "currency": self.currency,
            "currency_symbol": self.currency_symbol,
            "equity": equity,
            "cash": self.cash,
            "buying_power": self.cash,
            "today_pnl": 0.0,
            "today_pnl_pct": 0.0,
            "overall_pnl": overall_pnl,
            "overall_pnl_pct": overall_pnl_pct,
            "broker": "PaperBrokerAdapter (Simulated)",
        }

    def get_order_status(self, order_id: str) -> str:
        """Return status of given order."""
        for o in self.orders:
            if o.get("id") == order_id or o.get("client_order_id") == order_id:
                return str(o.get("status", "UNKNOWN")).upper()
        return "UNKNOWN"

    def place_order(
        self,
        symbol: str,
        qty: float,
        side: str = "BUY",
        price: float = 100.0,
        client_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Submit a paper order with simulated fill and cash/position update."""
        if not self._connected:
            raise OrderExecutionError("Fail-Closed: PaperBrokerAdapter is disconnected. Cannot place order.")
        
        abs_qty = abs(qty)
        if abs_qty <= 0:
            return {"success": False, "error": "Order quantity must be positive"}

        side_norm = side.upper()
        order_id = f"PAPER-ORD-{int(time.time() % 100000):05d}"
        order_record = {
            "id": order_id,
            "client_order_id": client_order_id or f"BOT-{order_id}",
            "symbol": symbol,
            "qty": abs_qty,
            "side": side_norm,
            "price": price,
            "status": "FILLED",
            "submitted_at": datetime.now().isoformat(),
        }
        self.orders.append(order_record)

        val = abs_qty * price
        if side_norm == "BUY":
            self.cash = max(0.0, self.cash - val)
            if symbol in self.positions:
                old_qty = self.positions[symbol]["qty"]
                old_p = self.positions[symbol]["avg_entry_price"]
                new_qty = old_qty + abs_qty
                new_avg = ((old_qty * old_p) + val) / new_qty
                self.positions[symbol]["qty"] = new_qty
                self.positions[symbol]["avg_entry_price"] = new_avg
                self.positions[symbol]["current_price"] = price
            else:
                self.positions[symbol] = {
                    "symbol": symbol,
                    "qty": abs_qty,
                    "avg_entry_price": price,
                    "current_price": price,
                }
        elif side_norm == "SELL":
            self.cash += val
            if symbol in self.positions:
                rem = self.positions[symbol]["qty"] - abs_qty
                if rem <= 0:
                    del self.positions[symbol]
                else:
                    self.positions[symbol]["qty"] = rem
                    self.positions[symbol]["current_price"] = price

        return {"success": True, "message": f"Simulated {side_norm} {abs_qty} {symbol} executed", "order": order_record}
