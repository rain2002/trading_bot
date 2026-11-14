"""
Unit Tests for Specialist Bot 1: ETF and Gold Bot (Gate B Paper Incubation)
"""

import os
import json
import pytest
import pandas as pd
from datetime import datetime, timezone, timedelta
from trading_system.app.bots.etf_gold_bot import (
    ETFGoldsStrategy,
    ETFGoldsPaperRunner,
    DEFAULT_CAPITAL,
    DEFAULT_UNIVERSE,
    DEFAULT_TARGET_WEIGHTS,
    DRIFT_BAND_THRESHOLD
)
from trading_system.app.common.interfaces import StrategyInterface


def test_etf_strategy_interface_compliance():
    strategy = ETFGoldsStrategy()
    assert isinstance(strategy, StrategyInterface)
    
    weights = strategy.evaluate_allocations(pd.Timestamp.now(), {}, {})
    assert len(weights) == 5
    assert sum(weights.values()) == pytest.approx(1.0)
    assert weights["GOLDBEES.NS"] == 0.25
    assert weights["MON100.NS"] == 0.25
    assert weights["NIFTYBEES.NS"] == 0.15
    assert weights["MID150BEES.NS"] == 0.15
    assert weights["LTGILTBEES.NS"] == 0.20

    status = strategy.get_risk_status()
    assert "regime" in status
    assert "weights" in status
    assert status["drift_band_threshold"] == DRIFT_BAND_THRESHOLD


def test_etf_runner_fail_closed_on_missing_quote(tmp_path):
    state_file = str(tmp_path / "test_state.json")
    trades_file = str(tmp_path / "test_trades.csv")
    equity_file = str(tmp_path / "test_equity.csv")

    runner = ETFGoldsPaperRunner(
        initial_capital=DEFAULT_CAPITAL,
        state_file=state_file,
        trades_file=trades_file,
        equity_log_file=equity_file
    )

    # Incomplete quotes (missing LTGILTBEES.NS)
    incomplete_quotes = {
        "GOLDBEES.NS": 112.50,
        "MON100.NS": 305.00,
        "NIFTYBEES.NS": 288.00,
        "MID150BEES.NS": 235.00
    }

    result = runner.run_daily_cycle(quotes=incomplete_quotes)
    assert result["status"] == "FAIL_CLOSED"
    assert "LTGILTBEES.NS" in result["missing_quotes"]
    assert runner.state["cash"] == DEFAULT_CAPITAL
    assert len(runner.state["positions"]) == 0


def test_etf_runner_opening_allocation_and_tracking(tmp_path):
    state_file = str(tmp_path / "test_state.json")
    trades_file = str(tmp_path / "test_trades.csv")
    equity_file = str(tmp_path / "test_equity.csv")

    runner = ETFGoldsPaperRunner(
        initial_capital=DEFAULT_CAPITAL,
        state_file=state_file,
        trades_file=trades_file,
        equity_log_file=equity_file
    )

    valid_quotes = {
        "GOLDBEES.NS": 100.00,
        "MON100.NS": 200.00,
        "NIFTYBEES.NS": 250.00,
        "MID150BEES.NS": 250.00,
        "LTGILTBEES.NS": 30.00
    }

    # First cycle: executes opening portfolio allocation across 5 assets
    res1 = runner.run_daily_cycle(quotes=valid_quotes)
    assert res1["status"] == "SUCCESS"
    assert res1["rebalance_executed"] is True
    assert os.path.exists(state_file)
    assert os.path.exists(trades_file)
    assert os.path.exists(equity_file)

    # Verify positions created for all 5 assets
    positions = runner.state["positions"]
    assert len(positions) == 5
    for sym in DEFAULT_UNIVERSE:
        assert sym in positions
        assert positions[sym]["shares"] > 0
        assert positions[sym]["entry_price"] == valid_quotes[sym]

    # Verify trades logged
    tdf = pd.read_csv(trades_file)
    assert len(tdf) == 5
    assert set(tdf["symbol"]) == set(DEFAULT_UNIVERSE)

    # Second cycle: prices within drift band -> no rebalance
    res2 = runner.run_daily_cycle(quotes=valid_quotes)
    assert res2["status"] == "SUCCESS"
    assert res2["rebalance_executed"] is False


def test_etf_runner_drift_band_rebalance(tmp_path):
    state_file = str(tmp_path / "test_state.json")
    trades_file = str(tmp_path / "test_trades.csv")
    equity_file = str(tmp_path / "test_equity.csv")

    runner = ETFGoldsPaperRunner(
        initial_capital=DEFAULT_CAPITAL,
        state_file=state_file,
        trades_file=trades_file,
        equity_log_file=equity_file
    )

    base_quotes = {
        "GOLDBEES.NS": 100.00,
        "MON100.NS": 200.00,
        "NIFTYBEES.NS": 250.00,
        "MID150BEES.NS": 250.00,
        "LTGILTBEES.NS": 30.00
    }
    runner.run_daily_cycle(quotes=base_quotes)

    # Gold surges +60%, drifting well past 5% band (25% target -> ~35% actual)
    surge_quotes = {
        "GOLDBEES.NS": 160.00,
        "MON100.NS": 200.00,
        "NIFTYBEES.NS": 250.00,
        "MID150BEES.NS": 250.00,
        "LTGILTBEES.NS": 30.00
    }
    res = runner.run_daily_cycle(quotes=surge_quotes)
    assert res["status"] == "SUCCESS"
    assert res["rebalance_executed"] is True
    assert "DRIFT_BAND_TRIGGER" in res["rebalance_reason"]

    # Verify sell trade logged for Gold
    tdf = pd.read_csv(trades_file)
    sells = tdf[tdf["side"] == "SELL"]
    assert len(sells) > 0
    assert "GOLDBEES.NS" in sells["symbol"].values
