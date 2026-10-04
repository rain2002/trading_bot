import pandas as pd
from datetime import datetime
from trading_system.app.common.logger import get_logger
from trading_system.app.common.database import engine
from sqlalchemy.orm import sessionmaker
import requests

logger = get_logger("CanaryValidator")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class CanaryValidationEngine:
    """
    Phase 16 Tool: Canary Validation.
    Retrieves Live/Paper real-world executions from the broker and compares them against
    the idealized backtest theoretical fills to calculate real-world slippage,
    timing latency, and execution divergence.
    """
    
    def __init__(self, api_key: str, api_secret: str):
        self.headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": api_secret
        }
        self.base_url = 'https://paper-api.alpaca.markets'
        
    def fetch_live_executions(self, start_time: datetime, end_time: datetime):
        """Fetch closed orders from Alpaca"""
        try:
            params = {
                'status': 'closed',
                'after': start_time.isoformat() + 'Z',
                'until': end_time.isoformat() + 'Z',
                'direction': 'asc'
            }
            
            response = requests.get(
                f"{self.base_url}/v2/orders",
                headers=self.headers,
                params=params
            )
            
            if response.status_code != 200:
                logger.error(f"Alpaca API Error: {response.text}")
                return pd.DataFrame()
                
            orders = response.json()
            
            executions = []
            for order in orders:
                if order.get('filled_qty') and float(order['filled_qty']) > 0:
                    executions.append({
                        "client_order_id": order.get('client_order_id'),
                        "symbol": order.get('symbol'),
                        "side": order.get('side'),
                        "requested_qty": float(order.get('qty', 0)),
                        "filled_qty": float(order.get('filled_qty', 0)),
                        "filled_avg_price": float(order.get('filled_avg_price', 0)),
                        "submitted_at": order.get('submitted_at'),
                        "filled_at": order.get('filled_at'),
                        "status": order.get('status')
                    })
            return pd.DataFrame(executions)
        except Exception as e:
            logger.error(f"Failed to fetch live executions: {e}")
            return pd.DataFrame()

    def generate_divergence_report(self, live_executions_df: pd.DataFrame, expected_price_dict: dict):
        """
        expected_price_dict: A dictionary mapping symbol -> expected fill price (usually close of previous bar).
        """
        if live_executions_df.empty:
            logger.warning("No live executions found to validate.")
            return {}
            
        report = {
            "total_orders": len(live_executions_df),
            "fully_filled": len(live_executions_df[live_executions_df['requested_qty'] == live_executions_df['filled_qty']]),
            "partially_filled": len(live_executions_df[live_executions_df['requested_qty'] != live_executions_df['filled_qty']]),
            "average_slippage_bps": 0.0,
            "average_latency_seconds": 0.0,
            "slippage_by_symbol": {}
        }
        
        total_slippage_bps = 0
        total_latency_seconds = 0
        
        for _, row in live_executions_df.iterrows():
            sym = row['symbol']
            actual_price = row['filled_avg_price']
            side = row['side']
            
            # Calculate Latency
            sub_time = pd.to_datetime(row['submitted_at'])
            fill_time = pd.to_datetime(row['filled_at'])
            latency = (fill_time - sub_time).total_seconds()
            total_latency_seconds += latency
            
            # Calculate Slippage (in Basis Points)
            expected_price = expected_price_dict.get(sym)
            if expected_price:
                # If buying, higher actual price = negative slippage (bad)
                # If selling, lower actual price = negative slippage (bad)
                diff = expected_price - actual_price if side == 'buy' else actual_price - expected_price
                slippage_bps = (diff / expected_price) * 10000
                total_slippage_bps += slippage_bps
                
                report["slippage_by_symbol"][sym] = round(slippage_bps, 2)
                
        if report["total_orders"] > 0:
            report["average_slippage_bps"] = round(total_slippage_bps / report["total_orders"], 2)
            report["average_latency_seconds"] = round(total_latency_seconds / report["total_orders"], 2)
            
        return report
