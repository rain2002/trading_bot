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
