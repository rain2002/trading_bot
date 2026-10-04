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

def run_test(name, symbols, start, end):
    print("\n" + "="*70)
    print(f">>> EXECUTING PURE OUT-OF-SAMPLE TEST: {name} <<<")
    print(f"Timeline: {start.date()} to {end.date()}")
    print(f"Universe: {symbols}")
    print("="*70)
    
    strategy_class = StrategyRegistry.get_strategy("T001_MovingAverage")
    strategy = strategy_class(fast_length=50, slow_length=200)
    
    data_provider = YFinanceDataProvider()
    portfolio = BasicPortfolio(initial_cash=100000.0)
    risk_engine = BasicRiskEngine(max_position_size=100000)
    constructor = EqualWeightPortfolioConstructor()
    execution = PaperExecutionAdapter()
    db = SessionLocal()
    
    backtester = MultiAssetBacktester(
        data_provider, strategy, portfolio, risk_engine, constructor, execution, db_session=db
    )
    
    # Run backtest
    backtester.run(symbols=symbols, start_date=start, end_date=end, experiment_id=f"OOS-{name}-{int(datetime.now().timestamp())}")
    
    analyzer = QuantitativePerformanceAnalyzer()
    
    if hasattr(backtester, 'equity_curve'):
        equity_series = pd.Series(backtester.equity_curve)
        metrics = analyzer.calculate_metrics([], equity_series)
        
        print(f"\n--- {name} TEAR SHEET ---")
        for k, v in metrics.items():
            print(f"{k.ljust(25)}: {v}")
    else:
        print("ERROR: No equity curve generated.")
        
    db.close()

def execute_global_oos_tests():
    # TEST 1: The Dot Com Bubble & Crash (US Tech)
    run_test(
        name="US_DOT_COM_CRASH",
        symbols=["SPY", "QQQ", "MSFT", "INTC", "CSCO"],
        start=datetime(1999, 1, 1),
        end=datetime(2004, 1, 1)
    )
    
    # TEST 2: The Great Financial Crisis (Global Financials)
    run_test(
        name="GLOBAL_FINANCIAL_CRISIS",
        symbols=["XLF", "JPM", "C", "BAC", "GS"],
        start=datetime(2006, 1, 1),
        end=datetime(2011, 1, 1)
    )
    
    # TEST 3: The Crypto Winter (Digital Assets)
    run_test(
        name="CRYPTO_WINTER",
        symbols=["BTC-USD", "ETH-USD"],
        start=datetime(2018, 1, 1),
        end=datetime(2023, 1, 1)
    )

if __name__ == "__main__":
    execute_global_oos_tests()
