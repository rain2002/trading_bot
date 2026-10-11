import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
import pandas as pd
from trading_system.app.data.yfinance_provider import YFinanceDataProvider
from trading_system.app.strategies.discovery.strategy_registry import StrategyRegistry
from trading_system.app.portfolio.basic import BasicPortfolio
from trading_system.app.risk.basic import BasicRiskEngine
from trading_system.app.portfolio.constructor import EqualWeightPortfolioConstructor
from trading_system.app.portfolio.adaptive_allocator import AdaptivePortfolioAllocator
from trading_system.app.execution.paper import PaperExecutionAdapter
from trading_system.app.backtesting.multi_asset_engine import MultiAssetBacktester
from trading_system.app.reporting.performance import QuantitativePerformanceAnalyzer
from trading_system.app.common.database import engine
from sqlalchemy.orm import sessionmaker

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def execute_sp500_26yr_test():
    print("\n" + "="*70)
    print(">>> EXECUTING 26-YEAR S&P 500 TEST (2000 - 2026) <<<")
    print("="*70)
    
    start = datetime(2000, 1, 1)
    end = datetime(2026, 1, 1)
    
    universe = [
        "SPY", "AAPL", "MSFT", "GOOGL", "AMZN", 
        "BRK-B", "JPM", "JNJ", "XOM", "WMT", "UNH", "PG", "V"
    ]
    
    print(f"[1/4] Loading Optimizer Parameters...")
    config_path = os.path.join(os.path.dirname(__file__), "..", "app", "config", "dynamic_params.json")
    fast_sma = 20
    slow_sma = 50
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                params = json.load(f)
                fast_sma = params.get("fast_sma", 20)
                slow_sma = params.get("slow_sma", 50)
                print(f"Loaded Optimizer Regime: Fast {fast_sma}, Slow {slow_sma}")
        except Exception as e:
            pass
            
    print(f"\n[2/4] Loading Strategy with Dynamic Sizing Engine...")
    strategy_class = StrategyRegistry.get_strategy("T001_MovingAverage")
    strategy = strategy_class(fast_length=fast_sma, slow_length=slow_sma) 
    
    print(f"\n[3/4] Executing Strategy Point-in-Time from 2000 to 2026 (26 Years)...")
    
    data_provider = YFinanceDataProvider()
    portfolio = BasicPortfolio(initial_cash=100000.0) 
    risk_engine = BasicRiskEngine(max_position_size=100000.0)
    
    # Portfolio Constructor now respects the 15% Max Dynamic Sizing
    base_constructor = EqualWeightPortfolioConstructor(rebalance_freq="daily")
    adaptive_allocator = AdaptivePortfolioAllocator(base_constructor, regime_index="SPY")
    
    execution = PaperExecutionAdapter()
    db = SessionLocal()
    
    backtester = MultiAssetBacktester(
        data_provider, strategy, portfolio, risk_engine, adaptive_allocator, execution, db_session=db
    )
    
    # Run backtest
    backtester.run(symbols=universe, start_date=start, end_date=end, experiment_id=f"SP500-26YR-{int(datetime.now().timestamp())}")
    
    print("\n[4/4] Calculating Performance Metrics...")
    analyzer = QuantitativePerformanceAnalyzer()
    
    if hasattr(backtester, 'equity_curve'):
        equity_series = pd.Series(backtester.equity_curve)
        metrics = analyzer.calculate_metrics([], equity_series)
        
        print("\n--- S&P 500 (2000-2026) FINAL TEAR SHEET ---")
        for k, v in metrics.items():
            print(f"{k.ljust(25)}: {v}")
            
    else:
        print("ERROR: No equity curve generated.")
        
    db.close()

if __name__ == "__main__":
    execute_sp500_26yr_test()
