import os
import json
import logging
import joblib
from datetime import datetime
from typing import Dict, Any, List, Optional
import pandas as pd
from trading_system.app.models.core import Strategy, PortfolioDecision
from trading_system.app.common.database import SessionLocal
from trading_system.app.data.yfinance_provider import YFinanceDataProvider
from trading_system.app.strategies.ensembles.mean_reversion import MeanReversionStrategy
from trading_system.app.ml.feature_pipeline import MLFeaturePipeline

logger = logging.getLogger("QuantEngine")


class InvestorSkillsHeuristics:
    """
    Structured judgment and sizing heuristics for systematic momentum.
    """
    _cached_params: Optional[Dict[str, int]] = None
    _last_mtime: float = 0.0

    @classmethod
    def get_dynamic_params(cls, force_reload: bool = False) -> Dict[str, int]:
        config_path = os.path.join(os.path.dirname(__file__), "..", "config", "dynamic_params.json")
        current_mtime = os.path.getmtime(config_path) if os.path.exists(config_path) else 0.0

        if not force_reload and cls._cached_params is not None and current_mtime <= cls._last_mtime:
            return cls._cached_params

        fast_sma = 20
        slow_sma = 50

        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    params = json.load(f)
                    fast_sma = params.get("fast_sma", 20)
                    slow_sma = params.get("slow_sma", 50)
                    cls._last_mtime = current_mtime
            except Exception:
                pass

        cls._cached_params = {"fast_sma": fast_sma, "slow_sma": slow_sma}
        return cls._cached_params

    @staticmethod
    def apply_judgment(
        symbol: str,
        data_context: pd.DataFrame,
        fast_sma_window: Optional[int] = None,
        slow_sma_window: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Uses moving averages and rate-of-change to calculate risk-adjusted momentum conviction.
        """
        if fast_sma_window is None or slow_sma_window is None:
            params = InvestorSkillsHeuristics.get_dynamic_params()
            fast_sma_window = params["fast_sma"]
            slow_sma_window = params["slow_sma"]

        if data_context.empty or len(data_context) < max(fast_sma_window, slow_sma_window):
            return {"confidence": 0.0, "conviction_score": 0.0, "rationale": "Insufficient data.", "target_weight": 0.0}

        # Prefer adj_close if available to account for splits, fallback to close
        close_prices = data_context.get("adj_close", data_context["close"])
        sma_fast = close_prices.rolling(window=fast_sma_window).mean().iloc[-1]
        sma_slow = close_prices.rolling(window=slow_sma_window).mean().iloc[-1]
        current_price = close_prices.iloc[-1]

        # Bullish Trend: Price > SMA_fast > SMA_slow
        if current_price > sma_fast and sma_fast > sma_slow:
            # 1. Trend Extension (Distance above trend anchor)
            trend_extension = (current_price - sma_slow) / sma_slow if sma_slow > 0 else 0.0

            # 2. 20-Day Velocity / Rate of Change
            lookback_roc = min(20, len(close_prices) - 1)
            past_price = close_prices.iloc[-lookback_roc]
            roc_20 = (current_price - past_price) / past_price if past_price > 0 else 0.0

            # 3. Volatility / Smoothness Adjustment
            returns_tail = close_prices.pct_change().tail(20)
            vol_20 = float(returns_tail.std()) * (252 ** 0.5) if len(returns_tail) > 5 else 0.20

            # 4. Composite Conviction Score (Risk-Adjusted Momentum)
            conviction_score = round(float((roc_20 / (vol_20 + 0.05)) * 0.7 + trend_extension * 0.3), 4)
            confidence = min(0.99, max(0.70, round(0.75 + conviction_score * 0.05, 2)))

            return {
                "confidence": confidence,
                "conviction_score": conviction_score,
                "trend_extension_pct": round(trend_extension * 100, 2),
                "roc_20_pct": round(roc_20 * 100, 2),
                "rationale": f"Bullish Leader: ROC20={roc_20*100:.1f}%, TrendExt={trend_extension*100:.1f}%, Score={conviction_score:.2f}",
                "target_weight": 0.05
            }
        elif current_price < sma_fast and sma_fast < sma_slow:
            return {
                "confidence": 0.20,
                "conviction_score": -1.0,
                "rationale": f"Bearish trend detected (Price < {fast_sma_window}SMA < {slow_sma_window}SMA).",
                "target_weight": 0.0
            }
        else:
            return {
                "confidence": 0.50,
                "conviction_score": 0.0,
                "rationale": "Sideways chop. Staying out.",
                "target_weight": 0.0
            }

    @classmethod
    def evaluate_holding_exit(
        cls,
        symbol: str,
        df: pd.DataFrame,
        current_plpc: float = 0.0,
        regime: str = "BULL_CHOPPY",
        mr_strategy: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Unified Institutional Holding & Exit Logic:
        Determines whether an open position should be EXITED (liquidated to 0.0) or HELD.
        Prevents whipsaw liquidations during normal chop while strictly cutting catastrophic losses.
        """
        # 1. Hard Stop-Loss Guardrail (-8%)
        if current_plpc <= -0.08:
            return {
                "should_exit": True,
                "reason": f"Hard Stop-Loss breached (Unrealized PnL: {current_plpc*100:.2f}% <= -8.0%)",
                "action": "STOP_LOSS_LIQUIDATE"
            }

        # 2. Macro Regime Crash Guardrail
        if regime == "CRASH_WARNING":
            return {
                "should_exit": True,
                "reason": "Market in CRASH_WARNING regime. Liquidating to 100% Cash Buffer.",
                "action": "CRASH_LIQUIDATE"
            }

        if df.empty or len(df) < 30:
            return {
                "should_exit": False,
                "reason": "Insufficient data; retaining position.",
                "action": "HOLD"
            }

        # 3. Check Mean Reversion state (Oversold Dip-Buy Protection)
        mr_sig = mr_strategy.generate_signal(df) if mr_strategy else {"signal": 0}
        if mr_sig.get("signal") == 1:
            return {
                "should_exit": False,
                "reason": f"Mean-Reversion dip support active ({mr_sig.get('rationale')}); holding for rebound.",
                "action": "HOLD"
            }

        # 4. Check Momentum Trend Health
        params = cls.get_dynamic_params()
        fast_sma = params.get("fast_sma", 20)
        slow_sma = params.get("slow_sma", 50)

        close_prices = df.get("adj_close", df["close"])
        current_price = float(close_prices.iloc[-1])
        sma_fast = float(close_prices.rolling(window=fast_sma).mean().iloc[-1])
        sma_slow = float(close_prices.rolling(window=slow_sma).mean().iloc[-1])

        # If price is above slow SMA, trend is structurally sound
        if current_price >= sma_slow:
            return {
                "should_exit": False,
                "reason": f"Core trend intact: Price (${current_price:.2f}) >= {slow_sma}SMA (${sma_slow:.2f}).",
                "action": "HOLD"
            }

        # If price broke down significantly below slow SMA (> 3%) AND fast SMA is below slow SMA
        if current_price < (sma_slow * 0.97) and sma_fast < sma_slow:
            return {
                "should_exit": True,
                "reason": f"Downtrend breakdown: Price (${current_price:.2f}) < 97% of {slow_sma}SMA (${sma_slow:.2f}) & {fast_sma}SMA < {slow_sma}SMA.",
                "action": "TREND_EXIT"
            }

        # Default: normal consolidation / healthy holding
        return {
            "should_exit": False,
            "reason": f"Normal consolidation (Price: ${current_price:.2f}, PnL: {current_plpc*100:+.1f}%). Preserving holding.",
            "action": "HOLD"
        }


class QuantEngine:
    """
    Multi-Engine Quant Brain coordinating Momentum Leaders, Mean-Reversion Dip-Buys,
    and Phase 3 Machine Learning Alpha Gating (Random Forest).
    """
    def __init__(self, enable_ml_gating: bool = True, ml_min_probability: float = 0.48):
        self.data_provider = YFinanceDataProvider()
        self.mean_reversion = MeanReversionStrategy()
        self.enable_ml_gating = enable_ml_gating
        self.ml_min_probability = ml_min_probability
        self.ml_model = None
        self.ml_pipeline = None
        if self.enable_ml_gating:
            self._load_ml_model()

    def _load_ml_model(self):
        try:
            model_path = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "data", "models", "quant_rf_model.joblib")
            )
            if os.path.exists(model_path):
                self.ml_model = joblib.load(model_path)
                self.ml_pipeline = MLFeaturePipeline()
                num_feats = len(self.ml_model.feature_names_in_) if hasattr(self.ml_model, "feature_names_in_") else 18
                logger.info(f"Phase 3 ML Alpha Gate Loaded: {type(self.ml_model).__name__} with {num_feats} features")
            else:
                logger.warning(f"ML model artifact not found at {model_path}. Running with ML gating disabled.")
                self.ml_model = None
        except Exception as e:
            logger.warning(f"Failed to load Phase 3 ML model: {e}. Falling back to Phase 2 heuristics.")
            self.ml_model = None

    def run_nightly_research(self, universe: List[str], as_of_time: datetime) -> Dict[str, List[Dict[str, Any]]]:
        """
        Runs multi-strategy pipeline across universe with Phase 3 ML Alpha Gating.
        Returns:
          {
            "momentum": List of positive conviction momentum signals,
            "mean_reversion": List of oversold dip-buy signals
          }
        """
        logger.info(f"Starting Quant Multi-Strategy Research Cycle for {len(universe)} symbols as of {as_of_time}")
        params = InvestorSkillsHeuristics.get_dynamic_params()
        fast_sma = params["fast_sma"]
        slow_sma = params["slow_sma"]

        momentum_signals: List[Dict[str, Any]] = []
        mean_rev_signals: List[Dict[str, Any]] = []

        for symbol in universe:
            df = self.data_provider.get_data_as_of(symbol, as_of_time)
            if df.empty or len(df) < 50:
                continue

            # 1. Momentum Leader Judgment
            judgment = InvestorSkillsHeuristics.apply_judgment(symbol, df, fast_sma, slow_sma)
            if judgment["confidence"] > 0.70 and judgment.get("conviction_score", 0.0) > 0.0:
                raw_conviction = judgment.get("conviction_score", 0.0)
                ml_prob = None
                ml_confirmed = True

                # Phase 3 ML Alpha Gate
                if self.enable_ml_gating and self.ml_model is not None and len(df) >= 200:
                    try:
                        feats = self.ml_pipeline.extract_features(df)
                        feat_cols = list(self.ml_model.feature_names_in_)
                        latest_feats = feats[feat_cols].iloc[[-1]]
                        if not latest_feats.isna().any().any():
                            # Probability of forward 5-day alpha > 0.5%
                            ml_prob = float(self.ml_model.predict_proba(latest_feats)[0, 1])
                            # Severe veto: only drop signal if ML signals elevated risk of immediate bull-trap
                            if ml_prob < max(0.38, self.ml_min_probability - 0.10):
                                ml_confirmed = False
                            else:
                                # Smooth conviction modulation (prob 0.50 -> 1.0x, prob 0.60 -> 1.06x, prob 0.45 -> 0.97x)
                                raw_conviction = raw_conviction * (0.70 + (ml_prob * 0.60))
                    except Exception as e:
                        logger.debug(f"ML gating error for {symbol}: {e}")

                if ml_confirmed:
                    momentum_signals.append({
                        "symbol": symbol,
                        "target_weight": judgment["target_weight"],
                        "confidence": judgment["confidence"],
                        "conviction_score": round(raw_conviction, 4),
                        "ml_prob": round(ml_prob, 4) if ml_prob is not None else None,
                        "rationale": judgment["rationale"] + (f" | ML Confirmed: {ml_prob*100:.1f}%" if ml_prob is not None else "")
                    })

            # 2. Mean-Reversion Dip-Buy Judgment (Oversold Quality)
            mr_sig = self.mean_reversion.generate_signal(df)
            if mr_sig.get("signal") == 1:
                mr_conf = mr_sig.get("confidence", 0.70)
                ml_prob = None
                ml_confirmed = True

                if self.enable_ml_gating and self.ml_model is not None and len(df) >= 200:
                    try:
                        feats = self.ml_pipeline.extract_features(df)
                        feat_cols = list(self.ml_model.feature_names_in_)
                        latest_feats = feats[feat_cols].iloc[[-1]]
                        if not latest_feats.isna().any().any():
                            ml_prob = float(self.ml_model.predict_proba(latest_feats)[0, 1])
                            # In dip buying, if ML probability is extremely low (< 0.40), avoid catching a falling knife
                            if ml_prob < 0.40:
                                ml_confirmed = False
                            else:
                                mr_conf = mr_conf * (0.80 + (ml_prob * 0.40))
                    except Exception as e:
                        logger.debug(f"ML dip-buy gating error for {symbol}: {e}")

                if ml_confirmed:
                    mean_rev_signals.append({
                        "symbol": symbol,
                        "signal": 1,
                        "confidence": round(mr_conf, 4),
                        "ml_prob": round(ml_prob, 4) if ml_prob is not None else None,
                        "rationale": mr_sig.get("rationale", "") + (f" | ML Confirmed: {ml_prob*100:.1f}%" if ml_prob is not None else "")
                    })

        return {
            "momentum": momentum_signals,
            "mean_reversion": mean_rev_signals
        }


def submit_quant_candidate(signals: List[Dict[str, Any]], session) -> str:
    """
    Submits generated strategy candidates to Strategy Registry and logs audit trail.
    """
    strat_id = f"Quant-META-{datetime.now().strftime('%Y%m%d')}"
    try:
        new_strat = Strategy(
            strategy_id=strat_id,
            name="Quant Multi-Agent Meta Strategy",
            author="TradingAgents + InvestorSkills",
            description="Daily generated portfolio allocation from the Quant Brain.",
            status="CANDIDATE"
        )
        session.add(new_strat)

        for sig in signals:
            decision = PortfolioDecision(
                strategy_id=strat_id,
                symbol=sig["symbol"],
                target_weight=sig.get("target_weight", 0.0),
                confidence=sig.get("confidence", 0.5),
                decision_metadata={"rationale": sig.get("rationale", "")}
            )
            session.add(decision)

        session.commit()
    finally:
        session.close()

    return strat_id
