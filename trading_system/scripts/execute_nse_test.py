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

from trading_system.app.strategies.library.p001_pullback_uptrend import P001_PullbackUptrend

def execute_nse_test():
    print("\n" + "="*70)
    print(">>> EXECUTING LONG RUN INDIA MARKET TEST (2015 - PRESENT) <<<")
    print("="*70)
    
    start = datetime(2015, 1, 1)
    end = datetime.now()
    
    # Diverse basket representing multiple industries from NSE
    nse_universe = [
        "RELIANCE.NS",   # Energy
        "HDFCBANK.NS",   # Financials
        "TCS.NS",        # IT
        "ITC.NS",        # FMCG
        "LART.NS",       # Industrials / Construction (L&T)
        "SUNPHARMA.NS",  # Pharmaceuticals
        "MARUTI.NS",     # Auto
        "TATASTEEL.NS",  # Metals
        "BHARTIARTL.NS", # Telecom
        "ULTRACEMCO.NS", # Cement
    ]
    
    print("[1/3] Loading Long-Term Trend Following Strategy...")
    strategy_class = StrategyRegistry.get_strategy("T001_MovingAverage")
    strategy = strategy_class(fast_length=50, slow_length=200)
    
    print(f"\n[2/3] Executing Strategy on {len(nse_universe)} NSE Stocks across 4+ Years...")
    
    data_provider = YFinanceDataProvider()
    portfolio = BasicPortfolio(initial_cash=1000000.0) # 10 Lakh INR starting capital
    risk_engine = BasicRiskEngine(max_position_size=1000000)
    
    base_constructor = EqualWeightPortfolioConstructor()
    adaptive_allocator = AdaptivePortfolioAllocator(base_constructor, regime_index="^NSEI")
    
    execution = PaperExecutionAdapter()
    db = SessionLocal()
    
    backtester = MultiAssetBacktester(
        data_provider, strategy, portfolio, risk_engine, adaptive_allocator, execution, db_session=db
    )
    
    # Run backtest. We append Nifty 50 to the universe explicitly so the Ensemble can calculate regime.
    backtester.run(symbols=nse_universe + ["^NSEI"], start_date=start, end_date=end, experiment_id=f"NSE-TEST-{int(datetime.now().timestamp())}")
    
    print("\n[3/3] Calculating Performance Metrics...")
    analyzer = QuantitativePerformanceAnalyzer()
    
    if hasattr(backtester, 'equity_curve'):
        equity_series = pd.Series(backtester.equity_curve)
        metrics = analyzer.calculate_metrics([], equity_series)
        
        print("\n--- NSE MARKET TEAR SHEET (2020-PRESENT) ---")
        for k, v in metrics.items():
            print(f"{k.ljust(25)}: {v}")
            
    else:
        print("ERROR: No equity curve generated.")
        
    db.close()

if __name__ == "__main__":
    execute_nse_test()
