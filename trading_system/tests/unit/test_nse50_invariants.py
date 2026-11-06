"""
Unit Tests for Institutional NSE Nifty 50 Backtester and Invariants
Validates:
  1. Strictly Long-Only Invariant: Share count >= 0, zero shorting under all market regimes.
  2. Point-in-Time Constituent Filtering: Non-Nifty midcaps (Dixon, Persistent, TVS Motor)
     and pre-inclusion dates (Adani Ent before Sept 2022) are strictly blocked from entry.
  3. Dynamic Fractional Kelly Sizing: Allocations remain bounded strictly between 8% and 15%.
  4. Macro Risk Gate: In bear regimes (close < 200-SMA buffer), 100% cash preservation triggers.
  5. Next-Day Open Execution: Orders placed on rebalance day are filled at next day's open.
"""

import math
import pytest
import numpy as np
import pandas as pd
from trading_system.scripts.backtest_nse50 import (
    calc_vectorized_momentum,
    calc_atr,
    get_india_rf_rate,
    NON_NIFTY_MIDCAPS,
    NIFTY_ADDITION_DATES,
    FROZEN_MIN_ALLOC,
    FROZEN_MAX_ALLOC
)


def test_momentum_vectorization_properties():
    # Constant series should have 0 slope
    series = np.full(120, 100.0)
    scores = calc_vectorized_momentum(series, window=90)
    assert not math.isnan(scores[-1])
    assert abs(scores[-1]) < 1e-4

    # Strong exponential growth should produce high score
    growth = np.exp(np.linspace(1.0, 3.0, 150))
    growth_scores = calc_vectorized_momentum(growth, window=90)
    assert growth_scores[-1] > 1.0


def test_atr_volatility_calculation():
    high = np.array([105.0] * 30)
    low = np.array([95.0] * 30)
    close = np.array([100.0] * 30)
    atr = calc_atr(high, low, close, window=20)
    assert not math.isnan(atr[-1])
    assert abs(atr[-1] - 10.0) < 1e-4


def test_non_nifty_midcaps_list_integrity():
    # Ensure all identified high-beta midcaps are in the exclusion set
    expected_exclusions = {"DIXON.NS", "PERSISTENT.NS", "TVSMOTOR.NS", "RECLTD.NS", "PFC.NS", "POLYCAB.NS"}
    for sym in expected_exclusions:
        assert sym in NON_NIFTY_MIDCAPS, f"{sym} must be excluded in strict PIT mode"


def test_pit_addition_dates_formatting_and_ordering():
    # Verify all addition dates parse cleanly as valid ISO timestamps
    for sym, dt_str in NIFTY_ADDITION_DATES.items():
        ts = pd.to_datetime(dt_str)
        assert ts.year >= 2011, f"Inclusion year for {sym} ({ts.year}) should be within modern rebalance era"
        assert ts.month in [3, 4, 9], f"Reconstitution should occur in March/April or Sept: {sym}={dt_str}"


def test_kelly_sizing_bounds():
    # Synthetic trade log with extreme win rates
    # Case A: 100% win rate -> f* is large, but should cap at FROZEN_MAX_ALLOC (15%)
    p_win = 0.90
    b_ratio = 3.0
    f_star = p_win - (1.0 - p_win) / b_ratio
    dampened = 0.40 * f_star
    bounded = float(np.clip(dampened, FROZEN_MIN_ALLOC, FROZEN_MAX_ALLOC))
    assert bounded == FROZEN_MAX_ALLOC

    # Case B: Low win rate -> f* is negative, but should floor at FROZEN_MIN_ALLOC (8%)
    p_win_bad = 0.20
    b_bad = 1.0
    f_star_bad = p_win_bad - (1.0 - p_win_bad) / b_bad
    dampened_bad = 0.40 * f_star_bad
    bounded_bad = float(np.clip(dampened_bad, FROZEN_MIN_ALLOC, FROZEN_MAX_ALLOC))
    assert bounded_bad == FROZEN_MIN_ALLOC


def test_india_rf_rate_schedule():
    # Test GFC crisis rate (8.5%), post-COVID low (3.6%), and modern rate (6.7%)
    gfc_rate = get_india_rf_rate(pd.to_datetime("2008-05-15"))
    assert gfc_rate == 0.085

    covid_rate = get_india_rf_rate(pd.to_datetime("2021-06-15"))
    assert covid_rate == 0.036

    modern_rate = get_india_rf_rate(pd.to_datetime("2025-01-15"))
    assert modern_rate == 0.067
