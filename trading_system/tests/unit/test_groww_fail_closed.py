"""
Unit tests verifying strict Fail-Closed behavior for GrowwBrokerAdapter.
Institutional Invariant:
In live mode (is_live=True), any network timeout, 4xx/5xx HTTP error, or disconnect
must raise clean BrokerConnectionError or OrderExecutionError, set is_connected()=False,
dispatch an emergency alert, and NEVER return mock holdings, fake balances, or arbitrary prices.
"""

import pytest
from unittest.mock import MagicMock, patch
from trading_system.app.broker.groww import (
    GrowwBrokerAdapter,
    BrokerConnectionError,
    OrderExecutionError,
    BrokerAPIError,
)


@pytest.fixture
def mock_notifier():
    notifier = MagicMock()
    notifier.send_discord_alert = MagicMock(return_value=True)
    notifier.send_discord_message = MagicMock(return_value=True)
    return notifier


@pytest.fixture
def mock_groww_client():
    client = MagicMock()
    client.get_user_balance.return_value = {"cash": 250000.0}
    client.get_holdings_for_user.return_value = {
        "holdings": [
            {
                "trading_symbol": "INFY",
                "quantity": 100,
                "average_price": 1800.0,
                "ltp": 1850.0,
            }
        ]
    }
    client.get_quote.return_value = {"ltp": 1850.0}
    return client


def test_live_groww_adapter_connected_init(mock_groww_client, mock_notifier):
    """When properly initialized with a healthy client, is_connected() is True."""
    adapter = GrowwBrokerAdapter(
        api_key="LIVE_KEY_123",
        api_secret="LIVE_SECRET_123",
        totp_secret="LIVE_TOTP_123",
        is_live=True,
        client=mock_groww_client,
        notifier=mock_notifier,
    )
    assert adapter.is_live is True
    assert adapter.is_mock is False
    assert adapter.is_connected() is True
    assert len(adapter._mock_positions) == 0


def test_live_groww_fails_closed_on_get_positions_500(mock_groww_client, mock_notifier):
    """
    When Groww API returns a 500 error during get_positions(), the adapter must:
    1. Raise BrokerConnectionError.
    2. NOT return mock positions (Reliance, TCS, etc.).
    3. Mark is_connected() as False.
    4. Dispatch an emergency alert.
    """
    mock_groww_client.get_holdings_for_user.side_effect = Exception("HTTP 500 Internal Server Error")
    adapter = GrowwBrokerAdapter(
        api_key="LIVE_KEY_123",
        is_live=True,
        client=mock_groww_client,
        notifier=mock_notifier,
    )

    with pytest.raises(BrokerConnectionError) as exc_info:
        adapter.get_positions()

    assert "Fail-Closed" in str(exc_info.value)
    assert "HTTP 500" in str(exc_info.value)
    assert adapter.is_connected() is False

    # Verify zero mock positions leaked
    assert "RELIANCE.NS" not in adapter._mock_positions

    # Verify emergency alert hook was called
    assert mock_notifier.send_discord_alert.called or mock_notifier.send_discord_message.called


def test_live_groww_fails_closed_on_get_account_details_disconnect(mock_groww_client, mock_notifier):
    """
    When Groww API disconnects during get_account_details():
    1. Raise BrokerConnectionError.
    2. Zero fake cash / balances returned.
    3. is_connected() returns False.
    """
    mock_groww_client.get_user_balance.side_effect = ConnectionError("Network unreachable")
    adapter = GrowwBrokerAdapter(
        api_key="LIVE_KEY_123",
        is_live=True,
        client=mock_groww_client,
        notifier=mock_notifier,
    )

    with pytest.raises(BrokerConnectionError) as exc_info:
        adapter.get_account_details()

    assert "Network unreachable" in str(exc_info.value)
    assert adapter.is_connected() is False
    assert mock_notifier.send_discord_alert.called or mock_notifier.send_discord_message.called


def test_live_groww_place_order_fails_closed_on_api_error(mock_groww_client, mock_notifier):
    """
    When Groww API rejects or fails order placement:
    1. Raise OrderExecutionError.
    2. Zero orders placed or simulated.
    3. Emergency alert dispatched.
    4. is_connected() returns False.
    """
    mock_groww_client.place_order.side_effect = Exception("HTTP 502 Bad Gateway")
    adapter = GrowwBrokerAdapter(
        api_key="LIVE_KEY_123",
        is_live=True,
        client=mock_groww_client,
        notifier=mock_notifier,
    )

    with patch("trading_system.app.broker.live_safety_fuse.verify_live_safety_fuse", return_value=True):
        with pytest.raises(OrderExecutionError) as exc_info:
            adapter.place_order(symbol="INFY.NS", qty=10, side="BUY")

    assert "HTTP 502" in str(exc_info.value)
    assert adapter.is_connected() is False
    assert len(adapter._mock_orders) == 0
    assert mock_notifier.send_discord_alert.called or mock_notifier.send_discord_message.called


def test_live_groww_price_fetch_fails_closed_without_fake_1000(mock_groww_client, mock_notifier):
    """
    When price cannot be determined from live quote or yfinance:
    1. MUST NOT return default ₹1,000.
    2. Raises BrokerConnectionError in live mode.
    """
    mock_groww_client.get_quote.side_effect = Exception("Quote server timeout")
    adapter = GrowwBrokerAdapter(
        api_key="LIVE_KEY_123",
        is_live=True,
        client=mock_groww_client,
        notifier=mock_notifier,
    )

    with patch("yfinance.Ticker") as mock_yf:
        mock_hist = MagicMock()
        mock_hist.empty = True
        mock_yf.return_value.history.return_value = mock_hist

        with pytest.raises(BrokerConnectionError) as exc_info:
            adapter.get_latest_price("UNKNOWN.NS")

        assert "Unable to determine valid market price" in str(exc_info.value)


def test_mock_groww_mode_retains_test_simulation():
    """
    Paper/Mock mode continues to operate cleanly for offline tests and simulations.
    """
    adapter = GrowwBrokerAdapter(
        api_key="placeholder_groww_key",
        is_live=False,
        initial_capital=1000000.0,
    )
    assert adapter.is_mock is True
    assert adapter.is_live is False
    assert adapter.is_connected() is True

    positions = adapter.get_positions()
    assert "RELIANCE.NS" in positions
    assert positions["RELIANCE.NS"] == 50
