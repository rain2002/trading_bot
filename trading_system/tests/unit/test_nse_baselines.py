"""
Unit tests for NSE Nifty 50 Baselines and Diagnostic Telemetry
"""

import os
import pytest
import pandas as pd
import numpy as np
from pathlib import Path

from trading_system.scripts.backtest_nse50 import (
    load_market_data,
    compute_baselines,
    get_india_rf_rate,
    START_DATE,
    DEFAULT_END_DATE
)


def test_nifty_benchmark_has_zero_synthesized_data():
    """Verify that the Nifty benchmark loaded has zero synthetic Sensex stitching."""
    bench_df, _, _, timeline = load_market_data(start_date=START_DATE, end_date=DEFAULT_END_DATE)
    
    assert len(bench_df) > 4000, f"Expected >4000 trading sessions, got {len(bench_df)}"
    assert bench_df.index[0].strftime("%Y-%m-%d") >= "2007-09-17"
    assert "close" in bench_df.columns
    assert "tri_close" in bench_df.columns
    assert not bench_df["close"].isna().any(), "Price index has NaNs"
    assert not bench_df["tri_close"].isna().any(), "TRI index has NaNs"
    assert (bench_df["tri_close"] >= bench_df["close"]).all(), "TRI must be >= Price index due to dividends"


def test_compute_baselines_integrity():
    """Verify that the 3 fiduciary baselines compute valid financial metrics."""
    bench_df, _, precalc, timeline = load_market_data(start_date=START_DATE, end_date=DEFAULT_END_DATE)
    baselines = compute_baselines(bench_df, precalc, timeline)

    # 1. Baseline 1: Buy-and-Hold Nifty 50 TRI
    assert "baseline_1_tri" in baselines
    b1 = baselines["baseline_1_tri"]
    assert b1["cagr_pct"] > 8.0, "Nifty 50 TRI CAGR must be reasonable"
    assert b1["terminal_equity"] > 1000.0, "Terminal equity must exceed starting capital"
    assert -70.0 < b1["max_drawdown_pct"] < -40.0, "Max drawdown in GFC 2008 expected between -40% and -70%"

    # 2. Baseline 2: Equal-Weight Top Equities
    assert "baseline_2_equal_weight" in baselines
    b2 = baselines["baseline_2_equal_weight"]
    assert b2["cagr_pct"] > 10.0
    assert b2["terminal_equity"] > b1["terminal_equity"], "Equal-weight top Indian equities historically beats cap-weighted index"

    # 3. Baseline 3: 200-SMA Trend vs Cash
    assert "baseline_3_trend_cash" in baselines
    b3 = baselines["baseline_3_trend_cash"]
    assert b3["max_drawdown_pct"] > b1["max_drawdown_pct"], "Trend-following on index must contain drawdown compared to buy-and-hold"
    assert b3["max_drawdown_pct"] > -30.0, "200-SMA with cash filter must contain drawdown to < -30%"
    assert 15.0 < b3["days_in_cash_pct"] < 45.0, "Trend filter expected to spend 15-45% of days in cash"


def test_india_rf_rate_causal_lookup():
    """Verify RBI repo / T-bill rate schedule lookup across key monetary cycles."""
    rate_2008 = get_india_rf_rate(pd.Timestamp("2008-07-01"))
    assert rate_2008 == 0.085, "Expected 8.5% during 2008 GFC peak"

    rate_2021 = get_india_rf_rate(pd.Timestamp("2021-06-01"))
    assert rate_2021 == 0.036, "Expected ~3.6% during post-COVID accommodative stance"

    rate_2024 = get_india_rf_rate(pd.Timestamp("2024-05-01"))
    assert rate_2024 >= 0.065, "Expected >=6.5% during 2024 monetary tightening"
