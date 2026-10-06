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

def execute_nse500_sample_test():
    print("\n" + "="*70)
    print(">>> EXECUTING 2023-2026 INDIA MARKET TEST (NIFTY 50 / Top NSE 500) <<<")
    print("="*70)
    
    start = datetime(2023, 1, 1)
    end = datetime(2026, 1, 1) # Jan 2026 is roughly "present" context
    
    # We fetch the top 50 constituents of the NSE 500 to avoid yfinance rate limits 
    # and keep backtest runtime reasonable.
    try:
        url = "https://en.wikipedia.org/wiki/NIFTY_50"
        tables = pd.read_html(url)
        nse_universe = [f"{s}.NS" for s in tables[1]['Symbol'].tolist()]
    except Exception:
        nse_universe = [
            "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS", "HUL.NS", 
            "SBIN.NS", "BAJFINANCE.NS", "BHARTIARTL.NS", "ITC.NS", "LT.NS", "ASIANPAINT.NS", 
            "AXISBANK.NS", "MARUTI.NS", "SUNPHARMA.NS", "TATASTEEL.NS", "ULTRACEMCO.NS", "NTPC.NS"
        ]
    
    # Filter out empty or weird symbols just in case
    nse_universe = [s for s in nse_universe if isinstance(s, str) and len(s) > 3][:50]
    
    print(f"[1/3] Loading T001_MovingAverage Strategy...")
    strategy_class = StrategyRegistry.get_strategy("T001_MovingAverage")
    strategy = strategy_class(fast_length=20, slow_length=50) # Faster MA for a 3-year period
    
    print(f"\n[2/3] Executing Strategy on {len(nse_universe)} NSE Stocks (2023 - 2026)...")
    
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
    
    # Run backtest
    backtester.run(symbols=nse_universe + ["^NSEI"], start_date=start, end_date=end, experiment_id=f"NSE-2023-2026-{int(datetime.now().timestamp())}")
    
    print("\n[3/3] Calculating Performance Metrics...")
    analyzer = QuantitativePerformanceAnalyzer()
    
    if hasattr(backtester, 'equity_curve'):
        equity_series = pd.Series(backtester.equity_curve)
        metrics = analyzer.calculate_metrics([], equity_series)
        
        print("\n--- NSE MARKET (2023-2026) TEAR SHEET ---")
        for k, v in metrics.items():
            print(f"{k.ljust(25)}: {v}")
            
    else:
        print("ERROR: No equity curve generated.")
        
    db.close()

if __name__ == "__main__":
    execute_nse500_sample_test()
