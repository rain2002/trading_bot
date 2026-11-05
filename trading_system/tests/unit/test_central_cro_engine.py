import os
import pytest
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

from trading_system.app.risk.cro import ChiefRiskOfficer, CRORiskStatus


@pytest.fixture
def cro(tmp_path: Path):
    state_file = str(tmp_path / "cro_test_state.json")
    return ChiefRiskOfficer(state_file=state_file)


def test_cro_daily_loss_circuit_breaker(cro):
    """
    Asserts CRO trips 2.0% daily circuit breaker when NAV drops >= 2.0% in a single day.
    """
    t0 = datetime(2026, 11, 4, 9, 30, tzinfo=timezone.utc)
    # Start of day NAV = 100,000
    cro.evaluate_daily_cycle(current_nav=100000.0, as_of_time=t0)

    # Intraday drop to 98,500 (1.5% drop < 2.0%) -> GREEN
    res_1 = cro.evaluate_daily_cycle(current_nav=98500.0, as_of_time=t0 + timedelta(hours=2))
    assert res_1.daily_circuit_breaker_active is False
    assert res_1.can_enter_new_trades is True

    # Intraday drop to 97,500 (2.5% drop >= 2.0%) -> TRIPPED
    res_2 = cro.evaluate_daily_cycle(current_nav=97500.0, as_of_time=t0 + timedelta(hours=4))
    assert res_2.daily_circuit_breaker_active is True
    assert res_2.can_enter_new_trades is False
    assert res_2.exposure_scale_factor == 0.0
    assert any("DAILY_LOSS_CIRCUIT_BREAKER" in b for b in res_2.active_breaches)


def test_cro_buffett_and_lynch_drawdown_ladder(cro):
    """
    Asserts 4-tier drawdown ladder:
    - -10% DD (Peter Lynch): Cut risk by 30% (scale 0.70)
    - -18% DD (Buffett Rule #1): Rotate to Cash/Defensive (scale 0.10)
    - -24% DD: Buying freeze (scale 0.0, can_enter=False)
    - -30% DD: Emergency circuit halt
    """
    t = datetime(2026, 11, 4, 15, 0, tzinfo=timezone.utc)
    # Establish HWM of 100,000
    cro.evaluate_daily_cycle(current_nav=100000.0, as_of_time=t)

    # Normal market (-5% DD) -> scale 1.0
    s_normal = cro.evaluate_daily_cycle(current_nav=95000.0, as_of_time=t + timedelta(days=1))
    assert s_normal.ladder_level == "NORMAL"
    assert s_normal.exposure_scale_factor == 1.0
    assert s_normal.can_enter_new_trades is True

    # Level 1 (-12% DD) -> Lynch step: cut risk by 30%
    s_lynch = cro.evaluate_daily_cycle(current_nav=88000.0, as_of_time=t + timedelta(days=2))
    assert s_lynch.ladder_level == "LADDER_STEP_1_LYNCH"
    assert s_lynch.exposure_scale_factor == 0.70
    assert s_lynch.can_enter_new_trades is True

    # Level 2 (-20% DD) -> Buffett step: rotate predominantly into cash (scale 0.10)
    s_buffett = cro.evaluate_daily_cycle(current_nav=80000.0, as_of_time=t + timedelta(days=3))
    assert s_buffett.ladder_level == "LADDER_STEP_2_BUFFETT"
    assert s_buffett.exposure_scale_factor == 0.10
    assert s_buffett.can_enter_new_trades is True

    # Level 3 (-25% DD) -> Complete buying freeze
    s_freeze = cro.evaluate_daily_cycle(current_nav=75000.0, as_of_time=t + timedelta(days=4))
    assert s_freeze.ladder_level == "LADDER_STEP_3_FREEZE"
    assert s_freeze.exposure_scale_factor == 0.0
    assert s_freeze.can_enter_new_trades is False

    # Level 4 (-32% DD) -> Emergency halt
    s_emerg = cro.evaluate_daily_cycle(current_nav=68000.0, as_of_time=t + timedelta(days=5))
    assert s_emerg.ladder_level == "EMERGENCY_HALT"
    assert s_emerg.can_enter_new_trades is False

    # Emergency halt persists across runs until manual Boss reset
    s_persisted = cro.evaluate_daily_cycle(current_nav=75000.0, as_of_time=t + timedelta(days=6))
    assert s_persisted.ladder_level == "EMERGENCY_HALT"

    # Reset by Boss
    cro.reset_emergency_halt()
    s_cleared = cro.evaluate_daily_cycle(current_nav=75000.0, as_of_time=t + timedelta(days=7))
    assert s_cleared.ladder_level == "LADDER_STEP_3_FREEZE"


def test_cro_earnings_blackout_gate(cro):
    """
    Asserts zero new swing entries allowed within 2 trading days before quarterly earnings release.
    """
    as_of = date(2026, 11, 4)  # Wednesday

    earnings_cal = {
        "RELIANCE.NS": date(2026, 11, 5),  # 1 day away -> BLACKOUT
        "TCS.NS": date(2026, 11, 6),       # 2 days away -> BLACKOUT
        "INFY.NS": date(2026, 11, 12),     # 8 days away -> CLEAN
        "AAPL": date(2026, 11, 4)          # Today -> BLACKOUT
    }

    assert cro.check_earnings_blackout("RELIANCE.NS", as_of, earnings_cal) is False
    assert cro.check_earnings_blackout("TCS.NS", as_of, earnings_cal) is False
    assert cro.check_earnings_blackout("AAPL", as_of, earnings_cal) is False
    assert cro.check_earnings_blackout("INFY.NS", as_of, earnings_cal) is True
    assert cro.check_earnings_blackout("MSFT", as_of, earnings_cal) is True


def test_cro_regime_flip_whipsaw_damping(cro):
    """
    Asserts regime flip requires 2-close persistence, while CRASH_WARNING bypasses instantly.
    """
    t0 = datetime(2026, 11, 2, tzinfo=timezone.utc)
    # Day 1: Start at TRENDING_BULL
    cro.evaluate_daily_cycle(current_nav=100000.0, as_of_time=t0, macro_regime="TRENDING_BULL")
    assert cro.state["confirmed_regime"] == "TRENDING_BULL"

    # Day 2: Single close in BEAR_CORRECTION -> damped (remains TRENDING_BULL)
    s1 = cro.evaluate_daily_cycle(current_nav=100000.0, as_of_time=t0 + timedelta(days=1), macro_regime="BEAR_CORRECTION")
    assert cro.state["confirmed_regime"] == "TRENDING_BULL"

    # Day 3: Second consecutive close in BEAR_CORRECTION -> confirmed transition
    s2 = cro.evaluate_daily_cycle(current_nav=100000.0, as_of_time=t0 + timedelta(days=2), macro_regime="BEAR_CORRECTION")
    assert cro.state["confirmed_regime"] == "BEAR_CORRECTION"

    # Immediate CRASH_WARNING bypasses 2-close damping for instant capital preservation
    s_crash = cro.evaluate_daily_cycle(current_nav=100000.0, as_of_time=t0 + timedelta(days=3), macro_regime="CRASH_WARNING")
    assert cro.state["confirmed_regime"] == "CRASH_WARNING"
    assert s_crash.crash_warning_active is True
    assert s_crash.can_enter_new_trades is False


def test_cro_boss_away_watchdog_mode(cro):
    """
    Asserts 14-day inactivity watchdog freezes new entries if no Boss handshake ping is received.
    """
    now = datetime(2026, 11, 4, tzinfo=timezone.utc)
    
    # Ping 5 days ago -> GREEN
    cro.register_boss_ping(timestamp=now - timedelta(days=5))
    s1 = cro.evaluate_daily_cycle(current_nav=100000.0, as_of_time=now)
    assert s1.boss_away_active is False
    assert s1.can_enter_new_trades is True

    # Inactivity for 16 days (> 14 days) -> TRIPPED
    cro.register_boss_ping(timestamp=now - timedelta(days=16))
    s2 = cro.evaluate_daily_cycle(current_nav=100000.0, as_of_time=now)
    assert s2.boss_away_active is True
    assert s2.can_enter_new_trades is False
    assert s2.exposure_scale_factor == 0.0

    # Boss checks in -> instant restoration
    cro.register_boss_ping(timestamp=now)
    s3 = cro.evaluate_daily_cycle(current_nav=100000.0, as_of_time=now)
    assert s3.boss_away_active is False
    assert s3.can_enter_new_trades is True


def test_cro_exchange_surveillance_and_circuit_band_filter(cro):
    """
    Asserts rejection of stocks on SEBI ASM/GSM watchlist or locked in daily circuit limits.
    """
    # ASM/GSM watchlist stock -> blocked
    assert cro.check_exchange_surveillance_and_circuits("JUNK.NS", 0.02, is_asm_gsm_list=True) is False

    # Circuit limit hit (+19.8% on 20% band) -> blocked
    assert cro.check_exchange_surveillance_and_circuits("CIRCUIT.NS", 0.198, is_asm_gsm_list=False, daily_circuit_limit_pct=0.20) is False

    # Normal liquid stock (+2.5%) -> permitted
    assert cro.check_exchange_surveillance_and_circuits("RELIANCE.NS", 0.025, is_asm_gsm_list=False, daily_circuit_limit_pct=0.20) is True
