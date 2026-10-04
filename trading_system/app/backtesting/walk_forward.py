import pandas as pd
from datetime import timedelta
from dateutil.relativedelta import relativedelta
from typing import List, Dict, Type
from trading_system.app.common.logger import get_logger
from trading_system.app.backtesting.multi_asset_engine import MultiAssetBacktester
from trading_system.app.reporting.performance import QuantitativePerformanceAnalyzer
import uuid

logger = get_logger("WalkForwardOptimizer")

class WalkForwardOptimizer:
    """
    Executes rigorous Walk-Forward Validation.
    Instead of a single train/test split, this rolls a training window forward,
    tests on the immediately following out-of-sample window, and stitches the
    out-of-sample results together to prove the strategy can adapt to changing regimes.
    """
    def __init__(self, data_provider, portfolio_class, risk_engine, constructor, execution_adapter, db_session):
        self.data_provider = data_provider
        self.portfolio_class = portfolio_class
        self.risk_engine = risk_engine
        self.constructor = constructor
        self.execution = execution_adapter
        self.db = db_session
        
    def generate_windows(self, start_date, end_date, train_years=5, test_years=1):
        """Generates rolling train/test date boundaries."""
        windows = []
        current_train_start = start_date
        
        while True:
            current_train_end = current_train_start + relativedelta(years=train_years)
            current_test_end = current_train_end + relativedelta(years=test_years)
            
            if current_test_end > end_date:
                break
                
            windows.append({
                'train_start': current_train_start,
                'train_end': current_train_end,
                'test_start': current_train_end + timedelta(days=1),
                'test_end': current_test_end
            })
            
            # Step the window forward by the test duration
            current_train_start = current_train_start + relativedelta(years=test_years)
            
        return windows

    def run_wfo(self, symbols: List[str], start_date, end_date, strategy_factory, train_callback=None):
        """
        strategy_factory: A function that returns an instantiated strategy.
        train_callback: Optional function to retrain ML models on the train_window before testing.
        """
        windows = self.generate_windows(start_date, end_date)
        logger.info(f"Generated {len(windows)} Walk-Forward Windows.")
        
        master_equity_curve = pd.Series(dtype=float)
        current_capital = 100000.0 # Starting capital
        
        for idx, win in enumerate(windows):
            logger.info(f"--- WFO Fold {idx+1}/{len(windows)} ---")
            logger.info(f"TRAIN: {win['train_start'].date()} to {win['train_end'].date()}")
            logger.info(f"TEST:  {win['test_start'].date()} to {win['test_end'].date()}")
            
            # 1. (Optional) Retrain ML Model on the Train Window
            if train_callback:
                train_callback(symbols, win['train_start'], win['train_end'])
                
            # 2. Instantiate fresh strategy (loading the newly trained model if applicable)
            strategy = strategy_factory()
            
            # 3. Instantiate a fresh portfolio carrying over the capital from the last fold
            portfolio = self.portfolio_class(initial_cash=current_capital)
            
            backtester = MultiAssetBacktester(
                self.data_provider, strategy, portfolio, self.risk_engine, 
                self.constructor, self.execution, self.db
            )
            
            # 4. Run the Engine strictly on the TEST window
            fold_id = f"WFO-{uuid.uuid4().hex[:6]}"
            backtester.run(symbols=symbols, start_date=win['test_start'], end_date=win['test_end'], experiment_id=fold_id)
            
            if hasattr(backtester, 'equity_curve'):
                fold_equity = pd.Series(backtester.equity_curve)
                
                # Align fold equity with master equity curve
                if not master_equity_curve.empty:
                    # Scale the new fold so its starting value matches the ending value of the previous fold
                    fold_return_series = fold_equity.pct_change().fillna(0)
                    scaled_fold = (1 + fold_return_series).cumprod() * current_capital
                    master_equity_curve = pd.concat([master_equity_curve, scaled_fold])
                else:
                    master_equity_curve = fold_equity
                    
                current_capital = master_equity_curve.iloc[-1]
                logger.info(f"Fold {idx+1} Final Capital: ${current_capital:,.2f}")
            else:
                logger.error("Fold failed to generate equity curve.")
                
        # Remove duplicate index dates that might occur at window boundaries
        master_equity_curve = master_equity_curve[~master_equity_curve.index.duplicated(keep='last')]
        
        # Analyze stitched Out-Of-Sample performance
        analyzer = QuantitativePerformanceAnalyzer()
        metrics = analyzer.calculate_metrics([], master_equity_curve)
        
        return master_equity_curve, metrics
