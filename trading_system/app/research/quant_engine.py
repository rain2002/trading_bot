import os
import math
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
from trading_system.app.config.stop_loss_manager import StopLossManager

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
        mr_strategy: Optional[Any] = None,
        holding_type: str = "MOMENTUM",
        avg_entry: Optional[float] = None,
        peak_price: Optional[float] = None,
        entry_date: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Unified Institutional Holding & Exit Logic:
        Determines whether an open position should be EXITED (liquidated to 0.0) or HELD.
        CRITICAL: Disentangles MOMENTUM from DIP_BUY positions.
        - MOMENTUM positions NEVER exit on mean-reversion/RSI profit targets.
        - DIP_BUY positions exit on BB mid / RSI reversion or profit target.
        - Peak price is strictly measured from bars on or after entry date.
        """
        # 1. Macro Regime Crash Guardrail
        if regime == "CRASH_WARNING":
            return {
                "should_exit": True,
                "reason": "Market in CRASH_WARNING regime. Liquidating to 100% Cash Buffer.",
                "action": "CRASH_LIQUIDATE"
            }

        # 2. Dynamic Hard Stop-Loss Guardrail (Bot & User-Overridden Limits)
        stop_threshold = -0.08
        try:
            sl_mgr = StopLossManager()
            stop_threshold = sl_mgr.get_stop_loss_pct(symbol)
        except Exception:
            stop_threshold = -0.08

        if current_plpc <= stop_threshold:
            return {
                "should_exit": True,
                "reason": f"Hard Stop-Loss breached (Unrealized PnL: {current_plpc*100:.2f}% <= {stop_threshold*100:.1f}%)",
                "action": "STOP_LOSS_LIQUIDATE"
            }

        if df is None or df.empty or len(df) < 5:
            return {
                "should_exit": False,
                "reason": "Insufficient data; retaining position.",
                "action": "HOLD"
            }

        close_prices = df.get("adj_close", df["close"])
        current_price = float(close_prices.iloc[-1])
        if avg_entry is None or avg_entry <= 0:
            avg_entry = current_price / (1.0 + current_plpc) if (1.0 + current_plpc) > 0 else current_price

        # Technical indicators
        params = cls.get_dynamic_params()
        slow_sma_window = params.get("slow_sma", 50)
        sma50_series = close_prices.rolling(window=slow_sma_window, min_periods=min(20, len(close_prices))).mean()
        sma50_val = float(sma50_series.iloc[-1]) if not sma50_series.empty and not math.isnan(sma50_series.iloc[-1]) else None

        # Mean reversion indicators (BB mid and RSI)
        sma20_series = close_prices.rolling(20, min_periods=10).mean()
        bb_mid_val = float(sma20_series.iloc[-1]) if not sma20_series.empty and not math.isnan(sma20_series.iloc[-1]) else None

        delta = close_prices.diff()
        gain = delta.clip(lower=0.0)
        loss = -delta.clip(upper=0.0)
        avg_gain = gain.ewm(alpha=1.0 / 14.0, min_periods=min(14, len(close_prices)), adjust=False).mean()
        avg_loss = loss.ewm(alpha=1.0 / 14.0, min_periods=min(14, len(close_prices)), adjust=False).mean()
        rs = avg_gain / (avg_loss + 1e-9)
        rsi_series = 100.0 - (100.0 / (1.0 + rs))
        rsi_val = float(rsi_series.iloc[-1]) if not rsi_series.empty and not math.isnan(rsi_series.iloc[-1]) else None

        # Peak price calculation: strictly on or after entry date to avoid pre-entry bias
        if entry_date is not None and hasattr(df.index, 'date'):
            try:
                entry_dt = pd.to_datetime(entry_date)
                df_since = df[df.index >= entry_dt]
                if not df_since.empty:
                    high_s = df_since.get("high", df_since["close"])
                    peak_calc = float(high_s.max())
                else:
                    peak_calc = current_price
            except Exception:
                peak_calc = current_price
        elif peak_price is not None and peak_price > 0:
            peak_calc = peak_price
        else:
            peak_calc = current_price

        peak_calc = max(peak_calc, current_price, avg_entry)

        # Delegate to unified StopLossManager
        sl_mgr = StopLossManager()
        dyn_res = sl_mgr.evaluate_dynamic_exit(
            symbol=symbol,
            current_price=current_price,
            avg_entry=avg_entry,
            peak_price=peak_calc,
            sma50=sma50_val,
            holding_type=holding_type,
            bb_mid=bb_mid_val,
            rsi=rsi_val
        )

        if dyn_res["should_exit"]:
            reason_str = dyn_res.get("reason", "Dynamic Exit")
            action_tag = "TARGET_PROFIT_EXIT" if "DIP_TARGET" in reason_str else (
                "BREAKEVEN_STOP" if "BREAKEVEN" in reason_str else (
                    "BIG_WINNER_TRAIL" if "BIG_WINNER" in reason_str else (
                        "TREND_EXIT" if "TREND" in reason_str else "STOP_LOSS_LIQUIDATE"
                    )
                )
            )
            return {
                "should_exit": True,
                "reason": reason_str,
                "action": action_tag
            }

        return {
            "should_exit": False,
            "reason": f"Holding safe ({holding_type} intact, PnL: {current_plpc*100:+.1f}%)",
            "action": "HOLD"
        }


class QuantEngine:
    """
    Multi-Engine Quant Brain coordinating Momentum Leaders, Mean-Reversion Dip-Buys,
    and optional Machine Learning Alpha Gating. Defaults to rules-only to prevent
    single-market curve-fitting across diverse international jurisdictions.
    """
    def __init__(self, enable_ml_gating: bool = False, ml_min_probability: float = 0.48):
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
                        "holding_type": "MOMENTUM",
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
                        "holding_type": "DIP_BUY",
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
