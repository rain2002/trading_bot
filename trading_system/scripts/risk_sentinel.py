"""
Continuous Intraday Risk Sentinel & Automated Stop-Loss Enforcement Daemon
Monitors open positions, enforces per-position stop-loss thresholds (bot default -8% or user overrides),
and maintains broker-level GTC stop orders directly on Alpaca's matching engine.
"""

import sys
import os
import time
import argparse
from datetime import datetime
import requests

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from trading_system.app.config.settings import settings
from trading_system.app.broker.alpaca import AlpacaBrokerAdapter
from trading_system.app.config.stop_loss_manager import StopLossManager
from trading_system.app.notifications.notifier import QuantNotifier


class RiskSentinel:
    def __init__(self):
        self.api_key = settings.PAPER_API_KEY
        self.api_secret = settings.PAPER_API_SECRET
        self.base_url = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
        self.headers = {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.api_secret
        }
        self.broker = AlpacaBrokerAdapter(self.api_key, self.api_secret)
        self.sl_manager = StopLossManager()
        self.notifier = QuantNotifier()

    def get_open_orders(self) -> list:
        try:
            res = requests.get(f"{self.base_url}/v2/orders?status=open", headers=self.headers, timeout=10)
            return res.json() if res.status_code == 200 else []
        except Exception as e:
            print(f"Error fetching open orders: {e}")
            return []

    def scan_and_enforce(self, sync_gtc_stops: bool = True) -> dict:
        """
        Scans all live positions on Alpaca.
        1. If any position breaches its stop-loss threshold:
           - Immediately cancels conflicting orders and executes market sell liquidation.
           - Dispatches an urgent Discord alert.
        2. For safe holdings:
           - Automatically registers resting GTC Stop orders on Alpaca matching engine
             to guarantee that stop losses execute 24/7 in the cloud without delay.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{timestamp}] Running Intraday Risk Sentinel Scan...")

        positions = self.broker.get_positions_detailed()
        if not positions:
            print(" -> No open positions detected on broker.")
            return {"scanned": 0, "liquidated": [], "safe": []}

        liquidated = []
        safe = []

        open_orders = self.get_open_orders()
        orders_by_symbol = {}
        for o in open_orders:
            orders_by_symbol.setdefault(o["symbol"], []).append(o)

        for pos in positions:
            sym = pos["symbol"]
            qty = float(pos.get("qty", 0.0))
            if qty <= 0:
                continue

            entry_price = float(pos.get("avg_entry_price", 0.0))
            curr_price = float(pos.get("current_price", 0.0))
            pl = float(pos.get("unrealized_pl", 0.0))
            plpc = float(pos.get("unrealized_plpc", 0.0))

            threshold = self.sl_manager.get_stop_loss_pct(sym)
            is_custom = self.sl_manager.is_custom_override(sym)
            tag = "CUSTOM" if is_custom else "DEFAULT"
            target_stop_price = round(entry_price * (1.0 + threshold), 2)

            # -------------------------------------------------------------
            # CASE A: POSITION BREACHED STOP-LOSS (EMERGENCY LIQUIDATION)
            # -------------------------------------------------------------
            if plpc <= threshold or curr_price <= target_stop_price:
                print(f" -> [CRITICAL STOP-LOSS BREACH] {sym}: Down {plpc*100:.2f}% (Limit: {threshold*100:.1f}% [{tag}])!")
                print(f"    Shares: {qty} | Entry: ${entry_price:.2f} | Current: ${curr_price:.2f} | Loss: ${pl:,.2f}")

                # Check if there is already an active market sell order for this symbol
                existing_market_sells = [
                    o for o in orders_by_symbol.get(sym, [])
                    if o["side"] == "sell" and o["type"] == "market"
                ]
                if existing_market_sells:
                    print(f"    Active market sell order already resting on broker for {sym} (ID: {existing_market_sells[0]['id']}). Awaiting fill.")
                    liquidated.append({"symbol": sym, "qty": qty, "plpc": plpc, "status": "ALREADY_QUEUED"})
                    continue

                # Cancel any conflicting orders (e.g. stop orders or buy orders) holding shares
                for o in orders_by_symbol.get(sym, []):
                    try:
                        requests.delete(f"{self.base_url}/v2/orders/{o['id']}", headers=self.headers, timeout=5)
                        print(f"    Cancelled existing order for {sym} (ID: {o['id']})")
                    except Exception as e:
                        print(f"    Failed to cancel conflicting order: {e}")

                # Submit emergency market sell order (supports fractional precision)
                payload = {
                    "symbol": sym.replace("-", "."),
                    "qty": str(qty) if isinstance(qty, (int, float)) else str(qty),
                    "side": "sell",
                    "type": "market",
                    "time_in_force": "day",
                    "client_order_id": f"SENTINEL_STOP_{datetime.now().strftime('%Y%m%d%H%M%S')}_{sym}"
                }

                try:
                    res = requests.post(f"{self.base_url}/v2/orders", headers=self.headers, json=payload, timeout=10)
                    if res.status_code in (200, 201):
                        order_data = res.json()
                        print(f"    [EXECUTED] Emergency Stop-Loss liquidation order submitted for {sym} (Order ID: {order_data.get('id')})")
                        liquidated.append({"symbol": sym, "qty": qty, "plpc": plpc, "status": "SUBMITTED"})

                        # Dispatch Discord alert
                        try:
                            self.notifier.send_discord_alert(
                                title=f"🚨 STOP-LOSS TRIGGERED: {sym}",
                                message=f"Position {sym} breached stop-loss limit of {threshold*100:.1f}%. Liquidation order for {int(qty)} shares submitted at market price ${curr_price:.2f} (Loss: ${pl:,.2f} / {plpc*100:.2f}%).",
                                color=16711680 # Red
                            )
                        except Exception:
                            pass
                    else:
                        print(f"    [ERROR] Failed to submit liquidation order for {sym}: {res.status_code} {res.text}")
                except Exception as e:
                    print(f"    [EXCEPTION] Network error submitting liquidation for {sym}: {e}")

            # -------------------------------------------------------------
            # CASE B: SAFE POSITION (ENSURE RESTING GTC STOP ORDER ON BROKER)
            # -------------------------------------------------------------
            else:
                safe.append({"symbol": sym, "qty": qty, "plpc": plpc, "limit": threshold})
                print(f" -> [SAFE] {sym:<6}: PnL {plpc*100:+.2f}% | Stop Limit: ${target_stop_price:.2f} ({threshold*100:.1f}% [{tag}])")

                if sync_gtc_stops and target_stop_price < curr_price:
                    # Check if any sell order is already queued or resting (market sell or stop)
                    open_sells = [o for o in orders_by_symbol.get(sym, []) if o.get("side") == "sell"]
                    if open_sells:
                        existing_stops = [o for o in open_sells if o.get("type") == "stop"]
                        if existing_stops:
                            existing_stop_p = float(existing_stops[0].get("stop_price", 0.0))
                            print(f"    [GTC STOP ACTIVE] Resting broker stop order verified at ${existing_stop_p:.2f} (ID: {existing_stops[0]['id']})")
                        else:
                            print(f"    [SELL QUEUED] Active market liquidation already queued on broker (ID: {open_sells[0]['id']}). Skipping GTC stop.")
                    else:
                        # Register new GTC Stop order directly on Alpaca (Alpaca requires integer shares for GTC stop orders)
                        int_qty = int(qty)
                        if int_qty < 1:
                            print(f"    [FRACTIONAL HOLDING] {sym} quantity ({qty:.4f}) is sub-integer. Intraday Sentinel monitors directly.")
                            continue

                        stop_payload = {
                            "symbol": sym.replace("-", "."),
                            "qty": str(int_qty),
                            "side": "sell",
                            "type": "stop",
                            "stop_price": str(target_stop_price),
                            "time_in_force": "gtc",
                            "client_order_id": f"GTC_STOP_{sym}_{int_qty}_{int(time.time())}"
                        }
                        try:
                            s_res = requests.post(f"{self.base_url}/v2/orders", headers=self.headers, json=stop_payload, timeout=10)
                            if s_res.status_code in (200, 201):
                                s_data = s_res.json()
                                print(f"    [GTC STOP REGISTERED] Placed server-side stop on Alpaca at ${target_stop_price:.2f} (ID: {s_data.get('id')})")
                            elif s_res.status_code == 422 and "stop price must be less than current price" in s_res.text:
                                # Market price has already fallen below stop price in extended hours! Submit immediate market sell.
                                print(f"    [IMMEDIATE BREACH DETECTED] Live market price is already below ${target_stop_price:.2f}! Submitting emergency market liquidation.")
                                m_payload = {
                                    "symbol": sym.replace("-", "."),
                                    "qty": str(qty),
                                    "side": "sell",
                                    "type": "market",
                                    "time_in_force": "day",
                                    "client_order_id": f"SENTINEL_EMERGENCY_{datetime.now().strftime('%Y%m%d%H%M%S')}_{sym}"
                                }
                                m_res = requests.post(f"{self.base_url}/v2/orders", headers=self.headers, json=m_payload, timeout=10)
                                if m_res.status_code in (200, 201):
                                    print(f"    [EXECUTED] Immediate market liquidation submitted for {sym} (ID: {m_res.json().get('id')})")
                                    liquidated.append({"symbol": sym, "qty": qty, "plpc": plpc, "status": "SUBMITTED"})
                            else:
                                print(f"    [GTC STOP NOTICE] Broker stop not registered: {s_res.status_code} {s_res.text}")
                        except Exception as e:
                            print(f"    [GTC STOP EXCEPTION] {e}")

        print(f"\nSentinel scan complete: {len(safe)} positions protected | {len(liquidated)} stop-loss liquidations active.")
        return {"scanned": len(positions), "liquidated": liquidated, "safe": safe}


def main():
    parser = argparse.ArgumentParser(description="QUANT Risk Sentinel")
    parser.add_argument("--once", action="store_true", help="Run a single risk audit pass and exit.")
    parser.add_argument("--loop", action="store_true", help="Run continuously in a background monitoring loop.")
    parser.add_argument("--interval", type=int, default=60, help="Check interval in seconds (default: 60s).")
    parser.add_argument("--no-gtc", action="store_true", help="Disable automatic GTC broker stop order placement.")
    args = parser.parse_args()

    sentinel = RiskSentinel()

    if args.loop:
        print(f"Starting Risk Sentinel continuous loop (Interval: {args.interval}s)... Press Ctrl+C to stop.")
        while True:
            try:
                sentinel.scan_and_enforce(sync_gtc_stops=not args.no_gtc)
                time.sleep(args.interval)
            except KeyboardInterrupt:
                print("\nRisk Sentinel stopped by user.")
                break
            except Exception as e:
                print(f"Error in Risk Sentinel loop: {e}")
                time.sleep(args.interval)
    else:
        sentinel.scan_and_enforce(sync_gtc_stops=not args.no_gtc)


if __name__ == "__main__":
    main()
