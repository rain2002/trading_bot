import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from app.data.yfinance_provider import YFinanceDataProvider
from app.strategies.multi_asset_dummy import MultiAssetMomentumStrategy
from app.portfolio.basic import BasicPortfolio
from app.risk.basic import BasicRiskEngine
from app.portfolio.constructor import EqualWeightPortfolioConstructor
from app.execution.paper import PaperExecutionAdapter
from app.backtesting.multi_asset_engine import MultiAssetBacktester
from app.common.database import SessionLocal
import warnings
warnings.filterwarnings("ignore")

def run_experiment():
    db_session = SessionLocal()
    try:
        # Notice we are passing the new PortfolioConstructor into the Engine
        engine = MultiAssetBacktester(
            data_provider=YFinanceDataProvider(),
            strategy=MultiAssetMomentumStrategy(lookback=20),
            portfolio=BasicPortfolio(initial_cash=100000.0), # Starting $100k
            risk_engine=BasicRiskEngine(max_position_size=1000), 
            portfolio_constructor=EqualWeightPortfolioConstructor(),
            execution_adapter=PaperExecutionAdapter(slippage_bps=2.0),
            db_session=db_session
        )
        
        # Test on Q1 of 2025
        start = datetime(2025, 1, 1)
        end = datetime(2025, 4, 1)
        
        # Defining a small universe representing Market, Tech, Dow, and Small Caps
        universe = ["SPY", "QQQ", "DIA", "IWM"]
        
        print(f"\n=== EXECUTING MULTI-ASSET PORTFOLIO EXPERIMENT ===")
        print(f"Universe: {universe}")
        print(f"Strategy: Cross-Sectional Momentum")
        print(f"Capital Allocation: Equal Weighting")
        
        final_portfolio = engine.run(universe, start, end)
        
        if final_portfolio:
            print("\n=== EXPERIMENT COMPLETE ===")
            print(f"Final Cash Balance: ${final_portfolio.cash:.2f}")
            print(f"Final Open Positions: {final_portfolio.get_positions()}")
            
    finally:
        db_session.close()

if __name__ == "__main__":
    run_experiment()
