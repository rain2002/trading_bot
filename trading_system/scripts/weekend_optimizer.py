import sys
import os
import json
import logging
import pandas as pd
from datetime import datetime, timedelta

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

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
    
    # We optimize against SPY over 252 trading days (1 full market year)
    # to capture robust macro regimes, fetching 2 years to warm up slow SMAs.
    end_date = datetime.now()
    start_date = end_date - timedelta(days=730)
    
    print(f"Fetching data for SPY from {start_date.date()} to {end_date.date()}...")
    df = provider.fetch_historical_data("SPY", start_date, end_date)
    
    if df.empty:
        print("ERROR: Could not fetch data for SPY. Optimization failed.")
        return
        
    best_params = {"fast_sma": 20, "slow_sma": 50}
    best_score = -999.0
    best_return = 0.0
    
    print("Starting parameter grid search across 252 trading days...")
    
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
            
            # Calculate daily returns and signals on full series before windowing
            test_df['daily_return'] = test_df['close'].pct_change()
            # Signal: 1 if Price > SMA_Fast > SMA_Slow, else 0 (shifted by 1 to prevent lookahead)
            test_df['signal'] = ((test_df['close'] > test_df['sma_fast']) & (test_df['sma_fast'] > test_df['sma_slow'])).astype(int).shift(1)
            test_df['strategy_return'] = test_df['signal'] * test_df['daily_return']
            
            # Restrict the backtest evaluation to the most recent 252 trading days (1 full market year)
            eval_df = test_df.dropna().tail(252)
            
            if len(eval_df) < 200:
                continue
                
            strat_returns = eval_df['strategy_return']
            
            # Compounded geometric cumulative return (1 + r).prod() - 1
            total_return = float(((1.0 + strat_returns).prod() - 1.0) * 100)
            vol = float(strat_returns.std() * (252 ** 0.5) * 100) if len(strat_returns) > 10 else 1.0
            # Risk-adjusted score (Sharpe proxy)
            risk_adj_score = (total_return / (vol + 0.01))
            
            print(f"  Tested Fast: {fast:02d} | Slow: {slow:03d} -> 252-Day Compounded Return: {total_return:6.2f}% | Vol: {vol:5.1f}% | Score: {risk_adj_score:5.2f}")
            
            if risk_adj_score > best_score:
                best_score = risk_adj_score
                best_return = total_return
                best_params = {"fast_sma": fast, "slow_sma": slow}
                
    print("\n" + "="*50)
    print(f"OPTIMIZATION / AUDIT COMPLETE.")
    print(f"Grid Search Best Fit (SPY 1Y): Fast {best_params['fast_sma']}, Slow {best_params['slow_sma']}")
    print(f"Simulated 252-Day Return: {best_return:.2f}% (Risk-Adjusted Score: {best_score:.2f})")
    print("="*50)
    print("INSTITUTIONAL GOVERNANCE: Production parameters remain frozen at canonical 20/50 baseline")
    print("to prevent in-sample single-asset curve fitting. Dynamic param file will not be overwritten automatically.")

if __name__ == "__main__":
    run_optimization()
