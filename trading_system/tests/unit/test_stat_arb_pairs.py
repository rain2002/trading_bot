import pytest
import numpy as np
import pandas as pd
from trading_system.app.strategies.library.stat_arb_pairs import StatArbPairsStrategy


def test_stat_arb_detects_cointegration_on_synthetic_stationary_spread():
    """Engle-Granger test must identify cointegration on synthetic cointegrated series."""
    np.random.seed(42)
    n = 250
    # X is a random walk
    x = 100.0 + np.cumsum(np.random.normal(0, 1, n))
    # Y is cointegrated with X: Y = 2.0 * X + stationary noise
    noise = np.random.normal(0, 0.5, n)
    y = 2.0 * x + noise

    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    x_series = pd.Series(x, index=dates)
    y_series = pd.Series(y, index=dates)

    strat = StatArbPairsStrategy()
    res = strat.test_cointegration(y_series, x_series)

    assert res["is_cointegrated"] is True
    assert res["p_value"] < 0.05
    # Hedge ratio on log prices should be positive and non-zero
    assert res["hedge_ratio"] > 0


def test_stat_arb_rejects_independent_random_walks():
    """Independent random walks should not be cointegrated."""
    np.random.seed(123)
    n = 250
    x = 100.0 + np.cumsum(np.random.normal(0, 1, n))
    y = 100.0 + np.cumsum(np.random.normal(0, 1, n))

    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    x_series = pd.Series(x, index=dates)
    y_series = pd.Series(y, index=dates)

    strat = StatArbPairsStrategy()
    res = strat.test_cointegration(y_series, x_series)

    assert res["is_cointegrated"] is False
    assert res["p_value"] >= 0.05


def test_half_life_calculation():
    """Ornstein-Uhlenbeck half-life should compute a positive finite number for mean-reverting series."""
    np.random.seed(42)
    # Mean-reverting AR(1) series: S_t = 0.8 * S_{t-1} + e_t
    n = 200
    spread = np.zeros(n)
    for t in range(1, n):
        spread[t] = 0.75 * spread[t - 1] + np.random.normal(0, 1)

    spread_series = pd.Series(spread)
    half_life = StatArbPairsStrategy.calculate_half_life(spread_series)

    assert 0.5 < half_life < 10.0


def test_signal_generation_on_oversold_and_stop_loss():
    """Z-score <= -2.0 triggers Long Spread; |Z| >= 3.5 triggers Stop-Loss."""
    strat = StatArbPairsStrategy(lookback_window=40, z_entry=2.0, z_stop=3.5)
    
    n = 60
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    x = pd.Series([100.0] * n, index=dates)
    
    # Case 1: Drop from 100 to 85 causes Z < -2.0 (Oversold entry)
    y_vals = [100.0] * 58 + [85.0] * 2
    y = pd.Series(y_vals, index=dates)
    df_spread = strat.calculate_rolling_spread_and_zscore(y, x, hedge_ratio=1.0)
    latest_z = df_spread["z_score"].iloc[-1]
    assert latest_z < -2.0

    # Case 2: Catastrophic 1-day gap causes extreme Z <= -3.5 (Structural breakdown stop-loss)
    y_vals_crash = [100.0] * 59 + [60.0] * 1
    y_crash = pd.Series(y_vals_crash, index=dates)
    df_crash = strat.calculate_rolling_spread_and_zscore(y_crash, x, hedge_ratio=1.0)
    crash_z = df_crash["z_score"].iloc[-1]
    assert crash_z <= -3.5
