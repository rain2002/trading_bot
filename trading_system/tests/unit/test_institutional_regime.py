import pytest
import pandas as pd
import numpy as np
from datetime import datetime

from trading_system.app.features.regime import InstitutionalMacroRegimeEngine, RegimeDetector
from trading_system.app.strategies.ensembles.ensemble_allocator import EnsembleAllocator


def test_trend_pillar_and_kaufman_efficiency():
    engine = InstitutionalMacroRegimeEngine()
    
    # 250 days of strong uptrend
    prices = [400.0 + i * 1.5 for i in range(250)]
    spy_df = pd.DataFrame({
        "close": prices,
        "high": [p + 1.0 for p in prices],
        "low": [p - 1.0 for p in prices]
    })
    
    res = engine.analyze_trend_pillar(spy_df)
    assert res["is_bull_200"] is True
    assert res["is_bull_50"] is True
    assert res["is_severe_breakdown"] is False
    assert res["trend_ratio"] > 0.30
    assert res["score"] < 0.25 # Low trend stress


def test_credit_pillar_detects_bearish_divergence():
    engine = InstitutionalMacroRegimeEngine()
    
    # SPY is at all-time highs
    spy_prices = [500.0] * 230 + [500.0 + i for i in range(20)] # rising to 520
    spy_df = pd.DataFrame({"close": spy_prices})
    
    # HYG / IEF credit ratio is dumping
    hyg_prices = [80.0] * 230 + [80.0 - i * 0.5 for i in range(20)] # falling sharply
    ief_prices = [90.0] * 250
    hyg_df = pd.DataFrame({"close": hyg_prices})
    ief_df = pd.DataFrame({"close": ief_prices})
    
    res = engine.analyze_credit_pillar(hyg_df, ief_df, spy_df=spy_df)
    assert res["divergence"] is True
    assert res["credit_state"] == "CREDIT_CRUNCH"
    assert res["score"] >= 0.70 # High credit stress score


def test_volatility_pillar_detects_velocity_shock():
    engine = InstitutionalMacroRegimeEngine()
    
    # VIX was 16.0, jumps to 24.0 in 5 days (+50% velocity shock)
    vix_prices = [16.0] * 245 + [18.0, 20.0, 22.0, 23.0, 24.0]
    vix_df = pd.DataFrame({"close": vix_prices})
    
    res = engine.analyze_volatility_pillar(vix_df)
    assert res["vol_shock"] is True
    assert res["vix"] == 24.0
    assert res["vix_velocity_5d"] >= 25.0
    assert res["score"] >= 0.50


def test_rates_pillar_detects_yield_curve_inversion():
    engine = InstitutionalMacroRegimeEngine()
    
    # 10Y Yield is 4.0%, Short-term yield is 4.5% (Spread = -0.5% Inverted)
    tnx_df = pd.DataFrame({"close": [4.0] * 250})
    irx_df = pd.DataFrame({"close": [4.5] * 250})
    
    res = engine.analyze_rates_pillar(tnx_df, irx_df)
    assert res["curve_state"] == "DEEPLY_INVERTED"
    assert res["yield_curve_spread"] == -0.50
    assert res["score"] >= 0.60


def test_composite_macro_stress_index_and_regimes():
    engine = InstitutionalMacroRegimeEngine()
    
    # Synthetic trending bull environment
    spy_df = pd.DataFrame({
        "close": [400.0 + i * 0.5 for i in range(250)],
        "high": [402.0 + i * 0.5 for i in range(250)],
        "low": [398.0 + i * 0.5 for i in range(250)]
    })
    vix_df = pd.DataFrame({"close": [15.0] * 250})
    hyg_df = pd.DataFrame({"close": [80.0] * 250})
    ief_df = pd.DataFrame({"close": [90.0] * 250})
    
    res = engine.evaluate(spy_df, vix_df=vix_df, hyg_df=hyg_df, ief_df=ief_df)
    assert res["macro_stress_index"] <= 0.35
    assert res["max_exposure"] >= 0.85
    assert "CRASH_WARNING" not in res["regime"]


def test_ensemble_allocator_delegation_and_backward_compatibility():
    allocator = EnsembleAllocator()
    
    # Severe crash data
    prices = [500.0] * 240 + [400.0] * 5 + [350.0] * 5
    spy_df = pd.DataFrame({
        "close": prices,
        "high": [p * 1.01 for p in prices],
        "low": [p * 0.99 for p in prices]
    })
    
    res = allocator.detect_regime(spy_df)
    assert res["regime"] == "CRASH_WARNING"
    assert res["max_exposure"] == 0.00
    assert res["macro_stress_index"] > 0.0


def test_legacy_regime_detector_shim():
    detector = RegimeDetector()
    prices = [400.0 + i * 0.5 for i in range(250)]
    spy_df = pd.DataFrame({
        "close": prices,
        "high": [p + 2.0 for p in prices],
        "low": [p - 2.0 for p in prices]
    })
    regime_str = detector.detect_regime(spy_df)
    assert isinstance(regime_str, str)
    assert regime_str in ("BULL_TRENDING", "BULL_ROTATION", "BULL_CHOPPY", "BEAR_CORRECTION", "CRASH_WARNING")
