"""
Unit tests validating all institutional fixes from the external code audit:
1. Inverted Exit logic fixed: clean uptrend momentum runners are NEVER dumped as mean-reversion targets.
2. Dip-buy positions exit when reversion target reached.
3. Pre-entry peak prices are ignored: breakeven stop strictly evaluates highs on/after entry.
4. Fail-closed broker adapter: raises BrokerAPIError on network/API drops instead of inventing $100k or [].
5. Benchmark data outage triggers DATA_OUTAGE_HALT with 0.0 max exposure.
6. Resting GTC stop loss preservation: cancel_pending_buy_orders only cancels BUY orders.
7. PositionTracker maintains attribution (MOMENTUM vs DIP_BUY) and true peak since entry.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from trading_system.app.research.quant_engine import InvestorSkillsHeuristics
from trading_system.app.strategies.core_signals import evaluate_holding_exit, generate_candidate_signals
from trading_system.app.broker.alpaca import AlpacaBrokerAdapter, BrokerAPIError
from trading_system.app.features.regime import UniversalLocalIndexRegimeEngine
from trading_system.app.portfolio.position_tracker import PositionTracker
from trading_system.app.risk.basic import BasicRiskEngine


def test_inverted_exit_fix_momentum_runners_not_exited_on_reversion():
    """
    Critical Fix Verification:
    In the bug, 100% of clean-uptrend stocks (Price > 20 SMA, RSI > 55) returned signal=-1
    from MeanReversionStrategy and were liquidated as TARGET_PROFIT_EXIT.
    Now, MOMENTUM positions must be preserved to compound as runners!
    """
    # Create clean uptrending stock dataframe
    dates = pd.date_range(end=datetime.now(), periods=100, freq="B")
    prices = [100.0 + (i * 0.5) for i in range(100)] # steady uptrend from $100 to $150
    df = pd.DataFrame({
        "close": prices,
        "high": [p * 1.01 for p in prices],
        "low": [p * 0.99 for p in prices],
        "adj_close": prices
    }, index=dates)

    # Position bought at $120, current price is $150 (+25% gain), trend completely intact
    current_plpc = (150.0 - 120.0) / 120.0
    exit_eval = InvestorSkillsHeuristics.evaluate_holding_exit(
        symbol="NVDA",
        df=df,
        current_plpc=current_plpc,
        regime="BULL_TRENDING",
        holding_type="MOMENTUM",
        avg_entry=120.0,
        entry_date=dates[40].strftime("%Y-%m-%d")
    )

    # Must NOT exit! Must hold runner!
    assert exit_eval["should_exit"] is False, f"Momentum runner was incorrectly dumped: {exit_eval}"
    assert exit_eval["action"] == "HOLD"


def test_dip_buy_reversion_exit_when_target_reached():
    """
    DIP_BUY positions should exit when price reverts to middle band / 20-SMA with positive profit.
    """
    dates = pd.date_range(end=datetime.now(), periods=60, freq="B")
    prices = [100.0] * 50 + [90.0, 91.0, 93.0, 96.0, 102.0, 104.0, 105.0, 106.0, 107.0, 108.0]
    df = pd.DataFrame({
        "close": prices,
        "high": [p * 1.01 for p in prices],
        "low": [p * 0.99 for p in prices],
        "adj_close": prices
    }, index=dates)

    current_price = prices[-1] # 108.0
    avg_entry = 95.0 # bought on dip at $95
    current_plpc = (current_price - avg_entry) / avg_entry # +13.7%

    exit_eval = InvestorSkillsHeuristics.evaluate_holding_exit(
        symbol="AAPL",
        df=df,
        current_plpc=current_plpc,
        regime="BULL_TRENDING",
        holding_type="DIP_BUY",
        avg_entry=avg_entry,
        entry_date=dates[52].strftime("%Y-%m-%d")
    )

    assert exit_eval["should_exit"] is True
    assert exit_eval["action"] == "TARGET_PROFIT_EXIT"


def test_peak_price_ignores_pre_entry_highs():
    """
    Bug: Taking 60-day high before entry caused a dip bought at $80 (when stock was $100 40 days ago)
    to compute gain_from_cost = (100 - 80) / 80 = 25%, immediately triggering Breakeven Ratchet
    the very next day! Also, dip buys must not hit 50-SMA breakdown exits.
    Fix:
    1. Dip buys (holding_type="DIP_BUY") do not use 50-SMA exits and do not fire pre-entry breakeven stops.
    2. Momentum holdings evaluate peak strictly since entry date.
    """
    dates = pd.date_range(end=datetime.now(), periods=60, freq="B")
    # Stock fell from $120 down to $80, and bot bought it as a dip at $80 on date index 50
    # Between index 50 and 59, price stayed between $80 and $81 (below mean reversion target, below 50-SMA)
    prices = [120.0 - (i * 0.8) for i in range(50)] + [80.0 + (i * 0.1) for i in range(10)]
    df = pd.DataFrame({
        "close": prices,
        "high": [p * 1.005 for p in prices],
        "low": [p * 0.995 for p in prices],
        "adj_close": prices
    }, index=dates)

    entry_date = dates[50].strftime("%Y-%m-%d")
    current_price = prices[-1] # 80.9
    avg_entry = 80.0
    current_plpc = (current_price - avg_entry) / avg_entry # +1.1%

    # Case A: DIP_BUY holding is not dumped by 50-SMA breakdown or pre-entry high
    exit_eval = InvestorSkillsHeuristics.evaluate_holding_exit(
        symbol="CAT",
        df=df,
        current_plpc=current_plpc,
        regime="BULL_TRENDING",
        holding_type="DIP_BUY",
        avg_entry=avg_entry,
        entry_date=entry_date
    )
    assert exit_eval["should_exit"] is False, f"Dip buy incorrectly dumped: {exit_eval}"

    # Case B: Momentum holding above 50-SMA that peaked at $120 prior to entry
    # Bot buys breakout at $100 on index 40. High after index 40 is $105 (+5% < +12% breakeven trigger)
    uptrend_prices = [90.0 + (i * 0.7) for i in range(40)] + [100.0 + (i * 0.2) for i in range(20)]
    df_mom = pd.DataFrame({
        "close": uptrend_prices,
        "high": [p * 1.01 for p in uptrend_prices],
        "low": [p * 0.99 for p in uptrend_prices],
        "adj_close": uptrend_prices
    }, index=dates)
    mom_entry_date = dates[40].strftime("%Y-%m-%d")
    mom_curr_price = uptrend_prices[-1] # 103.8
    mom_plpc = (mom_curr_price - 100.0) / 100.0 # +3.8%
    exit_mom = InvestorSkillsHeuristics.evaluate_holding_exit(
        symbol="GE",
        df=df_mom,
        current_plpc=mom_plpc,
        regime="BULL_TRENDING",
        holding_type="MOMENTUM",
        avg_entry=100.0,
        entry_date=mom_entry_date
    )
    assert exit_mom["should_exit"] is False, f"Momentum runner incorrectly dumped: {exit_mom}"


def test_broker_adapter_fails_closed_without_fake_balances():
    """
    Broker adapter must raise BrokerAPIError on network error when API key is provided,
    never invent $100,000 or return [] silently.
    """
    broker = AlpacaBrokerAdapter(api_key="real_key_xyz", api_secret="real_secret_xyz")
    
    with patch("requests.get", side_effect=Exception("Connection refused / 502 Bad Gateway")):
        with pytest.raises(BrokerAPIError):
            broker.get_account_equity()

        with pytest.raises(BrokerAPIError):
            broker.get_positions_detailed()


def test_benchmark_data_outage_halts_safely():
    """
    If benchmark index data is completely missing or empty, regime engine must return
    DATA_OUTAGE_HALT with 0.0 max exposure, never default to BULL_TRENDING.
    """
    engine = UniversalLocalIndexRegimeEngine()
    empty_df = pd.DataFrame()
    
    res = engine.evaluate(index_df=empty_df)
    assert res["regime"] == "DATA_OUTAGE_HALT"
    assert res["max_exposure"] == 0.0
    assert "BENCHMARK_DATA_OUTAGE" in res["canaries"]

    res_none = engine.evaluate(index_df=None)
    assert res_none["regime"] == "DATA_OUTAGE_HALT"
    assert res_none["max_exposure"] == 0.0


def test_cancel_pending_buy_orders_preserves_stop_orders():
    """
    cancel_pending_buy_orders must ONLY send DELETE to BUY orders,
    preserving resting GTC stop sell orders.
    """
    broker = AlpacaBrokerAdapter(api_key="key", api_secret="sec")
    
    mock_orders = [
        {"id": "order-1", "symbol": "AAPL", "side": "buy", "type": "limit"},
        {"id": "order-2", "symbol": "NVDA", "side": "sell", "type": "stop"}, # PROTECTIVE STOP
        {"id": "order-3", "symbol": "MSFT", "side": "buy", "type": "market"},
    ]
    
    deleted_ids = []
    def mock_delete(url, **kwargs):
        order_id = url.split("/")[-1]
        deleted_ids.append(order_id)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        return mock_resp

    with patch.object(broker, "get_open_orders", return_value=mock_orders):
        with patch("requests.delete", side_effect=mock_delete):
            count = broker.cancel_pending_buy_orders()
            assert count == 2
            assert "order-1" in deleted_ids
            assert "order-3" in deleted_ids
            # Critical: order-2 (protective stop) must NOT be deleted!
            assert "order-2" not in deleted_ids


def test_position_tracker_sync_and_peak_update(tmp_path):
    """
    PositionTracker correctly records strategy type, entry date, and tracks peaks.
    """
    test_json = tmp_path / "test_positions.json"
    tracker = PositionTracker(metadata_path=str(test_json))
    
    # 1. Record fresh momentum entry
    tracker.record_entry("MSFT", holding_type="MOMENTUM", entry_price=400.0, entry_date="2026-10-01", quantity=10)
    meta = tracker.get_position_meta("MSFT")
    assert meta["holding_type"] == "MOMENTUM"
    assert meta["entry_price"] == 400.0
    assert meta["peak_price"] == 400.0
    
    # 2. Update peak
    new_peak = tracker.update_peak("MSFT", 450.0)
    assert new_peak == 450.0
    assert tracker.get_position_meta("MSFT")["peak_price"] == 450.0
    
    # 3. Pullback does not reduce peak
    peak_after_pullback = tracker.update_peak("MSFT", 430.0)
    assert peak_after_pullback == 450.0
    assert tracker.get_position_meta("MSFT")["peak_price"] == 450.0
    
    # 4. Exit
    tracker.record_exit("MSFT")
    assert "MSFT" not in tracker.data
