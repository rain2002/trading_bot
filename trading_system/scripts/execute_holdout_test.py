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

def execute_final_holdout():
    print("\n" + "="*70)
    print(">>> PHASE 4: STRICT FINAL HOLDOUT EXAM (UNTOUCHED DATA) <<<")
    print("="*70)
    
    # The ultimate test: 2024 onwards. The strategy has NEVER seen this data during WFO/Training.
    start = datetime(2024, 1, 1)
    end = datetime.now()
    
    print("[1/3] Unlocking HYPOTHESIS Strategy Tier...")
    strat_trend = StrategyRegistry.get_strategy("T001_MovingAverage")(fast_length=20, slow_length=50)
    strat_mr = StrategyRegistry.get_strategy("MR001_MeanReversion")(bb_length=20, bb_std=2.0)
    
    strategy_class = StrategyRegistry.get_strategy("ENS001_RegimeSwitch")
    strategy = strategy_class(strategies={"TrendFollowing": strat_trend, "MeanReversion": strat_mr}, benchmark_symbol="SPY")
    
    print(f"\n[2/3] Executing Strategy [{strategy.__class__.__name__}] on Blind 2024+ Market Data...")
    
    # We use YFinanceDataProvider here because our ingested local Postgres database 
    # was intentionally truncated at 2023-12-31 to physically prevent training contamination.
    data_provider = YFinanceDataProvider()
    portfolio = BasicPortfolio(initial_cash=100000.0)
    risk_engine = BasicRiskEngine(max_position_size=100000)
    
    base_constructor = EqualWeightPortfolioConstructor()
    adaptive_allocator = AdaptivePortfolioAllocator(base_constructor, regime_index="SPY")
    
    execution = PaperExecutionAdapter()
    db = SessionLocal()
    
    backtester = MultiAssetBacktester(
        data_provider, strategy, portfolio, risk_engine, adaptive_allocator, execution, db_session=db
    )
    
    backtester.run(symbols=["SPY", "AAPL", "MSFT"], start_date=start, end_date=end, experiment_id=f"FINAL-HOLDOUT-2024-{int(datetime.now().timestamp())}")
    
    print("\n[3/3] Calculating Out-Of-Sample Truth Metrics...")
    analyzer = QuantitativePerformanceAnalyzer()
    
    if hasattr(backtester, 'equity_curve'):
        equity_series = pd.Series(backtester.equity_curve)
        metrics = analyzer.calculate_metrics([], equity_series)
        
        print("\n--- FINAL HOLDOUT TEAR SHEET ---")
        for k, v in metrics.items():
            print(f"{k.ljust(25)}: {v}")
            
        if metrics.get("Sharpe_Ratio", 0) > 0.8 and metrics.get("Annualized_Return_%", 0) > 0:
            print("\n✅ STRATEGY CLEARED FOR LIVE TRADING.")
        else:
            print("\n❌ STRATEGY FAILED HOLDOUT. RETURN TO RESEARCH PHASE.")
    else:
        print("ERROR: No equity curve generated.")
        
    db.close()

if __name__ == "__main__":
    execute_final_holdout()
