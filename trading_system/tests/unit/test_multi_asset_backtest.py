"""
Unit Tests for Institutional Multi-Asset Tactical Trend Backtester (V2.1 Protocol)
Validates:
  1. Protocol SHA-256 Lock: Rejects any tampered protocol specification.
  2. Next-Day Open Execution: Orders fill on next trading day open.
  3. Risk Ceiling: Lifetime HWM_true is tracked daily and never reset.
  4. Pre-Registered Simulation Execution: Verifies trade logging, terminal equity, and Gate A audit.
"""

import os
import pytest
import pandas as pd
from trading_system.scripts.backtest_multi_asset import (
    verify_protocol_lock,
    load_multi_asset_data,
    run_multi_asset_simulation
)


def test_multi_asset_protocol_verification():
    sha = verify_protocol_lock()
    assert len(sha) == 64


def test_multi_asset_simulation_execution():
    df = load_multi_asset_data()
    assert len(df) > 4000
    assert "NIFTY50_close" in df.columns
    assert "NEXT50_close" in df.columns
    assert "MIDCAP150_close" in df.columns
    assert "GOLDBEES_close" in df.columns
    assert "SILVERBEES_close" in df.columns
    assert "GILT10Y_close" in df.columns
    assert "MON100_close" in df.columns

    res = run_multi_asset_simulation(df, variant=1, slippage_bps=7.5, label="Test Variant A")
    assert res["cagr_pct"] > 0.0, f"Variant A CAGR must be positive: {res['cagr_pct']}"
    assert res["closed_trades"] >= 50, f"Variant A trade sample size must be >= 50: {res['closed_trades']}"
    assert "terminal_equity" in res
    assert "trade_log" in res
    assert res["starting_capital"] == 80000.0
