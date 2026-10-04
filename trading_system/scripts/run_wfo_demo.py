import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from trading_system.app.data.yfinance_provider import YFinanceDataProvider
from trading_system.app.strategies.library.t001_moving_average import T001_MovingAverageTrend
from trading_system.app.portfolio.basic import BasicPortfolio
from trading_system.app.risk.basic import BasicRiskEngine
from trading_system.app.portfolio.constructor import EqualWeightPortfolioConstructor
from trading_system.app.execution.paper import PaperExecutionAdapter
from trading_system.app.backtesting.walk_forward import WalkForwardOptimizer

class MockDB:
    def add(self, obj): pass
    def commit(self): pass

def run_wfo():
    print("\n" + "="*60)
    print(">>> V2 WALK-FORWARD OPTIMIZATION (WFO) ENGINE <<<")
    print("="*60)
    
    start = datetime(2015, 1, 1)
    end = datetime(2023, 12, 31)
    
    print("[1/3] Booting WFO Subsystem...")
    data_provider = YFinanceDataProvider()
    risk_engine = BasicRiskEngine(max_position_size=100000)
    constructor = EqualWeightPortfolioConstructor()
    execution = PaperExecutionAdapter()
    
    wfo_engine = WalkForwardOptimizer(
        data_provider, BasicPortfolio, risk_engine, constructor, execution, db_session=MockDB()
    )
    
    print("\n[2/3] Simulating 8 Years of Rolling Walk-Forward Folds...")
    
    # In a full ML run, this callback would retrain the Random Forest on the train window.
    # For this demo, we simulate the architecture using the Moving Average strategy.
    def strategy_factory():
        return T001_MovingAverageTrend(fast_length=20, slow_length=50)
        
    master_curve, metrics = wfo_engine.run_wfo(
        symbols=["SPY"], 
        start_date=start, 
        end_date=end, 
        strategy_factory=strategy_factory
    )
    
    print("\n[3/3] Calculating Stitched Out-Of-Sample Metrics...")
    print("\n--- WALK-FORWARD TEAR SHEET (STRICTLY OOS) ---")
    for k, v in metrics.items():
        print(f"{k.ljust(25)}: {v}")

if __name__ == "__main__":
    run_wfo()
