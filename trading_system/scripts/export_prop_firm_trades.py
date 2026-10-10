import pandas as pd
from datetime import datetime, timedelta
from trading_system.app.research.llm_brain import TradingAgentLLM, InvestorSkillsHeuristics
from trading_system.app.data.yfinance_provider import YFinanceDataProvider

def run_prop_firm_export():
    print("Initializing Prop Firm Signal Exporter...")
    brain = TradingAgentLLM()
    
    universe = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"]
    
    START_DATE = datetime(2023, 1, 1)
    END_DATE = datetime(2023, 12, 31)
    STARTING_EQUITY = 100000.0
    
    print("Pre-fetching dataset for entire universe to speed up simulation...")
    history = {}
    for sym in universe:
        df = brain.data_provider.fetch_historical_data(sym, START_DATE - timedelta(days=365), END_DATE + timedelta(days=5))
        history[sym] = df
        
    equity = STARTING_EQUITY
    current_positions = {} # symbol -> qty
    trade_log = []
    
    print(f"\nSimulating time-skip from {START_DATE.date()} to {END_DATE.date()}...")
    print(f"Starting Prop Firm Balance: ${equity:,.2f}")
    
    current_date = START_DATE
    while current_date <= END_DATE:
        if current_date.weekday() > 4:
            current_date += timedelta(days=1)
            continue
            
        target_weights = {}
        for sym in universe:
            df = history[sym]
            if df is not None and not df.empty:
                # CRITICAL: Slice the dataframe strictly up to current_date to ensure ZERO lookahead bias
                point_in_time_df = df[df.index <= pd.Timestamp(current_date, tz='UTC')]
                if not point_in_time_df.empty:
                    judgment = InvestorSkillsHeuristics.apply_judgment(sym, point_in_time_df)
                    target_weights[sym] = judgment["target_weight"]
                
        # Rebalance Portfolio
        # First, sell anything we need to reduce/close
        for sym in list(current_positions.keys()):
            target_weight = target_weights.get(sym, 0.0)
            df = history[sym]
            point_in_time_df = df[df.index <= pd.Timestamp(current_date, tz='UTC')]
            if not point_in_time_df.empty:
                current_price = point_in_time_df['close'].iloc[-1]
                target_value = equity * target_weight
                current_qty = current_positions[sym]
                current_value = current_qty * current_price
                
                if target_value < current_value:
                    value_to_sell = current_value - target_value
                    qty_to_sell = int(value_to_sell / current_price)
                    if qty_to_sell > 0:
                        current_positions[sym] -= qty_to_sell
                        equity += qty_to_sell * current_price
                        trade_log.append({
                            "Date": current_date.strftime("%Y-%m-%d"),
                            "Symbol": sym,
                            "Action": "SELL",
                            "Quantity": qty_to_sell,
                            "Price": round(current_price, 2)
                        })
                        
        # Second, buy anything we need to increase
        for sym, target_weight in target_weights.items():
            if target_weight > 0:
                df = history[sym]
                point_in_time_df = df[df.index <= pd.Timestamp(current_date, tz='UTC')]
                if not point_in_time_df.empty:
                    current_price = point_in_time_df['close'].iloc[-1]
                    target_value = equity * target_weight
                    current_qty = current_positions.get(sym, 0)
                    current_value = current_qty * current_price
                    
                    if target_value > current_value:
                        value_to_buy = target_value - current_value
                        qty_to_buy = int(value_to_buy / current_price)
                        if qty_to_buy > 0 and (qty_to_buy * current_price) <= equity:
                            current_positions[sym] = current_qty + qty_to_buy
                            equity -= qty_to_buy * current_price
                            trade_log.append({
                                "Date": current_date.strftime("%Y-%m-%d"),
                                "Symbol": sym,
                                "Action": "BUY",
                                "Quantity": qty_to_buy,
                                "Price": round(current_price, 2)
                            })
                            
        current_date += timedelta(days=1)
        
    print("\nSimulation Complete!")
    # Calculate final equity
    for sym, qty in current_positions.items():
        df = history[sym]
        point_in_time_df = df[df.index <= pd.Timestamp(END_DATE, tz='UTC')]
        if not point_in_time_df.empty:
            current_price = point_in_time_df['close'].iloc[-1]
            equity += qty * current_price
            
    print(f"Final Prop Firm Balance: ${equity:,.2f}")
    roi = ((equity - STARTING_EQUITY) / STARTING_EQUITY) * 100
    print(f"Total ROI: {roi:.2f}%")
    
    trade_df = pd.DataFrame(trade_log)
    output_file = "prop_firm_sim_trades.csv"
    trade_df.to_csv(output_file, index=False)
    print(f"Exported {len(trade_log)} trades to {output_file}. You can upload this directly to BacktestingMax or TradesViz!")

if __name__ == "__main__":
    run_prop_firm_export()
