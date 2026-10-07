import sys
import os
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

def execute_sp500_20yr_test():
    print("\n" + "="*70)
    print(">>> EXECUTING 20-YEAR S&P 500 TEST (2006 - 2026) <<<")
    print("="*70)
    
    start = datetime(2006, 1, 1)
    end = datetime(2026, 1, 1)
    
    # Representative basket: SPY (S&P 500 Index) + Top Mega-Caps to simulate the index heavyweights
    universe = [
        "SPY", "AAPL", "MSFT", "GOOGL", "AMZN", 
        "BRK-B", "JPM", "JNJ", "XOM", "WMT", "UNH", "PG", "V"
    ]
    
    print(f"[1/3] Loading Latest T001_MovingAverage Strategy...")
    strategy_class = StrategyRegistry.get_strategy("T001_MovingAverage")
    strategy = strategy_class(fast_length=50, slow_length=200) 
    
    print(f"\n[2/3] Executing Strategy Point-in-Time from 2006 to 2026 (20 Years)...")
    
    data_provider = YFinanceDataProvider()
    portfolio = BasicPortfolio(initial_cash=100000.0) # $100k starting capital
    risk_engine = BasicRiskEngine(max_position_size=100000.0)
    
    # The latest bot version uses the Adaptive Allocator which defends against crashes
    base_constructor = EqualWeightPortfolioConstructor()
    adaptive_allocator = AdaptivePortfolioAllocator(base_constructor, regime_index="SPY")
    
    execution = PaperExecutionAdapter()
    db = SessionLocal()
    
    backtester = MultiAssetBacktester(
        data_provider, strategy, portfolio, risk_engine, adaptive_allocator, execution, db_session=db
    )
    
    # Run backtest
    backtester.run(symbols=universe, start_date=start, end_date=end, experiment_id=f"SP500-20YR-{int(datetime.now().timestamp())}")
    
    print("\n[3/3] Calculating Performance Metrics...")
    analyzer = QuantitativePerformanceAnalyzer()
    
    if hasattr(backtester, 'equity_curve'):
        equity_series = pd.Series(backtester.equity_curve)
        metrics = analyzer.calculate_metrics([], equity_series)
        
        print("\n--- S&P 500 (2006-2026) TEAR SHEET ---")
        for k, v in metrics.items():
            print(f"{k.ljust(25)}: {v}")
            
    else:
        print("ERROR: No equity curve generated.")
        
    db.close()

if __name__ == "__main__":
    execute_sp500_20yr_test()
