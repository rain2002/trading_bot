import os
import pytest
from datetime import date, timedelta
from pathlib import Path

from trading_system.app.accounting.unitized_nav import UnitizedNAVEngine


@pytest.fixture
def nav_engine(tmp_path: Path):
    ledger_file = str(tmp_path / "test_unitized_nav_ledger.json")
    return UnitizedNAVEngine(ledger_path=ledger_file, initial_capital=100000.0)


def test_initial_unitized_nav_state(nav_engine):
    """Asserts fund initializes at $100.00 base NAV and 1,000 units for $100k capital."""
    metrics = nav_engine.get_fund_performance_metrics()
    assert metrics["nav_per_unit"] == 100.0
    assert metrics["base_nav_per_unit"] == 100.0
    assert metrics["total_units"] == 1000.0
    assert metrics["total_portfolio_value"] == 100000.0
    assert metrics["net_inflows"] == 100000.0
    assert metrics["true_trading_pnl_dollars"] == 0.0
    assert metrics["true_trading_return_pct"] == 0.0


def test_deposit_never_inflates_trading_returns(nav_engine):
    """
    CRITICAL FIDUCIARY INVARIANT:
    Depositing fresh SIP capital must NEVER inflate the fund's trading returns or trading PnL.
    """
    # 1. Trading gains: Portfolio grows from $100k to $110k (+10% true trading gain)
    nav_engine.update_portfolio_valuation(110000.0)
    m1 = nav_engine.get_fund_performance_metrics()
    assert m1["nav_per_unit"] == 110.0
    assert m1["true_trading_return_pct"] == 10.0
    assert m1["true_trading_pnl_dollars"] == 10000.0

    # 2. Boss deposits $50,000 fresh cash (SIP / bonus)
    tx = nav_engine.process_deposit(deposit_amount=50000.0, portfolio_value_before_deposit=110000.0)
    
    # 50,000 / 110 = 454.545455 new units issued
    assert pytest.approx(tx["units_issued"], 0.001) == 454.5455
    assert pytest.approx(tx["total_units_after"], 0.001) == 1454.5455
    assert tx["portfolio_value_after"] == 160000.0

    # 3. Assert NAV per unit and trading return are COMPLETELY UNCHANGED by the $50k deposit!
    m2 = nav_engine.get_fund_performance_metrics()
    assert m2["nav_per_unit"] == 110.0
    assert m2["true_trading_return_pct"] == 10.0
    assert m2["total_portfolio_value"] == 160000.0
    assert m2["cumulative_deposits"] == 150000.0
    assert m2["net_inflows"] == 150000.0
    # Trading PnL is still exactly $10,000, NOT $60,000!
    assert m2["true_trading_pnl_dollars"] == 10000.0


def test_withdrawal_redeems_units_without_altering_nav(nav_engine):
    """
    Asserts capital withdrawals redeem units proportionally without changing NAV per unit.
    """
    # Grow to $120k (+20% trading gain -> NAV = $120.00)
    nav_engine.update_portfolio_valuation(120000.0)
    assert nav_engine.get_fund_performance_metrics()["nav_per_unit"] == 120.0

    # Withdraw $24,000 -> 24,000 / 120 = 200 units redeemed
    tx = nav_engine.process_withdrawal(withdrawal_amount=24000.0, portfolio_value_before_withdrawal=120000.0)
    assert pytest.approx(tx["units_redeemed"], 0.001) == 200.0
    assert pytest.approx(tx["total_units_after"], 0.001) == 800.0
    assert tx["portfolio_value_after"] == 96000.0

    m = nav_engine.get_fund_performance_metrics()
    assert m["nav_per_unit"] == 120.0
    assert m["true_trading_return_pct"] == 20.0
    assert m["cumulative_withdrawals"] == 24000.0
    assert m["net_inflows"] == 76000.0  # 100k deposit - 24k withdrawal
    assert m["true_trading_pnl_dollars"] == 20000.0  # 96,000 - 76,000 = 20,000


def test_tactical_cash_reserve_and_dip_deployment(nav_engine):
    """
    Asserts SIP deposits build the Tactical Cash Reserve, and dip-buying deploys dry powder.
    """
    # Deposit $20,000 into tactical reserve
    nav_engine.process_deposit(deposit_amount=20000.0, portfolio_value_before_deposit=100000.0, allocate_to_tactical_reserve=True)
    assert nav_engine.state["tactical_cash_reserve"] == 20000.0

    # Deploy 50% on deep market dip (RSI < 35)
    deployed = nav_engine.deploy_opportunistic_dip_cash(deployment_pct=0.50, as_of_date=date(2026, 11, 4))
    assert deployed == 10000.0
    assert nav_engine.state["tactical_cash_reserve"] == 10000.0
    assert nav_engine.state["last_dip_date"] == "2026-11-04"


def test_30_day_tactical_drip_feeder(nav_engine):
    """
    Asserts that if the market enters a 30-day runaway bull market without pullbacks,
    the drip feeder allocates unspent tactical cash into momentum compounders.
    """
    nav_engine.process_deposit(deposit_amount=10000.0, portfolio_value_before_deposit=100000.0, allocate_to_tactical_reserve=True)
    assert nav_engine.state["tactical_cash_reserve"] == 10000.0
    
    nav_engine.state["last_dip_date"] = "2026-10-01"

    # Test 15 days later (2026-10-16): < 30 days -> no drip
    drip_15 = nav_engine.evaluate_30_day_drip_feeder(current_date=date(2026, 10, 16))
    assert drip_15 == 0.0
    assert nav_engine.state["tactical_cash_reserve"] == 10000.0

    # Test 35 days later (2026-11-05): >= 30 days -> drips 25% ($2,500)
    drip_35 = nav_engine.evaluate_30_day_drip_feeder(current_date=date(2026, 11, 5), drip_fraction=0.25)
    assert drip_35 == 2500.0
    assert nav_engine.state["tactical_cash_reserve"] == 7500.0
    assert nav_engine.state["last_dip_date"] == "2026-11-05"


def test_t2_accounting_random_lump_sums_and_sips(tmp_path: Path):
    """
    Phase 2 Protocol Test T2 (Accounting Verification):
    Random lump sums and SIP top-ups through unitized NAV, checked against an
    independent money-weighted calculation.
    Pass condition: Unit value matches within 0.01% on every date.
    """
    import numpy as np
    ledger_file = str(tmp_path / "t2_ledger.json")
    initial_cap = 80000.0
    engine = UnitizedNAVEngine(ledger_path=ledger_file, initial_capital=initial_cap)

    np.random.seed(42)
    n_days = 252
    daily_returns = np.random.normal(loc=0.0006, scale=0.012, size=n_days)

    current_val = initial_cap
    independent_unit_val = 100.0  # Base NAV per unit

    for day in range(n_days):
        ret = daily_returns[day]
        current_val *= (1.0 + ret)
        independent_unit_val *= (1.0 + ret)

        # Update engine valuation
        engine_nav = engine.update_portfolio_valuation(current_val)

        # Invariant check: unit value matches within 0.01% on every date
        pct_diff = abs(engine_nav - independent_unit_val) / independent_unit_val
        assert pct_diff < 0.0001, f"Day {day}: NAV mismatch! Engine: {engine_nav}, Independent: {independent_unit_val}, Diff: {pct_diff:.6f}"

        # Periodic SIP every 20 days (approx monthly)
        if (day + 1) % 20 == 0:
            sip_amount = float(np.random.uniform(5000.0, 15000.0))
            engine.process_deposit(deposit_amount=sip_amount, portfolio_value_before_deposit=current_val)
            current_val += sip_amount
            assert abs(engine.state["nav_per_unit"] - independent_unit_val) / independent_unit_val < 0.0001

        # Random lump sum deposits
        if np.random.random() < 0.02:
            lump_sum = float(np.random.uniform(20000.0, 50000.0))
            engine.process_deposit(deposit_amount=lump_sum, portfolio_value_before_deposit=current_val)
            current_val += lump_sum
            assert abs(engine.state["nav_per_unit"] - independent_unit_val) / independent_unit_val < 0.0001

