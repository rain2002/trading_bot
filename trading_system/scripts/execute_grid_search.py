import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
import pandas as pd
import itertools
from trading_system.app.data.database_provider import DatabaseDataProvider
from trading_system.app.strategies.library.mr001_mean_reversion import MR001_MeanReversion
from trading_system.app.portfolio.basic import BasicPortfolio
from trading_system.app.risk.basic import BasicRiskEngine
from trading_system.app.portfolio.constructor import EqualWeightPortfolioConstructor
from trading_system.app.execution.paper import PaperExecutionAdapter
from trading_system.app.backtesting.multi_asset_engine import MultiAssetBacktester
from trading_system.app.reporting.performance import QuantitativePerformanceAnalyzer
from trading_system.app.common.database import engine
from sqlalchemy.orm import sessionmaker

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def execute_grid_search():
    print("\n" + "="*70)
    print(">>> PHASE 7: IN-SAMPLE HYPERPARAMETER OPTIMIZATION <<<")
    print("="*70)
    
    # Train entirely on historical data, NO peeking at 2024
    start = datetime(2018, 1, 1)
    end = datetime(2023, 12, 31)
    
    db = SessionLocal()
    data_provider = DatabaseDataProvider(db)
    symbols = ["SPY", "AAPL", "MSFT"]
    
    # Define Parameter Grid (Reduced for speed)
    bb_lengths = [10, 20]
    bb_stds = [1.5, 2.0]
    rsi_oversolds = [30, 35]
    
    param_combinations = list(itertools.product(bb_lengths, bb_stds, rsi_oversolds))
    print(f"Executing Grid Search over {len(param_combinations)} combinations on {start.year}-{end.year} Data...")
    
    best_sharpe = -999
    best_params = None
    
    for idx, (b_len, b_std, rsi_o) in enumerate(param_combinations):
        strategy = MR001_MeanReversion(bb_length=b_len, bb_std=b_std, rsi_oversold=rsi_o, rsi_overbought=100-rsi_o)
        
        portfolio = BasicPortfolio(initial_cash=100000.0)
        risk_engine = BasicRiskEngine(max_position_size=100000)
        constructor = EqualWeightPortfolioConstructor()
        execution = PaperExecutionAdapter()
        
        backtester = MultiAssetBacktester(
            data_provider, strategy, portfolio, risk_engine, constructor, execution, db_session=db
        )
        
        # Suppress logging for speed during grid search
        import logging
        logging.getLogger("MultiAssetBacktester").setLevel(logging.ERROR)
        
        # Run backtest
        try:
            exp_id = f"GRID-{int(datetime.now().timestamp())}-{idx}"
            backtester.run(symbols=symbols, start_date=start, end_date=end, experiment_id=exp_id)
            
            if hasattr(backtester, 'equity_curve'):
                equity_series = pd.Series(backtester.equity_curve)
                analyzer = QuantitativePerformanceAnalyzer()
                metrics = analyzer.calculate_metrics([], equity_series)
                sharpe = metrics.get('Sharpe_Ratio', -999)
                
                print(f"[{idx+1}/{len(param_combinations)}] bb_len={b_len}, std={b_std}, rsi={rsi_o} -> Sharpe: {sharpe}")
                
                if sharpe > best_sharpe:
                    best_sharpe = sharpe
                    best_params = (b_len, b_std, rsi_o)
        except Exception as e:
            print(f"Failed combination {b_len}, {b_std}, {rsi_o}: {e}")
            
    print("\n" + "="*70)
    print(f"*** OPTIMIZATION COMPLETE ***")
    print(f"Best Parameters: bb_length={best_params[0]}, bb_std={best_params[1]}, rsi_oversold={best_params[2]}")
    print(f"In-Sample Sharpe Ratio: {best_sharpe}")
    print("="*70)
    db.close()

if __name__ == "__main__":
    execute_grid_search()
