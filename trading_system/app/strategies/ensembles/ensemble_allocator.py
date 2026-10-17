"""
Phase 2: Alpha Diversification (Moral Core Edition)
Module: Long-Only Multi-Strategy Ensemble Allocator

Coordinates risk allocation across:
  1. Systematic Momentum (Trend Following Leaders)
  2. Mean Reversion (Buying Deep Dips on S&P 500 Quality Leaders)
  3. Liquid Cash Buffer (Capital Preservation / Zero Drawdown in Crises)

Strictly Long-Only: No naked shorting, no borrow fees, no inverse ETF volatility decay traps.
"""

from typing import Dict, Any, List
import pandas as pd
import numpy as np


class EnsembleAllocator:
    """
    Coordinates long-only allocation across Momentum and Mean-Reversion dip buying:
      - TRENDING BULL: 70% Momentum Leaders, 25% Mean-Reversion Dips, 5% Cash Reserve
      - CHOPPY BULL: 50% Mean-Reversion Dips, 35% Momentum Leaders, 15% Cash Reserve
      - BEAR CORRECTION: 30% Mean-Reversion Dips, 20% Momentum Leaders, 50% Cash Reserve
      - CRASH WARNING: 0% Equities -> 100% Cash Reserve (Full Capital Preservation)
    """

    def __init__(
        self,
        max_total_exposure: float = 0.95,
        max_single_stock: float = 0.15,
        max_holdings: int = 25,
    ):
        self.max_total_exposure = max_total_exposure
        self.max_single_stock = max_single_stock
        self.max_holdings = max_holdings

    def detect_regime(self, spy_df: pd.DataFrame) -> Dict[str, Any]:
        """
        Determines market weather using SPY 200 SMA, 20 SMA, and 14-day trend ratio.
        """
        if spy_df.empty or len(spy_df) < 50:
            return {
                "regime": "NEUTRAL",
                "trend_ratio": 0.0,
                "max_exposure": 0.50,
                "weights": {"momentum": 0.50, "mean_reversion": 0.50},
            }

        close = spy_df["close"]
        current_price = close.iloc[-1]
        sma_200 = close.rolling(window=min(200, len(close))).mean().iloc[-1]
        sma_20 = close.rolling(window=min(20, len(close))).mean().iloc[-1]

        # 14-day trend efficiency ratio
        high = spy_df.get("high", close)
        low = spy_df.get("low", close)
        tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
        atr_14 = tr.rolling(14).mean().iloc[-1]
        price_change_14 = (close.iloc[-1] - close.iloc[-15]) if len(close) > 15 else 0
        trend_ratio = abs(price_change_14) / (atr_14 * 14 + 1e-6)

        is_bull = current_price >= sma_200
        is_crash = (current_price < sma_200) and (current_price < sma_20 * 0.95)

        if is_crash:
            return {
                "regime": "CRASH_WARNING",
                "trend_ratio": round(float(trend_ratio), 2),
                "max_exposure": 0.00,  # 100% Cash Reserve
                "weights": {"momentum": 0.0, "mean_reversion": 0.0},
            }
        elif is_bull and trend_ratio > 0.35:
            # Strong Bull Trend -> Prioritize Momentum
            return {
                "regime": "BULL_TRENDING",
                "trend_ratio": round(float(trend_ratio), 2),
                "max_exposure": 0.95,
                "weights": {"momentum": 0.70, "mean_reversion": 0.30},
            }
        elif is_bull and trend_ratio <= 0.35:
            # Choppy Bull -> Prioritize Buying Dips (Mean Reversion)
            return {
                "regime": "BULL_CHOPPY",
                "trend_ratio": round(float(trend_ratio), 2),
                "max_exposure": 0.85,
                "weights": {"momentum": 0.35, "mean_reversion": 0.65},
            }
        else:
            # Bear Correction -> High Cash Buffer
            return {
                "regime": "BEAR_CORRECTION",
                "trend_ratio": round(float(trend_ratio), 2),
                "max_exposure": 0.40,  # 60% Cash
                "weights": {"momentum": 0.30, "mean_reversion": 0.70},
            }

    def combine_allocations(
        self,
        momentum_signals: List[Dict[str, Any]],
        mean_rev_signals: List[Dict[str, Any]],
        regime_info: Dict[str, Any],
    ) -> Dict[str, float]:
        """
        Synthesizes Momentum leaders and Mean-Reversion dip buys into target weights.
        Strictly Long-Only (weights >= 0).
        Caps:
          - Total portfolio exposure <= regime_max_exposure (max 95%)
          - Single stock <= 15%
          - Total holdings <= max_holdings (25)
        """
        max_exposure = regime_info.get("max_exposure", self.max_total_exposure)
        if max_exposure <= 0.0:
            return {}  # 100% Cash

        strat_weights = regime_info.get("weights", {"momentum": 0.60, "mean_reversion": 0.40})
        mom_budget = max_exposure * strat_weights.get("momentum", 0.60)
        mr_budget = max_exposure * strat_weights.get("mean_reversion", 0.40)

        combined_raw: Dict[str, float] = {}

        # 1. Process Momentum Candidates (Filtered to Top Conviction)
        valid_mom = [s for s in momentum_signals if s.get("conviction_score", 0.0) > 0.0]
        valid_mom = sorted(valid_mom, key=lambda s: s.get("conviction_score", 0.0), reverse=True)[:self.max_holdings]
        
        if valid_mom:
            total_mom_score = sum(s.get("conviction_score", 1.0) for s in valid_mom)
            for sig in valid_mom:
                sym = sig["symbol"]
                score = sig.get("conviction_score", 1.0)
                weight = (score / total_mom_score) * mom_budget if total_mom_score > 0 else (mom_budget / len(valid_mom))
                combined_raw[sym] = combined_raw.get(sym, 0.0) + weight

        # 2. Process Mean-Reversion Dip-Buys (signal == 1)
        valid_mr = [s for s in mean_rev_signals if s.get("signal") == 1]
        valid_mr = sorted(valid_mr, key=lambda s: s.get("confidence", 0.7), reverse=True)[:10]

        if valid_mr:
            total_mr_conf = sum(s.get("confidence", 0.7) for s in valid_mr)
            for sig in valid_mr:
                sym = sig["symbol"]
                conf = sig.get("confidence", 0.7)
                weight = (conf / total_mr_conf) * mr_budget if total_mr_conf > 0 else (mr_budget / len(valid_mr))
                combined_raw[sym] = combined_raw.get(sym, 0.0) + weight

        if not combined_raw:
            return {}

        # 3. Filter down to Top max_holdings (25) by combined weight
        top_symbols = sorted(combined_raw.items(), key=lambda x: x[1], reverse=True)[:self.max_holdings]
        
        # 4. Enforce Single-Stock Cap (15%) and Normalize Total Exposure <= max_exposure
        final_targets: Dict[str, float] = {}
        for sym, w in top_symbols:
            final_targets[sym] = min(w, self.max_single_stock)

        total_gross = sum(final_targets.values())
        if total_gross > max_exposure and total_gross > 0:
            scale = max_exposure / total_gross
            final_targets = {sym: round(w * scale, 4) for sym, w in final_targets.items()}
        else:
            final_targets = {sym: round(w, 4) for sym, w in final_targets.items()}

        return final_targets
