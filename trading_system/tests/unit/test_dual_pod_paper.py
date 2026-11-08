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
from trading_system.scripts.run_dual_pod_paper import (
    PodPaperEngine,
    MultiAssetPodPaperEngine,
    POD_C_CORE_ALLOCATIONS,
    POD_C_ASSET_SPECS
)


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


def test_pit_universe_loader_and_exclusion_liquidation(tmp_path, monkeypatch):
    """
    Verifies that Point-in-Time (PIT) constituent loading is active for both India and US,
    and that membership exclusions automatically trigger mandatory liquidation.
    """
    from trading_system.scripts.run_dual_pod_paper import get_active_pit_universe

    # 1. Loader test
    in_pit = get_active_pit_universe("INDIA")
    assert len(in_pit) >= 50
    assert any(".NS" in s for s in in_pit)

    us_pit = get_active_pit_universe("US")
    assert len(us_pit) >= 490

    # 2. Mandatory exclusion liquidation test
    state_file = str(tmp_path / "test_pit_state.json")
    trades_file = str(tmp_path / "test_pit_trades.csv")
    dummy_log = str(tmp_path / "dummy_log_pit.csv")
    monkeypatch.setattr("trading_system.scripts.run_dual_pod_paper.EQUITY_LOG_CSV", dummy_log)

    engine = PodPaperEngine(
        pod_name="INDIA",
        currency="INR",
        initial_capital=80000.0,
        state_file=state_file,
        trades_file=trades_file
    )
    # Artificially insert a delisted / removed constituent
    engine.state["positions"]["EXCLUDED_CORP.NS"] = {
        "shares": 10.0,
        "entry_price": 100.0,
        "peak_price": 100.0
    }
    dates = pd.date_range("2024-01-01", periods=250, freq="B")
    bull_bench_df = pd.DataFrame({"close": np.linspace(15000, 25000, 250)}, index=dates)

    # Active PIT set that does NOT contain EXCLUDED_CORP.NS
    active_pit = {"RELIANCE.NS", "TCS.NS", "INFY.NS"}
    engine.scan_and_evaluate({}, bull_bench_df, active_pit_universe=active_pit)

    assert len(engine.state["pending_sells"]) == 1
    sell_order = engine.state["pending_sells"][0]
    assert sell_order["sym"] == "EXCLUDED_CORP.NS"
    assert "PIT_MEMBERSHIP_EXCLUSION_MANDATORY_LIQUIDATION" in sell_order["reason"]


def test_runner_refuses_silent_universe_fallback(monkeypatch):
    """
    Regression Test: Ensures that the runner strictly refuses to start and raises
    RuntimeError if the Point-in-Time constituent database is missing or empty.
    Silent fallback to static files is prohibited by fiduciary audit governance.
    """
    from trading_system.scripts.run_dual_pod_paper import get_active_pit_universe
    import pytest

    # Patch DATA_DIR to an empty non-existent directory to simulate missing PIT file
    monkeypatch.setattr("trading_system.scripts.run_dual_pod_paper.DATA_DIR", "/nonexistent_pit_dir")

    with pytest.raises(RuntimeError) as exc_info:
        get_active_pit_universe("INDIA")
    assert "PIT FATAL" in str(exc_info.value)
    assert "Silent fallback to static ticker files is strictly prohibited" in str(exc_info.value)

    with pytest.raises(RuntimeError) as exc_info:
        get_active_pit_universe("US")
    assert "PIT FATAL" in str(exc_info.value)
    assert "Silent fallback to static ticker files is strictly prohibited" in str(exc_info.value)


def test_runner_universe_matches_pit_backtest_database():
    """
    Ensures that the constituent database files referenced by the paper runner
    identically match the constituent databases used by the clean backtest engine.
    """
    from trading_system.scripts.run_dual_pod_paper import DATA_DIR
    from trading_system.scripts.backtest_nse50 import NIFTY_CHANGES_CSV, NIFTY_START_END_CSV

    runner_india_changes = os.path.join(DATA_DIR, "nifty50_historical_components_changes.csv")
    runner_india_se = os.path.join(DATA_DIR, "nifty50_ticker_start_end.csv")

    assert os.path.abspath(runner_india_changes) == os.path.abspath(NIFTY_CHANGES_CSV)
    assert os.path.abspath(runner_india_se) == os.path.abspath(NIFTY_START_END_CSV)
    assert os.path.exists(runner_india_changes)
    assert os.path.exists(runner_india_se)


def test_multi_asset_pod_c_lifecycle(tmp_path):
    """
    Verifies Pod C (Multi-Asset Trend) lifecycle:
      - Initial capital allocation (INR 80,000)
      - Next-Day Open fill execution with variable ETF slippage & charges
      - STT deduction on equity ETF (NIFTYBEES) and flat DP fee
      - Next-Day Open sell fill execution and cash replenishment
    """
    state_file = str(tmp_path / "test_pod_c_state.json")
    trades_file = str(tmp_path / "test_pod_c_trades.csv")

    engine = MultiAssetPodPaperEngine(
        pod_name="TEST_POD_C",
        currency="INR",
        initial_capital=80000.0,
        state_file=state_file,
        trades_file=trades_file
    )

    assert engine.state["cash"] == 80000.0
    assert len(engine.state["positions"]) == 0
    assert engine.state["initial_capital"] == 80000.0

    # 1. Queue Buy order for 40% NIFTYBEES (Rs 32,000)
    engine.state["pending_buys"].append({
        "sym": "NIFTYBEES.NS",
        "target_alloc": 32000.0,
        "score": 0.15,
        "reason": "TREND_BULL_ENTRY"
    })

    # Execute fill at open (Rs 300.0)
    engine.execute_open_fills({"NIFTYBEES.NS": 300.0})

    assert "NIFTYBEES.NS" in engine.state["positions"]
    pos = engine.state["positions"]["NIFTYBEES.NS"]
    assert pos["shares"] > 0
    # Price with stress slip (7.5 bps)
    assert pos["entry_price"] > 300.0
    assert engine.state["cash"] < 80000.0
    assert os.path.exists(trades_file)

    # 2. Queue Sell order (Trend break)
    engine.state["pending_sells"].append({
        "sym": "NIFTYBEES.NS",
        "reason": "TREND_DEFENSE_EXIT"
    })

    # Execute fill at open (Rs 310.0)
    engine.execute_open_fills({"NIFTYBEES.NS": 310.0})

    assert "NIFTYBEES.NS" not in engine.state["positions"]
    df_trades = pd.read_csv(trades_file)
    assert len(df_trades) == 2
    sell_row = df_trades[df_trades["action"] == "SELL"].iloc[0]
    # Sourced Dhan/CDSL DP fee
    assert sell_row["dp_fee"] == 14.75
    # Gross proceeds - friction added to cash
    assert engine.state["cash"] > 79000.0


def test_multi_asset_pod_c_trend_scan_and_defensive_cash(tmp_path, monkeypatch):
    """
    Verifies that Pod C:
      - Automatically qualifies assets in 200-SMA bull trend and queues 40%/30%/20% orders
      - Disqualifies assets below 200-SMA and preserves capital in Liquid Cash Yield
      - Daily interest yield is compounded into cash balance
    """
    state_file = str(tmp_path / "test_pod_c_scan_state.json")
    trades_file = str(tmp_path / "test_pod_c_scan_trades.csv")
    dummy_log = str(tmp_path / "dummy_equity_log_pod_c.csv")
    monkeypatch.setattr("trading_system.scripts.run_dual_pod_paper.EQUITY_LOG_CSV", dummy_log)

    engine = MultiAssetPodPaperEngine(
        pod_name="TEST_POD_C",
        currency="INR",
        initial_capital=80000.0,
        state_file=state_file,
        trades_file=trades_file
    )

    dates = pd.date_range("2024-01-01", periods=250, freq="B")
    
    # 1. NIFTYBEES.NS in bull trend (Price > 200-SMA, 6M Mom > 0)
    nifty_prices = np.linspace(250.0, 310.0, 250)
    # 2. MON100.NS in bull trend
    mon_prices = np.linspace(140.0, 190.0, 250)
    # 3. GOLDBEES.NS in bear downtrend (Price < 200-SMA)
    gold_prices = np.linspace(75.0, 55.0, 250)

    universe_data = {
        "NIFTYBEES.NS": pd.DataFrame({"close": nifty_prices}, index=dates),
        "MON100.NS": pd.DataFrame({"close": mon_prices}, index=dates),
        "GOLDBEES.NS": pd.DataFrame({"close": gold_prices}, index=dates)
    }

    engine.scan_and_evaluate(universe_data)

    # NIFTYBEES (40%) and MON100 (30%) qualified; GOLDBEES (20%) disqualified (kept in cash)
    assert len(engine.state["pending_buys"]) == 2
    buy_syms = {b["sym"] for b in engine.state["pending_buys"]}
    assert "NIFTYBEES.NS" in buy_syms
    assert "MON100.NS" in buy_syms
    assert "GOLDBEES.NS" not in buy_syms

    # Verify interest earned on idle cash
    assert engine.state["total_interest_earned"] > 0.0
    assert engine.state["trend_status"]["GOLDBEES.NS"]["regime"] == "DEFENSIVE_CASH"
    assert engine.state["trend_status"]["NIFTYBEES.NS"]["regime"] == "BULL_TREND"


def test_multi_asset_pod_c_defensive_exit_on_trend_break(tmp_path, monkeypatch):
    """
    Verifies that when an active holding breaks below its 200-SMA or exhibits negative momentum,
    Pod C immediately triggers a TREND_DEFENSE_EXIT order for Next-Day Open liquidation.
    """
    state_file = str(tmp_path / "test_pod_c_exit_state.json")
    trades_file = str(tmp_path / "test_pod_c_exit_trades.csv")
    dummy_log = str(tmp_path / "dummy_equity_log_pod_c_exit.csv")
    monkeypatch.setattr("trading_system.scripts.run_dual_pod_paper.EQUITY_LOG_CSV", dummy_log)

    engine = MultiAssetPodPaperEngine(
        pod_name="TEST_POD_C",
        currency="INR",
        initial_capital=80000.0,
        state_file=state_file,
        trades_file=trades_file
    )

    # Insert active holding in MON100
    engine.state["positions"]["MON100.NS"] = {
        "shares": 100.0,
        "entry_price": 180.0,
        "entry_date": "2024-01-01",
        "peak_price": 185.0
    }
    engine.state["cash"] = 56000.0

    # Provide market data showing sharp drop below 200-SMA
    dates = pd.date_range("2024-01-01", periods=250, freq="B")
    broken_prices = np.linspace(200.0, 140.0, 250)
    universe_data = {
        "MON100.NS": pd.DataFrame({"close": broken_prices}, index=dates)
    }

    engine.scan_and_evaluate(universe_data)

    # Must queue SELL for Next-Day Open
    assert len(engine.state["pending_sells"]) == 1
    sell_order = engine.state["pending_sells"][0]
    assert sell_order["sym"] == "MON100.NS"
    assert "TREND_DEFENSE_EXIT" in sell_order["reason"]

    # Execute fill at open (Rs 139.0)
    engine.execute_open_fills({"MON100.NS": 139.0})
    assert "MON100.NS" not in engine.state["positions"]
    # Proceeds restored to cash
    assert engine.state["cash"] > 56000.0 + 13000.0
