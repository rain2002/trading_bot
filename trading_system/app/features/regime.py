"""
Institutional Macro Regime Engine.
Implements a 4-Pillar Multi-Asset Macroeconomic & Tail-Risk Framework:
  1. Equity Trend & Efficiency Pillar (SPY / Benchmark, Kaufman Trend Ratio)
  2. Corporate Credit & Liquidity Pillar (HYG / IEF ratio, Credit Spread Divergence)
  3. Volatility Surface & Tail-Risk Pillar (VIX, 5-Day Volatility Velocity)
  4. Sovereign Rates & Yield Curve Pillar (10-Year Yield, Yield Curve Spread)
  5. Market Breadth & Sector Participation Pillar (Equal-Weight RSP/SPY, QQQ Tech Fatigue)
"""

from typing import Dict, Any, Optional, List
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger("InstitutionalMacroRegime")


class InstitutionalMacroRegimeEngine:
    """
    Multi-Asset Macroeconomic Regime & Tail-Risk Engine used by institutional systematic funds.
    Synthesizes rates, credit spreads, equity breadth, and volatility surface into a
    continuous Macro Stress Index (MSI) in [0.0, 1.0] and discrete macro regime states.
    """

    def __init__(
        self,
        trend_weight: float = 0.30,
        credit_weight: float = 0.25,
        vol_weight: float = 0.25,
        rates_weight: float = 0.10,
        breadth_weight: float = 0.10,
    ):
        self.w_trend = trend_weight
        self.w_credit = credit_weight
        self.w_vol = vol_weight
        self.w_rates = rates_weight
        self.w_breadth = breadth_weight

    # -------------------------------------------------------------------------
    # Pillar 1: Equity Trend & Structural Efficiency (SPY)
    # -------------------------------------------------------------------------
    def analyze_trend_pillar(self, spy_df: pd.DataFrame) -> Dict[str, Any]:
        """Analyzes broad market trend, 200/50/20 moving averages, and Kaufman Efficiency Ratio."""
        if spy_df is None or spy_df.empty or len(spy_df) < 20:
            return {
                "score": 0.5,
                "is_bull_200": True,
                "is_bull_50": True,
                "trend_ratio": 0.5,
                "distance_to_200_pct": 0.0,
                "distance_to_50_pct": 0.0,
                "diagnostics": {"spy_price": 0.0, "sma200": 0.0, "sma50": 0.0}
            }

        close = spy_df["close"]
        price = float(close.iloc[-1])
        len_close = len(close)

        sma200 = float(close.rolling(window=min(200, len_close)).mean().iloc[-1])
        sma50 = float(close.rolling(window=min(50, len_close)).mean().iloc[-1])
        sma20 = float(close.rolling(window=min(20, len_close)).mean().iloc[-1])

        dist_200 = (price - sma200) / sma200 * 100 if sma200 > 0 else 0.0
        dist_50 = (price - sma50) / sma50 * 100 if sma50 > 0 else 0.0

        # Kaufman Efficiency Ratio: |net change| / sum(absolute price changes)
        high = spy_df.get("high", close)
        low = spy_df.get("low", close)
        tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
        atr14 = float(tr.rolling(14).mean().iloc[-1])
        change14 = abs(float(close.iloc[-1] - close.iloc[-15])) if len_close > 15 else 0.0
        trend_ratio = min(1.0, change14 / (atr14 * 14 + 1e-6))

        # Stress Score: 0.0 = perfect strong bull trend, 1.0 = deep severe bear breakdown
        stress = 0.0
        if price < sma200:
            stress += 0.50
        elif dist_200 < 2.0:
            stress += 0.20

        if price < sma50:
            stress += 0.30

        if trend_ratio < 0.20:
            stress += 0.20  # Choppy / inefficient price discovery

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
                "spy_price": round(price, 2),
                "spy_sma50": round(sma50, 2),
                "spy_sma200": round(sma200, 2),
            }
        }

    # -------------------------------------------------------------------------
    # Pillar 2: Corporate Credit & Liquidity Radar (HYG / IEF)
    # -------------------------------------------------------------------------
    def analyze_credit_pillar(
        self,
        hyg_df: Optional[pd.DataFrame],
        ief_df: Optional[pd.DataFrame],
        spy_df: Optional[pd.DataFrame] = None
    ) -> Dict[str, Any]:
        """
        Calculates HYG/IEF ratio. Corporate bond spreads lead equity markets by 2-4 weeks.
        Detects credit spread widening and bearish credit divergence.
        """
        if hyg_df is None or ief_df is None or hyg_df.empty or ief_df.empty:
            return {
                "score": 0.25,
                "credit_ratio": None,
                "credit_sma20": None,
                "credit_state": "NEUTRAL",
                "divergence": False,
                "description": "Credit spread data not provided; using neutral default."
            }

        hyg_close = hyg_df["close"]
        ief_close = ief_df["close"]

        # Align series by index
        df_credit = pd.DataFrame({"hyg": hyg_close, "ief": ief_close}).dropna()
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

        # Credit state classification
        if curr_ratio >= sma20:
            state = "HEALTHY"
            score = 0.0
        elif curr_ratio < (sma20 * 0.985):
            state = "CREDIT_CRUNCH"
            score = 0.90
        else:
            state = "DETERIORATING"
            score = 0.45

        # Credit Divergence Check:
        # If SPY is near 20-day high but credit ratio is below its 20-day SMA, credit is refusing to confirm equity strength
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

    # -------------------------------------------------------------------------
    # Pillar 3: Volatility Surface & Tail-Risk Radar (VIX)
    # -------------------------------------------------------------------------
    def analyze_volatility_pillar(self, vix_df: Optional[pd.DataFrame]) -> Dict[str, Any]:
        """Analyzes implied volatility level and 5-day velocity shock."""
        if vix_df is None or vix_df.empty:
            return {
                "score": 0.20,
                "vix": None,
                "vix_velocity_5d": 0.0,
                "vol_state": "CALM",
                "vol_shock": False
            }

        close = vix_df["close"]
        vix_curr = float(close.iloc[-1])
        vix_5d_ago = float(close.iloc[-6]) if len(close) >= 6 else vix_curr
        vix_velocity = ((vix_curr - vix_5d_ago) / vix_5d_ago * 100) if vix_5d_ago > 0 else 0.0

        # Rapid jump in volatility (+25% in 5 days) indicates a tail-risk event
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
            "description": f"VIX {vix_curr:.2f} [{state}] | 5D Vel: {vix_velocity:+.1f}%"
        }

    # -------------------------------------------------------------------------
    # Pillar 4: Sovereign Rates & Yield Curve Radar (10Y Yield & Slope)
    # -------------------------------------------------------------------------
    def analyze_rates_pillar(
        self,
        tnx_df: Optional[pd.DataFrame],
        irx_df: Optional[pd.DataFrame] = None
    ) -> Dict[str, Any]:
        """
        Analyzes 10-Year Treasury Yield (^TNX) and Yield Curve Slope (^TNX - ^IRX).
        Yield curve inversion and sudden rate shocks dictate monetary tightening severity.
        """
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

        # Rate Shock: 10Y yield surges > +0.75% (75 bps) in 60 days
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
            "description": f"10Y Yield: {tnx_curr:.2f}% | Curve: {curve_state} (Spread: {spread if spread is not None else 'N/A'})"
        }

    # -------------------------------------------------------------------------
    # Pillar 5: Market Breadth & Sector Participation (RSP/SPY, QQQ, Internal %)
    # -------------------------------------------------------------------------
    def analyze_breadth_pillar(
        self,
        rsp_df: Optional[pd.DataFrame],
        spy_df: Optional[pd.DataFrame],
        qqq_df: Optional[pd.DataFrame] = None,
        breadth_pct: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Analyzes equal-weight vs cap-weight (RSP / SPY), QQQ tech fatigue, and internal breadth (% > 50 SMA).
        Mega-caps frequently mask severe systemic distribution under the hood.
        """
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

        # Equal-Weight RSP / SPY ratio
        eq_ratio = None
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

        # Direct Internal Breadth (% of stocks above 50-day SMA)
        if breadth_pct is not None:
            if breadth_pct < 0.30:
                score += 0.40  # Washed out / severe breadth breakdown
            elif breadth_pct < 0.45:
                score += 0.20  # Narrow market breadth

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
    # Composite Master Evaluation
    # -------------------------------------------------------------------------
    def evaluate(
        self,
        spy_df: pd.DataFrame,
        vix_df: Optional[pd.DataFrame] = None,
        qqq_df: Optional[pd.DataFrame] = None,
        hyg_df: Optional[pd.DataFrame] = None,
        ief_df: Optional[pd.DataFrame] = None,
        tnx_df: Optional[pd.DataFrame] = None,
        irx_df: Optional[pd.DataFrame] = None,
        rsp_df: Optional[pd.DataFrame] = None,
        breadth_pct: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Executes full 4-Pillar institutional analysis and computes composite Macro Stress Index.
        """
        p_trend = self.analyze_trend_pillar(spy_df)
        p_credit = self.analyze_credit_pillar(hyg_df, ief_df, spy_df=spy_df)
        p_vol = self.analyze_volatility_pillar(vix_df)
        p_rates = self.analyze_rates_pillar(tnx_df, irx_df)
        p_breadth = self.analyze_breadth_pillar(rsp_df, spy_df, qqq_df, breadth_pct)

        # Composite Macro Stress Index (0.0 = Peak Stability, 1.0 = Severe Crisis)
        msi = (
            self.w_trend * p_trend["score"] +
            self.w_credit * p_credit["score"] +
            self.w_vol * p_vol["score"] +
            self.w_rates * p_rates["score"] +
            self.w_breadth * p_breadth["score"]
        )
        msi = round(min(1.0, max(0.0, msi)), 3)

        # Canary Flags
        canaries = []
        if p_credit.get("divergence"):
            canaries.append("CREDIT_SPREAD_DIVERGENCE")
        if p_credit.get("credit_state") == "CREDIT_CRUNCH":
            canaries.append("CREDIT_CRUNCH_LIQUIDITY_STRESS")
        if p_vol.get("vol_shock"):
            canaries.append("VOLATILITY_SHOCK_SPIKE")
        if p_breadth.get("tech_fatigue"):
            canaries.append("TECH_MOMENTUM_FATIGUE")
        if p_breadth.get("eq_weight_divergence"):
            canaries.append("EQUAL_WEIGHT_BREADTH_DIVERGENCE")
        if p_rates.get("rate_shock"):
            canaries.append("BOND_YIELD_SPIKE_SHOCK")

        # ---------------------------------------------------------------------
        # Institutional State Machine
        # ---------------------------------------------------------------------
        is_bull_200 = p_trend["is_bull_200"]
        is_severe_breakdown = p_trend["is_severe_breakdown"]
        vix_val = p_vol.get("vix")

        # 1. SYSTEMIC CRASH WARNING (100% Cash Buffer)
        # Conditions: Severe trend breakdown OR Extreme VIX panic >= 28 with credit stress
        if (is_severe_breakdown) or \
           (vix_val is not None and vix_val >= 28.0 and not is_bull_200) or \
           (vix_val is not None and vix_val >= 35.0):
            regime = "CRASH_WARNING"
            max_exposure = 0.00
            strat_weights = {"momentum": 0.0, "mean_reversion": 0.0}
            cash_reserve = 1.00

        # 2. BEAR CORRECTION (Macro downtrend: SPY < 200 SMA)
        elif not is_bull_200:
            regime = "BEAR_CORRECTION"
            max_exposure = 0.40
            strat_weights = {"momentum": 0.20, "mean_reversion": 0.80}
            cash_reserve = 0.60

        # 3. CREDIT DIVERGENCE / VOLATILITY CAUTION (Pre-emptive Liquidity Defense)
        elif p_credit.get("divergence") or p_credit.get("credit_state") == "CREDIT_CRUNCH" or (vix_val is not None and vix_val >= 22.0):
            regime = "CREDIT_DIVERGENCE_CAUTION" if p_credit.get("divergence") else "VOLATILITY_CAUTION"
            max_exposure = 0.65
            strat_weights = {"momentum": 0.25, "mean_reversion": 0.75}
            cash_reserve = 0.35

        # 4. BULL ROTATION (Tech fatigue / Breadth dispersion)
        elif p_breadth.get("tech_fatigue") or p_breadth.get("eq_weight_divergence") or (p_trend["trend_ratio"] <= 0.35):
            regime = "BULL_ROTATION"
            max_exposure = 0.85
            strat_weights = {"momentum": 0.35, "mean_reversion": 0.65}
            cash_reserve = 0.15

        # 5. GOLDILOCKS BULL EXPANSION (Optimal institutional trending conditions)
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
            "credit_pillar": p_credit,
            "volatility_pillar": p_vol,
            "rates_pillar": p_rates,
            "breadth_pillar": p_breadth,
            "spy_price": p_trend["diagnostics"].get("spy_price"),
            "spy_sma50": p_trend["diagnostics"].get("spy_sma50"),
            "spy_sma200": p_trend["diagnostics"].get("spy_sma200"),
            "trend_ratio": p_trend.get("trend_ratio"),
            "vix": vix_val,
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
# Backward-Compatibility Shim for Legacy RegimeDetector calls
# =============================================================================
class RegimeDetector:
    """
    Maintains backward compatibility with legacy calls across the system
    while routing under the hood to InstitutionalMacroRegimeEngine.
    """
    def __init__(self, index_symbol="SPY"):
        self.index_symbol = index_symbol
        self.engine = InstitutionalMacroRegimeEngine()

    def detect_regime(self, market_data: pd.DataFrame) -> str:
        """Evaluates legacy single-dataframe regime call."""
        res = self.engine.evaluate(market_data)
        return res["regime"]
