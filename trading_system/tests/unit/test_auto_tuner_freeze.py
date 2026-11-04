import os
import json
import hashlib
import numpy as np
import pandas as pd
import pytest

from trading_system.scripts.weekend_optimizer import (
    run_optimization,
    compute_file_hash,
    PROTECTED_CONFIG_FILES,
    CANONICAL_BASELINE
)


@pytest.fixture
def synthetic_ohlcv_data():
    """Generates 350 trading days of realistic geometric random walk with trend."""
    np.random.seed(42)
    dates = pd.date_range(start="2024-01-01", periods=350, freq="B")
    
    # 0.05% daily drift, 1% daily volatility
    returns = np.random.normal(0.0005, 0.01, size=len(dates))
    price_series = 100.0 * np.exp(np.cumsum(returns))
    
    df = pd.DataFrame({
        "open": price_series * (1 + np.random.normal(0, 0.002, len(dates))),
        "high": price_series * 1.01,
        "low": price_series * 0.99,
        "close": price_series,
        "volume": np.random.randint(1000000, 5000000, len(dates))
    }, index=dates)
    return df


def test_auto_tuner_freeze_and_diagnostic_generation(tmp_path, synthetic_ohlcv_data):
    """
    Asserts that:
    1. Production configurations remain bit-for-bit identical.
    2. Candidate parameters are staged into candidate_params.json with Gate requirements.
    3. WEEKEND_OPTIMIZER_REPORT.md is generated with walk-forward Sharpe, profit factor, and stability score.
    """
    # 1. Snapshot existing production config hashes
    pre_hashes = {}
    for path in PROTECTED_CONFIG_FILES:
        if os.path.isfile(path):
            pre_hashes[path] = compute_file_hash(path)

    # 2. Run optimization in isolated temporary workspace
    res = run_optimization(df_override=synthetic_ohlcv_data, output_dir=str(tmp_path))

    assert res["status"] == "SUCCESS"
    assert "best_candidate" in res
    assert "canonical_baseline" in res

    # 3. Assert live production configs are bit-for-bit identical
    for path, original_hash in pre_hashes.items():
        assert os.path.isfile(path), f"File was deleted: {path}"
        current_hash = compute_file_hash(path)
        assert current_hash == original_hash, (
            f"CRITICAL VIOLATION: Production config file was altered: {path}"
        )

    # 4. Assert candidate_params.json was written to staging
    candidate_file = os.path.join(str(tmp_path), "trading_system", "app", "config", "candidate_params.json")
    assert os.path.isfile(candidate_file), "candidate_params.json was not created"
    
    with open(candidate_file, "r", encoding="utf-8") as f:
        cand_data = json.load(f)

    assert cand_data["status"] == "CANDIDATE_STAGED"
    assert cand_data["requires_gate_validation"] is True
    assert cand_data["canonical_baseline"]["fast_sma"] == CANONICAL_BASELINE["fast_sma"]
    assert cand_data["canonical_baseline"]["slow_sma"] == CANONICAL_BASELINE["slow_sma"]
    assert "proposed_candidate" in cand_data
    assert "fast_sma" in cand_data["proposed_candidate"]
    assert "slow_sma" in cand_data["proposed_candidate"]
    assert "parameter_shifts" in cand_data

    # 5. Assert WEEKEND_OPTIMIZER_REPORT.md was generated with required sections
    report_file = os.path.join(str(tmp_path), "WEEKEND_OPTIMIZER_REPORT.md")
    assert os.path.isfile(report_file), "WEEKEND_OPTIMIZER_REPORT.md was not generated"

    with open(report_file, "r", encoding="utf-8") as f:
        report_text = f.read()

    assert "Quantitative Weekend Optimizer Diagnostic Audit Report" in report_text
    assert "Proposed Parameter Shifts" in report_text
    assert "Walk-Forward Performance & Robustness Metrics" in report_text
    assert "In-Sample Sharpe" in report_text
    assert "Out-of-Sample Sharpe" in report_text
    assert "Profit Factor" in report_text
    assert "Out-of-Sample Stability Score" in report_text
    assert "UNALTERED (LOCKED)" in report_text or "VERIFIED" in report_text


def test_auto_tuner_insufficient_data_safety(tmp_path):
    """Asserts that optimizer fails safely when data is insufficient without touching any files."""
    tiny_df = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
    res = run_optimization(df_override=tiny_df, output_dir=str(tmp_path))
    assert res["status"] == "FAILED"
    assert not os.path.exists(os.path.join(str(tmp_path), "WEEKEND_OPTIMIZER_REPORT.md"))
