import pytest
from trading_system.app.broker.groww import GrowwBrokerAdapter

def test_groww_broker_mock_initialization():
    adapter = GrowwBrokerAdapter(
        api_key="placeholder_groww_key",
        api_secret="placeholder_groww_secret",
        totp_secret="placeholder_totp",
        initial_capital=1000000.0
    )
    assert adapter.is_mock is True
    assert adapter.currency == "INR"
    assert adapter.currency_symbol == "₹"
    
    details = adapter.get_account_details()
    assert details["currency"] == "INR"
    assert details["currency_symbol"] == "₹"
    assert details["equity"] >= 1000000.0
    assert details["cash"] > 0

def test_groww_broker_positions_and_pnl():
    adapter = GrowwBrokerAdapter(initial_capital=1000000.0)
    positions = adapter.get_positions()
    assert isinstance(positions, dict)
    assert "RELIANCE.NS" in positions
    assert positions["RELIANCE.NS"] == 50

    detailed = adapter.get_positions_detailed()
    assert len(detailed) >= 5
    rel = next(p for p in detailed if p["symbol"] == "RELIANCE.NS")
    assert rel["qty"] == 50
    assert rel["market_value"] > 0
    assert "unrealized_pl" in rel
    assert "unrealized_plpc" in rel

def test_groww_broker_enforces_integer_shares():
    adapter = GrowwBrokerAdapter(initial_capital=1000000.0)
    
    # Fractional quantities should be floored to integer
    res = adapter.place_order(symbol="TCS.NS", qty=5.8, side="BUY")
    assert res["success"] is True
    assert res["order"]["qty"] == 5

    # Orders resulting in < 1 share should be rejected
    tiny_res = adapter.place_order(symbol="TCS.NS", notional=100.0, side="BUY") # ₹100 cannot buy 1 share of TCS (~₹3800)
    assert tiny_res["success"] is False
    assert "whole share" in tiny_res["error"] or "Calculated quantity is < 1" in tiny_res["error"]

def test_groww_broker_gtt_stop_loss():
    adapter = GrowwBrokerAdapter(initial_capital=1000000.0)
    res = adapter.place_gtt_stop_loss(symbol="INFY.NS", qty=70, trigger_price=1750.0)
    assert res["success"] is True
    assert res["order"]["type"] == "GTT_STOP"
    assert res["order"]["stop_price"] == 1750.0

    open_orders = adapter.get_open_orders()
    gtt_orders = [o for o in open_orders if o.get("type") == "GTT_STOP"]
    assert len(gtt_orders) >= 3

def test_groww_broker_order_lifecycle():
    adapter = GrowwBrokerAdapter(initial_capital=1000000.0)
    res = adapter.place_order(symbol="SBIN.NS", qty=100, side="BUY")
    assert res["success"] is True
    order_id = res["order"]["id"]

    status = adapter.get_order_status(order_id)
    assert status == "FILLED"

    cancel_res = adapter.cancel_order(order_id)
    assert cancel_res["success"] is True
    assert adapter.get_order_status(order_id) == "CANCELED"

def test_groww_broker_replace_order():
    adapter = GrowwBrokerAdapter(initial_capital=1000000.0)
    # Target existing mock order GRW-ORD-1001 (LIMIT BUY RELIANCE.NS)
    res = adapter.replace_order("GRW-ORD-1001", new_qty=40, new_limit_price=2850.0)
    assert res["success"] is True
    assert res["order"]["qty"] == 40
    assert res["order"]["limit_price"] == 2850.0
    assert res["order"]["status"] in ("ACTIVE_GTT", "REPLACED", "OPEN")

    # Non-existent order replace test
    bad_res = adapter.replace_order("NON-EXISTENT-ID", new_qty=10)
    assert bad_res["success"] is False
    assert "not found" in bad_res["error"].lower()

def test_groww_broker_portfolio_history():
    adapter = GrowwBrokerAdapter(initial_capital=1000000.0)
    hist = adapter.get_portfolio_history()
    assert hist is not None
    assert not hist.empty
    assert "timestamp" in hist.columns
    assert "equity" in hist.columns
    assert hist["equity"].iloc[-1] >= 900000.0
