"""
Phase 2: Alpha Diversification
Module: Multi-Strategy Ensemble Allocator
Combines Momentum, Mean Reversion, and Market-Neutral Pairs Trading
based on market regime detection (Trend vs Chop vs Crisis).
"""

from typing import Dict, Any, List
import pandas as pd
import numpy as np


class EnsembleAllocator:
    """
    Coordinates risk allocation across multiple strategy engines:
      1. Momentum (Trend Following)
      2. Mean Reversion (Bollinger/RSI Dips)
      3. Statistical Pairs Trading (Market Neutral)
      
    Dynamically reallocates strategy weights based on Market Regime:
      - TRENDING (ADX > 25, SPY > 200 SMA): High Momentum weight (60%)
      - CHOP / SIDEWAYS (ADX <= 25): High Mean Reversion weight (50%)
      - CRISIS / HIGH VOL (SPY < 200 SMA): Defensive, Pairs Trading + Cash
    """

    def __init__(
        self,
        max_total_exposure: float = 0.95,
        max_single_stock: float = 0.15,
    ):
        self.max_total_exposure = max_total_exposure
        self.max_single_stock = max_single_stock

    def detect_regime(self, spy_df: pd.DataFrame) -> Dict[str, Any]:
        """
        Determines market regime using SPY 200-day SMA and 14-day ADX (trend strength).
        """
        if spy_df.empty or len(spy_df) < 50:
            return {"regime": "NEUTRAL", "trend_strength": 0.0, "weights": {"momentum": 0.5, "mean_reversion": 0.3, "pairs": 0.2}}

        close = spy_df["close"]
        current_price = close.iloc[-1]
        sma_200 = close.rolling(window=min(200, len(close))).mean().iloc[-1]

        # Calculate simplified 14-day directional movement / trend strength
        high = spy_df.get("high", close)
        low = spy_df.get("low", close)
        tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
        atr_14 = tr.rolling(14).mean().iloc[-1]
        price_change_14 = (close.iloc[-1] - close.iloc[-15]) if len(close) > 15 else 0
        trend_ratio = abs(price_change_14) / (atr_14 * 14 + 1e-6)

        is_bull_regime = current_price >= sma_200

        if is_bull_regime and trend_ratio > 0.35:
            # Strong Bull Trend: Favor Momentum
            return {
                "regime": "BULL_TRENDING",
                "trend_ratio": round(float(trend_ratio), 2),
                "weights": {"momentum": 0.60, "mean_reversion": 0.20, "pairs": 0.20},
            }
        elif is_bull_regime and trend_ratio <= 0.35:
            # Bull Market Chop: Favor Mean Reversion buying dips
            return {
                "regime": "BULL_CHOPPY",
                "trend_ratio": round(float(trend_ratio), 2),
                "weights": {"momentum": 0.25, "mean_reversion": 0.50, "pairs": 0.25},
            }
        else:
            # Bear / Crisis Regime: Reduce risk, prioritize Market-Neutral Pairs & Cash
            return {
                "regime": "BEAR_CRISIS",
                "trend_ratio": round(float(trend_ratio), 2),
                "weights": {"momentum": 0.10, "mean_reversion": 0.20, "pairs": 0.40},
            }

    def combine_allocations(
        self,
        momentum_signals: List[Dict[str, Any]],
        mean_rev_signals: List[Dict[str, Any]],
        pairs_signals: List[Dict[str, Any]],
        regime_info: Dict[str, Any],
    ) -> Dict[str, float]:
        """
        Synthesizes signals from all 3 engines into normalized portfolio target weights.
        Guarantees:
          1. Total absolute exposure <= max_total_exposure (95%)
          2. No single stock > max_single_stock (15%)
        """
        strat_weights = regime_info.get("weights", {"momentum": 0.4, "mean_reversion": 0.4, "pairs": 0.2})
        combined_raw: Dict[str, float] = {}

        # 1. Process Momentum Signals
        if momentum_signals:
            weight_per_mom = (self.max_total_exposure * strat_weights["momentum"]) / len(momentum_signals)
            for sig in momentum_signals:
                sym = sig["symbol"]
                combined_raw[sym] = combined_raw.get(sym, 0.0) + (weight_per_mom * sig.get("confidence", 1.0))

        # 2. Process Mean Reversion Signals
        active_mr = [s for s in mean_rev_signals if s.get("signal") == 1]
        if active_mr:
            weight_per_mr = (self.max_total_exposure * strat_weights["mean_reversion"]) / len(active_mr)
            for sig in active_mr:
                sym = sig["symbol"]
                combined_raw[sym] = combined_raw.get(sym, 0.0) + (weight_per_mr * sig.get("confidence", 1.0))

        # 3. Process Pairs Trading Signals (Market Neutral Allocations)
        for pair_res in pairs_signals:
            pair_alloc = pair_res.get("allocations", {})
            pair_budget = self.max_total_exposure * strat_weights["pairs"] / max(1, len(pairs_signals))
            for sym, sub_weight in pair_alloc.items():
                if sub_weight != 0:
                    combined_raw[sym] = combined_raw.get(sym, 0.0) + (pair_budget * sub_weight)

        # 4. Enforce Risk Constraints: Cap each asset at max_single_stock (15%)
        capped_weights: Dict[str, float] = {}
        for sym, weight in combined_raw.items():
            if weight > 0:
                capped_weights[sym] = min(weight, self.max_single_stock)
            elif weight < 0:
                capped_weights[sym] = max(weight, -self.max_single_stock)

        # 5. Normalize total gross exposure <= max_total_exposure (95%)
        gross_exposure = sum(abs(w) for w in capped_weights.values())
        if gross_exposure > self.max_total_exposure and gross_exposure > 0:
            scale_factor = self.max_total_exposure / gross_exposure
            final_weights = {sym: round(w * scale_factor, 4) for sym, w in capped_weights.items()}
        else:
            final_weights = {sym: round(w, 4) for sym, w in capped_weights.items()}

        return final_weights
