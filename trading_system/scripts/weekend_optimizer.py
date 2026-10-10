import os
import json
import logging
import pandas as pd
from datetime import datetime, timedelta
from trading_system.app.data.yfinance_provider import YFinanceDataProvider

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WeekendOptimizer")

def run_optimization():
    print("="*50)
    print(">>> CONTINUOUS WALK-FORWARD OPTIMIZER STARTING <<<")
    print("="*50)
    
    # Define the search space
    fast_sma_options = [10, 15, 20, 25, 30]
    slow_sma_options = [40, 50, 60, 100, 150]
    
    provider = YFinanceDataProvider()
    
    # We will optimize against the SPY ETF as a proxy for the S&P 500 trend
    # over the last 180 days to capture the current market regime.
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365) # Fetch 1 year to have enough data for 150 SMA
    
    print(f"Fetching data for SPY from {start_date.date()} to {end_date.date()}...")
    df = provider.fetch_historical_data("SPY", start_date, end_date)
    
    if df.empty:
        print("ERROR: Could not fetch data for SPY. Optimization failed.")
        return
        
    best_params = {"fast_sma": 20, "slow_sma": 50}
    best_return = -999.0
    
    print("Starting parameter grid search...")
    
    # Backtest logic: simple moving average crossover
    for fast in fast_sma_options:
        for slow in slow_sma_options:
            if fast >= slow:
                continue
                
            # Create a copy of the dataframe
            test_df = df.copy()
            test_df['sma_fast'] = test_df['close'].rolling(window=fast).mean()
            test_df['sma_slow'] = test_df['close'].rolling(window=slow).mean()
            
            # Drop NaN rows where SMAs haven't populated yet
            test_df = test_df.dropna()
            
            # Restrict the backtest to the most recent 90 days of actual trading
            test_df = test_df.tail(90)
            
            if test_df.empty:
                continue
                
            # Signal: 1 if Price > SMA_Fast > SMA_Slow, else 0
            # Shift by 1 to prevent lookahead bias (trade on next day's open)
            test_df['signal'] = ((test_df['close'] > test_df['sma_fast']) & (test_df['sma_fast'] > test_df['sma_slow'])).astype(int).shift(1)
            test_df['daily_return'] = test_df['close'].pct_change()
            
            # Calculate strategy returns
            test_df['strategy_return'] = test_df['signal'] * test_df['daily_return']
            total_return = test_df['strategy_return'].sum() * 100 # In percentage
            
            print(f"  Tested Fast: {fast:02d} | Slow: {slow:03d} -> 90-Day Return: {total_return:6.2f}%")
            
            if total_return > best_return:
                best_return = total_return
                best_params = {"fast_sma": fast, "slow_sma": slow}
                
    print("\n" + "="*50)
    print(f"OPTIMIZATION COMPLETE.")
    print(f"Current Regime Best Parameters: Fast {best_params['fast_sma']}, Slow {best_params['slow_sma']}")
    print(f"Simulated 90-Day Return: {best_return:.2f}%")
    print("="*50)
    
    # Save to config file
    config_dir = os.path.join(os.path.dirname(__file__), "..", "app", "config")
    os.makedirs(config_dir, exist_ok=True)
    config_path = os.path.join(config_dir, "dynamic_params.json")
    
    with open(config_path, "w") as f:
        json.dump(best_params, f, indent=4)
        
    print(f"Saved new parameters to {config_path}")
    print("The Quant Engine will automatically load these parameters on Monday.")

if __name__ == "__main__":
    run_optimization()
