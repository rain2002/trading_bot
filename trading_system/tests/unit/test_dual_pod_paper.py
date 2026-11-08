"""
Unit tests for Dual-Pod Forward Paper Trading Engine
====================================================
Tests state loading, order queueing, Next-Open fill execution,
DP fee deduction, and status tear sheet reporting.
"""

import os
import json
import pytest
import math
import numpy as np
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


def test_volatility_targeting_and_regional_invariants(tmp_path, monkeypatch):
    state_file = str(tmp_path / "test_vol_state.json")
    trades_file = str(tmp_path / "test_vol_trades.csv")
    dummy_log = str(tmp_path / "dummy_equity_log.csv")
    monkeypatch.setattr("trading_system.scripts.run_dual_pod_paper.EQUITY_LOG_CSV", dummy_log)

    engine = PodPaperEngine(
        pod_name="INDIA",
        currency="INR",
        initial_capital=80000.0,
        state_file=state_file,
        trades_file=trades_file
    )

    # 1. Bear defense test: benchmark below 200 SMA
    dates = pd.date_range("2024-01-01", periods=250, freq="B")
    # Declining prices so current close < 200 SMA
    prices = [25000.0 - i * 20.0 for i in range(250)]
    bench_df = pd.DataFrame({"close": prices}, index=dates)

    sym_data = {
        "RELIANCE.NS": pd.DataFrame({
            "close": [2800.0] * 250,
            "open": [2800.0] * 250,
            "volume": [1000000] * 250
        }, index=dates)
    }

    engine.scan_and_evaluate(sym_data, bench_df)
    # Under bear defense, no buy orders must be queued, cash is 100% preserved
    assert len(engine.state["pending_buys"]) == 0
    assert engine.state["cash"] == 80000.0

    # 2. Bull trending test with low volatility
    bull_prices = [15000.0 + i * 50.0 for i in range(250)]
    bull_bench_df = pd.DataFrame({"close": bull_prices}, index=dates)

    # Momentum candidate above 50, 150, 200 SMA
    cand_prices = [100.0 + i * 2.0 for i in range(250)]
    cand_df = pd.DataFrame({
        "close": cand_prices,
        "open": cand_prices,
        "volume": [2000000] * 250
    }, index=dates)

    engine.scan_and_evaluate({"TITAN.NS": cand_df}, bull_bench_df)
    assert len(engine.state["pending_buys"]) == 1
    assert engine.state["pending_buys"][0]["sym"] == "TITAN.NS"
    # Target allocation in calm bull is 10% of equity (8,000 INR)
    assert engine.state["pending_buys"][0]["target_alloc"] == 8000.0

    # 3. Target Exposure Math Check (10 slots x (10% x max_exposure) == total_equity * max_exposure)
    # Simulate elevated volatility with Scale = 0.60
    # Create 10 valid candidates
    ten_cands = {}
    for k in range(10):
        sym_name = f"STOCK_{k}.NS"
        ten_cands[sym_name] = pd.DataFrame({
            "close": cand_prices,
            "open": cand_prices,
            "volume": [2000000] * 250
        }, index=dates)

    # Bull bench with elevated vol (~25% vol -> scale = 0.15 / 0.25 = 0.60)
    swing_bench_prices = np.linspace(15000, 22000, 250)
    for idx_i in range(225, 250):
        swing_bench_prices[idx_i] += 400.0 if idx_i % 2 == 0 else -400.0
    mod_bench_df = pd.DataFrame({"close": swing_bench_prices}, index=dates)

    engine_mod = PodPaperEngine(
        pod_name="INDIA",
        currency="INR",
        initial_capital=80000.0,
        state_file=str(tmp_path / "test_scale_state.json"),
        trades_file=str(tmp_path / "test_scale_trades.csv")
    )
    engine_mod.scan_and_evaluate(ten_cands, mod_bench_df)
    queued_buys = engine_mod.state["pending_buys"]
    assert len(queued_buys) == 10  # Must keep all 10 slots (no double-scaling)
    total_queued_target = sum(b["target_alloc"] for b in queued_buys)
    # Per-candidate alloc must be (total_equity / 10) * max_exposure
    sample_alloc = queued_buys[0]["target_alloc"]
    expected_scale = sample_alloc / (80000.0 * 0.10)
    # Total target allocation must equal 80,000 * expected_scale
    assert math.isclose(total_queued_target, 80000.0 * expected_scale, rel_tol=1e-3)
    assert expected_scale < 0.75  # Verified in caution scaling

    # 4. Dynamic Trimming Test on Existing Positions
    # If a holding has grown to exceed target_pos_val * 1.15, scan_and_evaluate must queue VOL_TARGET_TRIM
    trim_state_file = str(tmp_path / "test_trim_state.json")
    engine_trim = PodPaperEngine(
        pod_name="INDIA",
        currency="INR",
        initial_capital=80000.0,
        state_file=trim_state_file,
        trades_file=str(tmp_path / "test_trim_trades.csv")
    )
    # Artificially insert a position with 100 shares @ Rs 1000 = Rs 100,000 value (way above target)
    engine_trim.state["cash"] = 20000.0
    engine_trim.state["positions"]["BIG_WINNER.NS"] = {
        "shares": 100.0,
        "entry_price": 500.0,
        "peak_price": 1000.0
    }
    # Latest price is 1000
    big_cand = pd.DataFrame({
        "close": [1000.0] * 250,
        "open": [1000.0] * 250,
        "volume": [1000000] * 250
    }, index=dates)
    engine_trim.scan_and_evaluate({"BIG_WINNER.NS": big_cand}, mod_bench_df)

    # Must queue a partial TRIM sell
    assert len(engine_trim.state["pending_sells"]) == 1
    trim_order = engine_trim.state["pending_sells"][0]
    assert trim_order["sym"] == "BIG_WINNER.NS"
    assert "VOL_TARGET_TRIM" in trim_order["reason"]
    assert trim_order.get("trim_shares") is not None
    assert 0 < trim_order["trim_shares"] < 100.0

    # Execute fill on the trim order and confirm position remains open with reduced shares
    engine_trim.execute_open_fills({"BIG_WINNER.NS": 1000.0})
    assert "BIG_WINNER.NS" in engine_trim.state["positions"]
    assert engine_trim.state["positions"]["BIG_WINNER.NS"]["shares"] == 100.0 - trim_order["trim_shares"]
    assert engine_trim.state["cash"] > 20000.0


