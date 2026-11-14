"""
Unit Tests for Central Portfolio Manager Runner (Phase 2)
=========================================================
Tests CLI execution cycle, bot ingestion, staleness guards,
fiduciary reconciliation, and state persistence.
"""

import os
import json
import pytest
import pandas as pd
from datetime import datetime, timezone, timedelta
from pathlib import Path

from trading_system.scripts.run_manager import execute_manager_cycle, is_bot_state_stale
from trading_system.app.accounting.unitized_nav import UnitizedNAVEngine


def test_staleness_detector():
    now = datetime(2026, 11, 13, 15, 45, tzinfo=timezone.utc)
    # 2 hours ago: Fresh
    fresh_ts = (now - timedelta(hours=2)).isoformat()
    assert is_bot_state_stale(fresh_ts, now) is False

    # 50 hours ago on weekday: Stale
    stale_ts = (now - timedelta(hours=50)).isoformat()
    assert is_bot_state_stale(stale_ts, now) is True

    # None / Empty: Not stale (initial unseeded state)
    assert is_bot_state_stale(None, now) is False


def test_manager_runner_initial_clean_run(tmp_path: Path):
    etf_state_path = str(tmp_path / "etf_gold_state.json")
    mgr_state_path = str(tmp_path / "manager_state.json")
    ledger_path = str(tmp_path / "unitized_nav_ledger.json")
    equity_log_path = str(tmp_path / "manager_equity_log.csv")

    res = execute_manager_cycle(
        etf_state_path=etf_state_path,
        manager_state_path=mgr_state_path,
        ledger_path=ledger_path,
        equity_log_path=equity_log_path,
        initial_capital=80000.0
    )

    assert res["status"]["is_halted"] is False
    assert res["status"]["throttle_level"] == 0
    assert res["shares"]["ETF_AND_GOLD"] == 1.0
    assert res["shares"]["CASH_SLEEVE"] == 0.0
    assert res["nav_metrics"]["nav_per_unit"] == 100.0
    assert res["nav_metrics"]["total_portfolio_value"] == 80000.0

    # Verify equity log written
    assert os.path.exists(equity_log_path)
    df_log = pd.read_csv(equity_log_path)
    assert len(df_log) == 1
    assert df_log.iloc[0]["nav_per_unit"] == 100.0
    assert df_log.iloc[0]["total_portfolio_value"] == 80000.0


def test_manager_runner_healthy_etf_state_ingestion(tmp_path: Path):
    etf_state_path = str(tmp_path / "etf_gold_state.json")
    mgr_state_path = str(tmp_path / "manager_state.json")
    ledger_path = str(tmp_path / "unitized_nav_ledger.json")
    equity_log_path = str(tmp_path / "manager_equity_log.csv")

    now = datetime.now(timezone.utc)
    etf_state = {
        "bot_name": "ETF_AND_GOLD_BOT",
        "phase": "PHASE_1",
        "gate": "GATE_B_PAPER",
        "nav": 84250.0,
        "cash": 450.0,
        "current_drawdown_pct": -1.2,
        "max_drawdown_pct": -4.5,
        "status": "HEALTHY_ACTIVE",
        "last_run_timestamp": now.isoformat()
    }
    with open(etf_state_path, "w") as f:
        json.dump(etf_state, f)

    res = execute_manager_cycle(
        etf_state_path=etf_state_path,
        manager_state_path=mgr_state_path,
        ledger_path=ledger_path,
        equity_log_path=equity_log_path,
        initial_capital=80000.0,
        as_of=now
    )

    assert res["status"]["is_halted"] is False
    assert res["shares"]["ETF_AND_GOLD"] == 1.0
    assert res["shares"]["CASH_SLEEVE"] == 0.0
    assert res["nav_metrics"]["total_portfolio_value"] == 84250.0
    # 84,250 / 80,000 * 100 = 105.3125
    assert pytest.approx(res["nav_metrics"]["nav_per_unit"], 0.01) == 105.3125
    assert res["status"]["last_reconciliation_gap_pct"] == 0.0


def test_manager_runner_stale_bot_freezes_allocation(tmp_path: Path):
    etf_state_path = str(tmp_path / "etf_gold_state.json")
    mgr_state_path = str(tmp_path / "manager_state.json")
    ledger_path = str(tmp_path / "unitized_nav_ledger.json")
    equity_log_path = str(tmp_path / "manager_equity_log.csv")

    # Bot last ran 5 days ago (stale)
    stale_time = datetime.now(timezone.utc) - timedelta(days=5)
    etf_state = {
        "bot_name": "ETF_AND_GOLD_BOT",
        "gate": "GATE_B_PAPER",
        "nav": 80000.0,
        "last_run_timestamp": stale_time.isoformat()
    }
    with open(etf_state_path, "w") as f:
        json.dump(etf_state, f)

    res = execute_manager_cycle(
        etf_state_path=etf_state_path,
        manager_state_path=mgr_state_path,
        ledger_path=ledger_path,
        equity_log_path=equity_log_path,
        initial_capital=80000.0
    )

    # Stale bot: allocation frozen to 0%, capital held in CASH_SLEEVE
    assert res["etf_report"]["stale"] is True
    assert res["shares"]["ETF_AND_GOLD"] == 0.0
    assert res["shares"]["CASH_SLEEVE"] == 1.0


def test_manager_runner_kill_switch_breach(tmp_path: Path):
    etf_state_path = str(tmp_path / "etf_gold_state.json")
    mgr_state_path = str(tmp_path / "manager_state.json")
    ledger_path = str(tmp_path / "unitized_nav_ledger.json")
    equity_log_path = str(tmp_path / "manager_equity_log.csv")

    now = datetime.now(timezone.utc)
    # Seed ledger at 100k, then crash to 55k (-45% drawdown)
    nav_engine = UnitizedNAVEngine(ledger_path=ledger_path, initial_capital=100000.0)

    etf_state = {
        "bot_name": "ETF_AND_GOLD_BOT",
        "gate": "GATE_B_PAPER",
        "nav": 55000.0,
        "last_run_timestamp": now.isoformat()
    }
    with open(etf_state_path, "w") as f:
        json.dump(etf_state, f)

    res = execute_manager_cycle(
        etf_state_path=etf_state_path,
        manager_state_path=mgr_state_path,
        ledger_path=ledger_path,
        equity_log_path=equity_log_path,
        initial_capital=100000.0,
        as_of=now
    )

    assert res["status"]["is_halted"] is True
    assert res["status"]["throttle_level"] == 3
    assert "KILL_SWITCH_TRIGGERED" in res["status"]["halt_reason"]
    assert res["shares"]["CASH_SLEEVE"] == 1.0
    assert res["shares"].get("ETF_AND_GOLD", 0.0) == 0.0
