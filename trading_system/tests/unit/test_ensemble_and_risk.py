import pytest
import pandas as pd
import numpy as np
from datetime import datetime

from trading_system.app.strategies.ensembles.ensemble_allocator import EnsembleAllocator
from trading_system.app.risk.basic import BasicRiskEngine


def test_ensemble_regime_crash_warning_moves_to_100_percent_cash():
    """CRASH_WARNING regime must allocate 0% exposure (100% cash)."""
    allocator = EnsembleAllocator()
    
    # Create synthetic crash data: steep drop below 200 SMA and breaking 20 SMA
    prices = [500.0] * 240 + [400.0] * 5 + [350.0] * 5  # sharp drop below 200 SMA and 20 SMA
    dates = pd.date_range(start="2024-01-01", periods=len(prices), freq="B")
    spy_df = pd.DataFrame({
        "close": prices,
        "high": [p * 1.01 for p in prices],
        "low": [p * 0.99 for p in prices]
    }, index=dates)
    
    regime_info = allocator.detect_regime(spy_df)
    assert regime_info["regime"] == "CRASH_WARNING"
    assert regime_info["max_exposure"] == 0.0

    # Combining allocations in crash regime must return empty dict (100% cash)
    mom_signals = [{"symbol": "AAPL", "conviction_score": 2.5}]
    mr_signals = [{"symbol": "MSFT", "signal": 1, "confidence": 0.9}]
    targets = allocator.combine_allocations(mom_signals, mr_signals, regime_info)
    assert targets == {}


def test_ensemble_enforces_max_holdings_and_single_stock_cap():
    """Ensemble must cap holdings at 25 when max_holdings is explicitly specified."""
    allocator = EnsembleAllocator(max_total_exposure=0.95, max_single_stock=0.15, max_holdings=25)
    
    # 35 momentum candidates
    mom_signals = [
        {"symbol": f"TICK{i}", "conviction_score": 1.0 + (i * 0.1)}
        for i in range(35)
    ]
    
    regime_info = {
        "regime": "BULL_TRENDING",
        "max_exposure": 0.95,
        "weights": {"momentum": 0.70, "mean_reversion": 0.30}
    }
    
    targets = allocator.combine_allocations(mom_signals, [], regime_info)
    
    assert len(targets) <= 25
    for sym, w in targets.items():
        assert w <= 0.15 + 1e-4, f"{sym} weight {w} exceeded 15% cap"
    assert sum(targets.values()) <= 0.95 + 1e-4


def test_ensemble_dynamic_allocation_expands_and_contracts_organically():
    """Ensemble without fixed max_holdings dynamically sizes based on conviction."""
    allocator = EnsembleAllocator(max_total_exposure=0.95, max_single_stock=0.15, max_holdings=None, min_position_pct=0.015)
    
    # Case A: 30 qualifying candidates all meet min_position_pct hurdle
    mom_signals = [
        {"symbol": f"MOM{i}", "conviction_score": 2.0}
        for i in range(30)
    ]
    
    regime_info = {
        "regime": "BULL_TRENDING",
        "max_exposure": 0.95,
        "weights": {"momentum": 0.70, "mean_reversion": 0.30}
    }
    
    targets = allocator.combine_allocations(mom_signals, [], regime_info)
    # Dynamic expansion beyond 25
    assert len(targets) == 30
    for sym, w in targets.items():
        assert w >= 0.015
        assert w <= 0.15 + 1e-4
    assert sum(targets.values()) <= 0.95 + 1e-4

    # Case B: Only 3 qualifying candidates -> contracts organically with 15% single-stock ceiling
    few_signals = [
        {"symbol": f"MOM{i}", "conviction_score": 3.0}
        for i in range(3)
    ]
    targets_few = allocator.combine_allocations(few_signals, [], regime_info)
    assert len(targets_few) == 3
    for sym, w in targets_few.items():
        assert w <= 0.15 + 1e-4
    # 3 * 0.15 = 0.45 total equity exposure, remaining 55% in cash
    assert sum(targets_few.values()) <= 0.45 + 1e-4


def test_basic_risk_engine_blocks_shorting():
    """Risk engine must reject any trade resulting in a short position."""
    risk = BasicRiskEngine(max_position_pct=0.15, max_portfolio_pct=0.95)
    positions = {"AAPL": 10.0}
    
    # Attempting to sell 15 shares when holding 10
    illegal_short = {"symbol": "AAPL", "quantity": -15, "price_hint": 200.0}
    assert risk.evaluate_trade(illegal_short, positions, total_equity=100000.0) is False
    
    # Selling 10 shares (full liquidation) is allowed
    legal_sell = {"symbol": "AAPL", "quantity": -10, "price_hint": 200.0}
    assert risk.evaluate_trade(legal_sell, positions, total_equity=100000.0) is True


def test_basic_risk_engine_tracks_invested_exposure_and_single_stock_cap():
    """Risk engine must respect 15% single-stock and 95% total exposure ceilings."""
    risk = BasicRiskEngine(max_position_pct=0.15, max_portfolio_pct=0.95)
    positions = {"AAPL": 10.0}
    total_eq = 100000.0
    
    # Single stock breach: proposed $20,000 > $15,000 limit
    oversized_buy = {"symbol": "NVDA", "quantity": 20, "price_hint": 1000.0}
    assert risk.evaluate_trade(oversized_buy, positions, total_equity=total_eq, current_invested_value=50000.0) is False
    
    # Portfolio ceiling breach: proposed $10,000 on $90,000 invested = $100,000 > $95,000 ceiling
    portfolio_breach = {"symbol": "MSFT", "quantity": 25, "price_hint": 400.0}
    assert risk.evaluate_trade(portfolio_breach, positions, total_equity=total_eq, current_invested_value=90000.0) is False

    # Compliant trade: proposed $5,000 on $70,000 invested = $75,000 <= $95,000 ceiling
    compliant_buy = {"symbol": "MSFT", "quantity": 12, "price_hint": 400.0}
    assert risk.evaluate_trade(compliant_buy, positions, total_equity=total_eq, current_invested_value=70000.0) is True
