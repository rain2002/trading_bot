"""
Universal Local-Index & Multi-Asset Macro Regime Engine.
Implements a 3-Universal-Signal Local Index Framework that works on ANY global equity market:
  1. Trend & Efficiency: Local Index vs 200-day & 50-day SMA + Kaufman Efficiency Ratio
  2. Local Realized Volatility: 20-day annualized realized volatility vs 60-day baseline
  3. Peak Drawdown: Distance of the local index from its trailing 252-day peak

Optional Multi-Asset Overlays (where available):
  - Corporate Credit & Liquidity Spreads (HYG/IEF ratio)
  - Volatility Surface & Tail-Risk Indices (^VIX / ^INDIAVIX)
  - Sovereign Rates & Yield Curve Slope (^TNX / ^IRX)
  - Market Breadth (RSP/SPY, QQQ)
"""

from typing import Dict, Any, Optional, List
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger("UniversalMacroRegime")


class UniversalLocalIndexRegimeEngine:
    """
    Universal Local-Index Macro Regime & Tail-Risk Engine.
    Operates on ANY global equity benchmark (US SPY, Indian NIFTY 50, UK FTSE 100, Japan Nikkei 225)
    using strictly three universal causal signals from the local benchmark index alone:
      1. Trend & Structural Efficiency: Index Price vs 200-day & 50-day SMA + Kaufman Efficiency
      2. Realized Volatility & Shock: Index's own recent 20-day annualized volatility vs 60-day baseline
      3. Drawdown from Peak: Distance from rolling 252-day peak (52-week high)

    External pillars (credit spreads, volatility surface indices, yield curves) are accepted as
    optional overlays when available, but the engine runs 100% autonomously without them.
    """

    def __init__(
        self,
        trend_weight: float = 0.35,
        vol_weight: float = 0.35,
        drawdown_weight: float = 0.30,
        credit_weight: float = 0.0,
        rates_weight: float = 0.0,
        breadth_weight: float = 0.0,
    ):
        self.w_trend = trend_weight
        self.w_vol = vol_weight
        self.w_drawdown = drawdown_weight
        self.w_credit = credit_weight
        self.w_rates = rates_weight
        self.w_breadth = breadth_weight

    # -------------------------------------------------------------------------
    # Pillar 1: Local Index Trend & Structural Efficiency
    # -------------------------------------------------------------------------
    def analyze_trend_pillar(self, index_df: pd.DataFrame) -> Dict[str, Any]:
        """Analyzes benchmark trend, 200/50/20 moving averages, and Kaufman Efficiency Ratio."""
        if index_df is None or index_df.empty or len(index_df) < 20:
            return {
                "score": 1.0,
                "is_bull_200": False,
                "is_bull_50": False,
                "is_severe_breakdown": True,
                "trend_ratio": 0.0,
                "distance_to_200_pct": 0.0,
                "distance_to_50_pct": 0.0,
                "diagnostics": {"price": 0.0, "sma200": 0.0, "sma50": 0.0}
            }

        close = index_df["close"]
        price = float(close.iloc[-1])
        len_close = len(close)

        sma200 = float(close.rolling(window=min(200, len_close)).mean().iloc[-1])
        sma50 = float(close.rolling(window=min(50, len_close)).mean().iloc[-1])
        sma20 = float(close.rolling(window=min(20, len_close)).mean().iloc[-1])

        dist_200 = (price - sma200) / sma200 * 100 if sma200 > 0 else 0.0
        dist_50 = (price - sma50) / sma50 * 100 if sma50 > 0 else 0.0

        # Kaufman Efficiency Ratio: |net change| / sum(absolute price changes)
        high = index_df.get("high", close)
        low = index_df.get("low", close)
        tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
        atr14 = float(tr.rolling(14).mean().iloc[-1]) if len(tr) >= 14 else 1.0
        change14 = abs(float(close.iloc[-1] - close.iloc[-15])) if len_close > 15 else 0.0
        trend_ratio = min(1.0, change14 / (atr14 * 14 + 1e-6))

        # Stress Score: 0.0 = strong bull trend, 1.0 = deep severe breakdown
        stress = 0.0
        if price < sma200:
            stress += 0.50
        elif dist_200 < 2.0:
            stress += 0.20

        if price < sma50:
            stress += 0.30

        if trend_ratio < 0.20:
            stress += 0.20  # Inefficient choppy price discovery

        stress = min(1.0, max(0.0, stress))

        return {
            "score": round(stress, 3),
            "is_bull_200": bool(price >= sma200),
            "is_bull_50": bool(price >= sma50),
            "is_severe_breakdown": bool(price < sma20 * 0.95 and price < sma200),
            "trend_ratio": round(trend_ratio, 2),
            "distance_to_200_pct": round(dist_200, 2),
            "distance_to_50_pct": round(dist_50, 2),
            "diagnostics": {
                "price": round(price, 2),
                "spy_price": round(price, 2),
                "spy_sma50": round(sma50, 2),
                "spy_sma200": round(sma200, 2),
            }
        }

    # -------------------------------------------------------------------------
    # Pillar 2: Local Realized Volatility & Shock
    # -------------------------------------------------------------------------
    def analyze_volatility_pillar(
        self,
        vix_df: Optional[pd.DataFrame] = None,
        index_df: Optional[pd.DataFrame] = None
    ) -> Dict[str, Any]:
        """
        Analyzes volatility using:
        1. Local Index Realized Volatility (20-day annualized std dev & 60-day ratio)
        2. Implied Volatility index (VIX, India VIX) if available
        """
        # If external volatility index is provided
        if vix_df is not None and not vix_df.empty:
            close = vix_df["close"]
            vix_curr = float(close.iloc[-1])
            vix_5d_ago = float(close.iloc[-6]) if len(close) >= 6 else vix_curr
            vix_velocity = ((vix_curr - vix_5d_ago) / vix_5d_ago * 100) if vix_5d_ago > 0 else 0.0

            vol_shock = bool(vix_velocity >= 25.0 and vix_curr >= 20.0)
            if vix_curr >= 32.0:
                state = "CRISIS_PANIC"
                score = 1.0
            elif vix_curr >= 28.0:
                state = "HIGH_STRESS"
                score = 0.85
            elif vix_curr >= 22.0:
                state = "ELEVATED_CAUTION"
                score = 0.50
            elif vix_curr >= 17.0:
                state = "NORMAL"
                score = 0.20
            else:
                state = "COMPLACENT_CALM"
                score = 0.05

            if vol_shock:
                score = max(score, 0.75)

            return {
                "score": round(score, 3),
                "vix": round(vix_curr, 2),
                "vix_velocity_5d": round(vix_velocity, 1),
                "vol_state": state,
                "vol_shock": vol_shock,
                "realized_vol20": None,
                "realized_vol_annualized": None,
                "vol_ratio": None,
                "is_implied_vol": True,
                "description": f"Vol Index {vix_curr:.2f} [{state}] | 5D Vel: {vix_velocity:+.1f}%"
            }

        # Otherwise: compute strictly from the local index's own daily price action
        if index_df is None or index_df.empty or len(index_df) < 10:
            return {
                "score": 0.20,
                "vix": None,
                "vix_velocity_5d": 0.0,
                "vol_state": "CALM",
                "vol_shock": False,
                "realized_vol20": 0.15,
                "realized_vol_annualized": 0.15,
                "vol_ratio": 1.0,
                "is_implied_vol": False,
                "description": "Baseline realized volatility."
            }

        close = index_df["close"]
        ret = close.pct_change().dropna()
        len_ret = len(ret)

        vol20 = float(ret.tail(min(20, len_ret)).std() * np.sqrt(252)) if len_ret >= 5 else 0.15
        if len_ret >= 40:
            vol_base = float(ret.iloc[:-15].tail(min(60, len_ret - 15)).std() * np.sqrt(252))
            vol_trail = float(ret.tail(min(60, len_ret)).std() * np.sqrt(252))
            vol60 = min(vol_trail, vol_base) if vol_base > 0 else vol_trail
        else:
            vol60 = float(ret.tail(min(60, len_ret)).std() * np.sqrt(252)) if len_ret >= 20 else vol20
        vol_ratio = vol20 / (vol60 + 1e-6) if vol60 > 0 else 1.0

        # 5-day volatility velocity
        vol20_5d_ago = float(ret.iloc[:-5].tail(20).std() * np.sqrt(252)) if len_ret >= 25 else vol20
        vol_velocity = ((vol20 - vol20_5d_ago) / vol20_5d_ago * 100) if vol20_5d_ago > 0 else 0.0

        # Universal Relative Volatility: Self-calibrating across any international index
        # (Nifty baseline 22%, FTSE baseline 11%, Nikkei baseline 18%)
        vol_shock = bool(vol_ratio >= 1.35 or vol_velocity >= 40.0 or vol20 >= 0.45)

        if vol_ratio >= 1.60 or vol_velocity >= 60.0 or vol20 >= 0.50:
            state = "CRISIS_PANIC"
            score = 1.0
        elif vol_ratio >= 1.35 or vol_velocity >= 35.0:
            state = "HIGH_STRESS"
            score = 0.80
        elif vol_ratio >= 1.20 or vol_velocity >= 20.0:
            state = "ELEVATED_CAUTION"
            score = 0.50
        elif vol_ratio >= 0.85:
            state = "NORMAL"
            score = 0.20
        else:
            state = "COMPLACENT_CALM"
            score = 0.05

        if vol_shock:
            score = max(score, 0.70)

        return {
            "score": round(score, 3),
            "vix": round(vol20 * 100, 2),  # Proxy as annualized percentage for legacy callers
            "vix_velocity_5d": round(vol_velocity, 1),
            "vol_state": state,
            "vol_shock": vol_shock,
            "realized_vol20": round(vol20, 4),
            "realized_vol_annualized": round(vol20, 4),
            "realized_vol60": round(vol60, 4),
            "vol_ratio": round(vol_ratio, 2),
            "is_implied_vol": False,
            "description": f"Realized Vol: {vol20*100:.1f}% (60D Ratio: {vol_ratio:.2f}x) [{state}]"
        }

    # -------------------------------------------------------------------------
    # Pillar 3: Peak Drawdown (Distance from 252-day / 52-week High)
    # -------------------------------------------------------------------------
    def analyze_drawdown_pillar(self, index_df: pd.DataFrame) -> Dict[str, Any]:
        """Analyzes benchmark peak drawdown across rolling 252-day (1-year) horizon."""
        if index_df is None or index_df.empty or len(index_df) < 5:
            return {
                "score": 0.0,
                "drawdown_pct": 0.0,
                "peak_price": 0.0,
                "current_price": 0.0,
                "is_correction": False,
                "is_bear_market": False,
                "description": "Insufficient drawdown history."
            }

        close = index_df["close"]
        price = float(close.iloc[-1])
        len_close = len(close)

        peak252 = float(close.rolling(window=min(252, len_close), min_periods=min(10, len_close)).max().iloc[-1])
        dd = (price - peak252) / peak252 if peak252 > 0 else 0.0

        if dd <= -0.25:
            state = "CRASH_DRAWDOWN"
            score = 1.0
        elif dd <= -0.18:
            state = "BEAR_DRAWDOWN"
            score = 0.85
        elif dd <= -0.10:
            state = "CORRECTION"
            score = 0.50
        elif dd <= -0.05:
            state = "PULLBACK"
            score = 0.20
        else:
            state = "EXPANSION_NEAR_HIGHS"
            score = 0.0

        return {
            "score": round(score, 3),
            "drawdown_pct": round(dd * 100, 2),
            "peak_price": round(peak252, 2),
            "current_price": round(price, 2),
            "is_correction": bool(dd <= -0.10),
            "is_bear_market": bool(dd <= -0.20),
            "state": state,
            "description": f"Drawdown: {dd*100:.1f}% from 52-Week Peak ${peak252:.2f} [{state}]"
        }

    # -------------------------------------------------------------------------
    # Optional Overlay Pillars (Credit, Rates, Breadth)
    # -------------------------------------------------------------------------
    def analyze_credit_pillar(
        self,
        hyg_df: Optional[pd.DataFrame],
        ief_df: Optional[pd.DataFrame],
        spy_df: Optional[pd.DataFrame] = None
    ) -> Dict[str, Any]:
        """Optional Corporate Credit & Liquidity Radar (HYG / IEF)."""
        if hyg_df is None or ief_df is None or hyg_df.empty or ief_df.empty:
            return {
                "score": 0.25,
                "credit_ratio": None,
                "credit_sma20": None,
                "credit_state": "NEUTRAL",
                "divergence": False,
                "description": "Credit spread data not provided; using neutral default."
            }

        df_credit = pd.DataFrame({"hyg": hyg_df["close"], "ief": ief_df["close"]}).dropna()
        if len(df_credit) < 10:
            return {
                "score": 0.25,
                "credit_ratio": None,
                "credit_sma20": None,
                "credit_state": "NEUTRAL",
                "divergence": False,
                "description": "Insufficient credit data."
            }

        ratio_series = df_credit["hyg"] / df_credit["ief"]
        curr_ratio = float(ratio_series.iloc[-1])
        sma20 = float(ratio_series.rolling(min(20, len(ratio_series))).mean().iloc[-1])
        ratio_change_5d = float((curr_ratio - ratio_series.iloc[-5]) / ratio_series.iloc[-5] * 100) if len(ratio_series) >= 5 else 0.0

        if curr_ratio >= sma20:
            state = "HEALTHY"
            score = 0.0
        elif curr_ratio < (sma20 * 0.985):
            state = "CREDIT_CRUNCH"
            score = 0.90
        else:
            state = "DETERIORATING"
            score = 0.45

        divergence = False
        if spy_df is not None and len(spy_df) >= 20:
            spy_close = spy_df["close"]
            spy_high20 = float(spy_close.rolling(20).max().iloc[-1])
            spy_curr = float(spy_close.iloc[-1])
            is_spy_near_high = (spy_curr >= spy_high20 * 0.985)
            if is_spy_near_high and curr_ratio < sma20:
                divergence = True
                score = max(score, 0.70)

        return {
            "score": round(score, 3),
            "credit_ratio": round(curr_ratio, 4),
            "credit_sma20": round(sma20, 4),
            "ratio_change_5d_pct": round(ratio_change_5d, 2),
            "credit_state": state,
            "divergence": divergence,
            "description": f"Credit Ratio {curr_ratio:.4f} vs 20-SMA {sma20:.4f} [{state}]"
        }

    def analyze_rates_pillar(
        self,
        tnx_df: Optional[pd.DataFrame],
        irx_df: Optional[pd.DataFrame] = None
    ) -> Dict[str, Any]:
        """Optional Sovereign Rates & Yield Curve Radar."""
        if tnx_df is None or tnx_df.empty:
            return {
                "score": 0.20,
                "tnx_yield": None,
                "yield_curve_spread": None,
                "curve_state": "NORMAL",
                "rate_shock": False
            }

        tnx_close = tnx_df["close"]
        tnx_curr = float(tnx_close.iloc[-1])
        tnx_60d_ago = float(tnx_close.iloc[-60]) if len(tnx_close) >= 60 else tnx_curr
        rate_change_60d = (tnx_curr - tnx_60d_ago)
        rate_shock = bool(rate_change_60d >= 0.75)

        spread = None
        curve_state = "NORMAL"
        score = 0.15

        if irx_df is not None and not irx_df.empty:
            irx_close = irx_df["close"]
            irx_curr = float(irx_close.iloc[-1])
            spread = round(tnx_curr - irx_curr, 3)

            if spread < -0.20:
                curve_state = "DEEPLY_INVERTED"
                score = 0.70
            elif spread < 0.0:
                curve_state = "INVERTED"
                score = 0.50
            elif 0.0 <= spread <= 0.25:
                curve_state = "FLAT_UNINVERTING"
                score = 0.40
            else:
                curve_state = "NORMAL_STEEP"
                score = 0.10

        if rate_shock:
            score = max(score, 0.60)

        return {
            "score": round(score, 3),
            "tnx_yield": round(tnx_curr, 2),
            "yield_curve_spread": spread,
            "rate_change_60d": round(rate_change_60d, 2),
            "curve_state": curve_state,
            "rate_shock": rate_shock,
            "description": f"10Y Yield: {tnx_curr:.2f}% | Curve: {curve_state}"
        }

    def analyze_breadth_pillar(
        self,
        rsp_df: Optional[pd.DataFrame],
        spy_df: Optional[pd.DataFrame],
        qqq_df: Optional[pd.DataFrame] = None,
        breadth_pct: Optional[float] = None
    ) -> Dict[str, Any]:
        """Optional Market Breadth & Sector Participation."""
        score = 0.20
        tech_fatigue = False
        qqq_price = None
        qqq_sma50 = None

        if qqq_df is not None and not qqq_df.empty and len(qqq_df) >= 50:
            qqq_close = qqq_df["close"]
            qqq_price = float(qqq_close.iloc[-1])
            qqq_sma50 = float(qqq_close.rolling(50).mean().iloc[-1])
            if qqq_price < qqq_sma50:
                tech_fatigue = True
                score += 0.30

        eq_divergence = False
        if rsp_df is not None and spy_df is not None and not rsp_df.empty and not spy_df.empty:
            df_b = pd.DataFrame({"rsp": rsp_df["close"], "spy": spy_df["close"]}).dropna()
            if len(df_b) >= 20:
                ratio_s = df_b["rsp"] / df_b["spy"]
                eq_ratio = float(ratio_s.iloc[-1])
                sma20 = float(ratio_s.rolling(20).mean().iloc[-1])
                if eq_ratio < (sma20 * 0.99):
                    eq_divergence = True
                    score += 0.25

        if breadth_pct is not None:
            if breadth_pct < 0.30:
                score += 0.40
            elif breadth_pct < 0.45:
                score += 0.20

        score = min(1.0, max(0.0, score))

        return {
            "score": round(score, 3),
            "tech_fatigue": tech_fatigue,
            "eq_weight_divergence": eq_divergence,
            "breadth_pct": round(breadth_pct * 100, 1) if breadth_pct is not None else None,
            "qqq_price": round(qqq_price, 2) if qqq_price is not None else None,
            "qqq_sma50": round(qqq_sma50, 2) if qqq_sma50 is not None else None,
        }

    # -------------------------------------------------------------------------
    # Master Composite Evaluation
    # -------------------------------------------------------------------------
    def evaluate(
        self,
        index_df: Optional[pd.DataFrame] = None,
        vix_df: Optional[pd.DataFrame] = None,
        qqq_df: Optional[pd.DataFrame] = None,
        hyg_df: Optional[pd.DataFrame] = None,
        ief_df: Optional[pd.DataFrame] = None,
        tnx_df: Optional[pd.DataFrame] = None,
        irx_df: Optional[pd.DataFrame] = None,
        rsp_df: Optional[pd.DataFrame] = None,
        breadth_pct: Optional[float] = None,
        spy_df: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        """
        Evaluates universal local-index signals (Trend, Volatility, Drawdown)
        with optional multi-asset overlay pillars where data exists.
        Supports both index_df (generic benchmark) and spy_df (legacy callers).
        """
        target_df = index_df if index_df is not None else spy_df
        if target_df is None or target_df.empty or len(target_df) < 20:
            return {
                "regime": "DATA_OUTAGE_HALT",
                "macro_stress_index": 1.00,
                "trend_ratio": 0.0,
                "max_exposure": 0.00,
                "weights": {"momentum": 0.0, "mean_reversion": 0.0},
                "cash_reserve_pct": 1.00,
                "canaries": ["BENCHMARK_DATA_OUTAGE"],
                "diagnostics": {"error": "Benchmark index data missing or insufficient (< 20 bars)"}
            }

        # 1. Core Universal Pillars (Derived strictly from benchmark index)
        p_trend = self.analyze_trend_pillar(target_df)
        p_vol = self.analyze_volatility_pillar(vix_df=vix_df, index_df=target_df)
        p_dd = self.analyze_drawdown_pillar(target_df)

        # 2. Optional Overlay Pillars
        p_credit = self.analyze_credit_pillar(hyg_df, ief_df, spy_df=target_df)
        p_rates = self.analyze_rates_pillar(tnx_df, irx_df)
        p_breadth = self.analyze_breadth_pillar(rsp_df, target_df, qqq_df, breadth_pct)

        # Calculate composite Macro Stress Index (MSI)
        # If optional overlays are present, blend them with modest weights; otherwise rely on core
        has_credit = bool(hyg_df is not None and ief_df is not None and not hyg_df.empty)
        has_rates = bool(tnx_df is not None and not tnx_df.empty)
        has_breadth = bool(rsp_df is not None or qqq_df is not None or breadth_pct is not None)

        if has_credit or has_rates or has_breadth:
            w_tr = 0.30
            w_vl = 0.25
            w_dd = 0.20
            w_cr = 0.15 if has_credit else 0.0
            w_rt = 0.05 if has_rates else 0.0
            w_br = 0.05 if has_breadth else 0.0
            tot_w = w_tr + w_vl + w_dd + w_cr + w_rt + w_br
            msi = (
                w_tr * p_trend["score"] +
                w_vl * p_vol["score"] +
                w_dd * p_dd["score"] +
                w_cr * p_credit["score"] +
                w_rt * p_rates["score"] +
                w_br * p_breadth["score"]
            ) / tot_w
        else:
            msi = (
                0.40 * p_trend["score"] +
                0.30 * p_vol["score"] +
                0.30 * p_dd["score"]
            )

        msi = round(min(1.0, max(0.0, msi)), 3)

        # Canaries
        canaries = []
        if p_dd.get("is_bear_market"):
            canaries.append("BEAR_MARKET_DRAWDOWN_BREACH")
        if p_vol.get("vol_shock"):
            canaries.append("VOLATILITY_SHOCK_SPIKE")
        if p_credit.get("divergence"):
            canaries.append("CREDIT_SPREAD_DIVERGENCE")
        if p_credit.get("credit_state") == "CREDIT_CRUNCH":
            canaries.append("CREDIT_CRUNCH_LIQUIDITY_STRESS")
        if p_breadth.get("tech_fatigue"):
            canaries.append("TECH_MOMENTUM_FATIGUE")
        if p_rates.get("rate_shock"):
            canaries.append("BOND_YIELD_SPIKE_SHOCK")

        # Universal State Machine
        is_bull_200 = p_trend["is_bull_200"]
        is_severe_breakdown = p_trend["is_severe_breakdown"]
        dd_pct = p_dd["drawdown_pct"]
        vol_score = p_vol["score"]
        vix_val = p_vol.get("vix")

        is_implied_vix = p_vol.get("is_implied_vol", False)

        # 1. CRASH_WARNING (0% exposure, 100% Cash Defense)
        realized_vol = p_vol.get("realized_vol20") or 0.0
        if is_severe_breakdown or \
           (dd_pct <= -20.0 and not is_bull_200) or \
           (vol_score >= 0.85 and not is_bull_200) or \
           (is_implied_vix and vix_val is not None and vix_val >= 35.0) or \
           (realized_vol >= 0.50 and not is_bull_200):
            regime = "CRASH_WARNING"
            max_exposure = 0.00
            strat_weights = {"momentum": 0.0, "mean_reversion": 0.0}
            cash_reserve = 1.00

        # 2. BEAR_CORRECTION (Macro downtrend: Index < 200 SMA or Drawdown <= -12%)
        elif not is_bull_200 or dd_pct <= -12.0:
            regime = "BEAR_CORRECTION"
            max_exposure = 0.40
            strat_weights = {"momentum": 0.20, "mean_reversion": 0.80}
            cash_reserve = 0.60

        # 3. CAUTION (Elevated Volatility or Credit Divergence)
        elif p_credit.get("divergence") or \
             p_credit.get("credit_state") == "CREDIT_CRUNCH" or \
             p_vol.get("vol_shock") or \
             (is_implied_vix and vix_val is not None and vix_val >= 22.0) or \
             (not is_implied_vix and vol_score >= 0.50):
            regime = "CREDIT_DIVERGENCE_CAUTION" if p_credit.get("divergence") else "VOLATILITY_CAUTION"
            max_exposure = 0.65
            strat_weights = {"momentum": 0.25, "mean_reversion": 0.75}
            cash_reserve = 0.35

        # 4. BULL_ROTATION (Mild Pullback or Choppy Efficiency)
        elif p_breadth.get("tech_fatigue") or p_breadth.get("eq_weight_divergence") or (p_trend["trend_ratio"] <= 0.35) or (dd_pct <= -5.0):
            regime = "BULL_ROTATION"
            max_exposure = 0.85
            strat_weights = {"momentum": 0.35, "mean_reversion": 0.65}
            cash_reserve = 0.15

        # 5. GOLDILOCKS BULL EXPANSION (Optimal trending conditions near highs)
        else:
            regime = "BULL_TRENDING"
            max_exposure = 0.95
            strat_weights = {"momentum": 0.70, "mean_reversion": 0.30}
            cash_reserve = 0.05

        diagnostics = {
            "macro_stress_index": msi,
            "regime": regime,
            "max_exposure": max_exposure,
            "cash_reserve_pct": round(cash_reserve * 100, 1),
            "weights": strat_weights,
            "canaries": canaries,
            "trend_pillar": p_trend,
            "volatility_pillar": p_vol,
            "drawdown_pillar": p_dd,
            "credit_pillar": p_credit,
            "rates_pillar": p_rates,
            "breadth_pillar": p_breadth,
            "spy_price": p_trend["diagnostics"].get("spy_price"),
            "spy_sma50": p_trend["diagnostics"].get("spy_sma50"),
            "spy_sma200": p_trend["diagnostics"].get("spy_sma200"),
            "trend_ratio": p_trend.get("trend_ratio"),
            "vix": vix_val,
            "drawdown_pct": dd_pct,
            "credit_ratio": p_credit.get("credit_ratio"),
            "yield_curve_spread": p_rates.get("yield_curve_spread"),
            "tech_fatigue": p_breadth.get("tech_fatigue"),
        }

        return {
            "regime": regime,
            "macro_stress_index": msi,
            "trend_ratio": p_trend.get("trend_ratio", 0.0),
            "max_exposure": max_exposure,
            "weights": strat_weights,
            "cash_reserve_pct": cash_reserve,
            "canaries": canaries,
            "diagnostics": diagnostics,
        }


# =============================================================================
# Backward-Compatibility Shim for Legacy Calls
# =============================================================================
class InstitutionalMacroRegimeEngine(UniversalLocalIndexRegimeEngine):
    """
    Maintains 100% backward compatibility with InstitutionalMacroRegimeEngine calls
    while inheriting the UniversalLocalIndexRegimeEngine.
    """
    pass


class RegimeDetector:
    """
    Legacy shim routing to UniversalLocalIndexRegimeEngine.
    """
    def __init__(self, index_symbol="SPY"):
        self.index_symbol = index_symbol
        self.engine = UniversalLocalIndexRegimeEngine()

    def detect_regime(self, market_data: pd.DataFrame) -> str:
        res = self.engine.evaluate(market_data)
        return res["regime"]
