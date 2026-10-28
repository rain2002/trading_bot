from typing import Dict, Any, Optional, List
from trading_system.app.common.interfaces import BrokerAdapter
import requests

class AlpacaBrokerAdapter(BrokerAdapter):
    """
    Adapter to interface with Alpaca (Paper or Live).
    """
    def __init__(self, api_key: str, api_secret: str, base_url: str = "https://paper-api.alpaca.markets"):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.headers = {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.api_secret
        }
        
    def get_positions(self) -> Dict[str, float]:
        """Fetch actual positions from the broker normalized with '-' for dual-class shares."""
        if not self.api_key or self.api_key == "mock":
            return {"DIA": 115.0, "QQQ": 80.0, "AAPL": 50.0}
            
        response = requests.get(f"{self.base_url}/v2/positions", headers=self.headers, timeout=10)
        response.raise_for_status()
        positions = response.json()
        
        # Normalize symbol so BRK.B becomes BRK-B (consistent with universe)
        return {pos['symbol'].replace('.', '-'): float(pos['qty']) for pos in positions}

    def get_positions_detailed(self) -> list:
        """Fetch detailed positions including unrealized PnL % for stop-loss monitoring."""
        if not self.api_key or self.api_key == "mock":
            return []
        try:
            response = requests.get(f"{self.base_url}/v2/positions", headers=self.headers, timeout=10)
            response.raise_for_status()
            positions = response.json()
            return [
                {
                    "symbol": pos['symbol'].replace('.', '-'),
                    "raw_symbol": pos['symbol'],
                    "qty": float(pos['qty']),
                    "market_value": float(pos.get('market_value', 0.0)),
                    "avg_entry_price": float(pos.get('avg_entry_price', 0.0)),
                    "current_price": float(pos.get('current_price', 0.0)),
                    "unrealized_pl": float(pos.get('unrealized_pl', 0.0)),
                    "unrealized_plpc": float(pos.get('unrealized_plpc', 0.0)),
                }
                for pos in positions
            ]
        except Exception:
            return []

    def get_recent_orders(self, limit: int = 500) -> list:
        """Fetch recent order executions directly from Alpaca."""
        if not self.api_key or self.api_key == "mock":
            return []
        try:
            response = requests.get(
                f"{self.base_url}/v2/orders?status=all&limit={limit}",
                headers=self.headers,
                timeout=8
            )
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return []

    def cancel_all_orders(self) -> bool:
        """Cancel all open/pending orders on Alpaca to prevent wash trades and duplicate fills."""
        if not self.api_key or self.api_key == "mock":
            return True
        try:
            resp = requests.delete(f"{self.base_url}/v2/orders", headers=self.headers, timeout=10)
            return resp.status_code in (200, 204, 207)
        except Exception:
            return False

    def get_order_status(self, order_id: str) -> str:
        """Fetch true order status from the broker."""
        if not self.api_key or self.api_key == "mock":
            return "FILLED"
        try:
            resp = requests.get(f"{self.base_url}/v2/orders/{order_id}", headers=self.headers, timeout=8)
            if resp.status_code == 200:
                return resp.json().get("status", "UNKNOWN").upper()
        except Exception:
            pass
        return "UNKNOWN"

    def get_account_equity(self) -> float:
        """Fetch total portfolio value (cash + long - short)."""
        if not self.api_key or self.api_key == "mock":
            return 100000.0
            
        try:
            response = requests.get(f"{self.base_url}/v2/account", headers=self.headers, timeout=10)
            response.raise_for_status()
            account = response.json()
            return float(account['equity'])
        except Exception:
            return 100000.0

    def get_account_details(self) -> Dict[str, float]:
        """Fetch comprehensive account metrics including Today PnL and Overall PnL."""
        if not self.api_key or self.api_key == "mock":
            return {
                "equity": 100000.0,
                "cash": 10000.0,
                "today_pnl": 0.0,
                "today_pnl_pct": 0.0,
                "overall_pnl": 0.0,
                "overall_pnl_pct": 0.0,
            }
        try:
            response = requests.get(f"{self.base_url}/v2/account", headers=self.headers, timeout=10)
            response.raise_for_status()
            account = response.json()
            
            equity = float(account.get("equity", 100000.0))
            last_equity = float(account.get("last_equity", equity))
            cash = float(account.get("cash", 0.0))
            buying_power = float(account.get("buying_power", cash))
            
            today_pnl = equity - last_equity
            today_pnl_pct = (today_pnl / last_equity * 100) if last_equity > 0 else 0.0
            
            initial_capital = 100000.0
            overall_pnl = equity - initial_capital
            overall_pnl_pct = (overall_pnl / initial_capital * 100)
            
            return {
                "equity": equity,
                "cash": cash,
                "buying_power": buying_power,
                "today_pnl": today_pnl,
                "today_pnl_pct": today_pnl_pct,
                "overall_pnl": overall_pnl,
                "overall_pnl_pct": overall_pnl_pct,
            }
        except Exception:
            return {
                "equity": 100000.0,
                "cash": 10000.0,
                "buying_power": 10000.0,
                "today_pnl": 0.0,
                "today_pnl_pct": 0.0,
                "overall_pnl": 0.0,
                "overall_pnl_pct": 0.0,
            }

    def get_latest_price(self, symbol: str) -> float:
        """Fetch latest trade price from Alpaca Market Data API (with feed=iex for free-tier compatibility)."""
        if not self.api_key or self.api_key == "mock":
            return 100.0
        try:
            alpaca_sym = symbol.replace('-', '.')
            url = f"https://data.alpaca.markets/v2/stocks/{alpaca_sym}/trades/latest?feed=iex"
            resp = requests.get(url, headers=self.headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if "trade" in data and "p" in data["trade"]:
                    return float(data["trade"]["p"])
        except Exception:
            pass
        return 0.0

    def get_portfolio_history(self, period: str = "1M", timeframe: str = "1D") -> Any:
        """Fetch historical equity curve for the account directly from Alpaca."""
        if not self.api_key or self.api_key == "mock":
            return None
        try:
            import pandas as pd
            from datetime import datetime
            url = f"{self.base_url}/v2/account/portfolio/history?period={period}&timeframe={timeframe}"
            resp = requests.get(url, headers=self.headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                timestamps = [datetime.fromtimestamp(ts) for ts in data.get("timestamp", [])]
                df = pd.DataFrame({
                    "timestamp": timestamps,
                    "equity": data.get("equity", []),
                    "profit_loss": data.get("profit_loss", []),
                    "profit_loss_pct": data.get("profit_loss_pct", [])
                }).dropna()
                return df
        except Exception:
            pass
        return None

    def get_open_orders(self) -> List[Dict[str, Any]]:
        """Fetch all currently open/active orders from Alpaca."""
        if not self.api_key or self.api_key == "mock":
            return []
        try:
            response = requests.get(
                f"{self.base_url}/v2/orders?status=open&limit=500",
                headers=self.headers,
                timeout=8
            )
            if response.status_code == 200:
                raw_orders = response.json()
                results = []
                for o in raw_orders:
                    qty = float(o.get("qty") or 0.0)
                    filled_qty = float(o.get("filled_qty") or 0.0)
                    lp = float(o.get("limit_price")) if o.get("limit_price") else None
                    sub = o.get("submitted_at") or o.get("created_at") or ""
                    results.append({
                        "id": o.get("id"),
                        "client_order_id": o.get("client_order_id", ""),
                        "symbol": str(o.get("symbol", "")).replace('.', '-'),
                        "raw_symbol": o.get("symbol", ""),
                        "side": str(o.get("side", "")).upper(),
                        "qty": int(qty) if qty.is_integer() else qty,
                        "filled_qty": int(filled_qty) if filled_qty.is_integer() else filled_qty,
                        "notional": float(o.get("notional")) if o.get("notional") else None,
                        "type": str(o.get("type", "")).upper(),
                        "limit_price": lp,
                        "status": str(o.get("status", "")).upper(),
                        "submitted_at": sub,
                        "time_in_force": str(o.get("time_in_force", "")).upper(),
                    })
                return results
        except Exception:
            pass
        return []

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel a specific open order on Alpaca."""
        if not self.api_key or self.api_key == "mock":
            return {"success": True, "message": f"Order {order_id} canceled (mock)"}
        try:
            resp = requests.delete(f"{self.base_url}/v2/orders/{order_id}", headers=self.headers, timeout=10)
            if resp.status_code in (200, 204):
                return {"success": True, "message": f"Order {order_id} successfully canceled"}
            else:
                err_text = resp.text
                try:
                    err_json = resp.json()
                    err_text = err_json.get("message", err_text)
                except Exception:
                    pass
                return {"success": False, "error": err_text or f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def replace_order(
        self,
        order_id: str,
        new_qty: Optional[float] = None,
        new_limit_price: Optional[float] = None,
        time_in_force: str = "day"
    ) -> Dict[str, Any]:
        """Modify an existing open order with automatic fallback to cancel-and-replace."""
        if not self.api_key or self.api_key == "mock":
            return {"success": True, "message": "Order modified (mock)"}
        try:
            # First fetch the existing order details in case cancel-and-replace is required
            existing_resp = requests.get(f"{self.base_url}/v2/orders/{order_id}", headers=self.headers, timeout=8)
            existing_data = existing_resp.json() if existing_resp.status_code == 200 else {}
            
            patch_payload = {"time_in_force": time_in_force.lower()}
            if new_qty is not None and float(new_qty) > 0:
                q_val = float(new_qty)
                patch_payload["qty"] = str(int(q_val) if q_val.is_integer() else q_val)
            if new_limit_price is not None and float(new_limit_price) > 0:
                patch_payload["limit_price"] = str(round(float(new_limit_price), 2))
                
            resp = requests.patch(f"{self.base_url}/v2/orders/{order_id}", headers=self.headers, json=patch_payload, timeout=10)
            if resp.status_code == 200:
                return {"success": True, "message": "Order successfully modified via PATCH", "order": resp.json()}
                
            # If PATCH is rejected (e.g. status is "accepted" outside regular hours), perform cancel-and-replace
            if existing_data:
                # Cancel old order
                requests.delete(f"{self.base_url}/v2/orders/{order_id}", headers=self.headers, timeout=8)
                
                # Determine new order parameters
                symbol = existing_data.get("symbol")
                side = existing_data.get("side", "buy")
                order_type = existing_data.get("type", "market")
                qty = new_qty if new_qty is not None else float(existing_data.get("qty", 1))
                lp = new_limit_price if new_limit_price is not None else existing_data.get("limit_price")
                
                return self.place_order(
                    symbol=symbol,
                    qty=qty,
                    side=side,
                    order_type=order_type,
                    limit_price=float(lp) if lp else None,
                    time_in_force=time_in_force
                )
            return {"success": False, "error": resp.text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def place_order(
        self,
        symbol: str,
        qty: Optional[float] = None,
        notional: Optional[float] = None,
        side: str = "buy",
        order_type: str = "market",
        limit_price: Optional[float] = None,
        time_in_force: str = "day",
        client_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Submit a manual or bot-prompted order to Alpaca (supports value $ or quantity shares)."""
        if not symbol:
            return {"success": False, "error": "Stock symbol must be specified"}
            
        alpaca_sym = symbol.strip().upper().replace('-', '.')
        norm_side = side.strip().lower()
        norm_type = order_type.strip().lower()
        norm_tif = time_in_force.strip().lower()
        
        payload = {
            "symbol": alpaca_sym,
            "side": norm_side,
            "type": norm_type,
            "time_in_force": norm_tif
        }
        
        if qty is not None and float(qty) > 0:
            q_val = float(qty)
            payload["qty"] = str(int(q_val) if q_val.is_integer() else q_val)
        elif notional is not None and float(notional) > 0:
            payload["notional"] = str(round(float(notional), 2))
        else:
            return {"success": False, "error": "Must specify either positive quantity (shares) or dollar value ($ notional)"}
            
        if norm_type == "limit":
            if not limit_price or float(limit_price) <= 0:
                return {"success": False, "error": "Limit orders require a positive limit price"}
            payload["limit_price"] = str(round(float(limit_price), 2))
            if "notional" in payload:
                calc_shares = max(1, int(float(notional) / float(limit_price)))
                payload.pop("notional")
                payload["qty"] = str(calc_shares)
                
        import time, hashlib
        if client_order_id:
            payload["client_order_id"] = str(client_order_id)
        else:
            short_hash = hashlib.md5(f"{alpaca_sym}_{norm_side}_{time.time()}".encode()).hexdigest()[:8]
            payload["client_order_id"] = f"MANUAL-{short_hash}"
            
        if not self.api_key or self.api_key == "mock":
            return {
                "success": True,
                "message": f"Order for {alpaca_sym} submitted in mock mode",
                "order": {
                    "id": f"mock-{int(time.time())}",
                    "client_order_id": payload["client_order_id"],
                    "symbol": alpaca_sym,
                    "qty": payload.get("qty", "1"),
                    "notional": payload.get("notional"),
                    "side": norm_side,
                    "type": norm_type,
                    "status": "accepted"
                }
            }
            
        try:
            resp = requests.post(
                f"{self.base_url}/v2/orders",
                headers=self.headers,
                json=payload,
                timeout=10
            )
            if resp.status_code in (200, 201):
                return {
                    "success": True,
                    "message": f"Successfully placed {norm_side.upper()} order for {alpaca_sym}",
                    "order": resp.json()
                }
            else:
                err_msg = resp.text
                try:
                    err_json = resp.json()
                    err_msg = err_json.get("message", err_msg)
                except Exception:
                    pass
                return {"success": False, "error": err_msg}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def close_position(self, symbol: str, qty: Optional[float] = None) -> Dict[str, Any]:
        """Liquidate an open position via market order."""
        if not self.api_key or self.api_key == "mock":
            return {"success": True, "message": f"Position in {symbol} closed (mock)"}
        try:
            alpaca_sym = symbol.strip().upper().replace('-', '.')
            url = f"{self.base_url}/v2/positions/{alpaca_sym}"
            params = {}
            if qty is not None and float(qty) > 0:
                params["qty"] = str(qty)
            resp = requests.delete(url, headers=self.headers, params=params, timeout=10)
            if resp.status_code in (200, 204):
                return {"success": True, "message": f"Successfully initiated liquidation for {alpaca_sym}"}
            else:
                err_msg = resp.text
                try:
                    err_json = resp.json()
                    err_msg = err_json.get("message", err_msg)
                except Exception:
                    pass
                return {"success": False, "error": err_msg}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_stock_dictionary(self) -> List[str]:
        """Fetch the full list of tradable symbols from the bot's S&P 500 universe and holdings."""
        symbols = set()
        for core in ["SPY", "QQQ", "DIA", "IWM", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "TSLA"]:
            symbols.add(core)
        try:
            import os
            sp500_file = os.path.join(os.path.dirname(__file__), "..", "..", "data", "sp500_tickers.txt")
            if os.path.exists(sp500_file):
                with open(sp500_file, "r") as f:
                    for line in f:
                        s = line.strip().upper().replace('.', '-')
                        if s:
                            symbols.add(s)
        except Exception:
            pass
        try:
            for p in self.get_positions_detailed():
                symbols.add(p["symbol"])
        except Exception:
            pass
        return sorted(list(symbols))
