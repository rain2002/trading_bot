import pytest
from trading_system.app.config.market_config import MarketConfig
from trading_system.app.risk.basic import BasicRiskEngine


def test_india_cost_model_exact_buy_ledger():
    """
    Asserts Indian Delivery BUY transaction friction matches exact hand-calculated ledger to the paisa.
    Buy trade value: Rs 10,000.
    """
    cfg = MarketConfig.load("IN")
    breakdown = cfg.calculate_transaction_costs(
        trade_value=10000.0,
        shares=10,
        side="BUY",
        return_breakdown=True
    )

    assert breakdown["trade_value"] == 10000.0
    assert breakdown["side"] == "BUY"
    assert breakdown["brokerage"] == 0.0

    # STT: 0.1% of Rs 10,000 = Rs 10.00
    assert breakdown["stt"] == pytest.approx(10.0, abs=0.0001)

    # Stamp Duty: 0.015% of Rs 10,000 = Rs 1.50
    assert breakdown["stamp_duty"] == pytest.approx(1.5, abs=0.0001)

    # DP charge: Rs 0.00 on BUY
    assert breakdown["dp_charge"] == 0.0

    # Exchange fee: 0.00345% of Rs 10,000 = Rs 0.345
    assert breakdown["exchange_fee"] == pytest.approx(0.345, abs=0.0001)

    # SEBI turnover fee: 0.0001% of Rs 10,000 = Rs 0.01
    assert breakdown["sebi_fee"] == pytest.approx(0.01, abs=0.0001)

    # GST: 18% on (Brokerage + Exchange + SEBI + DP Fee) = 0.18 * 0.355 = Rs 0.0639
    assert breakdown["gst"] == pytest.approx(0.0639, abs=0.0001)

    # Statutory Subtotal: 10 + 1.5 + 0.345 + 0.01 + 0.0639 = Rs 11.9189
    assert breakdown["statutory_total"] == pytest.approx(11.9189, abs=0.0001)

    # Slippage: 5 bps (0.05%) of Rs 10,000 = Rs 5.00
    assert breakdown["slippage"] == pytest.approx(5.0, abs=0.0001)

    # Total: Rs 16.9189
    assert breakdown["total"] == pytest.approx(16.9189, abs=0.0001)


def test_india_cost_model_exact_sell_ledger():
    """
    Asserts Indian Delivery SELL transaction friction matches exact hand-calculated ledger to the paisa.
    Sell trade value: Rs 12,000.
    """
    cfg = MarketConfig.load("IN")
    breakdown = cfg.calculate_transaction_costs(
        trade_value=12000.0,
        shares=10,
        side="SELL",
        return_breakdown=True
    )

    assert breakdown["trade_value"] == 12000.0
    assert breakdown["side"] == "SELL"
    assert breakdown["brokerage"] == 0.0

    # STT: 0.1% of Rs 12,000 = Rs 12.00
    assert breakdown["stt"] == pytest.approx(12.0, abs=0.0001)

    # Stamp Duty: Rs 0.00 on SELL
    assert breakdown["stamp_duty"] == 0.0

    # DP charge: Flat Rs 15.34 on SELL
    assert breakdown["dp_charge"] == pytest.approx(15.34, abs=0.0001)

    # Exchange fee: 0.00345% of Rs 12,000 = Rs 0.414
    assert breakdown["exchange_fee"] == pytest.approx(0.414, abs=0.0001)

    # SEBI turnover fee: 0.0001% of Rs 12,000 = Rs 0.012
    assert breakdown["sebi_fee"] == pytest.approx(0.012, abs=0.0001)

    # GST: 18% on (0 + 0.414 + 0.012 + 15.34) = 0.18 * 15.766 = Rs 2.83788
    assert breakdown["gst"] == pytest.approx(2.83788, abs=0.0001)

    # Statutory Subtotal: 12 + 15.34 + 0.414 + 0.012 + 2.83788 = Rs 30.60388
    assert breakdown["statutory_total"] == pytest.approx(30.60388, abs=0.0001)

    # Slippage: 5 bps (0.05%) of Rs 12,000 = Rs 6.00
    assert breakdown["slippage"] == pytest.approx(6.0, abs=0.0001)

    # Total: Rs 36.60388
    assert breakdown["total"] == pytest.approx(36.60388, abs=0.0001)


def test_cost_floor_gate_logic():
    """
    Asserts 15% Cost Floor Gate rejects trades when estimated round-trip friction > 15% of expected profit.
    Round-trip cost for Rs 10k buy + Rs 12k sell = 16.9189 + 36.60388 = Rs 53.52278.
    """
    cfg = MarketConfig.load("IN")
    buy_friction = cfg.calculate_transaction_costs(10000.0, side="BUY")
    sell_friction = cfg.calculate_transaction_costs(12000.0, side="SELL")
    round_trip_friction = buy_friction + sell_friction  # ~53.52

    # High expected profit: Rs 2,000 -> 15% threshold is Rs 300 -> PASS
    assert cfg.validate_cost_floor_gate(
        estimated_round_trip_costs=round_trip_friction,
        expected_trade_profit=2000.0,
        max_cost_pct=0.15
    ) is True

    # Low expected profit: Rs 200 -> 15% threshold is Rs 30 -> FAIL
    assert cfg.validate_cost_floor_gate(
        estimated_round_trip_costs=round_trip_friction,
        expected_trade_profit=200.0,
        max_cost_pct=0.15
    ) is False

    # Negative / zero profit -> FAIL
    assert cfg.validate_cost_floor_gate(round_trip_friction, 0.0) is False
    assert cfg.validate_cost_floor_gate(round_trip_friction, -100.0) is False


def test_basic_risk_engine_cost_floor_gate():
    """
    Asserts BasicRiskEngine enforces the 15% Cost Floor Gate in evaluate_trade.
    """
    risk_engine = BasicRiskEngine()

    portfolio_state = {
        "cash": 100000.0,
        "positions": {}
    }

    # Trade 1: Expected profit Rs 2,000, estimated friction Rs 53.52 (2.67% of profit <= 15%) -> PASS
    pass_trade = {
        "symbol": "RELIANCE.NS",
        "action": "BUY",
        "shares": 10,
        "price": 1000.0,
        "expected_profit": 2000.0,
        "estimated_friction": 53.52
    }
    assert risk_engine.evaluate_trade(pass_trade, portfolio_state) is True

    # Trade 2: Expected profit Rs 200, estimated friction Rs 53.52 (26.76% of profit > 15%) -> BLOCKED
    fail_trade = {
        "symbol": "TCS.NS",
        "action": "BUY",
        "shares": 10,
        "price": 1000.0,
        "expected_profit": 200.0,
        "estimated_friction": 53.52
    }
    assert risk_engine.evaluate_trade(fail_trade, portfolio_state) is False
