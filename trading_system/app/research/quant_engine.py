import logging
from datetime import datetime
from typing import Dict, Any, List
import pandas as pd
from trading_system.app.models.core import Strategy, PortfolioDecision
from trading_system.app.common.database import SessionLocal
from trading_system.app.data.yfinance_provider import YFinanceDataProvider

logger = logging.getLogger("QuantEngine")

class InvestorSkillsHeuristics:
    """
    Simulated wrapper for the InvestorSkills swift library logic.
    Provides structured judgment and sizing rules for the Quant.
    """
    @staticmethod
    def apply_judgment(symbol: str, data_context: pd.DataFrame) -> Dict[str, Any]:
        """
        Uses moving averages and ATR to calculate technical analysis judgment.
        Dynamically loads parameters optimized by the Walk-Forward Optimizer.
        """
        import os, json
        config_path = os.path.join(os.path.dirname(__file__), "..", "config", "dynamic_params.json")
        fast_sma_window = 20
        slow_sma_window = 50
        
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    params = json.load(f)
                    fast_sma_window = params.get("fast_sma", 20)
                    slow_sma_window = params.get("slow_sma", 50)
            except Exception:
                pass

        if data_context.empty or len(data_context) < max(fast_sma_window, slow_sma_window):
            return {"confidence": 0.0, "rationale": "Insufficient data.", "target_weight": 0.0}
            
        close_prices = data_context['close']
        sma_fast = close_prices.rolling(window=fast_sma_window).mean().iloc[-1]
        sma_slow = close_prices.rolling(window=slow_sma_window).mean().iloc[-1]
        current_price = close_prices.iloc[-1]
        
        # Bullish Trend: Price > SMA_fast > SMA_slow
        if current_price > sma_fast and sma_fast > sma_slow:
            return {
                "confidence": 0.85,
                "rationale": "Strong bullish momentum confirmed by moving averages.",
                "target_weight": 0.05  # 5% allocation per stock
            }
        # Bearish Trend
        elif current_price < sma_fast and sma_fast < sma_slow:
            return {
                "confidence": 0.20,
                "rationale": f"Bearish trend detected (Price < {fast_sma_window}SMA < {slow_sma_window}SMA).",
                "target_weight": 0.0  # Liquidate
            }
        else:
            return {
                "confidence": 0.50,
                "rationale": "Sideways chop. Staying out.",
                "target_weight": 0.0
            }

class QuantEngine:
    """
    Wrapper for TauricResearch/TradingAgents framework.
    Coordinates multiple agents (Market Analyst, Risk Manager, Portfolio Allocator).
    """
    def __init__(self):
        self.data_provider = YFinanceDataProvider()
        
    def run_nightly_research(self, universe: List[str], as_of_time: datetime) -> List[Dict[str, Any]]:
        """
        Runs the multi-agent pipeline to generate strategy candidates for tomorrow.
        """
        logger.info(f"Starting Quant Multi-Agent Research Cycle for {universe} as of {as_of_time}")
        signals = []
        
        for symbol in universe:
            # 1. Fetch Point-in-Time Data (Price + Alternative)
            df = self.data_provider.get_data_as_of(symbol, as_of_time)
            if df.empty:
                continue
                
            # 2. Quant Analyst reviews data (Simulated)
            # In a real setup, we pass the data to the Quant context window here.
            
            # 3. Apply InvestorSkills for structured sizing and judgment
            judgment = InvestorSkillsHeuristics.apply_judgment(symbol, df)
            
            # 4. Compile signal candidate
            if judgment["confidence"] > 0.7:
                signals.append({
                    "symbol": symbol,
                    "target_weight": judgment["target_weight"],
                    "confidence": judgment["confidence"],
                    "rationale": judgment["rationale"]
                })
                
        return signals

def submit_quant_candidate(signals: List[Dict[str, Any]], session) -> str:
    """
    Takes the output of the Quant Brain and submits it formally to the Strategy Registry
    as a CANDIDATE. It MUST be picked up by the Walk-Forward Validator next.
    """
    strat_id = f"Quant-META-{datetime.now().strftime('%Y%m%d')}"
    
    # 1. Register Strategy
    new_strat = Strategy(
        strategy_id=strat_id,
        name="Quant Multi-Agent Meta Strategy",
        author="TradingAgents + InvestorSkills",
        description="Daily generated portfolio allocation from the Quant Brain.",
        status="CANDIDATE" # Must pass validation to become PRODUCTION
    )
    session.add(new_strat)
    
    # 2. Log Portfolio Decisions (Audit Trail)
    for sig in signals:
        decision = PortfolioDecision(
            strategy_id=strat_id,
            symbol=sig["symbol"],
            target_weight=sig["target_weight"],
            confidence=sig["confidence"],
            decision_metadata={"rationale": sig["rationale"]}
        )
        session.add(decision)
        
    session.commit()
    return strat_id

if __name__ == "__main__":
    # Example execution: The Nightly Cron Job
    import pandas as pd # Ensure pandas is available globally for the mock
    db = SessionLocal()
    brain = QuantEngine()
    
    universe = ["SPY", "QQQ", "GLD"]
    generated_signals = brain.run_nightly_research(universe, datetime.now())
    
    candidate_id = submit_quant_candidate(generated_signals, db)
    print(f"Quant Brain generated candidate: {candidate_id}")
    print("This candidate is now waiting in the database for the Automated Validation Gate.")
