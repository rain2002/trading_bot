import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
import pandas as pd
from trading_system.app.data.yfinance_provider import YFinanceDataProvider
from trading_system.app.strategies.library.debug001_random_walk import DEBUG001_RandomWalk
from trading_system.app.portfolio.basic import BasicPortfolio
from trading_system.app.risk.basic import BasicRiskEngine
from trading_system.app.portfolio.constructor import EqualWeightPortfolioConstructor
from trading_system.app.execution.paper import PaperExecutionAdapter
from trading_system.app.backtesting.multi_asset_engine import MultiAssetBacktester
from trading_system.app.reporting.performance import QuantitativePerformanceAnalyzer

# We mock a DB session for the test so we don't require Postgres to be running just to test leakage
class MockDB:
    def add(self, obj): pass
    def commit(self): pass

def run_leakage_test():
    print("\n" + "="*60)
    print(">>> V2 ANTI-LEAKAGE RANDOM WALK TEST <<<")
    print("="*60)
    
    start = datetime(2020, 1, 1)
    end = datetime(2023, 12, 31)
    
    print("[1/3] Booting Engine with Random-Walk Strategy...")
    data_provider = YFinanceDataProvider()
    strategy = DEBUG001_RandomWalk(seed=999) # Fixed seed for reproducibility
    portfolio = BasicPortfolio(initial_cash=100000.0)
    risk_engine = BasicRiskEngine(max_position_size=100000)
    constructor = EqualWeightPortfolioConstructor()
    execution = PaperExecutionAdapter()
    
    backtester = MultiAssetBacktester(
        data_provider, strategy, portfolio, risk_engine, constructor, execution, db_session=MockDB()
    )
    
    print("\n[2/3] Simulating 4 Years of Random Trading (2020-2023)...")
    # We will test on SPY to see if the random strategy accidentally makes money
    backtester.run(symbols=["SPY"], start_date=start, end_date=end, experiment_id="DEBUG-LEAK-001")
    
    print("\n[3/3] Calculating Engine Integrity Metrics...")
    analyzer = QuantitativePerformanceAnalyzer()
    
    if hasattr(backtester, 'equity_curve'):
        equity_series = pd.Series(backtester.equity_curve)
        metrics = analyzer.calculate_metrics([], equity_series)
        
        print("\n--- RANDOM WALK TEAR SHEET ---")
        for k, v in metrics.items():
            print(f"{k.ljust(25)}: {v}")
            
        print("\n>>> LEAKAGE VERIFICATION RESULT <<<")
        # In a frictionless environment without spread/commission, random walk should hover around 0% alpha 
        # or match the baseline drift of the market if it happens to randomly hold long more often.
        # But crucially, if Sharpe > 1.5, we have a massive data leak.
        if metrics.get("Sharpe_Ratio", 0) > 1.0:
            print("FAIL: Random Walk achieved high Sharpe! The engine is leaking future data.")
        else:
            print("PASS: Random Walk failed to generate significant Alpha. Engine is secure from leakage.")
    else:
        print("ERROR: No equity curve generated.")

if __name__ == "__main__":
    run_leakage_test()
