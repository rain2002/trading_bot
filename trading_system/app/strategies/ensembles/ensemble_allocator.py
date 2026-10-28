"""
Phase 2: Alpha Diversification (Moral Core Edition)
Module: Long-Only Multi-Strategy Ensemble Allocator

Coordinates risk allocation across:
  1. Systematic Momentum (Trend Following Leaders)
  2. Mean Reversion (Buying Deep Dips on S&P 500 Quality Leaders)
  3. Liquid Cash Buffer (Capital Preservation / Zero Drawdown in Crises)

Strictly Long-Only: No naked shorting, no borrow fees, no inverse ETF volatility decay traps.
"""

from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np


class EnsembleAllocator:
    """
    Coordinates dynamic long-only allocation across Momentum and Mean-Reversion dip buying:
      - TRENDING BULL: 70% Momentum Leaders, 25% Mean-Reversion Dips, 5% Cash Reserve
      - CHOPPY BULL: 50% Mean-Reversion Dips, 35% Momentum Leaders, 15% Cash Reserve
      - BEAR CORRECTION: 30% Mean-Reversion Dips, 20% Momentum Leaders, 50% Cash Reserve
      - CRASH WARNING: 0% Equities -> 100% Cash Reserve (Full Capital Preservation)

    Dynamic holdings: Does not enforce an arbitrary fixed stock count. Expands and contracts
    organically based on strategy profitability, high-conviction signals, and market regime.
    """

    def __init__(
        self,
        max_total_exposure: float = 0.95,
        max_single_stock: float = 0.15,
        max_holdings: Optional[int] = None,
        min_position_pct: float = 0.015,
    ):
        self.max_total_exposure = max_total_exposure
        self.max_single_stock = max_single_stock
        self.max_holdings = max_holdings
        self.min_position_pct = min_position_pct

    def detect_regime(
        self,
        spy_df: pd.DataFrame,
        vix_df: Optional[pd.DataFrame] = None,
        qqq_df: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        """
        Institutional Multi-Asset Macro Weather & Crash Radar:
        Analyzes:
          1. SPY: Broad market trend anchor (200 SMA, 50 SMA, 14-day trend ratio)
          2. QQQ: Tech / Speculative bubble dispersion canary (50 SMA fatigue)
          3. VIX: Volatility risk & panic indicator
        """
        if spy_df.empty or len(spy_df) < 50:
            return {
                "regime": "NEUTRAL",
                "trend_ratio": 0.0,
                "max_exposure": 0.50,
                "weights": {"momentum": 0.50, "mean_reversion": 0.50},
                "diagnostics": {}
            }

        close = spy_df["close"]
        current_price = float(close.iloc[-1])
        sma_200 = float(close.rolling(window=min(200, len(close))).mean().iloc[-1])
        sma_50 = float(close.rolling(window=min(50, len(close))).mean().iloc[-1])
        sma_20 = float(close.rolling(window=min(20, len(close))).mean().iloc[-1])

        # 14-day trend efficiency ratio
        high = spy_df.get("high", close)
        low = spy_df.get("low", close)
        tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
        atr_14 = float(tr.rolling(14).mean().iloc[-1])
        price_change_14 = float(close.iloc[-1] - close.iloc[-15]) if len(close) > 15 else 0.0
        trend_ratio = abs(price_change_14) / (atr_14 * 14 + 1e-6)

        # Macro Volatility Radar (VIX)
        vix_val = None
        if vix_df is not None and not vix_df.empty:
            vix_val = float(vix_df["close"].iloc[-1])

        # Tech / Mega-cap Divergence Radar (QQQ)
        qqq_below_50 = False
        qqq_price = None
        qqq_sma50 = None
        if qqq_df is not None and not qqq_df.empty and len(qqq_df) >= 50:
            qqq_price = float(qqq_df["close"].iloc[-1])
            qqq_sma50 = float(qqq_df["close"].rolling(50).mean().iloc[-1])
            qqq_below_50 = (qqq_price < qqq_sma50)

        is_bull = current_price >= sma_200

        # Multi-factor crash conditions:
        # 1. Structural breakdown: SPY < 200 SMA and below 20 SMA by 5%
        # 2. Early Volatility Shock: SPY < 50 SMA and VIX >= 28.0 (early exit before 200 SMA)
        is_crash = (current_price < sma_200 and current_price < sma_20 * 0.95) or \
                   (vix_val is not None and vix_val >= 28.0 and current_price < sma_50)

        diagnostics = {
            "spy_price": round(current_price, 2),
            "spy_sma50": round(sma_50, 2),
            "spy_sma200": round(sma_200, 2),
            "trend_ratio": round(float(trend_ratio), 2),
            "vix": round(vix_val, 2) if vix_val is not None else None,
            "qqq_price": round(qqq_price, 2) if qqq_price is not None else None,
            "qqq_sma50": round(qqq_sma50, 2) if qqq_sma50 is not None else None,
            "tech_fatigue": qqq_below_50,
        }

        if is_crash:
            return {
                "regime": "CRASH_WARNING",
                "trend_ratio": round(float(trend_ratio), 2),
                "max_exposure": 0.00,  # 100% Cash Reserve
                "weights": {"momentum": 0.0, "mean_reversion": 0.0},
                "diagnostics": diagnostics,
            }

        # Elevated Volatility Caution: VIX elevated between 22.0 and 28.0
        if vix_val is not None and vix_val >= 22.0:
            return {
                "regime": "VOLATILITY_CAUTION",
                "trend_ratio": round(float(trend_ratio), 2),
                "max_exposure": 0.60,  # 40% Cash Defense
                "weights": {"momentum": 0.25, "mean_reversion": 0.75},
                "diagnostics": diagnostics,
            }

        if is_bull and trend_ratio > 0.35:
            # If tech is tiring (QQQ < 50 SMA), tilt towards mean-reversion rotation
            if qqq_below_50:
                return {
                    "regime": "BULL_ROTATION",
                    "trend_ratio": round(float(trend_ratio), 2),
                    "max_exposure": 0.85,
                    "weights": {"momentum": 0.40, "mean_reversion": 0.60},
                    "diagnostics": diagnostics,
                }
            return {
                "regime": "BULL_TRENDING",
                "trend_ratio": round(float(trend_ratio), 2),
                "max_exposure": 0.95,
                "weights": {"momentum": 0.70, "mean_reversion": 0.30},
                "diagnostics": diagnostics,
            }
        elif is_bull and trend_ratio <= 0.35:
            # Choppy Bull -> Heavy Mean Reversion Dip-Buying
            # If tech fatigue is active, reduce momentum allocation and tilt towards value dip-buys
            mom_weight = 0.25 if qqq_below_50 else 0.35
            mr_weight = 0.75 if qqq_below_50 else 0.65
            return {
                "regime": "BULL_CHOPPY",
                "trend_ratio": round(float(trend_ratio), 2),
                "max_exposure": 0.85,
                "weights": {"momentum": mom_weight, "mean_reversion": mr_weight},
                "diagnostics": diagnostics,
            }
        else:
            # Bear Correction -> 60% Cash Defense
            return {
                "regime": "BEAR_CORRECTION",
                "trend_ratio": round(float(trend_ratio), 2),
                "max_exposure": 0.40,  # 60% Cash
                "weights": {"momentum": 0.30, "mean_reversion": 0.70},
                "diagnostics": diagnostics,
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
          - Total holdings: Dynamic based on conviction & profitability (or capped if max_holdings is set)
          - Minimum position size hurdle: min_position_pct (default 1.5%)
        """
        max_exposure = regime_info.get("max_exposure", self.max_total_exposure)
        if max_exposure <= 0.0:
            return {}  # 100% Cash

        strat_weights = regime_info.get("weights", {"momentum": 0.60, "mean_reversion": 0.40})
        raw_mom_ratio = strat_weights.get("momentum", 0.60)
        raw_mr_ratio = strat_weights.get("mean_reversion", 0.40)

        # 1. Process Momentum Candidates (Filtered to Positive Conviction)
        valid_mom = [s for s in momentum_signals if s.get("conviction_score", 0.0) > 0.0]
        valid_mom = sorted(valid_mom, key=lambda s: s.get("conviction_score", 0.0), reverse=True)
        if self.max_holdings is not None:
            valid_mom = valid_mom[:self.max_holdings]

        # 2. Process Mean-Reversion Dip-Buys (signal == 1)
        valid_mr = [s for s in mean_rev_signals if s.get("signal") == 1]
        valid_mr = sorted(valid_mr, key=lambda s: s.get("confidence", 0.7), reverse=True)
        if self.max_holdings is not None:
            valid_mr = valid_mr[:self.max_holdings]

        # ADAPTIVE WATERFALL BUDGETING:
        # If one sub-strategy generates zero signals, its unspent budget dynamically
        # flows to the active strategy up to max_exposure, preventing false capital dry-ups.
        if not valid_mr and valid_mom:
            mom_budget = max_exposure
            mr_budget = 0.0
        elif not valid_mom and valid_mr:
            mr_budget = max_exposure
            mom_budget = 0.0
        elif valid_mom and valid_mr:
            mom_budget = max_exposure * raw_mom_ratio
            mr_budget = max_exposure * raw_mr_ratio
        else:
            return {}  # Zero valid signals across all strategies -> 100% Cash

        combined_raw: Dict[str, float] = {}
        
        if valid_mom:
            total_mom_score = sum(s.get("conviction_score", 1.0) for s in valid_mom)
            for sig in valid_mom:
                sym = sig["symbol"]
                score = sig.get("conviction_score", 1.0)
                weight = (score / total_mom_score) * mom_budget if total_mom_score > 0 else (mom_budget / len(valid_mom))
                combined_raw[sym] = combined_raw.get(sym, 0.0) + weight

        if valid_mr:
            total_mr_conf = sum(s.get("confidence", 0.7) for s in valid_mr)
            for sig in valid_mr:
                sym = sig["symbol"]
                conf = sig.get("confidence", 0.7)
                weight = (conf / total_mr_conf) * mr_budget if total_mr_conf > 0 else (mr_budget / len(valid_mr))
                combined_raw[sym] = combined_raw.get(sym, 0.0) + weight

        if not combined_raw:
            return {}

        # 3. Dynamic Selection: Rank candidates by combined conviction weight
        candidates = sorted(combined_raw.items(), key=lambda x: x[1], reverse=True)
        if self.max_holdings is not None:
            candidates = candidates[:self.max_holdings]

        # Filter out sub-hurdle dust positions (< min_position_pct)
        if self.min_position_pct > 0.0:
            candidates = [(sym, w) for sym, w in candidates if w >= self.min_position_pct]

        if not candidates:
            return {}

        # 4. Single-Stock Cap Sizing:
        # Enforce strict single-stock ceiling (self.max_single_stock, default 15.0%)
        # Excess conviction weight is redistributed across remaining uncapped candidates.
        # If few candidates qualify, exposure contracts organically into cash reserve.
        dynamic_cap = self.max_single_stock
        self.last_effective_cap = dynamic_cap

        # Enforce dynamic single-stock cap with iterative redistribution
        # Redistributes excess weight to uncapped candidates up to max_exposure
        weights_dict = {sym: w for sym, w in candidates}
        for _ in range(5):
            excess = 0.0
            uncapped_syms = []
            for sym, w in weights_dict.items():
                if w > dynamic_cap:
                    excess += (w - dynamic_cap)
                    weights_dict[sym] = dynamic_cap
                elif w < dynamic_cap:
                    uncapped_syms.append(sym)
            if excess <= 1e-6 or not uncapped_syms:
                break
            add_per_sym = excess / len(uncapped_syms)
            for sym in uncapped_syms:
                weights_dict[sym] += add_per_sym

        final_targets: Dict[str, float] = {
            sym: min(round(w, 4), dynamic_cap) for sym, w in weights_dict.items()
        }

        # Filter out positions below min_position_pct if any
        if self.min_position_pct > 0.0:
            final_targets = {sym: w for sym, w in final_targets.items() if w >= self.min_position_pct}

        total_gross = sum(final_targets.values())
        if total_gross > 0 and total_gross < (max_exposure * 0.90) and len(final_targets) >= 1:
            scale = min(max_exposure / total_gross, 1.50)
            final_targets = {
                sym: min(round(w * scale, 4), dynamic_cap)
                for sym, w in final_targets.items()
            }
        elif total_gross > max_exposure and total_gross > 0:
            scale = max_exposure / total_gross
            final_targets = {sym: round(w * scale, 4) for sym, w in final_targets.items()}
        else:
            final_targets = {sym: round(w, 4) for sym, w in final_targets.items()}

        # Guarantee strict mathematical non-exceedance of max_exposure after rounding
        current_sum = sum(final_targets.values())
        if current_sum > max_exposure:
            overage = current_sum - max_exposure
            for sym in sorted(final_targets, key=lambda s: final_targets[s], reverse=True):
                trim = min(round(overage, 4), 0.0001)
                final_targets[sym] = round(final_targets[sym] - trim, 4)
                overage -= trim
                if overage <= 1e-6:
                    break

        return final_targets
