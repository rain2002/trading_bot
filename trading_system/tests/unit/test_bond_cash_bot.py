"""
Unit Tests for Specialist Bot 2: Bond and Cash Bot (Gate B Paper Incubation)
=============================================================================
Governed strictly by: PROTOCOL-BOND-AND-CASH-BOT-V1-20261114
Tests cover:
  1. StrategyInterface compliance across B0, B1, and B2.
  2. B0 100% overnight cash invariants.
  3. B1 70/30 static split and manager max_duration_scale scaling.
  4. B2 200-day SMA trend gating and manager duration scale override.
  5. Dedicated INR 20,000 initial capital partition and GATE_B_PAPER status.
  6. Fail-closed safety on missing, invalid, or stale quotes.
  7. Opening allocation and trade logging.
  8. Drift band rebalancing (5 percentage points threshold).
  9. Manager duration retreat drill (max_duration_scale 1.0 -> 0.0).
"""

import os
import json
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

from trading_system.app.bots.bond_cash_bot import (
    BondCashB0Strategy,
    BondCashB1Strategy,
    BondCashB2Strategy,
    BondCashPaperRunner,
    DEFAULT_CAPITAL,
    DEFAULT_UNIVERSE,
    DRIFT_BAND_THRESHOLD
)
from trading_system.app.common.interfaces import StrategyInterface


def test_b0_strategy_interface_and_allocation():
    strategy = BondCashB0Strategy()
    assert isinstance(strategy, StrategyInterface)
    
    weights = strategy.evaluate_allocations(pd.Timestamp.now(), {}, {})
    assert weights["LIQUIDBEES.NS"] == 1.0
    assert weights["LTGILTBEES.NS"] == 0.0
    assert sum(weights.values()) == pytest.approx(1.0)

    # Even with duration scale forced, B0 stays 100% cash
    weights_scaled = strategy.evaluate_allocations(pd.Timestamp.now(), {}, {"max_duration_scale": 1.0})
    assert weights_scaled["LIQUIDBEES.NS"] == 1.0
    assert weights_scaled["LTGILTBEES.NS"] == 0.0


def test_b1_strategy_scaling():
    strategy = BondCashB1Strategy()
    assert isinstance(strategy, StrategyInterface)

    # Normal conditions: 70/30 split
    weights_normal = strategy.evaluate_allocations(pd.Timestamp.now(), {}, {"max_duration_scale": 1.0})
    assert weights_normal["LIQUIDBEES.NS"] == pytest.approx(0.70)
    assert weights_normal["LTGILTBEES.NS"] == pytest.approx(0.30)

    # Manager retreat override: max_duration_scale = 0.0 -> 100% cash
    weights_retreat = strategy.evaluate_allocations(pd.Timestamp.now(), {}, {"max_duration_scale": 0.0})
    assert weights_retreat["LIQUIDBEES.NS"] == pytest.approx(1.0)
    assert weights_retreat["LTGILTBEES.NS"] == pytest.approx(0.0)

    # Partial throttling: max_duration_scale = 0.50 -> 85% cash, 15% gilt
    weights_half = strategy.evaluate_allocations(pd.Timestamp.now(), {}, {"max_duration_scale": 0.50})
    assert weights_half["LIQUIDBEES.NS"] == pytest.approx(0.85)
    assert weights_half["LTGILTBEES.NS"] == pytest.approx(0.15)


def test_b2_strategy_trend_gating():
    strategy = BondCashB2Strategy(sma_lookback=5)

    # Construct synthetic data: Bullish trend (price above SMA)
    dates = pd.date_range("2026-01-01", periods=10, freq="D")
    bullish_df = pd.DataFrame({"Close": [10, 11, 12, 13, 14, 15, 16, 17, 18, 19]}, index=dates)
    market_data_bullish = {"LTGILTBEES.NS": bullish_df}

    weights_bull = strategy.evaluate_allocations(pd.Timestamp.now(), market_data_bullish, {"max_duration_scale": 1.0})
    assert weights_bull["LIQUIDBEES.NS"] == pytest.approx(0.70)
    assert weights_bull["LTGILTBEES.NS"] == pytest.approx(0.30)
    assert strategy.get_risk_status()["gilt_trend_bullish"] is True

    # Construct synthetic data: Bearish trend (price below SMA)
    bearish_df = pd.DataFrame({"Close": [20, 20, 20, 20, 20, 15, 14, 13, 12, 10]}, index=dates)
    market_data_bearish = {"LTGILTBEES.NS": bearish_df}

    weights_bear = strategy.evaluate_allocations(pd.Timestamp.now(), market_data_bearish, {"max_duration_scale": 1.0})
    assert weights_bear["LIQUIDBEES.NS"] == pytest.approx(1.0)
    assert weights_bear["LTGILTBEES.NS"] == pytest.approx(0.0)
    assert strategy.get_risk_status()["gilt_trend_bullish"] is False

    # When bullish but manager sets max_duration_scale = 0.0 -> forced 100% cash
    weights_override = strategy.evaluate_allocations(pd.Timestamp.now(), market_data_bullish, {"max_duration_scale": 0.0})
    assert weights_override["LIQUIDBEES.NS"] == pytest.approx(1.0)
    assert weights_override["LTGILTBEES.NS"] == pytest.approx(0.0)


def test_bond_cash_runner_state_initialization(tmp_path):
    state_file = str(tmp_path / "test_state.json")
    trades_file = str(tmp_path / "test_trades.csv")
    equity_file = str(tmp_path / "test_equity.csv")

    runner = BondCashPaperRunner(
        initial_capital=DEFAULT_CAPITAL,
        state_file=state_file,
        trades_file=trades_file,
        equity_log_file=equity_file
    )

    state = runner.state
    assert state["bot_name"] == "BOND_AND_CASH_BOT"
    assert state["phase"] == "PHASE_3"
    assert state["gate"] == "GATE_B_PAPER"
    assert state["initial_capital"] == 20000.0
    assert state["cash"] == 20000.0
    assert state["nav"] == 20000.0
    assert state["strategy_id"] == "B0"
    assert state["max_duration_scale"] == 1.0


def test_bond_cash_runner_fail_closed_on_missing_quote(tmp_path):
    state_file = str(tmp_path / "test_state.json")
    trades_file = str(tmp_path / "test_trades.csv")
    equity_file = str(tmp_path / "test_equity.csv")

    runner = BondCashPaperRunner(
        initial_capital=DEFAULT_CAPITAL,
        state_file=state_file,
        trades_file=trades_file,
        equity_log_file=equity_file
    )

    # Incomplete quotes (missing LTGILTBEES.NS)
    incomplete_quotes = {"LIQUIDBEES.NS": 1000.00}
    dates = pd.date_range("2026-01-01", periods=250, freq="D")
    market_data = {
        "LIQUIDBEES.NS": pd.DataFrame({"Close": [1000.0] * 250}, index=dates),
        "LTGILTBEES.NS": pd.DataFrame({"Close": [30.0] * 250}, index=dates)
    }

    result = runner.run_daily_cycle(quotes=incomplete_quotes, market_data=market_data)
    assert result["status"] == "FAIL_CLOSED"
    assert "LTGILTBEES.NS" in result["missing_quotes"]
    assert runner.state["cash"] == 20000.0
    assert len(runner.state["positions"]) == 0


def test_bond_cash_runner_opening_allocation_and_tracking(tmp_path):
    state_file = str(tmp_path / "test_state.json")
    trades_file = str(tmp_path / "test_trades.csv")
    equity_file = str(tmp_path / "test_equity.csv")

    runner = BondCashPaperRunner(
        strategy=BondCashB2Strategy(sma_lookback=200),
        initial_capital=DEFAULT_CAPITAL,
        state_file=state_file,
        trades_file=trades_file,
        equity_log_file=equity_file
    )

    quotes = {"LIQUIDBEES.NS": 1000.00, "LTGILTBEES.NS": 30.00}
    dates = pd.date_range("2026-01-01", periods=250, freq="D")
    # Upward trend above 200-SMA
    market_data = {
        "LIQUIDBEES.NS": pd.DataFrame({"Close": [1000.0] * 250}, index=dates),
        "LTGILTBEES.NS": pd.DataFrame({"Close": np.linspace(25.0, 32.0, 250)}, index=dates)
    }

    # First cycle: opening allocation (70% cash / 30% gilt)
    res1 = runner.run_daily_cycle(quotes=quotes, market_data=market_data)
    assert res1["status"] == "SUCCESS"
    assert res1["rebalance_executed"] is True
    assert os.path.exists(state_file)
    assert os.path.exists(trades_file)
    assert os.path.exists(equity_file)

    # Check holdings: 30% of 20,000 = ~6,000 in LTGILTBEES.NS (~200 shares @ 30)
    positions = runner.state["positions"]
    assert "LTGILTBEES.NS" in positions
    assert positions["LTGILTBEES.NS"]["shares"] > 180
    assert "LIQUIDBEES.NS" in positions
    assert positions["LIQUIDBEES.NS"]["shares"] >= 13

    # Check trade log
    tdf = pd.read_csv(trades_file)
    assert len(tdf) >= 2
    assert set(tdf["symbol"]) == {"LIQUIDBEES.NS", "LTGILTBEES.NS"}

    # Second cycle with same prices: no rebalance
    res2 = runner.run_daily_cycle(quotes=quotes, market_data=market_data)
    assert res2["status"] == "SUCCESS"
    assert res2["rebalance_executed"] is False


def test_bond_cash_runner_drift_band_rebalance(tmp_path):
    state_file = str(tmp_path / "test_state.json")
    trades_file = str(tmp_path / "test_trades.csv")
    equity_file = str(tmp_path / "test_equity.csv")

    runner = BondCashPaperRunner(
        strategy=BondCashB2Strategy(sma_lookback=200),
        initial_capital=DEFAULT_CAPITAL,
        state_file=state_file,
        trades_file=trades_file,
        equity_log_file=equity_file
    )

    base_quotes = {"LIQUIDBEES.NS": 1000.00, "LTGILTBEES.NS": 30.00}
    dates = pd.date_range("2026-01-01", periods=250, freq="D")
    market_data = {
        "LIQUIDBEES.NS": pd.DataFrame({"Close": [1000.0] * 250}, index=dates),
        "LTGILTBEES.NS": pd.DataFrame({"Close": np.linspace(25.0, 32.0, 250)}, index=dates)
    }

    runner.run_daily_cycle(quotes=base_quotes, market_data=market_data)

    # LTGILTBEES surges +35%, drifting > 5% points from 30% target
    surge_quotes = {"LIQUIDBEES.NS": 1000.00, "LTGILTBEES.NS": 40.50}
    res = runner.run_daily_cycle(quotes=surge_quotes, market_data=market_data)
    assert res["status"] == "SUCCESS"
    assert res["rebalance_executed"] is True
    assert "DRIFT_BAND_TRIGGER" in res["rebalance_reason"]

    # Verify sell trade logged for trimmed LTGILTBEES
    tdf = pd.read_csv(trades_file)
    sells = tdf[tdf["side"] == "SELL"]
    assert len(sells) > 0
    assert "LTGILTBEES.NS" in sells["symbol"].values


def test_bond_cash_runner_manager_retreat_override(tmp_path):
    state_file = str(tmp_path / "test_state.json")
    trades_file = str(tmp_path / "test_trades.csv")
    equity_file = str(tmp_path / "test_equity.csv")

    runner = BondCashPaperRunner(
        strategy=BondCashB2Strategy(sma_lookback=200),
        initial_capital=DEFAULT_CAPITAL,
        state_file=state_file,
        trades_file=trades_file,
        equity_log_file=equity_file
    )

    quotes = {"LIQUIDBEES.NS": 1000.00, "LTGILTBEES.NS": 30.00}
    dates = pd.date_range("2026-01-01", periods=250, freq="D")
    market_data = {
        "LIQUIDBEES.NS": pd.DataFrame({"Close": [1000.0] * 250}, index=dates),
        "LTGILTBEES.NS": pd.DataFrame({"Close": np.linspace(25.0, 32.0, 250)}, index=dates)
    }

    # Step 1: Normal cycle with max_duration_scale = 1.0 (holds gilt)
    runner.run_daily_cycle(quotes=quotes, market_data=market_data, max_duration_scale=1.0)
    assert "LTGILTBEES.NS" in runner.state["positions"]

    # Step 2: Manager triggers retreat (max_duration_scale = 0.0)
    res_retreat = runner.run_daily_cycle(quotes=quotes, market_data=market_data, max_duration_scale=0.0)
    assert res_retreat["status"] == "SUCCESS"
    assert res_retreat["rebalance_executed"] is True
    assert "MANAGER_DURATION_SCALE_CHANGED" in res_retreat["rebalance_reason"]
    
    # Verify LTGILTBEES completely liquidated (0 positions), 100% into cash/LIQUIDBEES
    assert "LTGILTBEES.NS" not in runner.state["positions"]
    assert runner.state["max_duration_scale"] == 0.0


def test_bond_cash_runner_default_b0_champion_flow(tmp_path):
    state_file = str(tmp_path / "test_state.json")
    trades_file = str(tmp_path / "test_trades.csv")
    equity_file = str(tmp_path / "test_equity.csv")

    runner = BondCashPaperRunner(
        initial_capital=DEFAULT_CAPITAL,
        state_file=state_file,
        trades_file=trades_file,
        equity_log_file=equity_file
    )
    assert runner.state["strategy_id"] == "B0"

    quotes = {"LIQUIDBEES.NS": 1000.00, "LTGILTBEES.NS": 30.00}
    dates = pd.date_range("2026-01-01", periods=10, freq="D")
    market_data = {
        "LIQUIDBEES.NS": pd.DataFrame({"Close": [1000.0] * 10}, index=dates),
        "LTGILTBEES.NS": pd.DataFrame({"Close": [30.0] * 10}, index=dates)
    }

    res = runner.run_daily_cycle(quotes=quotes, market_data=market_data)
    assert res["status"] == "SUCCESS"
    assert res["rebalance_executed"] is True
    # B0 allocates 100% to LIQUIDBEES.NS
    assert "LIQUIDBEES.NS" in runner.state["positions"]
    assert "LTGILTBEES.NS" not in runner.state["positions"]
    assert runner.state["positions"]["LIQUIDBEES.NS"]["shares"] >= 19


def test_bond_cash_daily_carry_accrual(tmp_path):
    """
    Verifies daily cash carry accrual for LIQUIDBEES.NS at protocol repo rate.
    Pass conditions:
    1. Day 0 (initial allocation): seeds positions, zero carry credited.
    2. Same-day re-run: idempotent, zero duplicate carry credited.
    3. Next session (Day 1): accrues daily carry (~INR 4.50 on INR 20k), cash & NAV increase.
    4. Audit trail: DIVIDEND_CARRY transaction logged in trades CSV.
    """
    state_file = str(tmp_path / "test_state.json")
    trades_file = str(tmp_path / "test_trades.csv")
    equity_file = str(tmp_path / "test_equity.csv")

    runner = BondCashPaperRunner(
        initial_capital=DEFAULT_CAPITAL,
        state_file=state_file,
        trades_file=trades_file,
        equity_log_file=equity_file
    )

    quotes = {"LIQUIDBEES.NS": 1000.00, "LTGILTBEES.NS": 30.00}
    dates = pd.date_range("2026-01-01", periods=10, freq="D")
    market_data = {
        "LIQUIDBEES.NS": pd.DataFrame({"Close": [1000.0] * 10}, index=dates),
        "LTGILTBEES.NS": pd.DataFrame({"Close": [30.0] * 10}, index=dates)
    }

    # Session 1: 2026-11-15 (Sunday Initial Run)
    dt1 = datetime(2026, 11, 15, 10, 15, tzinfo=timezone.utc)
    res1 = runner.run_daily_cycle(quotes=quotes, market_data=market_data, as_of=dt1)
    assert res1["status"] == "SUCCESS"
    assert res1["daily_carry_credited"] == 0.0
    assert runner.state["total_carry_earned"] == 0.0
    initial_cash = runner.state["cash"]
    initial_nav = runner.state["nav"]

    # Re-run same day: Idempotent guard prevents duplicate accrual
    res1_repeat = runner.run_daily_cycle(quotes=quotes, market_data=market_data, as_of=dt1)
    assert res1_repeat["daily_carry_credited"] == 0.0
    assert runner.state["cash"] == initial_cash

    # Session 2: 2026-11-16 (Monday Scheduled Run)
    dt2 = datetime(2026, 11, 16, 10, 15, tzinfo=timezone.utc)
    res2 = runner.run_daily_cycle(quotes=quotes, market_data=market_data, as_of=dt2)
    assert res2["status"] == "SUCCESS"
    assert res2["daily_carry_credited"] > 4.0  # ~INR 4.50 on ~INR 20,000 capital
    assert runner.state["cash"] == pytest.approx(initial_cash + res2["daily_carry_credited"], 0.01)
    assert runner.state["nav"] == pytest.approx(initial_nav + res2["daily_carry_credited"], 0.01)
    assert runner.state["total_carry_earned"] == res2["daily_carry_credited"]

    # Verify DIVIDEND_CARRY in trades log
    tdf = pd.read_csv(trades_file)
    carry_rows = tdf[tdf["side"] == "DIVIDEND_CARRY"]
    assert len(carry_rows) == 1
    assert carry_rows.iloc[0]["symbol"] == "LIQUIDBEES.NS"
    assert carry_rows.iloc[0]["net_cash_impact"] == -round(res2["daily_carry_credited"], 2)


def test_bond_cash_equity_log_migration(tmp_path):
    """
    Verifies that an older 11-column bond_cash_equity_log.csv (missing total_carry_earned)
    is transparently migrated to the canonical 12-column layout without column displacement.
    """
    state_file = str(tmp_path / "state.json")
    trades_file = str(tmp_path / "trades.csv")
    equity_file = str(tmp_path / "equity.csv")

    # Seed legacy 11-column file
    legacy_header = "timestamp,nav,cash,holdings_val,hwm,current_drawdown_pct,max_drawdown_pct,max_duration_scale,days_incubated,weeks_incubated,incubation_complete\n"
    legacy_row = "2026-11-15 01:44:14,19986.99,986.99,19000.0,20000.0,-0.07,-0.07,1.0,0,0.0,False\n"
    with open(equity_file, "w") as f:
        f.write(legacy_header + legacy_row)

    runner = BondCashPaperRunner(
        initial_capital=DEFAULT_CAPITAL,
        state_file=state_file,
        trades_file=trades_file,
        equity_log_file=equity_file
    )

    quotes = {"LIQUIDBEES.NS": 1000.00, "LTGILTBEES.NS": 30.00}
    dates = pd.date_range("2026-01-01", periods=10, freq="D")
    market_data = {
        "LIQUIDBEES.NS": pd.DataFrame({"Close": [1000.0] * 10}, index=dates),
        "LTGILTBEES.NS": pd.DataFrame({"Close": [30.0] * 10}, index=dates)
    }

    # Run cycle
    runner.run_daily_cycle(quotes=quotes, market_data=market_data)

    # Read back equity log
    df = pd.read_csv(equity_file)
    assert len(df) == 2
    assert "total_carry_earned" in df.columns
    assert len(df.columns) == 12
    # Verify legacy row has total_carry_earned = 0.0 and correct alignment
    row0 = df.iloc[0]
    assert row0["total_carry_earned"] == 0.0
    assert row0["hwm"] == 20000.0
    assert row0["current_drawdown_pct"] == -0.07
    assert row0["max_drawdown_pct"] == -0.07
    assert row0["max_duration_scale"] == 1.0


def test_bond_cash_equity_log_idempotent_replace_on_rerun(tmp_path):
    """
    Verifies that BondCashPaperRunner log_equity replaces the existing row for the same session date
    rather than duplicating it.
    """
    state_file = str(tmp_path / "state.json")
    trades_file = str(tmp_path / "trades.csv")
    equity_file = str(tmp_path / "equity.csv")

    runner = BondCashPaperRunner(
        initial_capital=DEFAULT_CAPITAL,
        state_file=state_file,
        trades_file=trades_file,
        equity_log_file=equity_file
    )
    quotes = {"LIQUIDBEES.NS": 1000.00, "LTGILTBEES.NS": 30.00}
    dates = pd.date_range("2026-01-01", periods=10, freq="D")
    market_data = {
        "LIQUIDBEES.NS": pd.DataFrame({"Close": [1000.0] * 10}, index=dates),
        "LTGILTBEES.NS": pd.DataFrame({"Close": [30.0] * 10}, index=dates)
    }

    # Run cycle twice on same day
    runner.run_daily_cycle(quotes=quotes, market_data=market_data)
    df1 = pd.read_csv(equity_file)
    assert len(df1) == 1

    runner.run_daily_cycle(quotes=quotes, market_data=market_data)
    df2 = pd.read_csv(equity_file)
    assert len(df2) == 1  # Replaced on re-run, not duplicated




