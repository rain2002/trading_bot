import unittest
from unittest.mock import MagicMock, patch
from trading_system.app.notifications.notifier import QuantNotifier

class TestQuantNotifier(unittest.TestCase):
    def setUp(self):
        self.notifier = QuantNotifier(
            discord_webhook_url="https://discord.mock/webhook",
            telegram_bot_token="mock_token",
            telegram_chat_id="mock_chat_id"
        )

    @patch("requests.post")
    def test_send_daily_summary_with_detailed_positions(self, mock_post):
        mock_post.return_value.status_code = 200

        detailed_positions = [
            {"symbol": "AAPL", "qty": 10.0, "market_value": 1500.0, "unrealized_plpc": -0.025},
            {"symbol": "MSFT", "qty": 5.0, "market_value": 2000.0, "unrealized_plpc": 0.082},
            {"symbol": "DASH_TEST", "qty": 20.0, "market_value": 3000.0, "unrealized_plpc": 0.155},
        ]

        self.notifier.send_daily_summary(
            equity=100000.0,
            cash=10000.0,
            open_positions_count=3,
            executed_orders=[],
            positions_detailed=detailed_positions,
            today_pnl=500.0,
            today_pnl_pct=0.5,
            overall_pnl=2500.0,
            overall_pnl_pct=2.5,
            regime_info="BULL_TREND",
            currency_symbol="$"
        )

        self.assertEqual(mock_post.call_count, 2)
        
        # Check Discord payload
        discord_call = mock_post.call_args_list[0]
        discord_payload = discord_call[1]["json"]["content"]
        self.assertIn("Open Portfolio Holdings (3):", discord_payload)
        # Verify DASH_TEST is first because it has highest return (+15.50%)
        dash_idx = discord_payload.find("DASH_TEST")
        msft_idx = discord_payload.find("MSFT")
        aapl_idx = discord_payload.find("AAPL")
        self.assertTrue(dash_idx < msft_idx < aapl_idx)
        self.assertIn("+15.50%", discord_payload)
        self.assertIn("-2.50%", discord_payload)
        self.assertIn("No rebalance orders required today", discord_payload)

        # Check Telegram payload (sanitized underscores)
        tg_call = mock_post.call_args_list[1]
        tg_payload = tg_call[1]["json"]["text"]
        self.assertIn("DASH TEST", tg_payload) # underscores replaced for Telegram Markdown safety
        self.assertIn("BULL TREND", tg_payload)

    @patch("requests.post")
    def test_send_daily_summary_empty_positions(self, mock_post):
        mock_post.return_value.status_code = 200

        self.notifier.send_daily_summary(
            equity=50000.0,
            cash=50000.0,
            open_positions_count=0,
            executed_orders=[],
            positions_detailed=[],
            today_pnl=0.0,
            today_pnl_pct=0.0,
            overall_pnl=0.0,
            overall_pnl_pct=0.0,
            regime_info="CRASH_WARNING",
            currency_symbol="₹"
        )

        discord_payload = mock_post.call_args_list[0][1]["json"]["content"]
        self.assertIn("Open Portfolio Holdings (0):", discord_payload)
        self.assertIn("No open positions (100% Cash Buffer)", discord_payload)
        self.assertIn("₹50,000.00", discord_payload)

    @patch("requests.post")
    def test_send_daily_summary_overflow_positions(self, mock_post):
        mock_post.return_value.status_code = 200

        detailed_positions = [
            {"symbol": f"SYM_{i}", "qty": 1.0, "market_value": 100.0, "unrealized_plpc": 0.01 * i}
            for i in range(25)
        ]

        self.notifier.send_daily_summary(
            equity=100000.0,
            cash=10000.0,
            open_positions_count=25,
            executed_orders=[],
            positions_detailed=detailed_positions,
        )

        discord_payload = mock_post.call_args_list[0][1]["json"]["content"]
        self.assertIn("Open Portfolio Holdings (25):", discord_payload)
        self.assertIn("...and 7 more positions", discord_payload)
        # Strictly ensure discord message is within 2,000 character limit
        self.assertLess(len(discord_payload), 2000)

if __name__ == "__main__":
    unittest.main()
