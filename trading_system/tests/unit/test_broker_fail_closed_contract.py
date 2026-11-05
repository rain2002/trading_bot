"""
Unit tests verifying standardized Broker-Wide Fail-Closed Enforcement (Task 2).
Covers:
1. AlpacaBrokerAdapter fail-closed contract on simulated API disconnect.
2. Standardized PaperBrokerAdapter behavior in connected and disconnected states.
3. Batch execution abort on network dropouts without state corruption.
"""

import pytest
from unittest.mock import MagicMock, patch
import requests

from trading_system.app.broker.alpaca import (
    AlpacaBrokerAdapter,
    BrokerAPIError,
    BrokerConnectionError,
    OrderExecutionError,
)
from trading_system.app.broker.paper import PaperBrokerAdapter


@pytest.fixture
def mock_notifier():
    notifier = MagicMock()
    notifier.send_discord_alert = MagicMock(return_value=True)
    notifier.send_discord_message = MagicMock(return_value=True)
    return notifier


def test_alpaca_is_connected_reflects_api_health():
    """is_connected() returns True on HTTP 200 and False on network error."""
    broker = AlpacaBrokerAdapter(api_key="LIVE_KEY", api_secret="LIVE_SECRET")

    # Healthy connection
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        assert broker.is_connected() is True

    # Broken connection / 500
    with patch("requests.get", side_effect=requests.exceptions.ConnectionError("Connection refused")):
        assert broker.is_connected() is False


def test_alpaca_get_positions_fails_closed_after_3_retries(mock_notifier):
    """
    On network disconnect, get_positions() retries exactly 3 times and raises
    BrokerConnectionError without hanging or corrupting state.
    """
    broker = AlpacaBrokerAdapter(
        api_key="LIVE_KEY",
        api_secret="LIVE_SECRET",
        notifier=mock_notifier,
    )

    with patch("requests.get", side_effect=requests.exceptions.Timeout("Timeout")) as mock_get:
        with patch("time.sleep"):  # fast-forward retries
            with pytest.raises(BrokerAPIError) as exc_info:
                broker.get_positions()

        assert mock_get.call_count == 3
        assert "Fail-Closed" in str(exc_info.value)


def test_alpaca_get_open_orders_fails_closed_on_disconnect(mock_notifier):
    """
    In live mode, get_open_orders() must raise BrokerConnectionError on failure,
    never silently return [] which would risk double-submitting or wiping stops.
    """
    broker = AlpacaBrokerAdapter(
        api_key="LIVE_KEY",
        api_secret="LIVE_SECRET",
        notifier=mock_notifier,
    )

    with patch("requests.get", side_effect=Exception("HTTP 503 Service Unavailable")):
        with patch("time.sleep"):
            with pytest.raises(BrokerConnectionError) as exc_info:
                broker.get_open_orders()

        assert "HTTP 503" in str(exc_info.value)
        assert mock_notifier.send_discord_alert.called or mock_notifier.send_discord_message.called


def test_alpaca_cancel_all_orders_fails_closed_on_error(mock_notifier):
    """cancel_all_orders() must raise OrderExecutionError on non-200 responses in live mode."""
    broker = AlpacaBrokerAdapter(
        api_key="LIVE_KEY",
        api_secret="LIVE_SECRET",
        notifier=mock_notifier,
    )

    with patch("requests.delete") as mock_delete:
        mock_delete.return_value.status_code = 500
        mock_delete.return_value.text = "Internal Server Error"

        with pytest.raises(OrderExecutionError):
            broker.cancel_all_orders()


def test_paper_broker_adapter_contract():
    """PaperBrokerAdapter must satisfy the standard BrokerAdapter interface and fail-closed when disconnected."""
    paper = PaperBrokerAdapter(initial_capital=50000.0)
    assert paper.is_connected() is True

    # Initial state
    assert paper.get_account_equity() == 50000.0
    assert len(paper.get_positions()) == 0

    # Place paper trade
    res = paper.place_order(symbol="AAPL", qty=10, side="BUY", price=150.0)
    assert res["success"] is True
    assert paper.get_positions().get("AAPL") == 10
    assert paper.get_account_equity() == 50000.0  # Cash + Invested = Total unchanged

    # Disconnect simulation
    paper.set_connected(False)
    assert paper.is_connected() is False

    with pytest.raises(BrokerConnectionError):
        paper.get_positions()

    with pytest.raises(BrokerConnectionError):
        paper.get_account_equity()

    with pytest.raises(OrderExecutionError):
        paper.place_order(symbol="MSFT", qty=5, side="BUY", price=300.0)


def test_alpaca_cancel_order_fails_closed_on_network_drop(mock_notifier):
    """cancel_order() raises OrderExecutionError when request times out."""
    broker = AlpacaBrokerAdapter(
        api_key="LIVE_KEY",
        api_secret="LIVE_SECRET",
        notifier=mock_notifier,
    )

    with patch("requests.delete", side_effect=requests.exceptions.Timeout("Delete timed out")):
        with pytest.raises(OrderExecutionError) as exc_info:
            broker.cancel_order("test-order-123")

        assert "Delete timed out" in str(exc_info.value)


def test_alpaca_get_portfolio_history_filters_zero_padding():
    """get_portfolio_history() strips zero-equity days from account history."""
    broker = AlpacaBrokerAdapter(api_key="LIVE_KEY", api_secret="LIVE_SECRET")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "timestamp": [1600000000, 1600086400, 1600172800, 1600259200],
        "equity": [0.0, 0.0, 100000.0, 101500.0],
        "profit_loss": [0.0, 0.0, 0.0, 1500.0],
        "profit_loss_pct": [0.0, 0.0, 0.0, 0.015],
    }

    with patch("requests.get", return_value=mock_resp):
        df = broker.get_portfolio_history(period="13W")
        assert df is not None
        assert len(df) == 2
        assert (df["equity"] > 0).all()
        assert df["equity"].iloc[0] == 100000.0
        assert df["equity"].iloc[1] == 101500.0


def test_alpaca_get_portfolio_history_mock_returns_none():
    """Mock/unauthenticated broker returns None rather than throwing an unhandled exception."""
    broker = AlpacaBrokerAdapter(api_key="mock", api_secret="mock")
    assert broker.get_portfolio_history(period="all") is None

