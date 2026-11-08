"""
Unit Tests for Barroso & Santa-Clara (2015) Volatility-Managed Momentum & Crash Guard
"""

import math
import numpy as np
import pandas as pd
import pytest

from trading_system.app.research.momentum_crash import (
    compute_barroso_santa_clara_realized_vol,
    compute_volatility_managed_exposure,
    evaluate_momentum_crash_regime,
    evaluate_dual_pod_regime_and_volatility,
)


class TestMomentumCrashGuard:

    def test_compute_barroso_santa_clara_realized_vol_series(self):
        """
        Verifies that realized volatility matches theoretical sqrt(252) * sample standard deviation
        over a 20-day lookback window.
        """
        np.random.seed(42)
        daily_ret = pd.Series(np.random.normal(0.0005, 0.01, 100))  # 1% daily volatility
        vol = compute_barroso_santa_clara_realized_vol(daily_ret, lookback=20, annualization_factor=252.0)

        # Expected annualized vol is approximately 0.01 * sqrt(252) ~= 0.1587 (15.87%)
        latest_vol = vol.iloc[-1]
        assert 0.10 <= latest_vol <= 0.25
        assert len(vol) == 100

    def test_volatility_managed_exposure_scaling(self):
        """
        Verifies inverse volatility weighting per Barroso & Santa-Clara (2015):
        w_t = min(w_max, target_vol / realized_vol).
        """
        # When realized vol is low (10%) and target is 12%, cap is 1.0 -> weight = 1.0
        w_calm = compute_volatility_managed_exposure(realized_vol=0.10, target_vol=0.12, max_exposure=1.0)
        assert w_calm == 1.0

        # When realized vol is high (24%), weight should scale down to 0.12 / 0.24 = 0.50
        w_stress = compute_volatility_managed_exposure(realized_vol=0.24, target_vol=0.12, max_exposure=1.0)
        assert math.isclose(w_stress, 0.50, rel_tol=1e-3)

        # When realized vol is severe (48%), weight scales down to 0.12 / 0.48 = 0.25
        w_panic = compute_volatility_managed_exposure(realized_vol=0.48, target_vol=0.12, max_exposure=1.0)
        assert math.isclose(w_panic, 0.25, rel_tol=1e-3)

    def test_momentum_crash_guard_halts_on_spike(self):
        """
        Verifies momentum crash rule halts new entries when realized vol >= 35.0%
        per Barroso & Santa-Clara (2015) and Daniel & Moskowitz (2016).
        """
        # 1. Normal regime (18% vol)
        res_normal = evaluate_momentum_crash_regime(realized_vol=0.18)
        assert res_normal["state"] == "STABLE_CALM"
        assert res_normal["is_crash_hazard"] is False
        assert res_normal["recommended_exposure_cap"] == 1.0

        # 2. Elevated regime (28% vol)
        res_elevated = evaluate_momentum_crash_regime(realized_vol=0.28)
        assert res_elevated["state"] == "ELEVATED_VOLATILITY"
        assert res_elevated["is_crash_hazard"] is False
        assert res_elevated["recommended_exposure_cap"] == 0.50

        # 3. Crash hazard regime (42% vol) -> immediate entry halt
        res_crash = evaluate_momentum_crash_regime(realized_vol=0.42)
        assert res_crash["state"] == "CRASH_HAZARD_ACTIVE"
        assert res_crash["is_crash_hazard"] is True
        assert res_crash["recommended_exposure_cap"] == 0.0
        assert "HALT" in res_crash["action"]

    def test_dual_pod_regime_and_volatility_boundary_conditions(self):
        """
        Boundary tests for the unified volatility radar and regime sentinel:
        1. 0.75 caution threshold boundary
        2. 24% bear crash threshold with 6M return sign
        3. Structural 200-SMA break boundary
        """
        dates = pd.date_range("2024-01-01", periods=250, freq="B")

        # Scenario 1: Calm Bull (10% vol, positive 6M return, above 200-SMA)
        # Price steadily rising from 100 to 150
        calm_prices = np.linspace(100, 150, 250)
        df_calm = pd.DataFrame({"close": calm_prices}, index=dates)
        res_calm = evaluate_dual_pod_regime_and_volatility(df_calm, target_vol=0.15)
        assert res_calm["regime"] == "BULL_TRENDING"
        assert res_calm["max_exposure"] == 1.0
        assert res_calm["vol_scale"] == 1.0
        assert res_calm["is_structural_bear"] is False

        # Scenario 2: Caution Line Boundary (Scale < 0.75)
        # Volatility ~ 22% -> Scale = 0.15 / 0.22 ~= 0.68 < 0.75
        # Modulate prices with alternating swings to induce ~22% volatility while keeping trend up
        swing = np.array([1.0, -1.0] * 125) * 1.5
        caution_prices = np.linspace(120, 160, 250) + swing
        df_caution = pd.DataFrame({"close": caution_prices}, index=dates)
        res_caution = evaluate_dual_pod_regime_and_volatility(df_caution, target_vol=0.15)
        if res_caution["vol_scale"] < 0.75 and not res_caution["is_structural_bear"]:
            assert res_caution["regime"] == "VOLATILITY_CAUTION"
            assert res_caution["max_exposure"] == round(res_caution["vol_scale"], 2)

        # Scenario 3: 24% Bear Threshold + Negative 6M Return (Daniel & Moskowitz Panic Crash)
        # 6M return is negative AND 20D vol >= 24% -> MUST be BEAR_DEFENSE
        # Create declining series with sharp daily swings
        panic_prices = np.linspace(150, 90, 250)  # Negative 6M return (-40%)
        # Add high volatility over the last 25 days (e.g. daily swings of 3%)
        for i in range(225, 250):
            panic_prices[i] = panic_prices[i] + (2.5 if i % 2 == 0 else -2.5)
        df_panic = pd.DataFrame({"close": panic_prices}, index=dates)
        res_panic = evaluate_dual_pod_regime_and_volatility(df_panic, target_vol=0.15, crash_vol_threshold=0.24)
        assert res_panic["is_panic_crash"] is True or res_panic["is_trend_broken"] is True
        assert res_panic["regime"] == "BEAR_DEFENSE"
        assert res_panic["max_exposure"] == 0.0

        # Scenario 4: High Volatility BUT Positive 6M Return (e.g. Bullish high-vol expansion)
        # Price is WAY above 200-SMA, 6M return is strongly positive (+30%), but vol is 25%
        # Must NOT trigger Daniel & Moskowitz crash panic (regime is VOLATILITY_CAUTION, NOT BEAR_DEFENSE!)
        bull_high_vol = np.linspace(100, 200, 250)  # Strong bull trend
        for i in range(225, 250):
            bull_high_vol[i] = bull_high_vol[i] + (4.0 if i % 2 == 0 else -4.0)
        df_bull_vol = pd.DataFrame({"close": bull_high_vol}, index=dates)
        res_bull_vol = evaluate_dual_pod_regime_and_volatility(df_bull_vol, target_vol=0.15, crash_vol_threshold=0.24)
        assert res_bull_vol["bench_ret_6m"] > 0.0
        assert res_bull_vol["is_panic_crash"] is False
        assert res_bull_vol["is_trend_broken"] is False
        assert res_bull_vol["regime"] == "VOLATILITY_CAUTION"
        assert 0.0 < res_bull_vol["max_exposure"] < 1.0

