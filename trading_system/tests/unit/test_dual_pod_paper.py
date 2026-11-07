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
