import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
import pandas as pd
from trading_system.app.models.core import Strategy, PortfolioDecision
from trading_system.app.common.database import SessionLocal
from trading_system.app.data.yfinance_provider import YFinanceDataProvider
from trading_system.app.strategies.ensembles.mean_reversion import MeanReversionStrategy

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


class QuantEngine:
    """
    Multi-Engine Quant Brain coordinating Momentum Leaders and Mean-Reversion Dip-Buys.
    """
    def __init__(self):
        self.data_provider = YFinanceDataProvider()
        self.mean_reversion = MeanReversionStrategy()

    def run_nightly_research(self, universe: List[str], as_of_time: datetime) -> Dict[str, List[Dict[str, Any]]]:
        """
        Runs multi-strategy pipeline across universe.
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
            if df.empty:
                continue

            # 1. Momentum Leader Judgment
            judgment = InvestorSkillsHeuristics.apply_judgment(symbol, df, fast_sma, slow_sma)
            if judgment["confidence"] > 0.70 and judgment.get("conviction_score", 0.0) > 0.0:
                momentum_signals.append({
                    "symbol": symbol,
                    "target_weight": judgment["target_weight"],
                    "confidence": judgment["confidence"],
                    "conviction_score": judgment.get("conviction_score", 0.0),
                    "rationale": judgment["rationale"]
                })

            # 2. Mean-Reversion Dip-Buy Judgment (Oversold Quality)
            mr_sig = self.mean_reversion.generate_signal(df)
            if mr_sig.get("signal") == 1:
                mean_rev_signals.append({
                    "symbol": symbol,
                    "signal": 1,
                    "confidence": mr_sig.get("confidence", 0.70),
                    "rationale": mr_sig.get("rationale", "")
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
