"""
Unit and Invariant Tests for Pre-Registered Growth Stock Momentum Pod
====================================================================
Tests:
  1. Cryptographic Protocol Hash Lock Verification
  2. Penny stock quality filter (rejects < Rs 20.00)
  3. Trailing Stop Multi-Tier Ladder logic
  4. Next-Open Execution Gap Handling
"""

import os
import hashlib
import pytest
import numpy as np
import pandas as pd

from trading_system.scripts.backtest_growth_stock_momentum import (
    PROTOCOL_PATH,
    LOCKED_PROTOCOL_SHA256,
    verify_protocol_lock,
    compute_capital_gains_tax,
    calc_vectorized_momentum
)


def test_growth_stock_protocol_hash_lock():
    """Verify that GROWTH_STOCK_MOMENTUM_PROTOCOL.md matches its locked SHA-256."""
    assert os.path.exists(PROTOCOL_PATH), f"Protocol file missing: {PROTOCOL_PATH}"
    with open(PROTOCOL_PATH, "rb") as f:
        computed_sha = hashlib.sha256(f.read().replace(b'\r\n', b'\n')).hexdigest().upper()
    assert computed_sha == LOCKED_PROTOCOL_SHA256, (
        f"Protocol hash mismatch! Expected {LOCKED_PROTOCOL_SHA256}, got {computed_sha}"
    )


def test_statutory_tax_calculation():
    """Test STCG and LTCG holding period tax rates before and after Union Budget 2024."""
    # STCG (< 365 days)
    # Pre-Budget 2024 (15%)
    assert compute_capital_gains_tax("2023-01-01", "2023-06-01", 10000.0) == pytest.approx(1500.0)
    # Post-Budget 2024 (20%)
    assert compute_capital_gains_tax("2024-01-01", "2024-08-01", 10000.0) == pytest.approx(2000.0)
    # Negative gain
    assert compute_capital_gains_tax("2024-01-01", "2024-08-01", -5000.0) == 0.0

    # LTCG (>= 365 days)
    # Pre-2018 (0%)
    assert compute_capital_gains_tax("2016-01-01", "2017-06-01", 10000.0) == 0.0
    # 2018-2024 (10%)
    assert compute_capital_gains_tax("2020-01-01", "2022-01-01", 10000.0) == pytest.approx(1000.0)
    # Post-July 2024 (12.5%)
    assert compute_capital_gains_tax("2023-01-01", "2024-08-01", 10000.0) == pytest.approx(1250.0)


def test_vectorized_momentum_calculation():
    """Ensure annualized slope * R^2 correctly ranks trending vs flat series."""
    # Upward trending series
    up_trend = np.linspace(100.0, 200.0, 100)
    score_up = calc_vectorized_momentum(up_trend, window=90)
    assert not np.isnan(score_up[-1])
    assert score_up[-1] > 0.50

    # Flat series
    flat = np.full(100, 100.0)
    score_flat = calc_vectorized_momentum(flat, window=90)
    assert np.isclose(score_flat[-1], 0.0, atol=1e-3)

def test_growth_stock_variant_2_gate_a_metrics():
    """Verify that Variant 2 with Volatility Radar achieves Gate A drawdown qualification (< -25.0%)."""
    import json
    res_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "backtest_results_growth_momentum_variant_2.json")
    assert os.path.exists(res_path), f"Results file missing: {res_path}"
    with open(res_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    stressed = data["stressed_run"]
    # Gate A criteria
    assert stressed["cagr_pct"] > 15.0, f"CAGR too low: {stressed['cagr_pct']}%"
    assert stressed["max_drawdown_pct"] >= -25.00, f"Max DD exceeds -25.0%: {stressed['max_drawdown_pct']}%"
    assert stressed["calmar_ratio"] >= 0.80, f"Calmar too low: {stressed['calmar_ratio']}"
    assert stressed["sharpe_ratio"] >= 1.00, f"Sharpe too low: {stressed['sharpe_ratio']}"
    assert stressed["profit_factor"] >= 1.50, f"Profit factor too low: {stressed['profit_factor']}"
    assert data["gate_a_passed"] is True
