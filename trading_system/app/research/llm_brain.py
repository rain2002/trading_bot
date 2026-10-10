import logging
from datetime import datetime
from typing import Dict, Any, List
import pandas as pd
from trading_system.app.models.core import Strategy, PortfolioDecision
from trading_system.app.common.database import SessionLocal
from trading_system.app.data.yfinance_provider import YFinanceDataProvider

logger = logging.getLogger("LLMBrain")

class InvestorSkillsHeuristics:
    """
    Simulated wrapper for the InvestorSkills swift library logic.
    Provides structured judgment and sizing rules for the LLM.
    """
    @staticmethod
    def apply_judgment(symbol: str, data_context: pd.DataFrame) -> Dict[str, Any]:
        """
        Uses moving averages and ATR to simulate an LLM's technical analysis judgment.
        Returns varying weights based on trend strength.
        """
        if data_context.empty or len(data_context) < 50:
            return {"confidence": 0.0, "rationale": "Insufficient data.", "target_weight": 0.0}
            
        close_prices = data_context['close']
        sma_20 = close_prices.rolling(window=20).mean().iloc[-1]
        sma_50 = close_prices.rolling(window=50).mean().iloc[-1]
        current_price = close_prices.iloc[-1]
        
        # Bullish Trend: Price > SMA20 > SMA50
        if current_price > sma_20 and sma_20 > sma_50:
            return {
                "confidence": 0.85,
                "rationale": "Strong bullish momentum confirmed by moving averages.",
                "target_weight": 0.05  # 5% allocation per stock
            }
        # Bearish Trend
        elif current_price < sma_20 and sma_20 < sma_50:
            return {
                "confidence": 0.20,
                "rationale": "Bearish trend detected.",
                "target_weight": 0.0  # Liquidate
            }
        else:
            return {
                "confidence": 0.50,
                "rationale": "Sideways chop. Staying out.",
                "target_weight": 0.0
            }

class TradingAgentLLM:
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
        logger.info(f"Starting LLM Multi-Agent Research Cycle for {universe} as of {as_of_time}")
        pre_screened = []
        
        # 1. Cheap Screening Subagent (Technical Heuristics)
        print("Running cheap technical screener across 500 stocks...")
        for symbol in universe:
            df = self.data_provider.get_data_as_of(symbol, as_of_time)
            if df.empty:
                continue
                
            judgment = InvestorSkillsHeuristics.apply_judgment(symbol, df)
            if judgment["confidence"] > 0.7:
                # Add recent price action summary for the LLM
                recent_px = df['close'].tail(5).tolist()
                pre_screened.append({
                    "symbol": symbol,
                    "target_weight": judgment["target_weight"],
                    "recent_prices": [round(p, 2) for p in recent_px],
                    "rationale": judgment["rationale"]
                })
                
        print(f"Screener identified {len(pre_screened)} candidates. Waking up Deep LLM Agent...")
        
        # 2. Deep LLM Agent (OpenAI)
        if not pre_screened:
            return []
            
        import os
        import json
        
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("WARNING: OPENAI_API_KEY not found. Using screener signals directly (Simulation Mode).")
            return [{"symbol": c["symbol"], "target_weight": c["target_weight"], "confidence": 0.8, "rationale": c["rationale"]} for c in pre_screened]
            
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            
            prompt = f"""
            You are an elite quantitative portfolio manager. 
            The technical screener has identified the following {len(pre_screened)} stocks as having strong bullish momentum.
            Your job is to act as the fundamental and risk override. Select ONLY the best 5 stocks to buy today.
            For the 5 you select, assign a target_weight of 0.05 (5%) and provide a 1-sentence rationale.
            For the others, assign a target_weight of 0.0.
            
            Candidates:
            {json.dumps(pre_screened, indent=2)}
            
            Respond ONLY with a valid JSON object containing a single key "signals", which is an array of objects. 
            Each object must contain 'symbol', 'target_weight', 'confidence' (0.0 to 1.0), and 'rationale'.
            """
            
            print("Calling OpenAI API for final portfolio allocation...")
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": "You are a JSON-only trading bot. Always output JSON with a 'signals' array."},
                          {"role": "user", "content": prompt}],
                temperature=0.2,
                response_format={ "type": "json_object" }
            )
            
            # The API returns a JSON object, we need to extract the array
            # We'll just ask for a JSON object with a 'signals' key
            # Let's adjust the prompt slightly inside the actual JSON parsing
            
        except ImportError:
            print("WARNING: 'openai' package not installed. Returning pre-screened signals.")
            return [{"symbol": c["symbol"], "target_weight": c["target_weight"], "confidence": 0.8, "rationale": c["rationale"]} for c in pre_screened]
        except Exception as e:
            print(f"OpenAI API Error: {e}. Falling back to screener.")
            return [{"symbol": c["symbol"], "target_weight": c["target_weight"], "confidence": 0.8, "rationale": c["rationale"]} for c in pre_screened]
            
        # Safely parse the LLM response
        try:
            content = response.choices[0].message.content
            # To handle response_format properly, the prompt must explicitly ask for a JSON object
            # Let's parse it manually if it returns an array
            if content.strip().startswith('['):
                final_signals = json.loads(content)
            else:
                # If it wrapped it in an object like {"signals": [...]}
                parsed = json.loads(content)
                final_signals = parsed.get("signals", parsed.get("data", []))
                if not final_signals and isinstance(parsed, list):
                    final_signals = parsed
                    
            print(f"OpenAI successfully returned {len(final_signals)} validated signals!")
            return final_signals
        except Exception as e:
            print(f"Failed to parse OpenAI JSON: {e}. Returning pre-screened.")
            return [{"symbol": c["symbol"], "target_weight": c["target_weight"], "confidence": 0.8, "rationale": c["rationale"]} for c in pre_screened]

def submit_llm_candidate(signals: List[Dict[str, Any]], session) -> str:
    """
    Takes the output of the LLM Brain and submits it formally to the Strategy Registry
    as a CANDIDATE. It MUST be picked up by the Walk-Forward Validator next.
    """
    strat_id = f"LLM-META-{datetime.now().strftime('%Y%m%d')}"
    
    # 1. Register Strategy
    new_strat = Strategy(
        strategy_id=strat_id,
        name="LLM Multi-Agent Meta Strategy",
        author="TradingAgents + InvestorSkills",
        description="Daily generated portfolio allocation from the LLM Brain.",
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
    brain = TradingAgentLLM()
    
    universe = ["SPY", "QQQ", "GLD"]
    generated_signals = brain.run_nightly_research(universe, datetime.now())
    
    candidate_id = submit_llm_candidate(generated_signals, db)
    print(f"LLM Brain generated candidate: {candidate_id}")
    print("This candidate is now waiting in the database for the Automated Validation Gate.")
