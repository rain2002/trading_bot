from datetime import datetime, timedelta
import logging
from trading_system.app.config.settings import settings
from trading_system.app.data.openbb_provider import OpenBBDataProvider
from trading_system.app.research.llm_brain import TradingAgentLLM, InvestorSkillsHeuristics
from trading_system.app.broker.alpaca import AlpacaBrokerAdapter
from trading_system.app.execution.alpaca_live import AlpacaExecutionAdapter
from trading_system.app.risk.basic import BasicRiskEngine

logger = logging.getLogger("LLMBot")

def execute_llm_live_cycle():
    print("\n" + "="*50)
    print(">>> AWAKENING LLM BRAIN (TRADING AGENTS MVP) <<<")
    print("="*50)
    
    API_KEY = settings.PAPER_API_KEY
    API_SECRET = settings.PAPER_API_SECRET
    
    if not API_KEY or not API_SECRET:
        print("ERROR: PAPER_API_KEY or PAPER_API_SECRET not found.")
        return
        
    broker = AlpacaBrokerAdapter(api_key=API_KEY, api_secret=API_SECRET)
    execution = AlpacaExecutionAdapter(api_key=API_KEY, api_secret=API_SECRET)
    risk_engine = BasicRiskEngine(max_position_size=100000)
    
    print("\n[1/4] Syncing with Broker for LIVE Positions...")
    current_positions = broker.get_positions()
    print(f"Broker reports we hold: {current_positions}")
    total_equity = broker.get_account_equity()
    print(f"Broker reports Total Account Equity: ${total_equity:,.2f}")
    
    print("\n[2/4] Waking up LLM Trading Agents & Fetching OpenBB Data...")
    brain = TradingAgentLLM()
    
    # Dynamically fetch the entire S&P 500 universe
    print("Fetching the complete S&P 500 universe for maximum opportunity scanning...")
    try:
        import pandas as pd
        import requests
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        response = requests.get(url, headers=headers)
        table = pd.read_html(response.text)
        df = table[0]
        universe = df['Symbol'].tolist()
        # Clean up some tickers that yfinance doesn't like (e.g. BRK.B -> BRK-B)
        universe = [sym.replace('.', '-') for sym in universe]
        print(f"Successfully loaded {len(universe)} S&P 500 symbols.")
    except Exception as e:
        print(f"Failed to fetch S&P 500, falling back to mega-caps. Error: {e}")
        universe = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META"]
    
    # Run the multi-agent research pipeline for today
    generated_signals = brain.run_nightly_research(universe, datetime.now())
    print(f"LLM Brain generated {len(generated_signals)} signals based on InvestorSkills heuristics.")
    
    # Convert LLM signals into target weights
    target_weights = {}
    for sig in generated_signals:
        target_weights[sig["symbol"]] = sig["target_weight"]
        print(f" -> {sig['symbol']}: {sig['target_weight']*100}% (Confidence: {sig['confidence']}, Rationale: {sig['rationale']})")
        
    print("\n[3/4] Reconciling LLM Targets against Broker State...")
    
    # Ensure any open positions no longer wanted by the LLM are sold
    for open_sym in current_positions.keys():
        if open_sym not in target_weights:
            target_weights[open_sym] = 0.0
            
    print("\n[4/4] Routing Orders to Risk Engine & Alpaca...")
    for sym, target_weight in target_weights.items():
        if target_weight == 'HOLD':
            continue
            
        current_price = 100.0 # Fallback, ideally fetch from broker or OpenBB
        # Let's fetch actual current price from broker
        try:
            current_price = float(broker.client.get_latest_trade(sym).price)
        except Exception:
            # Fallback to OpenBB if broker API differs
            df = brain.data_provider.get_data_as_of(sym, datetime.now())
            if not df.empty:
                current_price = df['close'].iloc[-1]
                
        target_value = total_equity * target_weight
        
        current_qty = current_positions.get(sym, 0.0)
        current_value = current_qty * current_price
        
        value_to_trade = target_value - current_value
        qty_to_trade = int(value_to_trade / current_price)
        
        if qty_to_trade != 0:
            side = "BUY" if qty_to_trade > 0 else "SELL"
            import hashlib
            run_date = datetime.now().date()
            order_hash_base = f"LLM_{run_date}_{sym}_{side}_{qty_to_trade}"
            deterministic_id = f"LLM-{hashlib.md5(order_hash_base.encode()).hexdigest()[:12]}"
            
            trade_request = {
                "client_order_id": deterministic_id,
                "symbol": sym,
                "quantity": qty_to_trade,
                "price_hint": current_price
            }
            if risk_engine.evaluate_trade(trade_request, current_positions):
                execution.submit_order(trade_request)
                print(f" -> EXECUTED: {side} {abs(qty_to_trade)} {sym}")
            else:
                print(f" -> [RISK HALT] Trade rejected by Risk Engine: {sym} {qty_to_trade}")
                
    print("\nSUCCESS: LLM BRAIN EXECUTION CYCLE COMPLETE.")
    print("="*50 + "\n")

if __name__ == "__main__":
    execute_llm_live_cycle()
