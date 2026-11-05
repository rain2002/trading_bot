"""
Unit Tests for Dual-Mode 1-Click Order Execution Safety Net (Chapter 2, Pod 2)
Governed by: FINAL_MASTER_HEDGE_FUND_ROADMAP.md (Section 3, Chapter 2)
"""

import json
import urllib.parse
import pytest
from unittest.mock import MagicMock, patch

from trading_system.app.execution.dhan_fallback import OneClickOrderSafetyNet


class TestOneClickSafetyNet:

    def test_generate_dhan_basket_url(self):
        """
        Verifies correct URL encoding and parameter schema for Dhan basket generation.
        """
        orders = [
            {"symbol": "BEL.NS", "side": "BUY", "quantity": 15, "price_hint": 295.40},
            {"symbol": "TCS.NS", "side": "BUY", "quantity": 2, "price_hint": 3950.0}
        ]

        url = OneClickOrderSafetyNet.generate_dhan_basket_url(orders)
        assert url.startswith("https://trade.dhan.co/basket?data=")

        parsed_url = urllib.parse.urlparse(url)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        assert "data" in query_params

        decoded_data = json.loads(query_params["data"][0])
        assert len(decoded_data) == 2
        assert decoded_data[0]["tradingSymbol"] == "BEL"
        assert decoded_data[0]["transactionType"] == "BUY"
        assert decoded_data[0]["productType"] == "CNC"
        assert decoded_data[0]["quantity"] == 15
        assert decoded_data[1]["tradingSymbol"] == "TCS"
        assert decoded_data[1]["quantity"] == 2

    def test_dispatch_fallback_basket_card(self):
        """
        Verifies that when triggered, the safety net formats and dispatches
        a high-priority rich Discord card with one-click URL.
        """
        mock_notifier = MagicMock()
        safety_net = OneClickOrderSafetyNet(notifier=mock_notifier)

        orders = [
            {"symbol": "RELIANCE.NS", "side": "BUY", "quantity": 5, "price_hint": 2700.0}
        ]

        result = safety_net.dispatch_fallback_basket_card(
            orders=orders,
            reason="Interactive TOTP challenge / token expired",
            currency_symbol="₹"
        )

        assert mock_notifier.send_discord_alert.called
        call_kwargs = mock_notifier.send_discord_alert.call_args[1]
        assert "1-CLICK MOBILE BASKET DESK" in call_kwargs["title"]
        assert "RELIANCE.NS" in call_kwargs["message"]
        assert "https://trade.dhan.co/basket" in call_kwargs["message"]
        assert call_kwargs["color"] == 16744448  # Amber
