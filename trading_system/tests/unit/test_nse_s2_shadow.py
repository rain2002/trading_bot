"""
Unit Tests for NSE Whole-Market Candidate S2 Shadow Runner
"""

import json
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd

from trading_system.scripts.run_nse_s2_shadow import (
    NSES2ShadowRunner,
    load_nse_s2_equity_universe,
)
from trading_system.app.data.corporate_actions import is_etf_ticker


def test_load_nse_s2_universe_excludes_all_etfs():
    tickers = load_nse_s2_equity_universe()
    assert len(tickers) >= 450
    for sym in tickers:
        assert sym.endswith(".NS")
        assert not is_etf_ticker(sym), f"ETF slipped into S2 stock universe: {sym}"


def test_nse_s2_shadow_cycle_bull_fill_and_discord(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ENABLE_NOTIFICATIONS", "1")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.mock/webhook")

    runner = NSES2ShadowRunner(
        state_file=str(tmp_path / "s2_state.json"),
        trades_file=str(tmp_path / "s2_trades.csv"),
        equity_log_file=str(tmp_path / "s2_eq.csv"),
        initial_capital=80000.0,
    )

    dates = pd.date_range("2025-01-01", periods=280, freq="B")
    bench_df = pd.DataFrame({"close": np.linspace(21000, 26000, 280)}, index=dates)
    stock_prices = np.linspace(200.0, 420.0, 280)
    stock_df = pd.DataFrame(
        {
            "open": stock_prices,
            "close": stock_prices,
            "volume": np.full(280, 500_000.0),  # ~10-21 Cr daily turnover (> 2 Cr threshold)
        },
        index=dates,
    )
    # Include an ETF in universe_data to prove defense-in-depth exclusion
    universe_data = {"TRENT.NS": stock_df, "GOLDBEES.NS": stock_df}

    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 204
        res1 = runner.run_daily_cycle(universe_data=universe_data, bench_df=bench_df)

    assert res1["status"] == "SCANNED_HOLD"
    assert len(runner.state["pending_buys"]) == 1
    assert runner.state["pending_buys"][0]["sym"] == "TRENT.NS"
    assert "GOLDBEES.NS" not in [b["sym"] for b in runner.state["pending_buys"]]
    assert mock_post.call_count == 1

    # Duplicate same-session call must be idempotent
    res_dup = runner.run_daily_cycle(universe_data=universe_data, bench_df=bench_df)
    assert res_dup["status"] == "ALREADY_PROCESSED"

    # Next session advances 1 day -> executes queued TRENT.NS buy at open and logs trade to Discord
    dates2 = pd.date_range("2025-01-02", periods=280, freq="B")
    bench2 = pd.DataFrame({"close": np.linspace(21020, 26040, 280)}, index=dates2)
    sp2 = np.linspace(201.0, 422.0, 280)
    stock2 = pd.DataFrame({"open": sp2, "close": sp2, "volume": np.full(280, 500_000.0)}, index=dates2)

    runner2 = NSES2ShadowRunner(
        state_file=str(tmp_path / "s2_state.json"),
        trades_file=str(tmp_path / "s2_trades.csv"),
        equity_log_file=str(tmp_path / "s2_eq.csv"),
        initial_capital=80000.0,
    )
    with patch("requests.post") as mock_post2:
        mock_post2.return_value.status_code = 204
        res2 = runner2.run_daily_cycle(universe_data={"TRENT.NS": stock2}, bench_df=bench2)

    assert res2["status"] == "EXECUTED_AND_SCANNED"
    assert res2["trades"] == 1
    assert "TRENT.NS" in runner2.state["positions"]
    embed = mock_post2.call_args[1]["json"]["embeds"][0]
    assert "BUY" in embed["description"]
    assert "TRENT.NS" in embed["description"]
