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

from trading_system.scripts.run_manager import execute_manager_cycle, is_bot_state_stale, append_manager_equity_log
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

    # Bot last ran 5 days ago (not in today's session) -> Recorded as DATA_FAULT per Reviewer Gap 1
    assert res["status"]["is_data_fault"] is True
    assert "did not execute in today's session" in res["status"]["data_fault_reason"]
    assert res["status"]["is_halted"] is False
    assert not os.path.exists(equity_log_path)


def test_manager_runner_kill_switch_breach(tmp_path: Path):
    etf_state_path = str(tmp_path / "etf_gold_state.json")
    mgr_state_path = str(tmp_path / "manager_state.json")
    ledger_path = str(tmp_path / "unitized_nav_ledger.json")
    equity_log_path = str(tmp_path / "manager_equity_log.csv")

    now = datetime.now(timezone.utc)
    # Seed ledger at 100k, then multi-day drawdown: 100k -> 80k -> 65k -> 55k (-45% drawdown)
    # Each daily step is <= 20% (passing the 25% single-day sanity threshold), but cumulatively breaches -40% kill switch
    nav_engine = UnitizedNAVEngine(ledger_path=ledger_path, initial_capital=100000.0)

    # Day 1: 80,000 (-20%)
    with open(etf_state_path, "w") as f:
        json.dump({"bot_name": "ETF_AND_GOLD_BOT", "gate": "GATE_B_PAPER", "nav": 80000.0, "last_run_timestamp": now.isoformat()}, f)
    execute_manager_cycle(
        etf_state_path=etf_state_path,
        manager_state_path=mgr_state_path,
        ledger_path=ledger_path,
        equity_log_path=equity_log_path,
        initial_capital=100000.0,
        as_of=now
    )

    # Day 2: 65,000 (-18.75%)
    d2 = now + timedelta(days=1)
    with open(etf_state_path, "w") as f:
        json.dump({"bot_name": "ETF_AND_GOLD_BOT", "gate": "GATE_B_PAPER", "nav": 65000.0, "last_run_timestamp": d2.isoformat()}, f)
    execute_manager_cycle(
        etf_state_path=etf_state_path,
        manager_state_path=mgr_state_path,
        ledger_path=ledger_path,
        equity_log_path=equity_log_path,
        initial_capital=100000.0,
        as_of=d2
    )

    # Day 3: 55,000 (-15.38% daily, -45% cumulative from 100k HWM -> triggers kill switch)
    d3 = now + timedelta(days=2)
    with open(etf_state_path, "w") as f:
        json.dump({"bot_name": "ETF_AND_GOLD_BOT", "gate": "GATE_B_PAPER", "nav": 55000.0, "last_run_timestamp": d3.isoformat()}, f)
    res = execute_manager_cycle(
        etf_state_path=etf_state_path,
        manager_state_path=mgr_state_path,
        ledger_path=ledger_path,
        equity_log_path=equity_log_path,
        initial_capital=100000.0,
        as_of=d3
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


def test_manager_runner_ingests_bond_cash_state_and_publishes_duration_scale(tmp_path: Path):
    etf_state_path = str(tmp_path / "etf_gold_state.json")
    bond_state_path = str(tmp_path / "bond_cash_state.json")
    mgr_state_path = str(tmp_path / "manager_state.json")
    ledger_path = str(tmp_path / "unitized_nav_ledger.json")
    equity_log_path = str(tmp_path / "manager_equity_log.csv")

    now = datetime.now(timezone.utc)
    bond_state = {
        "bot_name": "BOND_AND_CASH_BOT",
        "phase": "PHASE_3",
        "gate": "GATE_B_PAPER",
        "strategy_id": "B0",
        "nav": 20000.0,
        "cash": 20000.0,
        "positions": {},
        "current_drawdown_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "status": "HEALTHY_ACTIVE",
        "last_run_timestamp": now.isoformat()
    }
    with open(bond_state_path, "w") as f:
        json.dump(bond_state, f)

    res = execute_manager_cycle(
        etf_state_path=etf_state_path,
        bond_cash_state_path=bond_state_path,
        manager_state_path=mgr_state_path,
        ledger_path=ledger_path,
        equity_log_path=equity_log_path,
        initial_capital=80000.0
    )

    assert res["status"]["is_halted"] is False
    assert res["max_duration_scale"] == 1.0
    assert res["status"]["max_duration_scale"] == 1.0
    assert res["bond_cash_report"] is not None
    assert res["bond_cash_report"]["nav"] == 20000.0
    assert res["bond_cash_report"]["reconciliation_passed"] is True


def test_manager_runner_catches_tampered_bond_state(tmp_path: Path):
    etf_state_path = str(tmp_path / "etf_gold_state.json")
    bond_state_path = str(tmp_path / "bond_cash_state.json")
    mgr_state_path = str(tmp_path / "manager_state.json")
    ledger_path = str(tmp_path / "unitized_nav_ledger.json")
    equity_log_path = str(tmp_path / "manager_equity_log.csv")

    now = datetime.now(timezone.utc)
    # Tampered NAV: reports 25,000 but only holds 20,000 cash
    tampered_bond_state = {
        "bot_name": "BOND_AND_CASH_BOT",
        "phase": "PHASE_3",
        "gate": "GATE_B_PAPER",
        "strategy_id": "B0",
        "nav": 25000.0,
        "cash": 20000.0,
        "positions": {},
        "current_drawdown_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "status": "HEALTHY_ACTIVE",
        "last_run_timestamp": now.isoformat()
    }
    with open(bond_state_path, "w") as f:
        json.dump(tampered_bond_state, f)

    res = execute_manager_cycle(
        etf_state_path=etf_state_path,
        bond_cash_state_path=bond_state_path,
        manager_state_path=mgr_state_path,
        ledger_path=ledger_path,
        equity_log_path=equity_log_path,
        initial_capital=80000.0
    )

    assert res["status"]["is_halted"] is True
    assert "BOND_CASH_BOT_RECONCILIATION_BREACH" in res["status"]["halt_reason"]
    assert res["bond_cash_report"]["reconciliation_passed"] is False


def test_manager_runner_multi_sleeve_reconciliation(tmp_path: Path):
    """
    Verifies explicit multi-sleeve architecture and independent per-sleeve reconciliation:
    1. Primary Sleeve (ETF & Gold Bot): INR 80,000 target capital.
    2. Reserve Sleeve (Bond & Cash Bot): INR 20,000 target capital.
    3. Combined Fund NAV: INR 100,000 target capital (sum of both independent NAVs).
    4. Per-sleeve gap and pass/fail status persisted into manager_state.json.
    """
    etf_state_path = str(tmp_path / "etf_gold_state.json")
    bond_state_path = str(tmp_path / "bond_cash_state.json")
    mgr_state_path = str(tmp_path / "manager_state.json")
    ledger_path = str(tmp_path / "unitized_nav_ledger.json")
    equity_log_path = str(tmp_path / "manager_equity_log.csv")

    now = datetime.now(timezone.utc)
    etf_state = {
        "bot_name": "ETF_AND_GOLD_BOT",
        "phase": "PHASE_1",
        "gate": "GATE_B_PAPER",
        "nav": 79900.0,
        "cash": 400.0,
        "positions": {
            "GOLDBEES.NS": {"shares": 100, "last_price": 200.0},
            "LTGILTBEES.NS": {"shares": 595, "last_price": 100.0}
        },
        "last_run_timestamp": now.isoformat()
    }
    with open(etf_state_path, "w") as f:
        json.dump(etf_state, f)

    bond_state = {
        "bot_name": "BOND_AND_CASH_BOT",
        "phase": "PHASE_3",
        "gate": "GATE_B_PAPER",
        "strategy_id": "B0",
        "nav": 19990.0,
        "cash": 990.0,
        "positions": {
            "LIQUIDBEES.NS": {"shares": 19, "last_price": 1000.0}
        },
        "last_run_timestamp": now.isoformat()
    }
    with open(bond_state_path, "w") as f:
        json.dump(bond_state, f)

    quotes = {
        "GOLDBEES.NS": 200.0,
        "LTGILTBEES.NS": 100.0,
        "LIQUIDBEES.NS": 1000.0
    }

    res = execute_manager_cycle(
        etf_state_path=etf_state_path,
        bond_cash_state_path=bond_state_path,
        manager_state_path=mgr_state_path,
        ledger_path=ledger_path,
        equity_log_path=equity_log_path,
        initial_capital=80000.0,
        quotes_override=quotes,
        as_of=now
    )

    assert res["status"]["is_halted"] is False
    assert res["combined_fund_nav"] == pytest.approx(79900.0 + 19990.0, 0.1)

    # Verify sleeves breakdown in res and in persisted manager_state.json
    sleeves = res["sleeves"]
    assert "primary_sleeve" in sleeves
    assert "reserve_sleeve" in sleeves
    assert sleeves["primary_sleeve"]["target_capital"] == 80000.0
    assert sleeves["reserve_sleeve"]["target_capital"] == 20000.0
    assert sleeves["primary_sleeve"]["reconciliation_passed"] is True
    assert sleeves["reserve_sleeve"]["reconciliation_passed"] is True

    # Check persisted manager_state.json
    with open(mgr_state_path, "r") as f:
        saved_mgr = json.load(f)
    assert "sleeves" in saved_mgr
    assert saved_mgr["combined_fund_nav"] == res["combined_fund_nav"]
    assert saved_mgr["combined_target_capital"] == 100000.0
    assert saved_mgr["sleeves"]["primary_sleeve"]["reconciliation_passed"] is True
    assert saved_mgr["sleeves"]["reserve_sleeve"]["reconciliation_passed"] is True


def test_manager_equity_log_migration_and_header_alignment(tmp_path: Path):
    """
    Verifies that append_manager_equity_log transparently migrates a legacy equity log
    (with 11 header names and 12 values per row) to the canonical 15-column schema,
    preventing any column misalignment.
    """
    etf_state_path = str(tmp_path / "etf_gold_state.json")
    mgr_state_path = str(tmp_path / "manager_state.json")
    ledger_path = str(tmp_path / "unitized_nav_ledger.json")
    equity_log_path = str(tmp_path / "manager_equity_log.csv")

    # Write legacy 11-column header with ragged rows (11 and 12 columns)
    legacy_content = (
        "date,total_portfolio_value,nav_per_unit,true_trading_return_pct,current_drawdown_pct,throttle_level,is_halted,halt_reason,reconciliation_gap_pct,share_etf_gold,share_cash_sleeve\n"
        "2026-11-14 05:44:00,80000.0,100.0,0.0,0.0,0,False,,0.0,1.0,0.0\n"
        "2026-11-15 01:44:18,80000.0,100.0,0.0,0.0,0,False,,0.0,1.0,0.0,PAPER\n"
        "2026-11-15 05:46:58,79945.49,99.9319,-0.07,-0.07,0,False,,0.0,1.0,0.0,PAPER\n"
    )
    with open(equity_log_path, "w", encoding="utf-8") as f:
        f.write(legacy_content)

    res = execute_manager_cycle(
        etf_state_path=etf_state_path,
        manager_state_path=mgr_state_path,
        ledger_path=ledger_path,
        equity_log_path=equity_log_path,
        initial_capital=80000.0
    )

    # Read back migrated CSV
    df = pd.read_csv(equity_log_path)
    assert len(df) == 4  # 3 historical rows + 1 new row

    # Invariant: exactly 16 columns including explicit session_date
    expected_cols = [
        "date", "session_date", "total_portfolio_value", "primary_sleeve_nav", "reserve_sleeve_nav",
        "combined_fund_nav", "nav_per_unit", "true_trading_return_pct", "current_drawdown_pct",
        "throttle_level", "is_halted", "halt_reason", "reconciliation_gap_pct",
        "share_etf_gold", "share_cash_sleeve", "execution_mode"
    ]
    assert list(df.columns) == expected_cols

    # Verify column alignment on historical and new rows
    assert df.iloc[0]["date"] == "2026-11-14 05:44:00"
    assert df.iloc[0]["session_date"] == "2026-11-14"
    assert df.iloc[0]["total_portfolio_value"] == 80000.0
    assert df.iloc[0]["primary_sleeve_nav"] == 80000.0
    # Invariant: historical rows predating multi-sleeve logging MUST be blank (no invented numbers)
    assert pd.isna(df.iloc[0]["reserve_sleeve_nav"])
    assert pd.isna(df.iloc[0]["combined_fund_nav"])
    assert df.iloc[0]["nav_per_unit"] == 100.0
    assert df.iloc[0]["execution_mode"] == "PAPER"

    # Row 2 (had 79945.49)
    assert df.iloc[2]["date"] == "2026-11-15 05:46:58"
    assert df.iloc[2]["session_date"] == "2026-11-15"
    assert df.iloc[2]["total_portfolio_value"] == 79945.49
    assert df.iloc[2]["primary_sleeve_nav"] == 79945.49
    assert pd.isna(df.iloc[2]["reserve_sleeve_nav"])
    assert pd.isna(df.iloc[2]["combined_fund_nav"])
    assert df.iloc[2]["nav_per_unit"] == 99.9319
    assert df.iloc[2]["execution_mode"] == "PAPER"

    # Row 3 (new appended row)
    assert df.iloc[3]["total_portfolio_value"] == 80000.0
    assert df.iloc[3]["primary_sleeve_nav"] == 80000.0
    assert df.iloc[3]["nav_per_unit"] == 100.0
    assert df.iloc[3]["execution_mode"] == "PAPER"


def test_manager_equity_log_idempotent_replace_on_rerun(tmp_path: Path):
    """
    Verifies that append_manager_equity_log is strictly idempotent:
    - If multiple runs execute on the same session date, the existing row for that date
      is replaced rather than duplicated.
    - Delayed runs past midnight UTC (e.g. clock date 2026-11-17 with session_date 2026-11-16)
      are NOT overwritten by next session runs on the same calendar clock date.
    """
    equity_log_path = str(tmp_path / "manager_equity_log.csv")
    entry_1 = {
        "date": "2026-11-17 19:02:22",
        "session_date": "2026-11-17",
        "total_portfolio_value": 79555.34,
        "primary_sleeve_nav": 79555.34,
        "reserve_sleeve_nav": 19991.49,
        "combined_fund_nav": 99546.83,
        "nav_per_unit": 99.4442,
        "true_trading_return_pct": -0.56,
        "current_drawdown_pct": -0.56,
        "throttle_level": 0,
        "is_halted": False,
        "halt_reason": "",
        "reconciliation_gap_pct": 0.0,
        "share_etf_gold": 1.0,
        "share_cash_sleeve": 0.0,
        "execution_mode": "PAPER"
    }
    append_manager_equity_log(equity_log_path, entry_1)
    df1 = pd.read_csv(equity_log_path)
    assert len(df1) == 1
    assert df1.iloc[0]["date"] == "2026-11-17 19:02:22"
    assert df1.iloc[0]["session_date"] == "2026-11-17"

    # Re-run 10 minutes later on same session date
    entry_2 = dict(entry_1)
    entry_2["date"] = "2026-11-17 19:12:17"
    entry_2["combined_fund_nav"] = 99547.00
    append_manager_equity_log(equity_log_path, entry_2)

    df2 = pd.read_csv(equity_log_path)
    assert len(df2) == 1  # Replaced, not duplicated
    assert df2.iloc[0]["date"] == "2026-11-17 19:12:17"
    assert df2.iloc[0]["combined_fund_nav"] == 99547.00
    assert df2.iloc[0]["session_date"] == "2026-11-17"

    # Delayed run past midnight scenario:
    # A fresh log where run 1 ran at 00:31 UTC on 2026-11-17 for session 2026-11-16
    log_path_delayed = str(tmp_path / "delayed_run_log.csv")
    delayed_monday = dict(entry_1)
    delayed_monday["date"] = "2026-11-17 00:31:00"
    delayed_monday["session_date"] = "2026-11-16"
    append_manager_equity_log(log_path_delayed, delayed_monday)

    tuesday_run = dict(entry_1)
    tuesday_run["date"] = "2026-11-17 19:12:00"
    tuesday_run["session_date"] = "2026-11-17"
    append_manager_equity_log(log_path_delayed, tuesday_run)

    df_delayed = pd.read_csv(log_path_delayed)
    assert len(df_delayed) == 2  # Both preserved because session_dates differ!
    assert df_delayed.iloc[0]["session_date"] == "2026-11-16"
    assert df_delayed.iloc[1]["session_date"] == "2026-11-17"

    # Re-running Tuesday replaces only the Tuesday row
    tuesday_rerun = dict(tuesday_run)
    tuesday_rerun["date"] = "2026-11-17 19:25:00"
    append_manager_equity_log(log_path_delayed, tuesday_rerun)

    df_delayed_2 = pd.read_csv(log_path_delayed)
    assert len(df_delayed_2) == 2
    assert df_delayed_2.iloc[0]["session_date"] == "2026-11-16"
    assert df_delayed_2.iloc[1]["date"] == "2026-11-17 19:25:00"


def test_manager_runner_consecutive_unverified_quote_warning(tmp_path: Path):
    """
    Verifies that unverified quote fallbacks escalate to a formal warning alert
    after 3 consecutive unverified sessions, and reset to 0 once live quotes succeed.
    """
    etf_state_path = str(tmp_path / "etf_gold_state.json")
    mgr_state_path = str(tmp_path / "manager_state.json")
    ledger_path = str(tmp_path / "unitized_nav_ledger.json")
    equity_log_path = str(tmp_path / "manager_equity_log.csv")

    now = datetime.now(timezone.utc)
    etf_state = {
        "bot_name": "ETF_AND_GOLD_BOT",
        "phase": "PHASE_1",
        "gate": "GATE_B_PAPER",
        "nav": 80000.0,
        "cash": 30000.0,
        "positions": {
            "NON_EXISTENT_TICKER.NS": {"shares": 500, "last_price": 100.0}
        },
        "last_run_timestamp": now.isoformat()
    }
    with open(etf_state_path, "w") as f:
        json.dump(etf_state, f)

    # Session 1: Unverified
    res1 = execute_manager_cycle(
        etf_state_path=etf_state_path,
        manager_state_path=mgr_state_path,
        ledger_path=ledger_path,
        equity_log_path=equity_log_path,
        initial_capital=80000.0,
        quotes_override={},
        as_of=now
    )
    with open(mgr_state_path) as f:
        s1 = json.load(f)
    assert s1["consecutive_unverified_quote_days"] == 1
    assert s1.get("unverified_quotes_warning") is None

    # Session 2: Unverified
    d2 = now + timedelta(days=1)
    etf_state["last_run_timestamp"] = d2.isoformat()
    with open(etf_state_path, "w") as f:
        json.dump(etf_state, f)
    res2 = execute_manager_cycle(
        etf_state_path=etf_state_path,
        manager_state_path=mgr_state_path,
        ledger_path=ledger_path,
        equity_log_path=equity_log_path,
        initial_capital=80000.0,
        quotes_override={},
        as_of=d2
    )
    with open(mgr_state_path) as f:
        s2 = json.load(f)
    assert s2["consecutive_unverified_quote_days"] == 2
    assert s2.get("unverified_quotes_warning") is None

    # Session 3: 3rd consecutive unverified -> Escalate to Warning!
    d3 = now + timedelta(days=2)
    etf_state["last_run_timestamp"] = d3.isoformat()
    with open(etf_state_path, "w") as f:
        json.dump(etf_state, f)
    res3 = execute_manager_cycle(
        etf_state_path=etf_state_path,
        manager_state_path=mgr_state_path,
        ledger_path=ledger_path,
        equity_log_path=equity_log_path,
        initial_capital=80000.0,
        quotes_override={},
        as_of=d3
    )
    with open(mgr_state_path) as f:
        s3 = json.load(f)
    assert s3["consecutive_unverified_quote_days"] == 3
    assert "UNVERIFIED_QUOTES_WARNING" in s3["unverified_quotes_warning"]

    # Session 4: Live quote restored -> Resets counter & warning!
    d4 = now + timedelta(days=3)
    etf_state["last_run_timestamp"] = d4.isoformat()
    with open(etf_state_path, "w") as f:
        json.dump(etf_state, f)
    res4 = execute_manager_cycle(
        etf_state_path=etf_state_path,
        manager_state_path=mgr_state_path,
        ledger_path=ledger_path,
        equity_log_path=equity_log_path,
        initial_capital=80000.0,
        quotes_override={"NON_EXISTENT_TICKER.NS": 100.0},
        as_of=d4
    )
    with open(mgr_state_path) as f:
        s4 = json.load(f)
    assert s4["consecutive_unverified_quote_days"] == 0
    assert s4.get("unverified_quotes_warning") is None



def test_manager_runner_unverified_fallback_price(tmp_path: Path):
    """
    Verifies that when live quote fetching fails and independent NAV calculation
    falls back to the bot's unverified last_price, the reconciliation is explicitly
    marked as UNVERIFIED_FALLBACK_PRICE and reconciliation_passed=False (not claimed as PASS).
    """
    etf_state_path = str(tmp_path / "etf_gold_state.json")
    mgr_state_path = str(tmp_path / "manager_state.json")
    ledger_path = str(tmp_path / "unitized_nav_ledger.json")
    equity_log_path = str(tmp_path / "manager_equity_log.csv")

    now = datetime.now(timezone.utc)
    # Positions with last_price, but no live quote provided for NON_EXISTENT.NS
    etf_state = {
        "bot_name": "ETF_AND_GOLD_BOT",
        "phase": "PHASE_1",
        "gate": "GATE_B_PAPER",
        "nav": 80000.0,
        "cash": 30000.0,
        "positions": {
            "NON_EXISTENT_TICKER.NS": {"shares": 500, "last_price": 100.0}
        },
        "last_run_timestamp": now.isoformat()
    }
    with open(etf_state_path, "w") as f:
        json.dump(etf_state, f)

    # Empty quotes override forces fallback to last_price
    res = execute_manager_cycle(
        etf_state_path=etf_state_path,
        manager_state_path=mgr_state_path,
        ledger_path=ledger_path,
        equity_log_path=equity_log_path,
        initial_capital=80000.0,
        quotes_override={},
        as_of=now
    )

    primary = res["sleeves"]["primary_sleeve"]
    assert primary["quotes_verified"] is False
    assert primary["reconciliation_passed"] is False
    assert primary["reconciliation_status"] == "UNVERIFIED_FALLBACK_PRICE"
    # Fiduciary gap is 0.0%, so trading is not halted, but reconciliation does not count as a pass
    assert res["status"]["is_halted"] is False


def test_manager_runner_nan_quote_safe_fallback(tmp_path: Path):
    """
    Verifies that when a quote source provides NaN or negative prices,
    compute_independent_bot_nav gracefully ignores NaN, falls back to last_price,
    does NOT crash or return NaN independent NAV, and does NOT trigger the kill switch.
    """
    etf_state_path = str(tmp_path / "etf_gold_state.json")
    mgr_state_path = str(tmp_path / "manager_state.json")
    ledger_path = str(tmp_path / "unitized_nav_ledger.json")
    equity_log_path = str(tmp_path / "manager_equity_log.csv")

    now = datetime.now(timezone.utc)
    etf_state = {
        "bot_name": "ETF_AND_GOLD_BOT",
        "phase": "PHASE_1",
        "gate": "GATE_B_PAPER",
        "nav": 80000.0,
        "cash": 30000.0,
        "positions": {
            "GOLDBEES.NS": {"shares": 500, "last_price": 100.0}
        },
        "last_run_timestamp": now.isoformat()
    }
    with open(etf_state_path, "w") as f:
        json.dump(etf_state, f)

    # Provide explicit NaN quote override to test poison quote resistance
    res = execute_manager_cycle(
        etf_state_path=etf_state_path,
        manager_state_path=mgr_state_path,
        ledger_path=ledger_path,
        equity_log_path=equity_log_path,
        initial_capital=80000.0,
        quotes_override={"GOLDBEES.NS": float("nan")},
        as_of=now
    )

    primary = res["sleeves"]["primary_sleeve"]
    assert primary["quotes_verified"] is False
    assert primary["independent_nav"] == 80000.0
    assert res["status"]["is_halted"] is False
    assert res["status"]["throttle_level"] == 0
    assert res["nav_metrics"]["nav_per_unit"] == 100.0


def test_manager_runner_data_fault_on_failed_etf_step(tmp_path: Path):
    """
    Verifies that if the ETF Bot step fails (e.g. FAIL_CLOSED or FAILED status),
    the manager flags a DATA_FAULT, retains prior state, skips the ledger update,
    and NEVER triggers the kill switch from it.
    """
    etf_state_path = str(tmp_path / "etf_gold_state.json")
    mgr_state_path = str(tmp_path / "manager_state.json")
    ledger_path = str(tmp_path / "unitized_nav_ledger.json")
    equity_log_path = str(tmp_path / "manager_equity_log.csv")

    now = datetime.now(timezone.utc)
    # Seed prior manager state
    prior_state = {
        "unitized_nav": 100.0,
        "is_halted": False,
        "current_shares": {"ETF_AND_GOLD": 1.0, "BOND_AND_CASH": 0.0, "CASH_SLEEVE": 0.0}
    }
    with open(mgr_state_path, "w") as f:
        json.dump(prior_state, f)

    # ETF bot has FAIL_CLOSED status
    etf_state = {
        "bot_name": "ETF_AND_GOLD_BOT",
        "phase": "PHASE_1",
        "status": "FAIL_CLOSED",
        "nav": 80000.0,
        "cash": 80000.0,
        "positions": {},
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

    assert res["status"]["is_data_fault"] is True
    assert "DATA_FAULT" in res["status"]["data_fault_reason"]
    assert res["status"]["is_halted"] is False
    assert not os.path.exists(equity_log_path)  # Ledger log update skipped


def test_manager_runner_data_fault_on_extreme_nav_jump(tmp_path: Path):
    """
    Verifies that if independent NAV shows an impossible single-day move > 25%,
    the manager marks DATA_FAULT, keeps prior state, and does NOT trigger the kill switch.
    """
    etf_state_path = str(tmp_path / "etf_gold_state.json")
    mgr_state_path = str(tmp_path / "manager_state.json")
    ledger_path = str(tmp_path / "unitized_nav_ledger.json")
    equity_log_path = str(tmp_path / "manager_equity_log.csv")

    now = datetime.now(timezone.utc)
    # Prior manager state: 80,000 INR
    prior_state = {
        "unitized_nav": 100.0,
        "is_halted": False,
        "current_shares": {"ETF_AND_GOLD": 1.0, "BOND_AND_CASH": 0.0, "CASH_SLEEVE": 0.0}
    }
    with open(mgr_state_path, "w") as f:
        json.dump(prior_state, f)

    # Current ETF state drops by 45% (to 44,000 INR) - impossible for diversified ETF basket
    etf_state = {
        "bot_name": "ETF_AND_GOLD_BOT",
        "status": "HEALTHY_ACTIVE",
        "nav": 44000.0,
        "cash": 44000.0,
        "positions": {},
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

    assert res["status"]["is_data_fault"] is True
    assert "25.0% sanity threshold" in res["status"]["data_fault_reason"]
    # Crucially, the -40% kill switch was NOT triggered!
    assert res["status"]["is_halted"] is False
    assert not os.path.exists(equity_log_path)





