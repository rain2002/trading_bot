"""
Unit tests for Dual-Pod Forward Paper Trading Engine
====================================================
Tests state loading, order queueing, Next-Open fill execution,
DP fee deduction, and status tear sheet reporting.
"""

import os
import json
import pytest
import pandas as pd
from trading_system.scripts.run_dual_pod_paper import PodPaperEngine


def test_pod_paper_engine_lifecycle(tmp_path):
    state_file = str(tmp_path / "test_state.json")
    trades_file = str(tmp_path / "test_trades.csv")

    engine = PodPaperEngine(
        pod_name="TEST_INDIA",
        currency="INR",
        initial_capital=100000.0,
        state_file=state_file,
        trades_file=trades_file
    )

    assert engine.state["cash"] == 100000.0
    assert len(engine.state["positions"]) == 0

    # Queue buy order
    engine.state["pending_buys"].append({
        "sym": "TCS.NS",
        "target_alloc": 10000.0,
        "score": 0.45
    })

    # Execute fill at open (Rs 3500)
    engine.execute_open_fills({"TCS.NS": 3500.0})

    assert "TCS.NS" in engine.state["positions"]
    assert engine.state["positions"]["TCS.NS"]["shares"] > 0
    assert engine.state["cash"] < 100000.0
    assert os.path.exists(trades_file)

    # Queue sell order
    engine.state["pending_sells"].append({
        "sym": "TCS.NS",
        "reason": "TRAIL_STOP"
    })

    # Execute sell at open (Rs 3800)
    engine.execute_open_fills({"TCS.NS": 3800.0})
    assert "TCS.NS" not in engine.state["positions"]
    # Verify Dhan DP fee deduction
    df_trades = pd.read_csv(trades_file)
    assert len(df_trades) == 2
    sell_row = df_trades[df_trades["action"] == "SELL"].iloc[0]
    assert sell_row["dp_fee"] == 14.75


def test_us_pod_alpaca_sync_and_routing(tmp_path, monkeypatch):
    state_file = str(tmp_path / "test_us_state.json")
    trades_file = str(tmp_path / "test_us_trades.csv")

    class MockBroker:
        def __init__(self, *args, **kwargs):
            pass
        def is_connected(self):
            return True
        def get_account_details(self):
            return {"equity": 95000.0, "cash": 15000.0}
        def get_positions_detailed(self):
            return [{
                "symbol": "NVDA",
                "qty": 20.0,
                "avg_entry_price": 120.0,
                "current_price": 140.0
            }]

    submitted_orders = []
    class MockExecution:
        def __init__(self, *args, **kwargs):
            pass
        def submit_order(self, order):
            submitted_orders.append(order)
            return {"status": "SUBMITTED", "order_id": "mock-order-123"}

    monkeypatch.setattr("trading_system.app.broker.alpaca.AlpacaBrokerAdapter", MockBroker)
    monkeypatch.setattr("trading_system.app.execution.alpaca_live.AlpacaExecutionAdapter", MockExecution)

    # Set mock settings
    from trading_system.app.config.settings import settings
    monkeypatch.setattr(settings, "PAPER_API_KEY", "mock_key")
    monkeypatch.setattr(settings, "PAPER_API_SECRET", "mock_secret")

    engine = PodPaperEngine(
        pod_name="US",
        currency="USD",
        initial_capital=10000.0,
        state_file=state_file,
        trades_file=trades_file,
        live_broker=True
    )

    engine.sync_alpaca_live()

    assert engine.state["cash"] == 15000.0
    assert engine.state["initial_capital"] == 95000.0
    assert "NVDA" in engine.state["positions"]
    assert engine.state["positions"]["NVDA"]["shares"] == 20.0
    assert engine.state["positions"]["NVDA"]["entry_price"] == 120.0
    assert engine.state["positions"]["NVDA"]["peak_price"] == 140.0

    # Queue sell order and test live routing
    engine.state["pending_sells"].append({
        "sym": "NVDA",
        "reason": "TREND_SMA150_BREAK"
    })
    engine.execute_open_fills({"NVDA": 138.0})

    assert len(submitted_orders) == 1
    assert submitted_orders[0]["symbol"] == "NVDA"
    assert submitted_orders[0]["side"] == "sell"
    assert submitted_orders[0]["quantity"] == 20
    assert "NVDA" not in engine.state["positions"]
