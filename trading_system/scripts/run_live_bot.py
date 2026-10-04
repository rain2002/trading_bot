from datetime import datetime, timedelta
from trading_system.app.config.settings import settings
from trading_system.app.data.yfinance_provider import YFinanceDataProvider
from trading_system.app.strategies.library.t001_moving_average import T001_MovingAverageTrend
from trading_system.app.portfolio.constructor import EqualWeightPortfolioConstructor
from trading_system.app.portfolio.adaptive_allocator import AdaptivePortfolioAllocator
from trading_system.app.broker.alpaca import AlpacaBrokerAdapter
from trading_system.app.execution.alpaca_live import AlpacaExecutionAdapter
from trading_system.app.risk.basic import BasicRiskEngine
import uuid

def execute_live_cycle():
    print("\n" + "="*50)
    print(">>> AWAKENING LIVE TRADING ENGINE <<<")
    print("="*50)
    
    # API Keys are securely loaded from the .env file
    API_KEY = settings.PAPER_API_KEY
    API_SECRET = settings.PAPER_API_SECRET
    
    if not API_KEY or not API_SECRET:
        print("ERROR: PAPER_API_KEY or PAPER_API_SECRET not found in .env file.")
        print("Please add them to d:\\paper_trading_bot\\.env and run again.")
        return
    
    data_provider = YFinanceDataProvider()
    strategy = T001_MovingAverageTrend(fast_length=20, slow_length=50)
    base_constructor = EqualWeightPortfolioConstructor()
    adaptive_allocator = AdaptivePortfolioAllocator(base_constructor, regime_index="SPY")
    
    broker = AlpacaBrokerAdapter(api_key=API_KEY, api_secret=API_SECRET)
    execution = AlpacaExecutionAdapter(api_key=API_KEY, api_secret=API_SECRET)
    risk_engine = BasicRiskEngine(max_position_size=100000)
    
    # 1. Get Live State
    print("\n[1/5] Syncing with Broker for LIVE Positions...")
    current_positions = broker.get_positions()
    print(f"Broker reports we hold: {current_positions}")
    
    # 2. Fetch Latest Data
    print("\n[2/5] Ingesting LIVE Market Data (T-200 Days to Today)...")
    symbols = ["AAPL", "MSFT", "SPY"]
    end_date = datetime.now()
    start_date = end_date - timedelta(days=200) # Need 200 days for the Regime 200-SMA
    
    universe_data = {}
    for sym in symbols:
        df = data_provider.fetch_historical_data(sym, start_date, end_date)
        if not df.empty:
            universe_data[sym] = df
            
    # 3. Generate Strategy Signals
    print("\n[3/5] Querying Strategy Library for actionable edges...")
    signals = strategy.generate_signals(universe_data)
    print(f"Raw Signals: {signals}")
    
    # 4. Ask Allocator for Target Weights
    print("\n[4/5] Passing to Adaptive Allocator (Checking Crash Regimes)...")
    target_weights = adaptive_allocator.generate_target_weights(signals, universe_data)
    print(f"Final Target Portfolio Weights: {target_weights}")
    
    # 5. Generate Trades
    print("\n[5/5] Reconciling Targets against Broker State & Routing Orders...")
    
    total_equity = broker.get_account_equity()
    print(f"Broker reports Total Account Equity: ${total_equity:,.2f}")
    
    # Ensure any open positions no longer in the target dictionary are explicitly sold
    for open_sym in current_positions.keys():
        if open_sym not in target_weights and open_sym in universe_data:
            target_weights[open_sym] = 0.0
            
    for sym, target_weight in target_weights.items():
        if target_weight == 'HOLD':
            continue
            
        if sym not in universe_data or universe_data[sym].empty: continue
        
        current_price = universe_data[sym]['close'].iloc[-1]
        target_value = total_equity * target_weight
        
        current_qty = current_positions.get(sym, 0.0)
        current_value = current_qty * current_price
        
        value_to_trade = target_value - current_value
        qty_to_trade = int(value_to_trade / current_price)
        
        if qty_to_trade != 0:
            side = "BUY" if qty_to_trade > 0 else "SELL"
            import hashlib
            run_date = datetime.now().date()
            order_hash_base = f"LIVE_{strategy.__class__.__name__}_{run_date}_{sym}_{side}_{qty_to_trade}"
            deterministic_id = f"V2-{hashlib.md5(order_hash_base.encode()).hexdigest()[:12]}"
            
            trade_request = {
                "client_order_id": deterministic_id,
                "symbol": sym,
                "quantity": qty_to_trade,
                "price_hint": current_price
            }
            if risk_engine.evaluate_trade(trade_request, current_positions):
                execution.submit_order(trade_request)
            else:
                print(f"[RISK HALT] Trade rejected by Risk Engine: {sym} {qty_to_trade}")
                
    print("\nSUCCESS: LIVE EXECUTION CYCLE COMPLETE. SLEEPING UNTIL NEXT CRON TICK.")
    print("="*50 + "\n")

if __name__ == "__main__":
    execute_live_cycle()
