"""
Unified Notification Service for Quant Trading Bot.
Supports Discord Webhooks and Telegram Bots.
Fails gracefully: if credentials are missing or network drops,
it will NEVER interrupt or crash the trading bot.
"""

import os
import logging
from typing import List, Dict, Any, Optional
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("QuantNotifier")


class QuantNotifier:
    """
    Sends structured daily performance and execution alerts to Discord or Telegram.
    """

    def __init__(
        self,
        discord_webhook_url: Optional[str] = None,
        telegram_bot_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
    ):
        self.discord_url = discord_webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
        self.tg_token = telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.tg_chat_id = telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID")

    def send_discord_message(self, content: str) -> bool:
        if not self.discord_url:
            return False
        try:
            payload = {"content": content}
            resp = requests.post(self.discord_url, json=payload, timeout=8)
            return resp.status_code in (200, 204)
        except Exception as e:
            logger.warning(f"Failed to dispatch Discord webhook: {e}")
            return False

    def send_telegram_message(self, content: str) -> bool:
        if not self.tg_token or not self.tg_chat_id:
            return False
        try:
            url = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
            payload = {
                "chat_id": self.tg_chat_id,
                "text": content,
                "parse_mode": "Markdown",
            }
            resp = requests.post(url, json=payload, timeout=8)
            return resp.status_code == 200
        except Exception as e:
            logger.warning(f"Failed to dispatch Telegram alert: {e}")
            return False

    def send_daily_summary(
        self,
        equity: float,
        cash: float,
        open_positions_count: int,
        executed_orders: List[Dict[str, Any]],
        today_pnl: float = 0.0,
        today_pnl_pct: float = 0.0,
        overall_pnl: float = 0.0,
        overall_pnl_pct: float = 0.0,
        regime_info: str = "NORMAL (Conviction Filter Active)",
    ):
        """
        Formats and dispatches the daily rebalance report with Today's Return,
        Overall Return, and Cash Reserve status to configured channels.
        """
        # Format today's return indicator
        today_sign = "+" if today_pnl >= 0 else ""
        today_emoji = "🟢" if today_pnl >= 0 else "🔴"
        
        # Format overall return indicator
        overall_sign = "+" if overall_pnl >= 0 else ""
        overall_emoji = "🚀" if overall_pnl >= 0 else "🔻"

        cash_pct = (cash / equity * 100) if equity > 0 else 0.0

        # Format executed orders preview
        if executed_orders:
            orders_lines = []
            for o in executed_orders[:10]:
                side_emoji = "🟢" if o.get("side") == "BUY" else "🔴"
                orders_lines.append(
                    f"  {side_emoji} {o.get('side')} {abs(o.get('qty', 0))} {o.get('symbol')}"
                )
            if len(executed_orders) > 10:
                orders_lines.append(f"  ...and {len(executed_orders) - 10} more orders")
            orders_summary = "\n".join(orders_lines)
        else:
            orders_summary = "  ⚪ No orders required today (Portfolio balanced)"

        # Discord message (Discord Flavored Markdown)
        message = (
            f"🤖 **QUANT BOT DAILY REBALANCE REPORT**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 **Total Equity:** ${equity:,.2f}\n"
            f"📈 **Today's Return:** {today_emoji} {today_sign}${today_pnl:,.2f} ({today_sign}{today_pnl_pct:.2f}%)\n"
            f"🏆 **Overall Return:** {overall_emoji} {overall_sign}${overall_pnl:,.2f} ({overall_sign}{overall_pnl_pct:.2f}%)\n"
            f"💵 **Cash Reserve:** ${cash:,.2f} ({cash_pct:.1f}% uninvested buffer)\n"
            f"📊 **Active Holdings:** {open_positions_count} stocks\n"
            f"🛡️ **Regime Status:** {regime_info}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔄 **Orders Executed Today ({len(executed_orders)}):**\n"
            f"{orders_summary}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 *Cash Reserve is liquid uninvested cash protecting against drawdowns & ready for fresh breakouts.*"
        )

        sent_any = False
        if self.discord_url:
            if self.send_discord_message(message):
                sent_any = True
                print(" -> Discord alert sent successfully.")

        if self.tg_token and self.tg_chat_id:
            # Telegram message (Standard Markdown)
            tg_message = (
                f"🤖 *QUANT BOT DAILY REBALANCE REPORT*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 *Total Equity:* ${equity:,.2f}\n"
                f"📈 *Today's Return:* {today_emoji} {today_sign}${today_pnl:,.2f} ({today_sign}{today_pnl_pct:.2f}%)\n"
                f"🏆 *Overall Return:* {overall_emoji} {overall_sign}${overall_pnl:,.2f} ({overall_sign}{overall_pnl_pct:.2f}%)\n"
                f"💵 *Cash Reserve:* ${cash:,.2f} ({cash_pct:.1f}% uninvested buffer)\n"
                f"📊 *Active Holdings:* {open_positions_count} stocks\n"
                f"🛡️ *Regime:* {regime_info}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🔄 *Orders Executed ({len(executed_orders)}):*\n"
                f"{orders_summary}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💡 _Cash Reserve is uninvested cash protecting against drawdowns & ready for fresh breakouts._"
            )
            if self.send_telegram_message(tg_message):
                sent_any = True
                print(" -> Telegram alert sent successfully.")

        if not sent_any:
            print(" -> Notice: Neither Discord nor Telegram webhook configured. Alert logged to console only.")
