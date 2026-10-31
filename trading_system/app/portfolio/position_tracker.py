"""
Position State Metadata Tracker.

Persists and tracks position attribution (MOMENTUM vs DIP_BUY), entry timestamps,
and true peak price strictly since entry date.
Eliminates lookback-bias where pre-entry highs triggered false breakeven stops.
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

logger = logging.getLogger("PositionTracker")

DEFAULT_METADATA_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "portfolio_state_metadata.json"
)


class PositionTracker:
    def __init__(self, metadata_path: Optional[str] = None):
        self.path = metadata_path or os.path.abspath(DEFAULT_METADATA_PATH)
        self.data: Dict[str, Dict[str, Any]] = self._load()

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error loading position state metadata: {e}")
        return {}

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w") as f:
                json.dump(self.data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to persist position state metadata: {e}")

    def get_position_meta(self, symbol: str) -> Dict[str, Any]:
        """Returns metadata for a held symbol (or default values)."""
        sym = symbol.replace('.', '-')
        return self.data.get(sym, {
            "holding_type": "MOMENTUM",
            "entry_date": None,
            "entry_price": 0.0,
            "peak_price": 0.0
        })

    def record_entry(
        self,
        symbol: str,
        holding_type: str,
        entry_price: float,
        entry_date: Optional[str] = None,
        quantity: Optional[float] = None
    ) -> None:
        """Records fresh entry of a position with explicit strategy type."""
        sym = symbol.replace('.', '-')
        date_str = entry_date or datetime.now().strftime("%Y-%m-%d")
        self.data[sym] = {
            "symbol": sym,
            "holding_type": str(holding_type).upper(),
            "entry_date": date_str,
            "entry_price": float(entry_price),
            "peak_price": float(entry_price),
            "quantity": float(quantity) if quantity is not None else 0.0,
            "updated_at": datetime.now().isoformat()
        }
        self._save()

    def update_peak(self, symbol: str, current_price: float) -> float:
        """Updates and returns the true peak price since position entry."""
        sym = symbol.replace('.', '-')
        if sym in self.data:
            entry_p = self.data[sym].get("entry_price", current_price)
            curr_peak = self.data[sym].get("peak_price", entry_p)
            new_peak = max(curr_peak, current_price, entry_p)
            self.data[sym]["peak_price"] = new_peak
            self.data[sym]["updated_at"] = datetime.now().isoformat()
            self._save()
            return new_peak
        return current_price

    def record_exit(self, symbol: str) -> None:
        """Removes a closed position from the tracking ledger."""
        sym = symbol.replace('.', '-')
        if sym in self.data:
            del self.data[sym]
            self._save()

    def sync_with_broker(
        self,
        current_positions: Dict[str, float],
        detailed_positions: Optional[List[Dict[str, Any]]] = None,
        recent_orders: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """
        Reconciles local position metadata against broker state.
        1. Auto-discovers entry date and strategy type from recent broker order fills.
        2. Prunes any liquidated holdings that are no longer held.
        """
        active_syms = set(s.replace('.', '-') for s in current_positions.keys() if current_positions[s] > 0)

        # 1. Prune closed positions
        for sym in list(self.data.keys()):
            if sym not in active_syms:
                del self.data[sym]

        # Map detailed positions for quick entry price lookup
        pos_details_map = {}
        if detailed_positions:
            for p in detailed_positions:
                s = p.get("symbol", "").replace('.', '-')
                pos_details_map[s] = p

        # 2. Add or reconcile active positions
        for sym in active_syms:
            if sym not in self.data:
                # Check recent orders for strategy attribution and fill date
                found_type = "MOMENTUM"
                found_date = None
                found_entry_price = 0.0

                if recent_orders:
                    # Find most recent filled buy order for this symbol
                    for o in recent_orders:
                        o_sym = o.get("symbol", "").replace('.', '-')
                        side = str(o.get("side", "")).lower()
                        status = str(o.get("status", "")).lower()
                        if o_sym == sym and side == "buy" and status in ("filled", "partially_filled"):
                            client_id = o.get("client_order_id", "").upper()
                            if "DIP" in client_id:
                                found_type = "DIP_BUY"
                            elif "MOM" in client_id:
                                found_type = "MOMENTUM"
                            
                            found_date = o.get("filled_at") or o.get("created_at")
                            if found_date:
                                found_date = str(found_date)[:10]
                            found_entry_price = float(o.get("filled_avg_price") or 0.0)
                            break

                p_detail = pos_details_map.get(sym, {})
                avg_p = found_entry_price or float(p_detail.get("avg_entry_price", 0.0))
                curr_p = float(p_detail.get("current_price", avg_p))

                self.data[sym] = {
                    "symbol": sym,
                    "holding_type": found_type,
                    "entry_date": found_date or datetime.now().strftime("%Y-%m-%d"),
                    "entry_price": avg_p,
                    "peak_price": max(curr_p, avg_p),
                    "quantity": float(current_positions.get(sym, 0.0)),
                    "updated_at": datetime.now().isoformat()
                }

        self._save()
