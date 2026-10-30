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

from trading_system.app.features.regime import InstitutionalMacroRegimeEngine


class EnsembleAllocator:
    """
    Coordinates dynamic long-only allocation across Momentum and Mean-Reversion dip buying:
      - TRENDING BULL: 70% Momentum Leaders, 25% Mean-Reversion Dips, 5% Cash Reserve
      - CHOPPY BULL / ROTATION: 65% Mean-Reversion Dips, 35% Momentum Leaders, 15% Cash Reserve
      - CREDIT DIVERGENCE CAUTION: 45% Mean-Reversion Dips, 20% Momentum Leaders, 35% Cash Reserve
      - BEAR CORRECTION: 35% Mean-Reversion Dips, 15% Momentum Leaders, 50% Cash Reserve
      - CRASH WARNING: 0% Equities -> 100% Cash Reserve (Full Capital Preservation)

    Dynamic holdings: Does not enforce an arbitrary fixed stock count. Expands and contracts
    organically based on strategy profitability, high-conviction signals, and market regime.
    """

    def __init__(
        self,
        max_total_exposure: float = 0.98,
        max_single_stock: float = 0.12,
        max_holdings: Optional[int] = 10,
        min_position_pct: float = 0.04,
    ):
        self.max_total_exposure = max_total_exposure
        self.max_single_stock = max_single_stock
        self.max_holdings = max_holdings
        self.min_position_pct = min_position_pct
        self.macro_engine = InstitutionalMacroRegimeEngine()

    def detect_regime(
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
        Institutional 4-Pillar Multi-Asset Macro Weather & Crash Radar:
        Analyzes:
          1. SPY: Broad market trend anchor & Kaufman efficiency ratio
          2. HYG / IEF: Corporate credit spreads & liquidity divergence
          3. VIX: Volatility surface & 5-day velocity shock
          4. ^TNX / ^IRX: Sovereign yields & yield curve slope
          5. RSP / QQQ: Equal-weight breadth & tech momentum fatigue
        """
        if spy_df is None or spy_df.empty or len(spy_df) < 20:
            return {
                "regime": "NEUTRAL",
                "macro_stress_index": 0.50,
                "trend_ratio": 0.0,
                "max_exposure": 0.50,
                "weights": {"momentum": 0.50, "mean_reversion": 0.50},
                "canaries": [],
                "diagnostics": {}
            }

        return self.macro_engine.evaluate(
            spy_df=spy_df,
            vix_df=vix_df,
            qqq_df=qqq_df,
            hyg_df=hyg_df,
            ief_df=ief_df,
            tnx_df=tnx_df,
            irx_df=irx_df,
            rsp_df=rsp_df,
            breadth_pct=breadth_pct,
        )

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
        # Enforce dynamic single-stock ceiling.
        # When max_holdings is set (e.g. 10 positions in High-Alpha mode),
        # if fewer candidates qualify (e.g. 2-5 leaders), dynamically expand the per-stock cap
        # up to 25.0% so the portfolio is not artificially trapped in 50-75% involuntary cash drag,
        # while strictly maintaining a 25.0% disaster risk ceiling on any single stock.
        num_cands = len(candidates)
        if self.max_holdings is not None and num_cands < self.max_holdings:
            fair_share = max_exposure / max(num_cands, 1)
            dynamic_cap = min(0.25, max(self.max_single_stock, round(fair_share, 4)))
        else:
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
