import os
import pytest
from trading_system.app.broker.multi_bot_adapter import MultiBotBrokerAdapter


def test_multi_bot_adapter_initialization():
    adapter = MultiBotBrokerAdapter()
    assert adapter.initial_capital == 100000.0
    assert adapter.is_connected() is True
    assert adapter.is_mock is True


def test_multi_bot_adapter_account_details():
    adapter = MultiBotBrokerAdapter()
    details = adapter.get_account_details()

    assert details["currency"] == "INR"
    assert details["currency_symbol"] == "₹"
    assert details["equity"] > 0
    assert "cash" in details
    assert "unitized_nav" in details
    assert details["unitized_nav"] > 0
    assert details["throttle_level"] == 0
    assert details["reconciliation_gap_pct"] == 0.0


def test_multi_bot_adapter_positions_detailed():
    adapter = MultiBotBrokerAdapter()
    positions = adapter.get_positions_detailed()

    assert len(positions) >= 5
    symbols = [p["symbol"] for p in positions]
    assert "GOLDBEES.NS" in symbols
    assert "LIQUIDBEES.NS" in symbols
    for p in positions:
        assert p["qty"] > 0
        assert p["market_value"] > 0
        assert "sleeve" in p


def test_multi_bot_adapter_portfolio_history():
    adapter = MultiBotBrokerAdapter()
    df_hist = adapter.get_portfolio_history()

    assert df_hist is not None
    assert len(df_hist) >= 4
    assert "timestamp" in df_hist.columns
    assert "equity" in df_hist.columns
    assert "profit_loss" in df_hist.columns


def test_multi_bot_adapter_recent_orders():
    adapter = MultiBotBrokerAdapter()
    orders = adapter.get_recent_orders(limit=20)

    assert len(orders) >= 5
    first = orders[0]
    assert "id" in first
    assert "symbol" in first
    assert "status" in first
    assert first["status"] == "FILLED"
