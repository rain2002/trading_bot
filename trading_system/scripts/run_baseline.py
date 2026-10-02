import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from app.data.yfinance_provider import YFinanceDataProvider
from app.strategies.mean_reversion import MeanReversionStrategy
from app.portfolio.basic import BasicPortfolio
from app.risk.basic import BasicRiskEngine
from app.portfolio.sizer import BasicPositionSizer
from app.execution.paper import PaperExecutionAdapter
from app.backtesting.engine import EventDrivenBacktester
from app.common.database import SessionLocal
import warnings
warnings.filterwarnings("ignore")

def run_experiment():
    db_session = SessionLocal()
    try:
        engine = EventDrivenBacktester(
            data_provider=YFinanceDataProvider(),
            strategy=MeanReversionStrategy(),
            portfolio=BasicPortfolio(initial_cash=50000.0),
            risk_engine=BasicRiskEngine(max_position_size=200),
            position_sizer=BasicPositionSizer(),
            execution_adapter=PaperExecutionAdapter(slippage_bps=5.0), # 5 bps slippage
            db_session=db_session
        )
        
        # Run a 1-year baseline test
        start = datetime(2025, 1, 1)
        end = datetime(2026, 1, 1)
        
        print("\n=== EXECUTING BASELINE EXPERIMENT ===")
        print("Strategy: Mean Reversion")
        print("Target: SPY (S&P 500 ETF)")
        print("Period: 2025-01-01 to 2026-01-01")
        print("Constraints: Strict Point-in-Time, 5 BPS Slippage, 200 Max Position\n")
        
        final_portfolio = engine.run("SPY", start, end)
        
        if final_portfolio:
            print("\n=== EXPERIMENT COMPLETE ===")
            print(f"Final Cash Balance: ${final_portfolio.cash:.2f}")
            print(f"Final Open Positions: {final_portfolio.get_positions()}")
            
    finally:
        db_session.close()

if __name__ == "__main__":
    run_experiment()
