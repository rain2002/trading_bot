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
        "cash": 4250.0,
        "positions": {
            "GOLDBEES.NS": {"shares": 100, "last_price": 200.0},
            "MON100.NS": {"shares": 100, "last_price": 200.0},
            "NIFTYBEES.NS": {"shares": 100, "last_price": 200.0},
            "LTGILTBEES.NS": {"shares": 200, "last_price": 100.0}
        },
        "current_drawdown_pct": -1.2,
        "max_drawdown_pct": -4.5,
        "status": "HEALTHY_ACTIVE",
        "last_run_timestamp": now.isoformat()
    }
    with open(etf_state_path, "w") as f:
        json.dump(etf_state, f)

    quotes = {
        "GOLDBEES.NS": 200.0,
        "MON100.NS": 200.0,
        "NIFTYBEES.NS": 200.0,
        "LTGILTBEES.NS": 100.0
    }

    res = execute_manager_cycle(
        etf_state_path=etf_state_path,
        manager_state_path=mgr_state_path,
        ledger_path=ledger_path,
        equity_log_path=equity_log_path,
        initial_capital=80000.0,
        quotes_override=quotes,
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


def test_manager_runner_reads_real_bot_state_file(tmp_path: Path):
    """
    Asserts that the Manager reads the actual state file generated by ETFGoldsPaperRunner
    with matching gate status ('GATE_B_PAPER'), granting 100% target capital allocation.
    """
    from trading_system.app.bots.etf_gold_bot import ETFGoldsPaperRunner

    etf_state_path = str(tmp_path / "etf_gold_state.json")
    mgr_state_path = str(tmp_path / "manager_state.json")
    ledger_path = str(tmp_path / "unitized_nav_ledger.json")
    equity_log_path = str(tmp_path / "manager_equity_log.csv")

    # Instantiate real ETFGoldsPaperRunner with tmp paths
    bot_runner = ETFGoldsPaperRunner(
        state_file=etf_state_path,
        trades_file=str(tmp_path / "trades.csv"),
        equity_log_file=str(tmp_path / "equity.csv"),
        initial_capital=80000.0
    )
    # Save bot's real state to disk
    bot_runner._save_state()

    # Verify bot wrote GATE_B_PAPER
    with open(etf_state_path, "r") as f:
        real_state = json.load(f)
    assert real_state["gate"] == "GATE_B_PAPER"

    # Execute Manager cycle reading this exact real state file
    res = execute_manager_cycle(
        etf_state_path=etf_state_path,
        manager_state_path=mgr_state_path,
        ledger_path=ledger_path,
        equity_log_path=equity_log_path,
        initial_capital=80000.0
    )

    # Invariant: ETF bot receives 100% allocation, cash sleeve is 0%
    assert res["status"]["is_halted"] is False
    assert res["shares"]["ETF_AND_GOLD"] == 1.0
    assert res["shares"]["CASH_SLEEVE"] == 0.0
    assert res["status"]["last_reconciliation_gap_pct"] == 0.0


def test_manager_runner_reconciliation_catches_tampered_state_file(tmp_path: Path):
    """
    Protocol Test T4 Invariant:
    If a bot's state file is corrupted or tampered (reported NAV differs from
    raw cash + positions * quotes by > 0.1%), the Manager independent reconciliation
    MUST catch the gap, pause all trading (is_halted=True), and route 100% to CASH_SLEEVE.
    """
    etf_state_path = str(tmp_path / "etf_gold_state.json")
    mgr_state_path = str(tmp_path / "manager_state.json")
    ledger_path = str(tmp_path / "unitized_nav_ledger.json")
    equity_log_path = str(tmp_path / "manager_equity_log.csv")

    now = datetime.now(timezone.utc)
    # True independent NAV = 10,000 cash + (100 shs * 200 = 20,000) + (50 shs * 1000 = 50,000) = 80,000
    # But state file is tampered: reports "nav": 85000.0 (gap = 5,000 / 80,000 = 6.25% > 0.1% limit)
    tampered_state = {
        "bot_name": "ETF_AND_GOLD_BOT",
        "gate": "GATE_B_PAPER",
        "cash": 10000.0,
        "nav": 85000.0,  # Corrupted / tampered!
        "positions": {
            "GOLDBEES.NS": {"shares": 100, "last_price": 200.0},
            "NIFTYBEES.NS": {"shares": 50, "last_price": 1000.0}
        },
        "last_run_timestamp": now.isoformat()
    }
    with open(etf_state_path, "w") as f:
        json.dump(tampered_state, f)

    quotes = {"GOLDBEES.NS": 200.0, "NIFTYBEES.NS": 1000.0}

    res = execute_manager_cycle(
        etf_state_path=etf_state_path,
        manager_state_path=mgr_state_path,
        ledger_path=ledger_path,
        equity_log_path=equity_log_path,
        initial_capital=80000.0,
        quotes_override=quotes,
        as_of=now
    )

    # Invariant: Reconciliation gap detected (>0.1%), trading halted, 100% to CASH_SLEEVE
    assert res["status"]["is_halted"] is True
    assert "RECONCILIATION_GAP_BREACH" in res["status"]["halt_reason"]
    assert res["status"]["last_reconciliation_gap_pct"] > 0.1
    assert res["shares"]["CASH_SLEEVE"] == 1.0
    assert res["shares"].get("ETF_AND_GOLD", 0.0) == 0.0


def test_manager_runner_live_mode_vs_paper_mode(tmp_path: Path):
    """
    Protocol Pre-Live Invariant:
    - In PAPER mode: Bots with GATE_B_PAPER receive paper capital (100%).
    - In LIVE mode: Bots with GATE_B_PAPER receive 0% real capital (100% to CASH_SLEEVE).
      Only bots with LIVE_APPROVED receive real capital.
    """
    etf_state_path = str(tmp_path / "etf_gold_state.json")
    mgr_state_path = str(tmp_path / "manager_state.json")
    ledger_path = str(tmp_path / "unitized_nav_ledger.json")
    equity_log_path = str(tmp_path / "manager_equity_log.csv")

    now = datetime.now(timezone.utc)
    etf_state = {
        "bot_name": "ETF_AND_GOLD_BOT",
        "gate": "GATE_B_PAPER",
        "nav": 80000.0,
        "cash": 80000.0,
        "positions": {},
        "last_run_timestamp": now.isoformat()
    }
    with open(etf_state_path, "w") as f:
        json.dump(etf_state, f)

    # 1. PAPER Mode: GATE_B_PAPER gets 100%
    res_paper = execute_manager_cycle(
        etf_state_path=etf_state_path,
        manager_state_path=mgr_state_path,
        ledger_path=ledger_path,
        equity_log_path=equity_log_path,
        mode="PAPER",
        initial_capital=80000.0,
        as_of=now
    )
    assert res_paper["shares"]["ETF_AND_GOLD"] == 1.0
    assert res_paper["shares"]["CASH_SLEEVE"] == 0.0

    # 2. LIVE Mode: GATE_B_PAPER gets 0%, 100% remains in CASH_SLEEVE
    res_live = execute_manager_cycle(
        etf_state_path=etf_state_path,
        manager_state_path=mgr_state_path,
        ledger_path=ledger_path,
        equity_log_path=equity_log_path,
        mode="LIVE",
        initial_capital=80000.0,
        as_of=now
    )
    assert res_live["shares"]["ETF_AND_GOLD"] == 0.0
    assert res_live["shares"]["CASH_SLEEVE"] == 1.0

    # 3. LIVE Mode with LIVE_APPROVED: Gets 100% real capital
    etf_state["gate"] = "LIVE_APPROVED"
    with open(etf_state_path, "w") as f:
        json.dump(etf_state, f)

    res_live_approved = execute_manager_cycle(
        etf_state_path=etf_state_path,
        manager_state_path=mgr_state_path,
        ledger_path=ledger_path,
        equity_log_path=equity_log_path,
        mode="LIVE",
        initial_capital=80000.0,
        as_of=now
    )
    assert res_live_approved["shares"]["ETF_AND_GOLD"] == 1.0
    assert res_live_approved["shares"]["CASH_SLEEVE"] == 0.0
