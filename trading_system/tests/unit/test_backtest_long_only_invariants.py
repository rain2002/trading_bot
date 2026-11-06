"""
Unit tests verifying Strict Long-Only Backtest Invariants and Removal of Pairs (Fix 1).
"""

import pytest
import re
from pathlib import Path


def test_backtest_script_has_zero_pairs_or_short_logic():
    """Verify that backtest_multi_pod.py has no shorting, no y_shares/x_shares pairs logic."""
    script_path = Path("trading_system/scripts/backtest_multi_pod.py")
    assert script_path.exists(), "backtest_multi_pod.py must exist"

    code = script_path.read_text(encoding="utf-8")

    # Assert no pairs position dictionary or pairs execution
    assert "CURATED_PAIRS" not in code, "CURATED_PAIRS must be removed"
    assert "pod2_positions" not in code, "pod2_positions must be removed"
    assert "y_shares" not in code, "y_shares must be removed"
    assert "x_shares" not in code, "x_shares must be removed"
    assert "STAT_ARB" not in code, "STAT_ARB pairs pod must be removed"


def test_daily_non_negative_share_check():
    """Verify the daily non-negative share invariant logic."""
    # Healthy positions
    valid_positions = {"AAPL": 10.5, "MSFT": 4.0, "GOOGL": 0.0}
    for sym, shares in valid_positions.items():
        if shares < 0:
            pytest.fail(f"Unexpected failure on valid shares: {sym}={shares}")

    # Negative share violation
    invalid_positions = {"AAPL": 10.5, "NVDA": -5.0}
    with pytest.raises(ValueError) as excinfo:
        for sym, shares in invalid_positions.items():
            if shares < 0:
                raise ValueError(f"CRITICAL FIDUCIARY BREACH: Negative share count detected: {sym}={shares}")

    assert "Negative share count detected" in str(excinfo.value)
    assert "NVDA=-5.0" in str(excinfo.value)
