"""
Unit Tests for Phase 2 Manager Bot: Throttle, Kill Switch, Re-risking and Reconciliation
Tests T3, T4, and T5 per PROTOCOL-MANAGER-BOT-CASH-SLEEVE-V1-20261113
"""

import os
import pytest
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

from trading_system.app.common.interfaces import BotReport
from trading_system.app.manager.manager import PortfolioManagerEngine


def make_bot_report(nav: float, stale: bool = False, gate_status: str = "GATE_B_PAPER") -> BotReport:
    return BotReport(
        nav=nav,
        risk_status={"regime": "ACTIVE"},
        gate_status=gate_status,
        last_update=pd.Timestamp.now(timezone.utc),
        stale=stale
    )


def test_t3_kill_switch_inject_41_pct_drawdown(tmp_path: Path):
    """
    Phase 2 Protocol Test T3 (Kill Switch Verification):
    Inject a -41% NAV path on paper.
    Pass condition: All capital moves to LIQUIDBEES in one cycle, status flips to halted,
    and no automatic restart occurs.
    """
    state_file = str(tmp_path / "test_mgr_state.json")
    mgr = PortfolioManagerEngine(
        target_shares={"ETF_AND_GOLD": 1.0},
        initial_capital=100000.0,
        state_file=state_file,
        policy="THROTTLE_AND_KILL_SWITCH"
    )

    now = pd.Timestamp.now(timezone.utc)

    # 1. Normal state: Unit NAV = 100.0 (HWM = 100.0)
    rep_normal = {"ETF_AND_GOLD": make_bot_report(nav=100000.0)}
    nav_state_normal = {"nav_per_unit": 100.0, "total_portfolio_value": 100000.0}
    shares_0 = mgr.evaluate_shares(now, rep_normal, nav_state_normal)
    assert shares_0["ETF_AND_GOLD"] == 1.0
    assert shares_0["CASH_SLEEVE"] == 0.0
    assert mgr.state["is_halted"] is False
    assert mgr.state["throttle_level"] == 0

    # 2. Inject -41% crash: Unit NAV drops to 59.0
    rep_crash = {"ETF_AND_GOLD": make_bot_report(nav=59000.0)}
    nav_state_crash = {"nav_per_unit": 59.0, "total_portfolio_value": 59000.0}
    shares_crash = mgr.evaluate_shares(now, rep_crash, nav_state_crash)

    # Invariant: 100% capital routed to LIQUIDBEES (CASH_SLEEVE), status flips to halted
    assert shares_crash["CASH_SLEEVE"] == 1.0
    assert shares_crash.get("ETF_AND_GOLD", 0.0) == 0.0
    assert mgr.state["is_halted"] is True
    assert mgr.state["throttle_level"] == 3
    assert "KILL_SWITCH_TRIGGERED" in mgr.state["halt_reason"]

    # 3. Market rebounds to 85.0 (-15% DD): Assert NO automatic restart without human approval!
    rep_rebound = {"ETF_AND_GOLD": make_bot_report(nav=85000.0)}
    nav_state_rebound = {"nav_per_unit": 85.0, "total_portfolio_value": 85000.0}
    shares_rebound = mgr.evaluate_shares(now, rep_rebound, nav_state_rebound)

    assert shares_rebound["CASH_SLEEVE"] == 1.0
    assert shares_rebound.get("ETF_AND_GOLD", 0.0) == 0.0
    assert mgr.state["is_halted"] is True

    # 4. Human boss override: Cautiously resumes at Level 2
    mgr.resume_approved()
    assert mgr.state["is_halted"] is False
    assert mgr.state["throttle_level"] == 2


def test_t4_reconciliation_gap_pauses_trading(tmp_path: Path):
    """
    Phase 2 Protocol Test T4 (Reconciliation Verification):
    Break a bot's state file on purpose.
    Pass condition: Gap above 0.1% pauses all trading and raises an alert.
    """
    state_file = str(tmp_path / "test_mgr_state.json")
    mgr = PortfolioManagerEngine(
        target_shares={"ETF_AND_GOLD": 1.0},
        initial_capital=80000.0,
        state_file=state_file
    )

    now = pd.Timestamp.now(timezone.utc)

    # Broken bot state: Manager has 80,000, but bot reports 79,500 (gap = 500 / 80000 = 0.625% > 0.1%)
    rep_broken = {"ETF_AND_GOLD": make_bot_report(nav=79500.0)}
    nav_state = {"nav_per_unit": 100.0, "total_portfolio_value": 80000.0}

    shares = mgr.evaluate_shares(now, rep_broken, nav_state)

    # Invariant: Trading paused, all capital shifted to CASH_SLEEVE, gap logged
    assert shares["CASH_SLEEVE"] == 1.0
    assert mgr.state["is_halted"] is True
    assert "RECONCILIATION_GAP_BREACH" in mgr.state["halt_reason"]
    assert mgr.state["last_reconciliation_gap_pct"] > 0.10


def test_t5_re_risking_and_throttle_ladder(tmp_path: Path):
    """
    Phase 2 Protocol Test T5 (Re-risking Ladder Verification):
    Replay a drawdown and recovery path.
    Pass condition: Moves up one level only after 21 days +5 pts better, never skips a level.
    """
    state_file = str(tmp_path / "test_mgr_state.json")
    mgr = PortfolioManagerEngine(
        target_shares={"ETF_AND_GOLD": 1.0},
        initial_capital=100000.0,
        state_file=state_file,
        policy="THROTTLE_AND_KILL_SWITCH"
    )

    now = pd.Timestamp.now(timezone.utc)

    # Day 0: Normal -> Level 0 (100% risk)
    rep = {"ETF_AND_GOLD": make_bot_report(nav=100000.0)}
    s0 = mgr.evaluate_shares(now, rep, {"nav_per_unit": 100.0, "total_portfolio_value": 100000.0})
    assert mgr.state["throttle_level"] == 0
    assert s0["ETF_AND_GOLD"] == 1.0

    # Step 1: Drawdown drops to -18% (NAV = 82.0) -> Level 1 (50% risk)
    rep1 = {"ETF_AND_GOLD": make_bot_report(nav=82000.0)}
    s1 = mgr.evaluate_shares(now, rep1, {"nav_per_unit": 82.0, "total_portfolio_value": 82000.0})
    assert mgr.state["throttle_level"] == 1
    assert s1["ETF_AND_GOLD"] == 0.50
    assert s1["CASH_SLEEVE"] == 0.50

    # Step 2: Drawdown drops to -32% (NAV = 68.0) -> Level 2 (25% risk)
    rep2 = {"ETF_AND_GOLD": make_bot_report(nav=68000.0)}
    s2 = mgr.evaluate_shares(now, rep2, {"nav_per_unit": 68.0, "total_portfolio_value": 68000.0})
    assert mgr.state["throttle_level"] == 2
    assert s2["ETF_AND_GOLD"] == 0.25
    assert s2["CASH_SLEEVE"] == 0.75

    # Step 3: Drawdown recovers to -24% (NAV = 76.0, which is >= -25% recovery trigger)
    # Days 1 to 20: Must stay at Level 2!
    for day in range(1, 21):
        rep_rec = {"ETF_AND_GOLD": make_bot_report(nav=76000.0)}
        s_rec = mgr.evaluate_shares(now, rep_rec, {"nav_per_unit": 76.0, "total_portfolio_value": 76000.0})
        assert mgr.state["throttle_level"] == 2, f"Premature de-throttle on day {day}!"
        assert s_rec["ETF_AND_GOLD"] == 0.25

    # Day 21: Exactly 21 days completed -> moves up to Level 1!
    rep_rec21 = {"ETF_AND_GOLD": make_bot_report(nav=76000.0)}
    s_rec21 = mgr.evaluate_shares(now, rep_rec21, {"nav_per_unit": 76.0, "total_portfolio_value": 76000.0})
    assert mgr.state["throttle_level"] == 1
    assert s_rec21["ETF_AND_GOLD"] == 0.50
    # Crucial Invariant: Never skips Level 1 to go directly to Level 0!
    assert s_rec21["ETF_AND_GOLD"] != 1.0

    # Step 4: Drawdown recovers to -8% (NAV = 92.0, which is >= -10% recovery trigger)
    # Days 1 to 20: Must stay at Level 1!
    for day in range(1, 21):
        rep_rec = {"ETF_AND_GOLD": make_bot_report(nav=92000.0)}
        s_rec = mgr.evaluate_shares(now, rep_rec, {"nav_per_unit": 92.0, "total_portfolio_value": 92000.0})
        assert mgr.state["throttle_level"] == 1
        assert s_rec["ETF_AND_GOLD"] == 0.50

    # Day 21 at >= -10%: moves up to Level 0 (Normal 100%)!
    rep_rec42 = {"ETF_AND_GOLD": make_bot_report(nav=92000.0)}
    s_rec42 = mgr.evaluate_shares(now, rep_rec42, {"nav_per_unit": 92.0, "total_portfolio_value": 92000.0})
    assert mgr.state["throttle_level"] == 0
    assert s_rec42["ETF_AND_GOLD"] == 1.0
    assert s_rec42["CASH_SLEEVE"] == 0.0


def test_fixed_shares_plus_kill_switch_policy(tmp_path: Path):
    """
    Verifies that under FIXED_SHARES_PLUS_KILL_SWITCH (shipped production policy):
    - Drawdown of -18% or -32% does NOT throttle risk (ETF Bot retains 100% allocation).
    - Hard kill switch at -40% breaches and routes 100% to CASH_SLEEVE.
    """
    state_file = str(tmp_path / "test_fixed_mgr_state.json")
    mgr = PortfolioManagerEngine(
        target_shares={"ETF_AND_GOLD": 1.0},
        initial_capital=100000.0,
        state_file=state_file,
        policy="FIXED_SHARES_PLUS_KILL_SWITCH"
    )

    now = pd.Timestamp.now(timezone.utc)

    # 1. Normal state: 100% ETF Bot
    s0 = mgr.evaluate_shares(now, {"ETF_AND_GOLD": make_bot_report(nav=100000.0)}, {"nav_per_unit": 100.0, "total_portfolio_value": 100000.0})
    assert s0["ETF_AND_GOLD"] == 1.0
    assert s0["CASH_SLEEVE"] == 0.0
    assert mgr.state["throttle_level"] == 0

    # 2. Drawdown at -18%: No throttle!
    s1 = mgr.evaluate_shares(now, {"ETF_AND_GOLD": make_bot_report(nav=82000.0)}, {"nav_per_unit": 82.0, "total_portfolio_value": 82000.0})
    assert s1["ETF_AND_GOLD"] == 1.0
    assert s1["CASH_SLEEVE"] == 0.0
    assert mgr.state["throttle_level"] == 0

    # 3. Drawdown at -32%: Still no throttle!
    s2 = mgr.evaluate_shares(now, {"ETF_AND_GOLD": make_bot_report(nav=68000.0)}, {"nav_per_unit": 68.0, "total_portfolio_value": 68000.0})
    assert s2["ETF_AND_GOLD"] == 1.0
    assert s2["CASH_SLEEVE"] == 0.0
    assert mgr.state["throttle_level"] == 0

    # 4. Drawdown at -41%: Hard kill switch triggers!
    s3 = mgr.evaluate_shares(now, {"ETF_AND_GOLD": make_bot_report(nav=59000.0)}, {"nav_per_unit": 59.0, "total_portfolio_value": 59000.0})
    assert s3.get("ETF_AND_GOLD", 0.0) == 0.0
    assert s3["CASH_SLEEVE"] == 1.0
    assert mgr.state["is_halted"] is True
    assert mgr.state["throttle_level"] == 3

