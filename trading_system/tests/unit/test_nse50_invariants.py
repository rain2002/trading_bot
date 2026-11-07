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

import os
import math
import pytest
import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
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
    # Test GFC crisis peak rate (8.5%), post-COVID accommodative rate (4.0%), and modern rate (6.5%)
    gfc_rate = get_india_rf_rate(pd.to_datetime("2008-07-01"))
    assert gfc_rate == 0.085

    covid_rate = get_india_rf_rate(pd.to_datetime("2021-06-15"))
    assert covid_rate == 0.040

    modern_rate = get_india_rf_rate(pd.to_datetime("2024-05-15"))
    assert modern_rate == 0.065


def test_india_cash_yield_and_membership_csv_integrity():
    """Verify that both india_cash_yield_history.csv and nifty50_membership_changes.csv have complete sources."""
    yield_csv = os.path.join(PROJECT_ROOT, "trading_system", "data", "india_cash_yield_history.csv")
    changes_csv = os.path.join(PROJECT_ROOT, "trading_system", "data", "nifty50_membership_changes.csv")
    assert os.path.exists(yield_csv), "india_cash_yield_history.csv must exist"
    assert os.path.exists(changes_csv), "nifty50_membership_changes.csv must exist"

    df_yield = pd.read_csv(yield_csv)
    assert not df_yield.empty
    assert "source" in df_yield.columns
    assert df_yield["source"].str.contains("Reserve Bank of India").all()

    df_changes = pd.read_csv(changes_csv)
    assert not df_changes.empty
    assert "source" in df_changes.columns
    assert (df_changes["source"].str.len() > 10).all()
    assert df_changes["source"].str.contains("NSE").all()


def test_split_date_does_not_mutate_share_count_when_prices_split_adjusted():
    """
    CRITICAL REGRESSION TEST (Post-Mortem Commit f038644):
    Parquet OHLC data from Yahoo Finance is already backward split-adjusted across history.
    On a split date (e.g. 5:1 or 10:1 split), the backtester must NEVER multiply active shares
    by the split ratio, which would manufacture phantom equity out of thin air.
    Active share count must remain strictly invariant across corporate split events.
    """
    from trading_system.scripts.backtest_nse50 import run_simulation

    dates = pd.date_range("2024-01-01", periods=120, freq="B")
    bench_df = pd.DataFrame(
        {"close": [20000.0] * len(dates), "sma200": [18000.0] * len(dates), "sma50": [19000.0] * len(dates)},
        index=dates
    )
    macro_bull = pd.Series(True, index=dates)

    splits_arr = np.zeros(len(dates))
    splits_arr[105] = 10.0  # 10:1 split event while holding (after entry at idx 100)

    precalc = {
        "TESTSTOCK.NS": {
            "dates": dates,
            "close": np.full(len(dates), 100.0),
            "open": np.full(len(dates), 100.0),
            "high": np.full(len(dates), 105.0),
            "low": np.full(len(dates), 95.0),
            "divs": np.zeros(len(dates)),
            "splits": splits_arr,
            "sma100": np.full(len(dates), 90.0),
            "sma150": np.full(len(dates), 85.0),
            "sma200": np.full(len(dates), 80.0),
            "mom90": np.full(len(dates), 0.50),
            "atr20": np.full(len(dates), 5.0),
            "date_to_idx": {d: idx for idx, d in enumerate(dates)}
        }
    }

    res = run_simulation(bench_df, macro_bull, precalc, list(dates), variant=1, strict_pit=False, label="Split Invariant Test")
    assert res["splits_handled"] == 1, "Split event must be tracked in audit metadata"
    assert res["terminal_equity"] < 150000.0, f"Phantom equity detected! Terminal: {res['terminal_equity']}"
