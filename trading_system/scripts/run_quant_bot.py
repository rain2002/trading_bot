from datetime import datetime, timedelta
import logging
from trading_system.app.config.settings import settings
from trading_system.app.data.openbb_provider import OpenBBDataProvider
from trading_system.app.research.quant_engine import QuantEngine, InvestorSkillsHeuristics
from trading_system.app.broker.alpaca import AlpacaBrokerAdapter
from trading_system.app.execution.alpaca_live import AlpacaExecutionAdapter
from trading_system.app.risk.basic import BasicRiskEngine
from trading_system.app.notifications.notifier import QuantNotifier

logger = logging.getLogger("QUANTBot")

def execute_quant_live_cycle():
    print("\n" + "="*50)
    print(">>> AWAKENING QUANT BRAIN (TRADING AGENTS MVP) <<<")
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
    
    print("\n[2/4] Waking up QUANT Trading Agents & Fetching OpenBB Data...")
    brain = QuantEngine()
    
    # Dynamically fetch the entire S&P 500 universe
    print("Fetching the complete S&P 500 universe for maximum opportunity scanning...")
    try:
        import os
        filepath = os.path.join(os.path.dirname(__file__), "..", "data", "sp500_tickers.txt")
        with open(filepath, "r") as f:
            universe = [line.strip().replace('.', '-') for line in f.readlines() if line.strip()]
        print(f"Successfully loaded {len(universe)} S&P 500 symbols from local dataset.")
    except Exception as e:
        print(f"Failed to load S&P 500 file, falling back to mega-caps. Error: {e}")
        universe = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META"]
    
    # Run the multi-agent research pipeline for today
    generated_signals = brain.run_nightly_research(universe, datetime.now())
    print(f"QUANT Brain generated {len(generated_signals)} signals based on InvestorSkills heuristics.")
    
    # --- DYNAMIC SIZING ENGINE ---
    # Max exposure: 95% of portfolio (leave 5% cash for safety)
    # Max single stock exposure: 15%
    target_weights = {}
    if generated_signals:
        total_signals = len(generated_signals)
        print(f"Dynamic Sizing Engine active. Distributing capital across {total_signals} valid signals...")
        
        # Calculate equal weight per signal, capped at 15%
        calculated_weight = min(0.95 / total_signals, 0.15)
        
        for sig in generated_signals:
            sym = sig["symbol"]
            target_weights[sym] = calculated_weight
            print(f" -> {sym}: {calculated_weight*100:.1f}% (Confidence: {sig['confidence']}, Rationale: {sig['rationale']})")
    else:
        print("No bullish signals generated today. Moving to 100% Cash.")
    # ----------------------------
        
    print("\n[3/4] Reconciling QUANT Targets against Broker State...")
    
    # Ensure any open positions no longer wanted by the QUANT are sold
    for open_sym in current_positions.keys():
        if open_sym not in target_weights:
            target_weights[open_sym] = 0.0
            
    print("\n[4/4] Routing Orders to Risk Engine & Alpaca...")
    executed_orders_log = []
    for sym, target_weight in target_weights.items():
        if target_weight == 'HOLD':
            continue
            
        current_price = broker.get_latest_price(sym)
        if current_price <= 0:
            df = brain.data_provider.get_data_as_of(sym, datetime.now())
            if not df.empty:
                current_price = float(df['close'].iloc[-1])
            else:
                current_price = 100.0
                
        target_value = total_equity * target_weight
        
        current_qty = current_positions.get(sym, 0.0)
        current_value = current_qty * current_price
        
        value_to_trade = target_value - current_value
        qty_to_trade = int(value_to_trade / current_price)
        
        if qty_to_trade != 0:
            side = "BUY" if qty_to_trade > 0 else "SELL"
            import hashlib
            run_date = datetime.now().date()
            order_hash_base = f"QUANT_{run_date}_{sym}_{side}_{qty_to_trade}"
            deterministic_id = f"QUANT-{hashlib.md5(order_hash_base.encode()).hexdigest()[:12]}"
            
            trade_request = {
                "client_order_id": deterministic_id,
                "symbol": sym,
                "quantity": qty_to_trade,
                "price_hint": current_price
            }
            if risk_engine.evaluate_trade(trade_request, current_positions):
                execution.submit_order(trade_request)
                executed_orders_log.append({"symbol": sym, "side": side, "qty": qty_to_trade})
                print(f" -> EXECUTED: {side} {abs(qty_to_trade)} {sym}")
            else:
                print(f" -> [RISK HALT] Trade rejected by Risk Engine: {sym} {qty_to_trade}")

    print("\n[5/5] Dispatching Daily Quant Summary Notification...")
    notifier = QuantNotifier()
    try:
        acc_details = broker.get_account_details()
        open_pos_count = len(broker.get_positions())
        notifier.send_daily_summary(
            equity=acc_details["equity"],
            cash=acc_details["cash"],
            open_positions_count=open_pos_count,
            executed_orders=executed_orders_log,
            today_pnl=acc_details["today_pnl"],
            today_pnl_pct=acc_details["today_pnl_pct"],
            overall_pnl=acc_details["overall_pnl"],
            overall_pnl_pct=acc_details["overall_pnl_pct"],
            regime_info="NORMAL (Dynamic Momentum Active)"
        )
    except Exception as e:
        print(f"Notification dispatch failed: {e}")
                
    print("\nSUCCESS: QUANT BRAIN EXECUTION CYCLE COMPLETE.")
    print("="*50 + "\n")

if __name__ == "__main__":
    execute_quant_live_cycle()
