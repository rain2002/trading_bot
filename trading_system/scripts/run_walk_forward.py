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
from app.research.walk_forward import WalkForwardEngine
from app.common.database import SessionLocal
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

def backtest_factory():
    """Generates a fresh, isolated state for every walk-forward window."""
    db_session = SessionLocal()
    return EventDrivenBacktester(
        data_provider=YFinanceDataProvider(),
        strategy=MeanReversionStrategy(rsi_length=14, bb_length=20),
        portfolio=BasicPortfolio(initial_cash=50000.0),
        risk_engine=BasicRiskEngine(max_position_size=200),
        position_sizer=BasicPositionSizer(),
        execution_adapter=PaperExecutionAdapter(slippage_bps=5.0),
        db_session=db_session
    )

def run():
    print("\n=== EXECUTING WALK-FORWARD ANALYSIS ===")
    print("Method: Expanding Window")
    print("Train: Starts at 1 Year, expands over time")
    print("Test: 90 Days Out-Of-Sample per window\n")
    
    start = datetime(2023, 1, 1)
    end = datetime(2026, 1, 1)
    
    wfa_engine = WalkForwardEngine(backtest_engine_factory=backtest_factory)
    
    # Run the rigorous out-of-sample blocks
    results = wfa_engine.run_expanding_window("SPY", start, end, initial_train_days=365, test_days=90)
    
    print("\n=== WALK-FORWARD OUT-OF-SAMPLE RESULTS ===")
    df_results = pd.DataFrame(results)
    print(df_results[['window', 'test_start', 'test_end', 'final_cash']])

if __name__ == "__main__":
    run()
