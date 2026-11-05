import pytest
import pandas as pd
import numpy as np

from trading_system.app.strategies.ensembles.mean_reversion import MeanReversionStrategy
from trading_system.app.strategies.ensembles.ensemble_allocator import EnsembleAllocator


def test_mean_reversion_dip_buy_signal():
    """
    Asserts MeanReversionStrategy triggers BUY when Price <= Lower BB and RSI < 35.0.
    """
    mr = MeanReversionStrategy(bb_window=20, bb_std=2.0, rsi_window=14, rsi_oversold=35.0)

    # 35 bars of normal prices, followed by oversold dip below Lower BB
    prices = [100.0] * 35 + [97.0, 94.0, 91.0, 89.0, 88.0]
    dates = pd.date_range("2024-01-01", periods=len(prices), freq="B")
    df = pd.DataFrame({"close": prices}, index=dates)

    sig = mr.generate_signal(df)
    assert sig["signal"] == 1
    assert sig["confidence"] >= 0.70
    assert "Mean-Reversion BUY" in sig["rationale"]
    assert sig["indicators"]["rsi"] < 35.0
    assert sig["indicators"]["current_price"] <= sig["indicators"]["bb_lower"] * 1.01


def test_mean_reversion_exit_signal_at_mean():
    """
    Asserts MeanReversionStrategy triggers EXIT (-1) when price reverts to middle band.
    """
    mr = MeanReversionStrategy(bb_window=20, bb_std=2.0, rsi_window=14, rsi_exit=55.0)

    # Prices drop, then recover strongly above the 20-period moving average
    prices = [100.0] * 30 + [85.0, 86.0, 92.0, 98.0, 102.0, 104.0]
    dates = pd.date_range("2024-01-01", periods=len(prices), freq="B")
    df = pd.DataFrame({"close": prices}, index=dates)

    sig = mr.generate_signal(df)
    assert sig["signal"] == -1
    assert "Mean-Reversion EXIT" in sig["rationale"]


def test_adaptive_waterfall_allocation():
    """
    Asserts Adaptive Waterfall Budgeting routes unspent budget between Momentum and Dips:
    - If only Momentum candidates qualify, 100% of available risk budget goes to Momentum.
    - If only Dips qualify, 100% goes to Dips.
    - Zero short positions are ever generated (Strictly Long-Only).
    """
    allocator = EnsembleAllocator(max_total_exposure=0.95, max_single_stock=0.15, max_holdings=10)
    regime_bull = {
        "max_exposure": 0.95,
        "weights": {"momentum": 0.70, "mean_reversion": 0.25}
    }

    mom_signals = [
        {"symbol": "RELIANCE.NS", "conviction_score": 1.8},
        {"symbol": "TCS.NS", "conviction_score": 1.5},
        {"symbol": "INFY.NS", "conviction_score": 1.2}
    ]
    dip_signals = [
        {"symbol": "HDFCBANK.NS", "signal": 1, "confidence": 0.85},
        {"symbol": "ICICIBANK.NS", "signal": 1, "confidence": 0.80}
    ]

    # Case 1: Both Momentum and Dips exist
    t_both = allocator.combine_allocations(mom_signals, dip_signals, regime_bull)
    assert len(t_both) == 5
    assert all(w > 0 for w in t_both.values())  # Strictly long-only
    assert sum(t_both.values()) <= 0.95 + 1e-4

    # Case 2: Zero Dips (runaway bull) -> waterfall routes full 0.95 budget to Momentum
    t_mom_only = allocator.combine_allocations(mom_signals, [], regime_bull)
    assert len(t_mom_only) == 3
    assert set(t_mom_only.keys()) == {"RELIANCE.NS", "TCS.NS", "INFY.NS"}
    # Eliminates cash drag: weights expand up to individual caps
    assert sum(t_mom_only.values()) > 0.40

    # Case 3: Zero Momentum (choppy market) -> waterfall routes budget to Dips
    t_dip_only = allocator.combine_allocations([], dip_signals, regime_bull)
    assert len(t_dip_only) == 2
    assert set(t_dip_only.keys()) == {"HDFCBANK.NS", "ICICIBANK.NS"}
    assert sum(t_dip_only.values()) > 0.25

    # Case 4: Zero signals anywhere -> 100% Cash
    t_none = allocator.combine_allocations([], [], regime_bull)
    assert t_none == {}
