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

from trading_system.app.config.settings import settings

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
        self.discord_url = (
            discord_webhook_url
            or os.getenv("DISCORD_WEBHOOK_URL")
            or getattr(settings, "DISCORD_WEBHOOK_URL", None)
        )
        self.tg_token = (
            telegram_bot_token
            or os.getenv("TELEGRAM_BOT_TOKEN")
            or getattr(settings, "TELEGRAM_BOT_TOKEN", None)
        )
        self.tg_chat_id = (
            telegram_chat_id
            or os.getenv("TELEGRAM_CHAT_ID")
            or getattr(settings, "TELEGRAM_CHAT_ID", None)
        )

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

    def send_discord_alert(self, title: str, message: str, color: int = 16711680) -> bool:
        """
        Dispatches a rich embed alert (e.g., stop-loss trigger, broker fail-closed event)
        to the configured Discord webhook.
        """
        if not self.discord_url:
            return False
        try:
            payload = {
                "embeds": [
                    {
                        "title": title,
                        "description": message,
                        "color": color,
                    }
                ]
            }
            resp = requests.post(self.discord_url, json=payload, timeout=8)
            return resp.status_code in (200, 204)
        except Exception as e:
            logger.warning(f"Failed to dispatch Discord embed alert: {e}")
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
        positions_detailed: Optional[List[Dict[str, Any]]] = None,
        today_pnl: float = 0.0,
        today_pnl_pct: float = 0.0,
        overall_pnl: float = 0.0,
        overall_pnl_pct: float = 0.0,
        regime_info: str = "NORMAL (Conviction Filter Active)",
        currency_symbol: str = "$",
        cro_tier: Optional[str] = None,
        nav_per_unit: Optional[float] = None,
        true_trading_return_pct: Optional[float] = None,
        tactical_cash_reserve: Optional[float] = None,
    ):
        """
        Formats and dispatches the daily rebalance report with Today's Return,
        Overall Return, Cash Reserve status, Unitized NAV, CRO Risk Tier, and Detailed Holdings.
        """
        # Format today's return indicator
        today_sign = "+" if today_pnl >= 0 else ""
        today_emoji = "🟢" if today_pnl >= 0 else "🔴"
        
        # Format overall return indicator
        overall_sign = "+" if overall_pnl >= 0 else ""
        overall_emoji = "🚀" if overall_pnl >= 0 else "🔻"

        cash_pct = (cash / equity * 100) if equity > 0 else 0.0

        extra_metrics = ""
        tg_extra_metrics = ""
        if nav_per_unit is not None:
            t_sign = "+" if (true_trading_return_pct or 0.0) >= 0 else ""
            t_ret = true_trading_return_pct or 0.0
            extra_metrics += f"🏷️ **Unitized NAV:** {currency_symbol}{nav_per_unit:,.2f}/unit (True Trading Return: {t_sign}{t_ret:.2f}%)\n"
            tg_extra_metrics += f"🏷️ *Unitized NAV:* {currency_symbol}{nav_per_unit:,.2f}/unit (True Trading Return: {t_sign}{t_ret:.2f}%)\n"
        if tactical_cash_reserve is not None and tactical_cash_reserve > 0:
            extra_metrics += f"🎯 **Tactical SIP Buffer:** {currency_symbol}{tactical_cash_reserve:,.2f} dry powder\n"
            tg_extra_metrics += f"🎯 *Tactical SIP Buffer:* {currency_symbol}{tactical_cash_reserve:,.2f} dry powder\n"
        if cro_tier is not None:
            extra_metrics += f"🛡️ **CRO Drawdown Tier:** {cro_tier}\n"
            tg_cro = str(cro_tier).replace('_', ' ')
            tg_extra_metrics += f"🛡️ *CRO Drawdown Tier:* {tg_cro}\n"

        # Determine effective holdings count
        effective_count = len(positions_detailed) if positions_detailed is not None else open_positions_count

        # Format positions preview for Discord & Telegram
        if positions_detailed:
            sorted_pos = sorted(
                positions_detailed,
                key=lambda p: p.get("unrealized_plpc", 0.0),
                reverse=True,
            )
            positions_lines = []
            tg_positions_lines = []
            for p in sorted_pos[:18]:
                sym = str(p.get("symbol", ""))
                qty = p.get("qty", 0)
                mv = p.get("market_value", 0.0)
                plpc = p.get("unrealized_plpc", 0.0) * 100.0
                sign = "+" if plpc >= 0 else ""
                pl_emoji = "🟢" if plpc >= 0 else "🔴"
                qty_str = f"{int(qty)}" if float(qty).is_integer() else f"{qty:.2f}"
                
                positions_lines.append(
                    f"  {pl_emoji} **{sym}**: {qty_str} shs | {currency_symbol}{mv:,.2f} ({sign}{plpc:.2f}%)"
                )
                tg_sym = sym.replace("_", " ")
                tg_positions_lines.append(
                    f"  {pl_emoji} *{tg_sym}*: {qty_str} shs | {currency_symbol}{mv:,.2f} ({sign}{plpc:.2f}%)"
                )

            if len(sorted_pos) > 18:
                overflow_msg = f"  ...and {len(sorted_pos) - 18} more positions"
                positions_lines.append(overflow_msg)
                tg_positions_lines.append(overflow_msg)

            positions_summary = "\n".join(positions_lines)
            tg_positions_summary = "\n".join(tg_positions_lines)
        else:
            if effective_count == 0:
                positions_summary = "  ⚪ No open positions (100% Cash Buffer)"
                tg_positions_summary = "  ⚪ No open positions (100% Cash Buffer)"
            else:
                positions_summary = f"  📊 {effective_count} active positions held"
                tg_positions_summary = f"  📊 {effective_count} active positions held"

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
            orders_summary = "  ⚪ No rebalance orders required today (Holdings within targets)"

        # Discord message (Discord Flavored Markdown)
        message = (
            f"🤖 **QUANT BOT DAILY REBALANCE REPORT**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 **Total Equity:** {currency_symbol}{equity:,.2f}\n"
            f"{extra_metrics}"
            f"📈 **Today's Return:** {today_emoji} {today_sign}{currency_symbol}{today_pnl:,.2f} ({today_sign}{today_pnl_pct:.2f}%)\n"
            f"🏆 **Overall Return:** {overall_emoji} {overall_sign}{currency_symbol}{overall_pnl:,.2f} ({overall_sign}{overall_pnl_pct:.2f}%)\n"
            f"💵 **Cash Reserve:** {currency_symbol}{cash:,.2f} ({cash_pct:.1f}% uninvested buffer)\n"
            f"🛡️ **Regime Status:** {regime_info}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 **Open Portfolio Holdings ({effective_count}):**\n"
            f"{positions_summary}\n"
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
            # Telegram message (Standard Markdown - sanitize underscores to prevent 400 Bad Request)
            tg_regime = str(regime_info).replace('_', ' ')
            tg_orders = str(orders_summary).replace('_', ' ')
            tg_message = (
                f"🤖 *QUANT BOT DAILY REBALANCE REPORT*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 *Total Equity:* {currency_symbol}{equity:,.2f}\n"
                f"{tg_extra_metrics}"
                f"📈 *Today's Return:* {today_emoji} {today_sign}{currency_symbol}{today_pnl:,.2f} ({today_sign}{today_pnl_pct:.2f}%)\n"
                f"🏆 *Overall Return:* {overall_emoji} {overall_sign}{currency_symbol}{overall_pnl:,.2f} ({overall_sign}{overall_pnl_pct:.2f}%)\n"
                f"💵 *Cash Reserve:* {currency_symbol}{cash:,.2f} ({cash_pct:.1f}% uninvested buffer)\n"
                f"🛡️ *Regime:* {tg_regime}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📋 *Open Portfolio Holdings ({effective_count}):*\n"
                f"{tg_positions_summary}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🔄 *Orders Executed ({len(executed_orders)}):*\n"
                f"{tg_orders}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💡 _Cash Reserve is uninvested cash protecting against drawdowns and ready for fresh breakouts._"
            )
            if self.send_telegram_message(tg_message):
                sent_any = True
                print(" -> Telegram alert sent successfully.")

        if not sent_any:
            print(" -> Notice: Neither Discord nor Telegram webhook configured. Alert logged to console only.")
