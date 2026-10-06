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
from trading_system.app.execution.paper import PaperExecutionAdapter
from trading_system.app.backtesting.multi_asset_engine import MultiAssetBacktester
from trading_system.app.reporting.performance import QuantitativePerformanceAnalyzer
from trading_system.app.common.database import engine
from sqlalchemy.orm import sessionmaker

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def execute_massive_test():
    print("\n" + "="*80)
    print(">>> EXECUTING MASSIVE 26-YEAR GLOBAL BACKTEST (2000 - PRESENT) <<<")
    print("="*80)
    
    # Combined Universe of highly liquid US and Indian Mega-Caps
    symbols = [
        # US Market Core
        "SPY", "QQQ", "MSFT", "AAPL"
    ]
    
    start_date = datetime(2000, 1, 1)
    end_date = datetime.now()
    
    print(f"[1/3] Loading Trend Following Strategy...")
    strategy_class = StrategyRegistry.get_strategy("T001_MovingAverage")
    # Using classic institutional trend parameters
    strategy = strategy_class(fast_length=50, slow_length=200)
    
    data_provider = YFinanceDataProvider()
    portfolio = BasicPortfolio(initial_cash=100000.0) # $100k starting capital
    risk_engine = BasicRiskEngine(max_position_size=100000)
    constructor = EqualWeightPortfolioConstructor(rebalance_freq="monthly")
    execution = PaperExecutionAdapter()
    db = SessionLocal()
    
    backtester = MultiAssetBacktester(
        data_provider, strategy, portfolio, risk_engine, constructor, execution
    )
    
    print(f"\n[2/3] Simulating 26 years of daily market events for {len(symbols)} assets...")
    print("      (This includes the Dot Com Crash, 2008 Financial Crisis, and COVID-19)")
    
    experiment_id = f"MASSIVE-2000-GLOBAL-{int(datetime.now().timestamp())}"
    backtester.run(symbols=symbols, start_date=start_date, end_date=end_date, experiment_id=experiment_id)
    
    print("\n[3/3] Calculating Performance Metrics...")
    analyzer = QuantitativePerformanceAnalyzer()
    
    if hasattr(backtester, 'equity_curve'):
        equity_series = pd.Series(backtester.equity_curve)
        metrics = analyzer.calculate_metrics([], equity_series)
        
        print("\n" + "="*50)
        print("--- 26-YEAR GLOBAL MARKET TEAR SHEET ---")
        print("="*50)
        for k, v in metrics.items():
            print(f"{k.ljust(25)}: {v}")
    else:
        print("ERROR: No equity curve generated.")
        
    db.close()

if __name__ == "__main__":
    execute_massive_test()
