import pytest
import pandas as pd
import numpy as np

from trading_system.app.config.market_config import MarketConfig
from trading_system.app.features.regime import UniversalLocalIndexRegimeEngine


def test_market_config_loading_all_four_jurisdictions():
    """MarketConfig must load US, IN, UK, and JP configurations seamlessly."""
    # US
    us = MarketConfig.load("US")
    assert us.market_code == "US"
    assert us.currency_symbol == "$"
    assert us.benchmark_symbol == "SPY"
    assert us.integer_shares_only is False
    assert len(us.get_universe()) > 400

    # India
    india = MarketConfig.load("IN")
    assert india.market_code == "IN"
    assert india.currency_symbol == "₹"
    assert india.benchmark_symbol == "^NSEI"
    assert india.integer_shares_only is True
    assert len(india.get_universe()) >= 50

    # UK
    uk = MarketConfig.load("UK")
    assert uk.market_code == "UK"
    assert uk.currency_symbol == "£"
    assert uk.benchmark_symbol == "^FTSE"
    assert uk.integer_shares_only is True
    assert len(uk.get_universe()) >= 20

    # Japan
    jp = MarketConfig.load("JP")
    assert jp.market_code == "JP"
    assert jp.currency_symbol == "¥"
    assert jp.benchmark_symbol == "^N225"
    assert jp.integer_shares_only is True
    assert len(jp.get_universe()) >= 15


def test_market_config_transaction_costs():
    """Transaction costs must account for local taxes like STT in India and Stamp Duty in UK."""
    india = MarketConfig.load("IN")
    # Buy ₹100,000 worth of shares: 5 bps slippage (₹50) + ₹20 flat + 0.1% STT (₹100) = ₹170
    costs_in = india.calculate_transaction_costs(trade_value=100000.0, shares=100, side="BUY")
    assert pytest.approx(costs_in, 0.01) == 170.0

    uk = MarketConfig.load("UK")
    # Buy £10,000 worth of shares: 5 bps slippage (£5) + £3 flat + 0.5% SDRT (£50) = £58
    costs_uk = uk.calculate_transaction_costs(trade_value=10000.0, shares=100, side="BUY")
    assert pytest.approx(costs_uk, 0.01) == 58.0


def test_universal_local_index_regime_bull_trending():
    """Universal regime engine must detect BULL_TRENDING on any index near 52-week highs above 200 SMA."""
    engine = UniversalLocalIndexRegimeEngine()

    # Synthetic trending index: 250 days steadily rising from 10,000 to 15,000 (like Nifty or Nikkei)
    prices = [10000.0 + i * 20.0 for i in range(250)]
    index_df = pd.DataFrame({
        "close": prices,
        "high": [p + 20.0 for p in prices],
        "low": [p - 20.0 for p in prices]
    })

    res = engine.evaluate(index_df)
    assert res["regime"] == "BULL_TRENDING"
    assert res["max_exposure"] >= 0.95
    assert res["macro_stress_index"] < 0.20
    assert res["diagnostics"]["drawdown_pillar"]["drawdown_pct"] == 0.0


def test_universal_local_index_regime_detects_bear_correction():
    """Universal regime engine detects BEAR_CORRECTION when index breaks 200 SMA with -15% drawdown."""
    engine = UniversalLocalIndexRegimeEngine()

    # Index peaked at 20,000, then dropped -15% down to 17,000 below its 200 SMA
    prices = [18000.0] * 100 + [20000.0] * 100 + [17000.0] * 50
    index_df = pd.DataFrame({"close": prices})

    res = engine.evaluate(index_df)
    assert res["regime"] == "BEAR_CORRECTION"
    assert res["max_exposure"] == 0.40
    assert res["diagnostics"]["drawdown_pillar"]["drawdown_pct"] <= -12.0


def test_universal_local_index_regime_detects_crash_warning_without_us_data():
    """
    Universal regime engine detects CRASH_WARNING on ANY international index
    experiencing a severe breakdown and volatility surge, with ZERO US credit or treasury data!
    """
    engine = UniversalLocalIndexRegimeEngine()

    # Steep crash: Index collapses -25% below 200 SMA with extreme daily swings
    prices = [1000.0] * 230 + [750.0] * 20  # -25% collapse
    index_df = pd.DataFrame({
        "close": prices,
        "high": [p * 1.05 for p in prices],
        "low": [p * 0.95 for p in prices]
    })

    res = engine.evaluate(index_df)
    assert res["regime"] == "CRASH_WARNING"
    assert res["max_exposure"] == 0.00
    assert res["cash_reserve_pct"] == 1.00
    assert "BEAR_MARKET_DRAWDOWN_BREACH" in res["canaries"]
