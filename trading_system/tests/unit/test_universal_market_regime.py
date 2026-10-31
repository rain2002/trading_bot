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
    """Transaction costs must account for local taxes like STT, Stamp Duty, GST, and exchange fees."""
    # India:
    # Buy ₹100,000 worth of shares:
    # 5 bps slippage (₹50) + ₹20 flat + 0.35 bps turnover (₹3.50) + 18% GST on (₹20+₹3.50=₹4.23) + 0.1% STT (₹100) + 1.5 bps stamp duty (₹15) = ₹192.73
    india = MarketConfig.load("IN")
    costs_in_buy = india.calculate_transaction_costs(trade_value=100000.0, shares=100, side="BUY")
    assert pytest.approx(costs_in_buy, 0.01) == 192.73

    # Sell ₹100,000 worth of shares:
    # Stamp duty is BUY only (₹0). Total = ₹177.73
    costs_in_sell = india.calculate_transaction_costs(trade_value=100000.0, shares=100, side="SELL")
    assert pytest.approx(costs_in_sell, 0.01) == 177.73

    # UK:
    # Buy £10,000 worth of shares:
    # 5 bps slippage (£5) + £3 flat + 0.2 bps turnover (£0.20) + 0.5% SDRT (£50) = £58.20
    uk = MarketConfig.load("UK")
    costs_uk_buy = uk.calculate_transaction_costs(trade_value=10000.0, shares=100, side="BUY")
    assert pytest.approx(costs_uk_buy, 0.01) == 58.20

    # Sell £10,000 worth of shares:
    # SDRT is BUY only (£0). Total = £8.20
    costs_uk_sell = uk.calculate_transaction_costs(trade_value=10000.0, shares=100, side="SELL")
    assert pytest.approx(costs_uk_sell, 0.01) == 8.20

    # US:
    # Sell $10,000 worth of shares:
    # 5 bps slippage ($5.00) + 0.28 bps SEC/FINRA fee ($0.28) = $5.28
    us = MarketConfig.load("US")
    costs_us_sell = us.calculate_transaction_costs(trade_value=10000.0, shares=100, side="SELL")
    assert pytest.approx(costs_us_sell, 0.01) == 5.28


def test_get_universe_preserves_non_us_ticker_dots():
    """
    Non-US tickers like RELIANCE.NS, SHEL.L, 7203.T MUST preserve dots for Yahoo Finance.
    Only US dual-class tickers (BRK.B) swap '.' to '-'.
    """
    india = MarketConfig.load("IN")
    in_univ = india.get_universe()
    assert "RELIANCE.NS" in in_univ
    assert "TCS.NS" in in_univ
    assert "RELIANCE-NS" not in in_univ
    assert "TCS-NS" not in in_univ

    uk = MarketConfig.load("UK")
    uk_univ = uk.get_universe()
    assert "SHEL.L" in uk_univ
    assert "SHEL-L" not in uk_univ

    jp = MarketConfig.load("JP")
    jp_univ = jp.get_universe()
    assert "7203.T" in jp_univ
    assert "7203-T" not in jp_univ

    us = MarketConfig.load("US")
    us_univ = us.get_universe()
    # In US universe, Berkshire Hathaway B is BRK-B, not BRK.B
    assert "BRK-B" in us_univ
    assert "BRK.B" not in us_univ


def test_universal_relative_volatility_self_calibrating():
    """
    Universal relative volatility must NOT trigger false stress on high-volatility baseline indices (e.g. Nifty 22% baseline).
    It triggers based on relative surge (vol_ratio = vol20 / vol60).
    """
    engine = UniversalLocalIndexRegimeEngine()

    # Case A: Market with naturally high 22% annualized volatility baseline
    # Both 20-day and 60-day vol are ~22% (ratio ~ 1.0)
    np.random.seed(42)
    daily_returns_calm = np.random.normal(0.0005, 0.22 / np.sqrt(252), 100)
    prices_calm = [10000.0]
    for r in daily_returns_calm:
        prices_calm.append(prices_calm[-1] * (1.0 + r))
    df_calm = pd.DataFrame({"close": prices_calm})

    p_vol_calm = engine.analyze_volatility_pillar(index_df=df_calm)
    assert p_vol_calm["vol_ratio"] <= 1.15
    assert p_vol_calm["vol_state"] in ("NORMAL", "COMPLACENT_CALM")
    assert p_vol_calm["score"] <= 0.25
    assert p_vol_calm["vol_shock"] is False

    # Case B: Low-baseline market (10% vol) experiencing a sudden volatility explosion to 25% (ratio >= 1.6x)
    returns_spike = list(np.random.normal(0.0002, 0.10 / np.sqrt(252), 75)) + \
                    list(np.random.normal(-0.005, 0.35 / np.sqrt(252), 25))
    prices_spike = [10000.0]
    for r in returns_spike:
        prices_spike.append(prices_spike[-1] * (1.0 + r))
    df_spike = pd.DataFrame({"close": prices_spike})

    p_vol_spike = engine.analyze_volatility_pillar(index_df=df_spike)
    assert p_vol_spike["vol_ratio"] >= 1.35
    assert p_vol_spike["vol_state"] in ("HIGH_STRESS", "CRISIS_PANIC")
    assert p_vol_spike["vol_shock"] is True


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
