"""
Dual-Mode Order Execution: 1-Click Mobile Safety Net
Document Classification: Master Fiduciary Blueprint & Final Architecture
Strictly Governed by: FINAL_MASTER_HEDGE_FUND_ROADMAP.md (Chapter 2, Pod 2)

Fiduciary Principles:
1. Primary Mode (100% Autonomous Hands-Free Execution):
   - Authenticated broker REST APIs (Alpaca for US; Dhan OpenAPI with PyOTP TOTP 2FA for India).
   - Places orders autonomously with zero manual effort and posts execution receipts to Discord.
2. Secondary Mode (1-Click Mobile Safety Net):
   - If a broker token expires, network disconnects, or broker triggers an interactive 2FA challenge:
     The bot will NEVER crash, gamble, or drop the intended rebalance.
   - It immediately dispatches an interactive Discord card with pre-filled 1-click order execution links.
   - The Boss taps the link on mobile, verifies biometric login, and executes the basket in 5 seconds.
3. Fail-Closed Invariant:
   - Zero simulated/mock fallbacks in live mode.
   - Resting broker GTC stops remain active.
"""

import json
import urllib.parse
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from trading_system.app.common.logger import get_logger
from trading_system.app.notifications.notifier import QuantNotifier

logger = get_logger("OneClickSafetyNet")


@dataclass
class PendingBasketOrder:
    symbol: str
    side: str            # BUY or SELL
    quantity: float
    price_hint: float
    market_code: str = "IN"  # IN (NSE) or US


class OneClickOrderSafetyNet:
    """
    Manages generation of 1-click order baskets and dispatch of interactive
    Discord cards when broker APIs face authentication or interactive 2FA blocks.
    """

    DHAN_WEB_BASE = "https://trade.dhan.co"
    DHAN_MOBILE_APP_URI = "dhan://basket"

    def __init__(self, notifier: Optional[QuantNotifier] = None):
        self.notifier = notifier or QuantNotifier()

    @staticmethod
    def generate_dhan_basket_url(orders: List[Dict[str, Any]]) -> str:
        """
        Builds a pre-filled Dhan deep-link basket parameter string.
        """
        items = []
        for o in orders:
            # Clean symbol (e.g., RELIANCE.NS -> RELIANCE)
            sym = str(o.get("symbol", "")).replace(".NS", "").replace(".BO", "")
            items.append({
                "tradingSymbol": sym,
                "exchange": "NSE",
                "transactionType": str(o.get("side", "BUY")).upper(),
                "orderType": "MARKET",
                "productType": "CNC",  # Cash and Carry (Long-Only)
                "quantity": int(abs(float(o.get("quantity", 1))))
            })
        
        encoded_basket = urllib.parse.quote(json.dumps(items))
        return f"https://trade.dhan.co/basket?data={encoded_basket}"

    def dispatch_fallback_basket_card(
        self,
        orders: List[Dict[str, Any]],
        reason: str,
        market_code: str = "IN",
        currency_symbol: str = "₹"
    ) -> bool:
        """
        Formats and dispatches the 1-Click Mobile Safety Net card to Discord.
        """
        if not orders:
            return False

        basket_url = self.generate_dhan_basket_url(orders)
        
        # Build order summary bullet points
        order_lines = []
        total_est_val = 0.0
        for o in orders:
            sym = str(o.get("symbol", ""))
            side = str(o.get("side", "BUY")).upper()
            qty = abs(float(o.get("quantity", 0)))
            p = float(o.get("price_hint", 0.0))
            est_val = qty * p
            total_est_val += est_val

            side_emoji = "🟢 BUY" if side == "BUY" else "🔴 SELL"
            qty_str = f"{int(qty)}" if qty.is_integer() else f"{qty:.2f}"
            order_lines.append(
                f"• **{side_emoji}** {qty_str} shs of **{sym}** @ ~{currency_symbol}{p:,.2f} (Est: {currency_symbol}{est_val:,.2f})"
            )

        orders_str = "\n".join(order_lines)

        title = "📲 1-CLICK MOBILE BASKET DESK (SAFETY NET ACTIVE)"
        message = (
            f"⚠️ **Broker API Notice**: {reason}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"The Autonomous Quant Engine prepared {len(orders)} order(s) totaling ~{currency_symbol}{total_est_val:,.2f}.\n\n"
            f"**Pending Planned Trades:**\n"
            f"{orders_str}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 **[👉 Tap Here to Review & Execute Basket on Dhan Mobile/Web]({basket_url})**\n\n"
            f"*(Tap link, authenticate with your biometric login, and execute in 5 seconds. Resting GTC stop-losses remain fully active.)*"
        )

        logger.info(f"[1-CLICK SAFETY NET] Dispatched basket card for {len(orders)} orders: {reason}")
        return self.notifier.send_discord_alert(
            title=title,
            message=message,
            color=16744448  # High-visibility warning amber/orange
        )
