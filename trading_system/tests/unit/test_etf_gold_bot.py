"""
Unit Tests for Specialist Bot 1: ETF and Gold Bot (Gate B Paper Incubation)
"""

import os
import json
import pytest
import pandas as pd
from trading_system.app.bots.etf_gold_bot import (
    ETFGoldsStrategy,
    ETFGoldsPaperRunner,
    DEFAULT_CAPITAL,
    DEFAULT_UNIVERSE
)
from trading_system.app.common.interfaces import StrategyInterface


def test_etf_strategy_interface_compliance():
    strategy = ETFGoldsStrategy()
    assert isinstance(strategy, StrategyInterface)
    
    weights = strategy.evaluate_allocations(pd.Timestamp.now(), {}, {})
    assert len(weights) == 4
    assert sum(weights.values()) == pytest.approx(1.0)
    for sym in DEFAULT_UNIVERSE:
        assert sym in weights
        assert weights[sym] == 0.25

    status = strategy.get_risk_status()
    assert "regime" in status
    assert "weights" in status


def test_etf_runner_fail_closed(tmp_path):
    state_file = str(tmp_path / "test_state.json")
    trades_file = str(tmp_path / "test_trades.csv")
    equity_file = str(tmp_path / "test_equity.csv")

    runner = ETFGoldsPaperRunner(
        initial_capital=DEFAULT_CAPITAL,
        state_file=state_file,
        trades_file=trades_file,
        equity_log_file=equity_file
    )

    # Incomplete quotes (missing MID150BEES.NS)
    incomplete_quotes = {
        "GOLDBEES.NS": 112.50,
        "MON100.NS": 305.00,
        "NIFTYBEES.NS": 288.00
    }

    result = runner.run_daily_cycle(quotes=incomplete_quotes)
    assert result["status"] == "FAIL_CLOSED"
    assert "MID150BEES.NS" in result["missing_quotes"]
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
        "MID150BEES.NS": 250.00
    }

    # First cycle: executes opening portfolio allocation
    res1 = runner.run_daily_cycle(quotes=valid_quotes)
    assert res1["status"] == "SUCCESS"
    assert os.path.exists(state_file)
    assert os.path.exists(trades_file)
    assert os.path.exists(equity_file)

    # Verify positions created
    positions = runner.state["positions"]
    assert len(positions) == 4
    for sym in DEFAULT_UNIVERSE:
        assert sym in positions
        assert positions[sym]["shares"] > 0
        assert positions[sym]["entry_price"] == valid_quotes[sym]

    # Verify trades logged
    tdf = pd.read_csv(trades_file)
    assert len(tdf) == 4
    assert set(tdf["symbol"]) == set(DEFAULT_UNIVERSE)

    # Second cycle: price appreciation
    higher_quotes = {
        "GOLDBEES.NS": 110.00,    # +10%
        "MON100.NS": 220.00,      # +10%
        "NIFTYBEES.NS": 275.00,   # +10%
        "MID150BEES.NS": 275.00   # +10%
    }
    res2 = runner.run_daily_cycle(quotes=higher_quotes)
    assert res2["status"] == "SUCCESS"
    assert res2["nav"] > res1["nav"]
    assert res2["current_drawdown_pct"] == 0.0

    # Third cycle: price decline (drawdown test)
    lower_quotes = {
        "GOLDBEES.NS": 90.00,
        "MON100.NS": 180.00,
        "NIFTYBEES.NS": 225.00,
        "MID150BEES.NS": 225.00
    }
    res3 = runner.run_daily_cycle(quotes=lower_quotes)
    assert res3["status"] == "SUCCESS"
    assert res3["nav"] < res2["nav"]
    assert res3["current_drawdown_pct"] < 0.0
    assert runner.state["max_drawdown_pct"] < 0.0
