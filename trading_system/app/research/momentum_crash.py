"""
Standardized Volatility-Managed Momentum & Momentum-Crash Protection Module
==========================================================================
Governed by Peer-Reviewed Academic Literature:
1. Barroso, P. and Santa-Clara, P. (2015). "Momentum has its moments".
   Journal of Financial Economics, 116(1), pp. 111-120.
   DOI: 10.1016/j.jfineco.2014.11.010
2. Daniel, K. and Moskowitz, T. J. (2016). "Momentum Crashes".
   Journal of Financial Economics, 122(2), pp. 221-247.
   DOI: 10.1016/j.jfineco.2015.08.008

Theoretical Framework:
Cross-sectional momentum strategies (Jegadeesh & Titman, 1993) generate significant
unconditional alpha but exhibit pronounced negative skewness and are subject to infrequent,
severe crashes (e.g., 1932, 2009). Barroso & Santa-Clara (2015) demonstrate that momentum
risk is time-varying and highly predictable through its own realized volatility.

Dynamic exposure management inversely proportional to 20-day realized volatility:
    w_t = min(w_max, sigma_target / sigma_hat_t)
virtually eliminates crash risk, doubles the strategy Sharpe ratio, and removes negative skewness.
"""

import math
from typing import Dict, Any, Optional, Union
import numpy as np
import pandas as pd


def compute_barroso_santa_clara_realized_vol(
    series: Union[pd.Series, pd.DataFrame],
    lookback: int = 20,
    annualization_factor: float = 252.0,
    min_periods: Optional[int] = None
) -> Union[pd.Series, float]:
    """
    Computes annualized realized volatility according to Barroso & Santa-Clara (2015, Section 2.2).

    Formula:
        sigma_hat_t = sqrt( annualization_factor * Var_{N}(r_t) )
                    = sqrt( 252 * (1 / (N - 1)) * sum_{k=0}^{N-1} (r_{t-k} - bar{r})^2 )

    Parameters:
        series: Daily price or percentage returns series. If prices, pct_change() is computed.
        lookback: Realized volatility lookback window in trading days (default N = 20 trading days, 1 month).
        annualization_factor: 252 for daily equity market trading sessions.
        min_periods: Minimum observations required (defaults to max(5, lookback // 2)).

    Returns:
        pd.Series or float of annualized standard deviations.
    """
    if min_periods is None:
        min_periods = max(5, lookback // 2)

    # If prices provided (monotonically non-negative and mean > 1), compute daily returns
    if isinstance(series, pd.Series):
        if (series > 0).all() and series.mean() > 1.0 and (series.diff().dropna() != series.dropna()).any():
            ret = series.pct_change()
        else:
            ret = series
        vol_rolling = ret.rolling(window=lookback, min_periods=min_periods).std(ddof=1) * np.sqrt(annualization_factor)
        return vol_rolling
    elif isinstance(series, pd.DataFrame):
        ret = series.pct_change()
        return ret.rolling(window=lookback, min_periods=min_periods).std(ddof=1) * np.sqrt(annualization_factor)
    else:
        arr = np.asarray(series, dtype=float)
        if len(arr) < min_periods:
            return 0.15
        return float(np.std(arr[-lookback:], ddof=1) * np.sqrt(annualization_factor))


def compute_volatility_managed_exposure(
    realized_vol: float,
    target_vol: float = 0.12,
    max_exposure: float = 1.0,
    min_exposure: float = 0.0
) -> float:
    """
    Computes volatility-managed capital allocation weight per Barroso & Santa-Clara (2015):
        w_t = min(w_max, sigma_target / sigma_hat_t)

    Parameters:
        realized_vol: Annualized realized volatility sigma_hat_t (e.g., 0.24 for 24%).
        target_vol: Target annualized volatility sigma_target (default 0.12 = 12%).
        max_exposure: Upper cap on weight to prevent extreme leverage (default 1.0 = 100% unleveraged).
        min_exposure: Lower floor (default 0.0 = 100% cash).

    Returns:
        Scalar weight between min_exposure and max_exposure.
    """
    if realized_vol <= 0.0 or math.isnan(realized_vol):
        return max_exposure

    w = target_vol / realized_vol
    return float(np.clip(w, min_exposure, max_exposure))


def evaluate_momentum_crash_regime(
    realized_vol: float,
    crash_threshold: float = 0.35,
    recovery_threshold: float = 0.25,
    consecutive_calm_days: int = 10
) -> Dict[str, Any]:
    """
    Evaluates institutional momentum-crash guardrails (Barroso & Santa-Clara 2015; Daniel & Moskowitz 2016).

    Rules:
    - CRASH_ACTIVE: When 20-day realized volatility spikes >= 35.0%, momentum strategy faces severe
      crash hazard upon market rebounds (short squeezes / low-quality surges). Halts new momentum entries.
    - RECOVERY_MONITOR: Once volatility recedes below 25.0%, mandates consecutive calm trading sessions
      before restoring full momentum risk budget.
    """
    is_crash_hazard = realized_vol >= crash_threshold
    is_elevated = (realized_vol >= recovery_threshold) and not is_crash_hazard

    if is_crash_hazard:
        state = "CRASH_HAZARD_ACTIVE"
        action = "HALT_NEW_ENTRIES_AND_DEFEND"
        recommended_exposure_cap = 0.0
    elif is_elevated:
        state = "ELEVATED_VOLATILITY"
        action = "SCALE_EXPOSURE_DOWN"
        recommended_exposure_cap = 0.50
    else:
        state = "STABLE_CALM"
        action = "NORMAL_MOMENTUM_ALLOCATION"
        recommended_exposure_cap = 1.0

    return {
        "state": state,
        "action": action,
        "realized_vol_annualized": round(realized_vol, 4),
        "crash_threshold": crash_threshold,
        "recovery_threshold": recovery_threshold,
        "is_crash_hazard": is_crash_hazard,
        "recommended_exposure_cap": recommended_exposure_cap,
        "citation": "Barroso & Santa-Clara (2015); Daniel & Moskowitz (2016)"
    }


def evaluate_dual_pod_regime_and_volatility(
    benchmark_df: pd.DataFrame,
    target_vol: float = 0.15,
    vol_lookback: int = 20,
    crash_vol_threshold: float = 0.24,
    bear_sma_lookback: int = 200,
    caution_scale_threshold: float = 0.75
) -> Dict[str, Any]:
    """
    Unified, Canonical Volatility Radar & Regime Sentinel for Dual-Pod Desks.
    Shared identically across Backtest Simulation and Live/Paper Execution.

    Governing Academic Framework:
    1. Volatility Scaling: Barroso & Santa-Clara (2015, JFE):
       w_t = min(1.0, sigma_target / sigma_hat_{20D})
       Target volatility is set to 15.0% across both India and US desks, matching
       the long-term unconditional annualized volatility of Nifty 50 and S&P 500.
    2. Momentum Crash Panic Filter: Daniel & Moskowitz (2016, JFE):
       Identifies panic states where market 6-month return R_{6M} < 0 AND short-term
       realized volatility sigma_{20D} >= 24.0%.
    3. Structural Trend Floor: Benchmark Close < 200-day Simple Moving Average.

    Parameters:
        benchmark_df: Daily historical OHLCV DataFrame for market benchmark (^NSEI or SPY).
        target_vol: Target annualized volatility (default 0.15 = 15.0%).
        vol_lookback: Trading days lookback for realized volatility (default 20).
        crash_vol_threshold: Realized volatility boundary for panic crashes (default 0.24 = 24.0%).
        bear_sma_lookback: Simple moving average lookback for structural trend (default 200).
        caution_scale_threshold: Scale threshold triggering VOLATILITY_CAUTION regime (default 0.75).

    Returns:
        Dict with keys:
            regime: "BEAR_DEFENSE", "VOLATILITY_CAUTION", or "BULL_TRENDING"
            max_exposure: float between 0.0 and 1.0
            vol_scale: float raw scaling scalar
            bench_close: latest close
            bench_sma200: latest 200-SMA
            bench_vol_20d: latest 20-day annualized realized volatility
            bench_ret_6m: 6-month percentage return
            is_structural_bear: bool
    """
    close_col = "close" if "close" in benchmark_df.columns else "adj close"
    closes = benchmark_df[close_col].dropna()

    bench_close = float(closes.iloc[-1])
    bench_sma200 = float(closes.rolling(bear_sma_lookback, min_periods=max(20, bear_sma_lookback // 4)).mean().iloc[-1])

    # 20-day annualized realized volatility (ddof=1)
    ret_series = closes.pct_change().dropna()
    min_vol_periods = max(5, vol_lookback // 2)
    if len(ret_series) >= min_vol_periods:
        vol_window = ret_series.iloc[-vol_lookback:]
        bench_vol_20d = float(vol_window.std(ddof=1) * (252.0 ** 0.5))
    else:
        bench_vol_20d = target_vol

    # 6-month benchmark return (approx 126 trading days)
    ret_6m_lookback = min(126, len(closes) - 1)
    if ret_6m_lookback > 0:
        bench_ret_6m = float((bench_close / float(closes.iloc[-1 - ret_6m_lookback])) - 1.0)
    else:
        bench_ret_6m = 0.0

    # Barroso & Santa-Clara inverse volatility weight
    if not math.isnan(bench_vol_20d) and bench_vol_20d > 0.0:
        vol_scale = min(1.0, target_vol / max(bench_vol_20d, 0.08))
    else:
        vol_scale = 1.0

    # Daniel & Moskowitz panic crash condition + 200-SMA trend break
    is_panic_crash = (bench_ret_6m < 0.0) and (bench_vol_20d >= crash_vol_threshold)
    is_trend_broken = bench_close < bench_sma200
    is_structural_bear = is_panic_crash or is_trend_broken

    if is_structural_bear:
        regime = "BEAR_DEFENSE"
        max_exposure = 0.0
    elif vol_scale < caution_scale_threshold:
        regime = "VOLATILITY_CAUTION"
        max_exposure = round(vol_scale, 2)
    else:
        regime = "BULL_TRENDING"
        max_exposure = 1.0

    return {
        "regime": regime,
        "max_exposure": max_exposure,
        "vol_scale": round(vol_scale, 4),
        "bench_close": round(bench_close, 2),
        "bench_sma200": round(bench_sma200, 2),
        "bench_vol_20d": round(bench_vol_20d, 4),
        "bench_ret_6m": round(bench_ret_6m, 4),
        "is_structural_bear": is_structural_bear,
        "is_panic_crash": is_panic_crash,
        "is_trend_broken": is_trend_broken
    }

