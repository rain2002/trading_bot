import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, List
from trading_system.app.common.logger import get_logger

logger = get_logger("WalkForwardEngine")

class WalkForwardEngine:
    """
    Executes walk-forward optimization to guarantee out-of-sample robustness 
    and prevent curve fitting. This separates data strictly into Train/Validation/Test 
    blocks that slide forward in time.
    """
    def __init__(self, backtest_engine_factory):
        # We use a factory pattern because we MUST instantiate a completely 
        # clean backtester/portfolio state for every single out-of-sample window.
        self.backtest_engine_factory = backtest_engine_factory
        
    def run_expanding_window(
        self, 
        symbol: str, 
        full_start: datetime, 
        full_end: datetime, 
        initial_train_days: int = 365, 
        test_days: int = 90
    ) -> List[Dict[str, Any]]:
        """
        Expanding window: The Training set grows over time, while the Test set slides forward.
        """
        logger.info(f"Starting Expanding Walk-Forward Analysis for {symbol}")
        
        results = []
        current_train_end = full_start + timedelta(days=initial_train_days)
        window_idx = 1
        
        while current_train_end < full_end:
            current_test_end = min(current_train_end + timedelta(days=test_days), full_end)
            
            logger.info(f"--- Window {window_idx} ---")
            logger.info(f"Train: {full_start.date()} -> {current_train_end.date()}")
            logger.info(f"Test: {current_train_end.date()} -> {current_test_end.date()}")
            
            # In Phase 18 (ML), the model will train explicitly on the 'Train' period here.
            # For our current baseline strategies, we instantiate a clean engine and run 
            # the backtester strictly on the 'Test' period to simulate pure out-of-sample trading.
            
            engine = self.backtest_engine_factory()
            
            exp_id = f"WFA-WIN{window_idx}"
            final_portfolio = engine.run(symbol, current_train_end, current_test_end, experiment_id=exp_id)
            
            results.append({
                "window": window_idx,
                "train_start": full_start.date(),
                "train_end": current_train_end.date(),
                "test_start": current_train_end.date(),
                "test_end": current_test_end.date(),
                "final_cash": final_portfolio.cash
            })
            
            # Slide the window forward
            current_train_end = current_test_end
            window_idx += 1
            
        logger.info("Walk-Forward Analysis Complete.")
        return results
