import os
import json
import pytest
import pandas as pd
from trading_system.app.broker.multi_bot_adapter import MultiBotBrokerAdapter


@pytest.fixture
def mock_data_dir(tmp_path):
    """Creates isolated mock state files in a temporary directory for hermetic unit testing."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # 1. manager_state.json
    manager_state = {
        "manager_name": "CENTRAL_PORTFOLIO_MANAGER",
        "combined_fund_nav": 99215.91,
        "unitized_nav": 99.0147,
        "hwm_unit_nav": 100.0,
        "max_drawdown": -0.015,
        "current_drawdown": -0.0099,
        "throttle_level": 0,
        "last_reconciliation_gap_pct": 0.0,
        "last_update": "2026-11-19T19:09:41.733508+00:00",
    }
    with open(data_dir / "manager_state.json", "w", encoding="utf-8") as f:
        json.dump(manager_state, f)

    # 2. etf_gold_state.json
    etf_state = {
        "bot_name": "ETF_AND_GOLD_BOT",
        "cash": 366.31,
        "days_incubated": 4,
        "positions": {
            "GOLDBEES.NS": {"shares": 178, "entry_price": 111.91, "last_price": 106.30, "entry_date": "2026-11-15"},
            "MON100.NS": {"shares": 66, "entry_price": 302.35, "last_price": 303.30, "entry_date": "2026-11-15"},
            "NIFTYBEES.NS": {"shares": 41, "entry_price": 286.64, "last_price": 290.61, "entry_date": "2026-11-15"},
            "MID150BEES.NS": {"shares": 51, "entry_price": 234.72, "last_price": 234.75, "entry_date": "2026-11-15"},
            "LTGILTBEES.NS": {"shares": 541, "entry_price": 29.54, "last_price": 29.61, "entry_date": "2026-11-15"},
        },
    }
    with open(data_dir / "etf_gold_state.json", "w", encoding="utf-8") as f:
        json.dump(etf_state, f)

    # 3. bond_cash_state.json
    bond_state = {
        "bot_name": "BOND_AND_CASH_BOT",
        "cash": 4.33,
        "positions": {
            "LIQUIDBEES.NS": {"shares": 20, "entry_price": 1000.0, "last_price": 999.99, "entry_date": "2026-11-15"}
        },
    }
    with open(data_dir / "bond_cash_state.json", "w", encoding="utf-8") as f:
        json.dump(bond_state, f)

    # 4. manager_equity_log.csv
    equity_df = pd.DataFrame([
        {"session_date": "2026-11-13", "combined_fund_nav": 79945.49, "nav_per_unit": 99.9319},
        {"session_date": "2026-11-16", "combined_fund_nav": 99535.34, "nav_per_unit": 99.4298},
        {"session_date": "2026-11-17", "combined_fund_nav": 99551.33, "nav_per_unit": 99.4442},
        {"session_date": "2026-11-18", "combined_fund_nav": 98804.20, "nav_per_unit": 98.5046},
        {"session_date": "2026-11-19", "combined_fund_nav": 99215.91, "nav_per_unit": 99.0147},
    ])
    equity_df.to_csv(data_dir / "manager_equity_log.csv", index=False)

    # 5. etf_gold_trades.csv
    etf_trades = pd.DataFrame([
        {"timestamp": "2026-11-15 05:46:43", "bot": "ETF_AND_GOLD", "symbol": "GOLDBEES.NS", "side": "BUY", "shares": 178, "price": 111.91, "trade_value": 19919.98, "fees_paid": 13.65},
        {"timestamp": "2026-11-15 05:46:43", "bot": "ETF_AND_GOLD", "symbol": "MON100.NS", "side": "BUY", "shares": 66, "price": 302.35, "trade_value": 19955.10, "fees_paid": 13.67},
    ])
    etf_trades.to_csv(data_dir / "etf_gold_trades.csv", index=False)

    # 6. bond_cash_trades.csv
    bond_trades = pd.DataFrame([
        {"timestamp": "2026-11-15 01:44:14", "bot": "BOND_AND_CASH", "symbol": "LIQUIDBEES.NS", "side": "BUY", "shares": 20, "price": 1000.0, "trade_value": 20000.0, "fees_paid": 13.01},
        {"timestamp": "2026-11-19 19:09:40", "bot": "BOND_AND_CASH", "symbol": "LIQUIDBEES.NS", "side": "DIVIDEND_CARRY", "shares": 0, "price": 999.99, "trade_value": 0.0, "fees_paid": 0.0},
    ])
    bond_trades.to_csv(data_dir / "bond_cash_trades.csv", index=False)

    return str(data_dir)


def test_multi_bot_adapter_initialization(mock_data_dir):
    adapter = MultiBotBrokerAdapter(data_dir=mock_data_dir)
    assert adapter.initial_capital == 100000.0
    assert adapter.is_connected() is True
    assert adapter.is_mock is True


def test_multi_bot_adapter_account_details(mock_data_dir):
    adapter = MultiBotBrokerAdapter(data_dir=mock_data_dir)
    details = adapter.get_account_details()

    assert details["currency"] == "INR"
    assert details["currency_symbol"] == "₹"
    assert details["equity"] == 99215.91
    assert details["cash"] == pytest.approx(370.64, 0.01)
    assert details["unitized_nav"] == 99.0147
    assert details["throttle_level"] == 0
    assert details["reconciliation_gap_pct"] == 0.0
    assert details["days_incubated"] == 4
    assert details["today_pnl"] == pytest.approx(411.71, 0.01)


def test_multi_bot_adapter_positions_detailed(mock_data_dir):
    adapter = MultiBotBrokerAdapter(data_dir=mock_data_dir)
    positions = adapter.get_positions_detailed()

    assert len(positions) == 6
    symbols = [p["symbol"] for p in positions]
    assert "GOLDBEES.NS" in symbols
    assert "LIQUIDBEES.NS" in symbols
    for p in positions:
        assert p["qty"] > 0
        assert p["market_value"] > 0
        assert p["sleeve"] in ("MULTI_ASSET_ETF_GOLD", "BOND_AND_CASH_CARRY")


def test_multi_bot_adapter_portfolio_history(mock_data_dir):
    adapter = MultiBotBrokerAdapter(data_dir=mock_data_dir)
    df_hist = adapter.get_portfolio_history()

    assert df_hist is not None
    assert len(df_hist) == 5
    assert "timestamp" in df_hist.columns
    assert "equity" in df_hist.columns
    assert "profit_loss" in df_hist.columns
    # Check normalized unitized equity
    assert df_hist["equity"].iloc[-1] == pytest.approx(99014.7, 0.1)


def test_multi_bot_adapter_recent_orders(mock_data_dir):
    adapter = MultiBotBrokerAdapter(data_dir=mock_data_dir)
    orders = adapter.get_recent_orders(limit=20)

    assert len(orders) == 4
    first = orders[0]
    assert "id" in first
    assert "client_order_id" in first
    assert first["client_order_id"].startswith("Q-GATEB-")
    assert first["status"] == "FILLED"


def test_multi_bot_adapter_empty_directory_graceful_fallback(tmp_path):
    """Hermetic test verifying fail-safe behavior when state files are missing on a fresh checkout."""
    empty_dir = tmp_path / "empty_data"
    empty_dir.mkdir()

    adapter = MultiBotBrokerAdapter(data_dir=str(empty_dir))
    assert adapter.is_connected() is True

    details = adapter.get_account_details()
    assert details["equity"] == 99215.91
    assert details["cash"] == pytest.approx(370.64, 0.01)

    positions = adapter.get_positions_detailed()
    assert positions == []

    history = adapter.get_portfolio_history()
    assert history is None

    orders = adapter.get_recent_orders()
    assert orders == []

    open_orders = adapter.get_open_orders()
    assert open_orders == []
