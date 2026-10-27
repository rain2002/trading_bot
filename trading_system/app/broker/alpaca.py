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
            
            today_pnl = equity - last_equity
            today_pnl_pct = (today_pnl / last_equity * 100) if last_equity > 0 else 0.0
            
            initial_capital = 100000.0
            overall_pnl = equity - initial_capital
            overall_pnl_pct = (overall_pnl / initial_capital * 100)
            
            return {
                "equity": equity,
                "cash": cash,
                "today_pnl": today_pnl,
                "today_pnl_pct": today_pnl_pct,
                "overall_pnl": overall_pnl,
                "overall_pnl_pct": overall_pnl_pct,
            }
        except Exception:
            return {
                "equity": 100000.0,
                "cash": 10000.0,
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
