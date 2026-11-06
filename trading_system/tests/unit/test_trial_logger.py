"""
Unit tests for Institutional Trial Logger & Anti-Overfitting Defense
"""

import os
import pandas as pd
import pytest
from trading_system.app.validation.trial_logger import (
    log_trial,
    get_trial_count,
    get_trial_log_df,
    initialize_trial_log,
    CSV_COLUMNS,
)


def test_log_trial_records_script_and_universe(tmp_path):
    """Ensure log_trial records caller script and universe correctly."""
    log_file = tmp_path / "test_trial_log.csv"
    
    entry = log_trial(
        cagr_pct=14.5,
        max_drawdown_pct=-18.2,
        sharpe_ratio=0.85,
        kelly_fraction=0.40,
        lookback_days=90,
        is_holdout_opened=False,
        commit_hash="abc1234",
        script="backtest_nse50.py",
        universe="NSE_NIFTY50",
        notes="Test NSE trial",
        target_paths=[str(log_file)]
    )

    assert entry["script"] == "backtest_nse50.py"
    assert entry["universe"] == "NSE_NIFTY50"
    assert entry["cagr_pct"] == 14.5
    assert entry["max_drawdown_pct"] == -18.2

    df = pd.read_csv(log_file)
    assert len(df) == 1
    assert df.iloc[0]["script"] == "backtest_nse50.py"
    assert df.iloc[0]["universe"] == "NSE_NIFTY50"
    assert df.iloc[0]["notes"] == "Test NSE trial"
    assert get_trial_count(str(log_file)) == 1


def test_log_trial_backward_compatibility_with_legacy_headers(tmp_path):
    """Ensure log_trial can append to older CSVs without script/universe columns without crashing."""
    log_file = tmp_path / "legacy_trial_log.csv"
    legacy_columns = [
        "date", "commit_hash", "kelly_fraction", "lookback_days",
        "cagr_pct", "max_drawdown_pct", "sharpe_ratio", "is_holdout_opened", "notes"
    ]
    df_legacy = pd.DataFrame(columns=legacy_columns)
    df_legacy.to_csv(log_file, index=False)

    # Append a row using log_trial
    entry = log_trial(
        cagr_pct=11.2,
        max_drawdown_pct=-24.1,
        sharpe_ratio=0.65,
        commit_hash="leg1234",
        notes="Legacy append",
        target_paths=[str(log_file)]
    )

    df_read = pd.read_csv(log_file)
    assert len(df_read) == 1
    assert df_read.iloc[0]["cagr_pct"] == 11.2
    assert df_read.iloc[0]["notes"] == "Legacy append"
    assert get_trial_count(str(log_file)) == 1


def test_auto_detect_universe_fallback(tmp_path):
    """Ensure automatic detection of universe based on script name."""
    log_file = tmp_path / "autodetect_log.csv"
    
    entry_us = log_trial(
        cagr_pct=12.0,
        max_drawdown_pct=-22.0,
        sharpe_ratio=0.70,
        script="backtest_multi_pod.py",
        target_paths=[str(log_file)]
    )
    assert entry_us["universe"] == "US_SP500"

    entry_nse = log_trial(
        cagr_pct=15.0,
        max_drawdown_pct=-19.0,
        sharpe_ratio=0.80,
        script="backtest_nse50.py",
        target_paths=[str(log_file)]
    )
    assert entry_nse["universe"] == "NSE_NIFTY50"
